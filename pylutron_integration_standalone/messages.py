from dataclasses import dataclass
from . import connection

class ParseError(Exception):
    """Exception raised when a message doesn't parse correctly."""
    
    def __init__(self, message: str) -> None:
        super().__init__(str)

@dataclass
class DeviceDetails:
    sn: bytes
    integration_id: bytes
    family: bytes
    product: bytes

    # raw_attrs likely contains at least b'CODE', b'BOOT', and b'HW',
    # and it also contins b'SN', b'INTEGRATIONID', etc.
    raw_attrs: dict[bytes, bytes]

_DETAILS_KEYS = {'SN':'sn',
                 'INTEGRATIONID':'integration_id',
                 'FAMILY':'family',
                 'PRODUCT':'product'}

def parse_details(data: bytes) -> list[DeviceDetails]:
    """
    Parse a reply to ?DETAILS into a list of dictionaries, one per device
    
    Each line is formatted as
    ~DETAILS,KEY1:VALUE1,KEY2:VALUE2,...
    
    Args:
        data: Raw bytes containing multiple ~DETAILS lines separated by \r\n
        
    Returns:
        List of dictionaries, where each dict represents one device with
        keys and values as bytes
    """
    result: list[DeviceDetails] = []

    # Split into lines
    lines = data.split(b'\r\n')

    if not lines or lines[-1] != b'':
        raise ParseError('~DETAILS list does not split correctly')
    lines = lines[:-1]

    for line in lines:
        # Check if line starts with ~DETAILS,
        if not line.startswith(b'~DETAILS,'):
            raise ParseError(f'Unexpected details line: {line!r}')

        # Remove the ~DETAILS, prefix
        details_str = line[9:]  # len(b'~DETAILS,') == 9

        # Split by comma to get key-value pairs
        pairs = details_str.split(b',')

        attrs: dict[bytes, bytes] = {}
        for pair in pairs:
            # Split by first colon only (values might contain colons)
            if b':' in pair:
                key, value = pair.split(b':', 1)
                attrs[key] = value
            else:
                raise ParseError('Details entry {pair!r} has no comma')

        # Normalize the serial number.  The QSE-CI-NWK-E seems happy to ignore
        # any number of leading b'0x' prefixes (yes, b'0x0x00456' works), and
        # it even ignores zeros after all the 0x prefixes, but it seems
        # wise to try to match the documentation exactly when possible.
        sn = attrs[b'SN']
        if sn.startswith(b'0x'):
            sn = sn[2:]
        sn = sn.upper()

        device = DeviceDetails(
            sn = sn,
            integration_id=attrs[b'INTEGRATIONID'],
            family=attrs[b'FAMILY'],
            product=attrs[b'PRODUCT'],
            raw_attrs=attrs)

        result.append(device)
    
    return result

async def enumerate_qse_devices(qse: connection.LutronConnection) -> list[DeviceDetails]:
    return parse_details(await qse.raw_query(b'?DETAILS,ALL_DEVICES'))
