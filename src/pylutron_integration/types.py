from dataclasses import dataclass
import re

_SN_RE = re.compile(b'(?:0x)?([0-9A-Fa-f]{0,8})', re.S)

# A serial number as reported by the integration access point
# is an optional 0x followed by
# 8 hexadecimal digits, with inconsistent case.  The NWK accepts a serial
# number with up to two 0x prefixes followed by any number (maybe up to
# some limit) of zeros followed by case-insensitive hex digits.
#
# Some but not all commands will accept an integration id in place of
# a serial number.  The NWK can get extremely confused if there is an
# integration id that is also a well-formed serial number.
#
# (All of this comes from testing a QSE-CI-NWK-E, but I expect
#  it to be compatible with other integration access points
#  as well.)
#
# This class represents a canonicalized serial number.  It's hashable.
@dataclass(order=False, eq=True, frozen=True)
class SerialNumber:
    sn: bytes

    def __init__(self, sn: bytes):
        m = _SN_RE.fullmatch(sn)
        if not m:
            raise ValueError(f'Malformed serial number {sn!r}')
        sn = m[1]
        object.__setattr__(self, 'sn', b'0' * (8 - len(sn)) + sn.upper())

    def __repr__(self):
        return f'SerialNumber({self.sn!r})'
    
    def __str__(self):
        return self.sn.decode()

