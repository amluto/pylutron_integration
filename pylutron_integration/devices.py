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
class DeviceComponent:
    name: str | None  # Name for use in Python (like ZONE01), None for grouped components
    desc: str  # What Lutron calls it (e.g. "Scene 1 Button" or "Scene Controller")
    number: int  # The component number in the integration protocol
    group: 'ComponentGroup | None'  # The group this component belongs to, if any

@dataclass(frozen=True)
class ComponentGroup:
    name: str  # Base name for components in group, like "ZONE"
    desc: str  # Base description without number, like "Zone Controller"
    array_spec: ArraySpec | None = None # Array specification (for array mode)
    numbers: tuple[int, ...] | None = None  # Explicit list of component numbers (for arbitrary mode)

    # TODO: make this weak?
    _cache: dict[int, DeviceComponent] = field(init=False, repr=False, hash=False, compare=False)
    
    def __post_init__(self):
        # Validate that exactly one mode is specified
        if (self.array_spec is None) == (self.numbers is None):
            raise ValueError("Must specify either array_spec or numbers but not both")
        
        if self.numbers is not None and not self.numbers:
            raise ValueError("numbers cannot be an empty list")
        
        # Initialize per-group cache
        object.__setattr__(self, '_cache', {})
    
    def __getitem__(self, i: int) -> 'DeviceComponent':
        # Determine mode and validate index
        if self.numbers is not None:
            # Arbitrary mode
            if not (1 <= i <= len(self.numbers)):
                raise IndexError(f"{self.name} index {i} out of range (1-{len(self.numbers)})")
            component_number = self.numbers[i - 1]
        else:
            # Array mode
            assert self.array_spec is not None
            if not (1 <= i <= self.array_spec.count):
                raise IndexError(f"{self.name} index {i} out of range -- range is 1 .. {self.array_spec.count}")
            component_number = self.array_spec.base + (i - 1) * self.array_spec.stride
        
        # Check cache
        if i in self._cache:
            return self._cache[i]
        
        # Create component
        component_desc = f"{self.desc} {i}"
        
        component = DeviceComponent(
            name=None,
            desc=component_desc,
            number=component_number,
            group=self
        )
        
        # Cache and register with device class
        self._cache[i] = component
        
        return component
    
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
    components: dict[str, DeviceComponent]
    
    def __init__(self, groups: list[ComponentGroup], components: list[DeviceComponent]):
        """Initialize a device class with component groups and individual components.
        
        Args:
            groups: List of ComponentGroup instances
            components: Dictionary mapping component names to DeviceComponent instances
        """
        self.groups = {g.name: g for g in groups}

        self.components = {}
        for c in components:
            if c.name is None:
                raise ValueError('All non-group components need names')
            self.components[c.name] = c
        self._components_by_number: dict[int, DeviceComponent] = {}
        
        # Register all individual components
        for comp in self.components.values():
            self._components_by_number[comp.number] = comp
    
    def _register_component(self, component: DeviceComponent):
        """Register a component for lookup by number."""
        self._components_by_number[component.number] = component
    
    def lookup_component(self, number: int) -> DeviceComponent | None:
        """Look up a DeviceComponent by its component number.
        
        This function first checks if the component has already been created.
        If not, it searches through registered ComponentGroups to see if the
        number falls within any group's range, and creates it on demand.
        """
        # Check if already registered
        if number in self._components_by_number:
            return self._components_by_number[number]
        
        # Search through component groups to find a match
        for group in self.groups:
            index = group.lookup_component(number)
            if index is not None:
                # Found it! Create and return the component
                return group[index]

        return None

# Grafik Eye QS Device Definition
GrafikEyeQS = DeviceClass(
    groups=[
        ComponentGroup(name='ZONE', desc='Zone Controller', array_spec=ArraySpec(count=24, base=1)),
        ComponentGroup(name='WIRELESS_OCC_SENSOR', desc='Wireless Occupancy Sensor', array_spec=ArraySpec(count=30, base=500)),
        ComponentGroup(name='ECOSYSTEM_OCC_SENSOR', desc='EcoSystem Ballast Occupancy Sensor', array_spec=ArraySpec(count=64, base=700)),
        
        ComponentGroup(name='SCENE_LED', desc='Scene LED', array_spec=ArraySpec(count=4, base=201, stride=9)),
        ComponentGroup(name='SHADE_OPEN_LED', desc='Shade Column Open LED', array_spec=ArraySpec(count=3, base=174, stride=9)),
        ComponentGroup(name='SHADE_PRESET1_LED', desc='Shade Column Preset 1 LED', array_spec=ArraySpec(count=3, base=175, stride=9)),
        ComponentGroup(name='SHADE_CLOSE_LED', desc='Shade Column Close LED', array_spec=ArraySpec(count=3, base=211, stride=9)),
        
        # Arbitrary mode groups - shade buttons by type across columns
        ComponentGroup(name='SHADE_OPEN', desc='Shade Column Open', numbers=(38, 44, 50)),
        ComponentGroup(name='SHADE_PRESET', desc='Shade Column Preset', numbers=(39, 45, 51)),
        ComponentGroup(name='SHADE_CLOSE', desc='Shade Column Close', numbers=(40, 46, 56)),
        ComponentGroup(name='SHADE_LOWER', desc='Shade Column Lower', numbers=(41, 52, 57)),
        ComponentGroup(name='SHADE_RAISE', desc='Shade Column Raise', numbers=(47, 53, 58)),
        
        # Arbitrary mode groups - scene buttons
        ComponentGroup(name='SCENE_BUTTON', desc='Scene Button', numbers=(70, 71, 76, 77)),
    ],
    components=[
        DeviceComponent(name='SCENE_OFF_BUTTON', desc='Scene Off Button', number=83, group=None),
        DeviceComponent(name='SCENE_CONTROLLER', desc='Scene Controller', number=141, group=None),
        DeviceComponent(name='LOCAL_CCI', desc='Local CCI', number=163, group=None),
        DeviceComponent(name='TIMECLOCK_CONTROLLER', desc='Timeclock Controller', number=166, group=None),
        DeviceComponent(name='SCENE_OFF_LED', desc='Scene Off LED', number=237, group=None),
    ]
)
