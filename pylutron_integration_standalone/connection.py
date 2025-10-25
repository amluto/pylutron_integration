import asyncio
from dataclasses import dataclass
import re
import collections

class LoginError(Exception):
    """Exception raised when login fails."""
    
    message: bytes
    
    def __init__(self, message: bytes) -> None:
        self.message = message
        super().__init__(message.decode('utf-8', errors='replace'))

class ProtocolError(Exception):
    """Exception raised when the protocol doesn't parse correctly."""
    
    def __init__(self, message: str) -> None:
        super().__init__(str)

class DisconnectedError(Exception):
    """Exception raised when we aren't connected."""
    
    def __init__(self) -> None:
        super().__init__('Disconnected')

# If we catch a CancelledError and we don't want to swallow a cancellation,
# then call we can use this.  (Python does not cleanly distinguish
# between await raising because it awaited a canceled task and raising
# because the awaiting task was canceled.)
def _i_need_to_cancel() -> bool:
    task = asyncio.current_task()
    assert task is not None
    return task.cancelling()

@dataclass
class _Conn:
    r: asyncio.StreamReader
    w: asyncio.StreamWriter

# Monitoring messages may be arbitrarily interspersed with actual replies, and
# there is no mechanism in the protocol to tell which messages are part of a reply vs.
# which are asynchronously received monitoring messages.
#
# On the bright side, once we enable prompts, we at least know that all direct
# replies to queries (critically, ?DETAILS) will be received before the QSE>
# prompt.  However, we do not know *which* QSE> prompt they preceed because
# unsolicited messages end with '\r\nQSE>'.  Thanks, Lutron.
#
# We manage to parse the protocol by observing that the incoming stream is a
# stream of messages where each message either ends with b'\r\nQSE>' or
# is just b'QSE>' (no newline).  We further observe that no actual logical
# line of the protocol can start with a Q (everything starts with ~), so
# we can't get confused by a stray Q at the start of a line.
#
# This does not handle the #PASSWD flow.

