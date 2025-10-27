from dataclasses import dataclass, field
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
    
@dataclass(frozen=True)
class ArraySpec:
    count: int
    base: int  # First component number
    stride: int = 1  # Spacing between component numbers

@dataclass(frozen=True)
class ComponentGroup:
    name: str  # Programmer-friendly name, like "ZONE"
    desc: str  # Base description without number, like "Zone Controller"
    array_spec: ArraySpec | None = None # Array specification (for array mode)
    numbers: tuple[int, ...] | None = None  # Explicit list of component numbers (for arbitrary mode)

    @property
    def count(self) -> int:
        if self.array_spec is not None:
            return self.array_spec.count
        else:
                assert self.numbers is not None
                return len(self.numbers)

    def __post_init__(self):
        # Validate that exactly one mode is specified
        if (self.array_spec is None) == (self.numbers is None):
            raise ValueError("Must specify either array_spec or numbers but not both")
        
        if self.numbers is not None and not self.numbers:
            raise ValueError("numbers cannot be an empty list")
        
        # Initialize per-group cache
        object.__setattr__(self, '_cache', {})
    
    def lookup_component(self, number: int) -> int | None:
        """Check if this group contains a component number.
        
        Returns the 1-based index if found, None otherwise.
        """
        if self.numbers is not None:
            # Arbitrary mode
            try:
                return self.numbers.index(number) + 1
            except ValueError:
                return None
        else:
            # Array mode
            assert self.array_spec is not None
            if number >= self.array_spec.base:
                offset = number - self.array_spec.base
                if offset % self.array_spec.stride == 0:
                    index = offset // self.array_spec.stride + 1
                    if 1 <= index <= self.array_spec.count:
                        return index
            return None

class DeviceClass:
    """Represents a device type with its component groups and individual components."""

    groups: dict[str, ComponentGroup]
    
    def __init__(self, groups: list[ComponentGroup]):
        """Initialize a device class with component groups and individual components.
        
        Args:
            groups: List of ComponentGroup instances
            components: Dictionary mapping component names to ComponentGroup instances
        """
        self.groups = {g.name: g for g in groups}
    
    def lookup_component(self, number: int) -> tuple[ComponentGroup, int] | None:
        """Resolves a component number to a ComponentGroup and index within the group"""

        # TODO: Consider adding a cache

        # Search through component groups to find a match
        for group in self.groups.values():
            index = group.lookup_component(number)
            if index is not None:
                return (group, index)

        return None
    
# Grafik Eye QS Device Definition
GrafikEyeQS = DeviceClass(
    groups=[
        ComponentGroup(name='ZONE', desc='Zone Controller', array_spec=ArraySpec(count=24, base=1)),

        ComponentGroup(name='SHADE_OPEN', desc='Shade Column Open', numbers=(38, 44, 50)),
        ComponentGroup(name='SHADE_PRESET', desc='Shade Column Preset', numbers=(39, 45, 51)),
        ComponentGroup(name='SHADE_CLOSE', desc='Shade Column Close', numbers=(40, 46, 56)),
        ComponentGroup(name='SHADE_LOWER', desc='Shade Column Lower', numbers=(41, 52, 57)),
        ComponentGroup(name='SHADE_RAISE', desc='Shade Column Raise', numbers=(47, 53, 58)),

        ComponentGroup(name='SCENE_BUTTON', desc='Scene Button', numbers=(70, 71, 76, 77)),
        ComponentGroup(name='SCENE_OFF_BUTTON', desc='Scene Off Button', numbers=(83,)),

        ComponentGroup(name='SCENE_CONTROLLER', desc='Scene Controller', numbers=(141,)),
        ComponentGroup(name='LOCAL_CCI', desc='Local CCI', numbers=(163,)),
        ComponentGroup(name='TIMECLOCK_CONTROLLER', desc='Timeclock Controller', numbers=(166,)),

        # The LEDs are not available in QS Standalone
        ComponentGroup(name='SCENE_LED', desc='Scene LED', array_spec=ArraySpec(count=4, base=201, stride=9)),
        ComponentGroup(name='SCENE_OFF_LED', desc='Scene Off LED', numbers=(237,)),
        ComponentGroup(name='SHADE_OPEN_LED', desc='Shade Column Open LED', array_spec=ArraySpec(count=3, base=174, stride=9)),
        ComponentGroup(name='SHADE_PRESET_LED', desc='Shade Column Preset LED', array_spec=ArraySpec(count=3, base=175, stride=9)),
        ComponentGroup(name='SHADE_CLOSE_LED', desc='Shade Column Close LED', array_spec=ArraySpec(count=3, base=211, stride=9)),

        ComponentGroup(name='WIRELESS_OCC_SENSOR', desc='Wireless Occupancy Sensor', array_spec=ArraySpec(count=30, base=500)),
        ComponentGroup(name='ECOSYSTEM_OCC_SENSOR', desc='EcoSystem Ballast Occupancy Sensor', array_spec=ArraySpec(count=64, base=700)),
    ]
)
