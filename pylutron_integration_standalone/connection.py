import asyncio
from dataclasses import dataclass
import re

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

@dataclass
class _Conn:
    r: asyncio.StreamReader
    w: asyncio.StreamWriter

# TODO: Monitoring messages may be arbitrarily interspersed with actual replies, and
# there isn't an obvious way to tell which messages are part of a reply vs. which
# are asynchronously received monitoring messages.
#
# On the bright side, once we enable prompts, we at least know that all direct
# replies to queries (critically, ?DETAILS) will be received before the QSE>
# prompt.

class LutronConnection:
    """Represents an established Lutron connection."""

    # TDB: a bit of a state machine is needed.  And we need to deal with the MONITORING config
    # and the fact that the protocol looks different depending on the prompt and reply modes.

    __conn: _Conn | None
    __prompt_prefix: bytes
    
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.__conn = _Conn(reader, writer)

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
    
    async def raw_query(self, command: bytes) -> bytes:
        assert self.__conn is not None
        assert b'\r\n' not in command

        self.__conn.w.write(command + b'\r\n')
        await self.__conn.w.drain()
    
        reply = await self.__conn.r.readuntil(self.__prompt_prefix + b'>')
        return reply[:-(len(self.__prompt_prefix) + 1)]

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
