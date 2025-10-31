from dataclasses import dataclass
from . import connection
from .types import SerialNumber
import re

# Notes:
#
# Integration ids for devices appear to be stored on the devices (or at least if you
# wipe the flash on the NWK via #RESET,2 then they are not cleared).  You cannot
# set an integration id for a nonexistent device.  Setting an integration id for
# a device that does exist is quite slow.
#
# Integration ids for *outputs* seem to be rather different.  They can be set quite
# quickly, but only for devices that actually exist, but you can integration ids
# for absurdly large output numbers that do not actually exist.  Additionally,
# #RESET,2 seems to erase all the output integration ids.
#
# My hypotheses is that output integration IDs are translated in the NWK
# to/from device commands and states.  For example, Grafik Eye has documented
# DEVICE component numbers for up to 24 zone controllers.  Monitoring shows
# ~DEVICE if no integrationid is assigned and ~OUTPUT if an integration id
# is assigned.  This mapping might not even care about the device type --
# it might be the case that action 14 (light level) always maps to OUTPUT
# action 1 (light level), and that the component number maps straight through.

# The integrationid system tries to be well behaved.  It tries to reject
# duplicates.  You can set any number of device integration ids to
# b"(Not Set)", in which case they appear to be not set.  But it does
# not prevent you from setting an integration id that looks like a
# serial number, and you can cause #INTEGRATIONID to go into an
# infinite loop by first setting a device's integration id to its own
# serial number and then trying to change it.  (This appears to be
# recoverable by rebooting the NWK.)

class ParseError(Exception):
    """Exception raised when a message doesn't parse correctly."""
    
    def __init__(self, message: str) -> None:
        super().__init__(str)

@dataclass
class DeviceDetails:
    sn: SerialNumber
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

        device = DeviceDetails(
            sn = SerialNumber(attrs[b'SN']),
            integration_id=attrs[b'INTEGRATIONID'],
            family=attrs[b'FAMILY'],
            product=attrs[b'PRODUCT'],
            raw_attrs=attrs)

        result.append(device)
    
    return result

# TODO: This isn't just QSE.  Homeworks QS, Quantum, and myRoom Plus support this.  
@dataclass
class IntegrationIDRecord:
    iid: bytes
    style: bytes # either b'DEVICE' or b'OUTPUT'
    sn: SerialNumber

class LutronUniverse:
    devices_by_sn: dict[SerialNumber, DeviceDetails]
    devices_by_iid: dict[bytes, DeviceDetails]

    # Maps output integration ids to the device sn and output/zone number
    output_ids: dict[bytes, tuple[SerialNumber, int]]

    # We don't bother storing the reverse mapping anywhere -- we need
    # to be able to control outputs that don't have integration IDs,
    # and there appears to be no benefit to ever sending an #OUTPUT command.

_IIDLINE_RE = re.compile(b'~INTEGRATIONID,([^,]+),(DEVICE|OUTPUT),([0-9A-Fa-fx]+)(?:,([0-9]+))?', re.S)

async def enumerate_universe(conn: connection.LutronConnection) -> LutronUniverse:
    all_devices = parse_details(await conn.raw_query(b'?DETAILS,ALL_DEVICES'))

    universe = LutronUniverse()
    universe.devices_by_sn = {d.sn: d for d in all_devices}
    universe.devices_by_iid = {d.integration_id: d for d in all_devices if d.integration_id != b'(Not Set)'}

    # Now we need to read all the integration ids.  The device integration ids
    # are already known, but we need the output integration ids.
    universe.output_ids = {}
    integration_ids = await conn.raw_query(b'?INTEGRATIONID,3')
    iidlines = integration_ids.split(b'\r\n')

    if not iidlines or iidlines[-1] != b'':
        raise ParseError('~INTEGRATIONIDS,3 list does not split correctly')
    iidlines = iidlines[:-1]

    for line in iidlines:
        m = _IIDLINE_RE.fullmatch(line)
        if not m:
            raise ParseError(f'Integration id line {line!r} does not parse')
        if m[2] == b'DEVICE':
            # No need to validate it -- we already know the device integration ids
            continue
        else:
            sn = SerialNumber(m[3])
            universe.output_ids[m[1]] = (sn, int(m[4]))

    return universe

async def wip_probe_universe_components(conn: connection.LutronConnection, univ: LutronUniverse):
    # Good news: you can probe like this!
    # Mediocre news: outputs with assigned integration ids are reported by integration id
    # Bad news: I noticed that #OUTPUT doesn't result in what we consider to be a sync reply
    for d in univ.devices_by_sn.values():
        _, results = await conn.raw_query_collect(b'?DEVICE,%s,0,0' % d.sn.sn)
        for result in results:
            print(f"SN {d.sn}: {result.decode().strip()}")