class LutronConnection:
    """Represents an established Lutron connection."""

    __lock: asyncio.Lock
    __conn: _Conn | None  # TODO: There is no value to ever nulling this out
    __prompt_prefix: bytes

    # We can only handle one query and one read_unsolicited at a time.
    __unsolicited_lock: asyncio.Lock
    __query_lock: asyncio.Lock

    # Deadlock prevention rules: __lock nests inside __query_lock, which nests inside __unsolicited_lock.
    # Also, read_unsolicited() may not hold __query_lock while waiting for a message to arrive, as otherwise
    # a query could be forced to wait forever if there aren't any messages.

    __unsolicited_task: asyncio.Task[bytes] | None # protected by __lock
    __unsolicited_queue: collections.deque[bytes]

    # Only used by __read_one_message(), which is never called
    # concurrently with itself.
    __buffered_byte: bytes

    # Nests inside __query_lock and __unsolicited_lock
    __buffer_lock: asyncio.Lock

    # TODO: We should possibly track when we are in a bad state and quickly fail future operations
    
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.__conn = _Conn(reader, writer)
        self.__unsolicited_lock = asyncio.Lock()
        self.__query_lock = asyncio.Lock()
        self.__lock = asyncio.Lock()
        self.__buffer_lock = asyncio.Lock()
        self.__unsolicited_task = None
        self.__unsolicited_queue = collections.deque()
        self.__buffered_byte = b''

    @classmethod
    async def create_from_connnection(cls, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> 'LutronConnection':
        self = LutronConnection(reader, writer)
        assert self.__conn is not None

        # When we first connect, the MONITORING state is uknown, which is rather annoying.
        # To function sensibly, we need:
        #
        # Diagnostic Monitoring (1): otherwise errors will be ignored and we won't find out about them
        # Reply State (11): Queries will never be answered if this is off
        # Prompt State (12): The prompt is how we tell that the system has finished processing a request
        #
        # And, awkwardly, until we set these, we might be in a state where the system
        # is entirely silent, and we don't really know what replies to expect.

        # Send the commands to enable the above monitoring modes
        self.__conn.w.write(b''.join(b'#MONITORING,%d,1\r\n' % mode for mode in (1,11,12)))

        # In response, we really have no idea what to expect, except that there really ought
        # be at least one prompt.  So we'll do an outrageous cheat and send a command with
        # a known reply that we wouldn't otherwise see so we can wait for it.
        self.__conn.w.write(b'?MONITORING,2\r\n')

        await self.__conn.r.readuntil(b'~MONITORING,2,')
        data = await self.__conn.r.readuntil(b'>')

        m = re.fullmatch(b'\\d\r\n([A-Za-z0-9]+)>', data)
        if not m:
            raise ProtocolError(f'Could not parse {(b'~MONITORING,2,' + data + b'>')!r} as a monitoring ping reply')
        self.__prompt_prefix = m[1]
        return self
    
    async def __read_one_message(self) -> bytes:
        print('enter __read_one_message')
        # This needs to be cancelable and then runnable again without losing data
        assert self.__conn is not None
        async with self.__buffer_lock:
            if not self.__buffered_byte:
                self.__buffered_byte = await self.__conn.r.read(1)

                if not self.__buffered_byte:
                    # We got EOF.
                    raise DisconnectedError()

            if self.__buffered_byte == self.__prompt_prefix[0:1]:
                # We got Q and expect SE>
                expected = self.__prompt_prefix[1:] + b'>'
                data = await self.__conn.r.readexactly(len(expected))
                if data != expected:
                    raise ProtocolError(f'Expected {expected!r} but received {data!r}')
                self.__buffered_byte = b''
                print('__read_one_message: returning blank')
                return b''
            else:
                # We got the first byte of a message and expect the rest of it
                # followed by b'\r\nQSE>'
                data = await self.__conn.r.readuntil(b'\r\n' + self.__prompt_prefix + b'>')
                result = self.__buffered_byte + data[:-(len(self.__prompt_prefix) + 1)] # strip the QSE>
                self.__buffered_byte = b''
                print(f'__read_one_message: returning {result!r}')
                return result
            
    def __is_message_a_reply(self, message: bytes) -> bool:
        # If it's blank (i.e. they send b'QSE>'), then it's a reply.
        if not message:
            return True
        
        # If it starts with b'~DETAILS,' or b'~ERROR,', then it's a reply
        upper = message.upper()
        if upper.startswith(b'~DETAILS') or upper.startswith(b'~ERROR') or upper.startswith(b'~INTEGRATIONID'):
            return True
        
        # Otherwise it's not a reply.  (Note that messages like ~DEVICE
        # may well be sent as a result of a query, but they are not sent
        # as a reply to the query -- they're sent as though they're
        # unsolicited.)

        # Sanity check: we expect exactly one b'\r\n', and it will be at the
        # end.
        assert message.endswith(b'\r\n')
        assert b'\r\n' not in message[:-2]
        return False
    
    async def raw_query(self, command: bytes) -> bytes:
        async with self.__query_lock:
            assert self.__conn is not None
            assert b'\r\n' not in command

            # Pause any concurrent read_unsolicited
            unsolicited_task: asyncio.Task[bytes] | None = None
            async with self.__lock:
                unsolicited_task = self.__unsolicited_task

            # read_unsolicited might complete here, but a new unsolicited task
            # cannot be created because we hold query_lock.

            if unsolicited_task is not None:
                unsolicited_task.cancel()
                # Wait for it to finish cancelling.
                try:
                    await unsolicited_task
                except asyncio.CancelledError:
                    if _i_need_to_cancel():
                        raise

            self.__conn.w.write(command + b'\r\n')
            await self.__conn.w.drain()

            while True:
                message = await self.__read_one_message()

                if self.__is_message_a_reply(message):
                    print(f'raw_query got {message!r} and is returning it')
                    return message

                print(f'raw_query got {message!r} and queued it for later')
                self.__unsolicited_queue.append(message)
        
    # Reads one single unsolicited message
    async def read_unsolicited(self) -> bytes:
        print('entered: read_unsolicited')
        assert self.__conn is not None

        while True:
            async with self.__query_lock:
                # Why did we take the lock?  For two reasons:
                # 1. If there is a query in progress, we need to wait for it to finish.
                # 2. It protects __unsolicited_queue.
                if len(self.__unsolicited_queue):
                    return self.__unsolicited_queue.popleft()

                async with self.__lock:
                    self.__unsolicited_task = asyncio.create_task(self.__read_one_message())

            try:
                result = await self.__unsolicited_task
            except asyncio.CancelledError:
                if _i_need_to_cancel():
                    print('read_unsolicited was canceled!')
                    raise
                print('read_unsolicited sees that __unsolicited_task was cancelled')
                async with self.__lock:
                    self.__unsolicited_task = None
                    continue # Try again

            async with self.__lock:
                self.__unsolicited_task = None

            print(f'read_unsolicited got {result!r}')
            assert not self.__is_message_a_reply(result)
            return result

    async def disconnect(self) -> None:
        if self.__conn is None:
            return None
        self.__conn.w.close()
        await self.__conn.w.wait_closed()
        self._conn = None
        return None

async def login(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    username: bytes,
    password: None | bytes
) -> LutronConnection:
    """
    Authenticate with a Lutron device over an asyncio stream.
    
    Waits for the login prompt, sends the username, and validates the response.
    
    Args:
        reader: The asyncio StreamReader for receiving data
        writer: The asyncio StreamWriter for sending data
        username: The username as bytes
        password: The password as bytes, or None if no password is required
        
    Returns:
        LutronConnection object representing the established connection
        
    Raises:
        LoginError: If the login fails, containing the error message from the server
    """
    # Wait for the login prompt
    await reader.readuntil(b'login: ')
    
    # Send the username (line-oriented protocol requires newline)
    writer.write(username + b'\r\n')
    await writer.drain()
    
    # Read the server's response
    response = await reader.readline()
    response = response.strip()
    
    # Check if login was successful
    if response == b'connection established':
        return await LutronConnection.create_from_connnection(reader, writer)
    else:
        raise LoginError(response)
