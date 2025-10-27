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

@dataclass(frozen=True)
class ComponentGroup:
    name: str  # Base name for components in group, like "ZONE"
    desc: str  # Base description without number, like "Zone Controller"
    base_number: int | None = None  # First component number (for array mode)
    max_instances: int | None = None  # Number of instances (for array mode)
    stride: int = 1  # Spacing between component numbers (for array mode)
    numbers: tuple[int, ...] | None = None  # Explicit list of component numbers (for arbitrary mode)
    
    def __post_init__(self):
        # Validate that exactly one mode is specified
        array_mode = self.base_number is not None and self.max_instances is not None
        arbitrary_mode = self.numbers is not None
        
        if array_mode == arbitrary_mode:
            raise ValueError("Must specify either (base_number, max_instances) for array mode OR numbers for arbitrary mode")
        
        if arbitrary_mode and not self.numbers:
            raise ValueError("numbers list cannot be empty in arbitrary mode")
    
    def __getitem__(self, i: int) -> 'DeviceComponent':
        # Determine mode and validate index
        if self.numbers is not None:
            # Arbitrary mode
            if not (1 <= i <= len(self.numbers)):
                raise IndexError(f"{self.name} index {i} out of range (1-{len(self.numbers)})")
            component_number = self.numbers[i - 1]
        else:
            # Array mode
            if not (1 <= i <= self.max_instances):
                raise IndexError(f"{self.name} index {i} out of range (1-{self.max_instances})")
            component_number = self.base_number + (i - 1) * self.stride
        
        # Check cache
        cache_key = (self.name, i)
        if cache_key in _component_cache:
            return _component_cache[cache_key]
        
        # Create component
        component_desc = f"{self.desc} {i}"
        
        component = DeviceComponent(
            name=None,
            desc=component_desc,
            number=component_number,
            group=self
        )
        
        _component_cache[cache_key] = component
        _reg_comp(component)
        
        return component
    
    def contains_number(self, number: int) -> int | None:
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
            if number >= self.base_number:
                offset = number - self.base_number
                if offset % self.stride == 0:
                    index = offset // self.stride + 1
                    if 1 <= index <= self.max_instances:
                        return index
            return None

@dataclass(frozen=True)
class DeviceComponent:
    name: str | None  # Name for use in Python (like ZONE01), None for grouped components
    desc: str  # What Lutron calls it (e.g. "Scene 1 Button" or "Scene Controller")
    number: int  # The component number in the integration protocol
    group: ComponentGroup | None  # The group this component belongs to, if any

    # NB: We make up a description if there isn't one in the spec.

_COMPONENTS_BY_NUMBER: dict[int, DeviceComponent] = {}
_component_cache: dict[tuple[str, int], DeviceComponent] = {}
_COMPONENT_GROUPS: list['ComponentGroup'] = []

def _reg_comp(component: DeviceComponent):
    _COMPONENTS_BY_NUMBER[component.number] = component

def _reg_group(group: 'ComponentGroup'):
    """Register a component group for lookup purposes."""
    _COMPONENT_GROUPS.append(group)

def lookup_component(number: int) -> DeviceComponent:
    """Look up a DeviceComponent by its component number.
    
    This function first checks if the component has already been created.
    If not, it searches through registered ComponentGroups to see if the
    number falls within any group's range, and creates it on demand.
    
    Args:
        number: The component number to look up
        
    Returns:
        The DeviceComponent with that number
        
    Raises:
        KeyError: If no component exists with that number
    """
    # Check if already registered
    if number in _COMPONENTS_BY_NUMBER:
        return _COMPONENTS_BY_NUMBER[number]
    
    # Search through component groups to find a match
    for group in _COMPONENT_GROUPS:
        index = group.contains_number(number)
        if index is not None:
            # Found it! Create and return the component
            return group[index]
    
    # Not found in any group or individual components
    raise KeyError(f"No component with number {number}")

# Component Groups for numbered devices
ZONE = ComponentGroup(name='ZONE', desc='Zone Controller', base_number=1, max_instances=24, stride=1)
_reg_group(ZONE)
WIRELESS_OCC_SENSOR = ComponentGroup(name='WIRELESS_OCC_SENSOR', desc='Wireless Occupancy Sensor', base_number=500, max_instances=30, stride=1)
_reg_group(WIRELESS_OCC_SENSOR)
ECOSYSTEM_OCC_SENSOR = ComponentGroup(name='ECOSYSTEM_OCC_SENSOR', desc='EcoSystem Ballast Occupancy Sensor', base_number=700, max_instances=64, stride=1)
_reg_group(ECOSYSTEM_OCC_SENSOR)

# Scene LEDs (Scene Off LED is handled separately)
SCENE_LED = ComponentGroup(name='SCENE_LED', desc='Scene LED', base_number=201, max_instances=4, stride=9)
_reg_group(SCENE_LED)

# Shade Column LEDs (organized by button type across columns 1-3)
SHADE_OPEN_LED = ComponentGroup(name='SHADE_OPEN_LED', desc='Shade Column Open LED', base_number=174, max_instances=3, stride=9)
_reg_group(SHADE_OPEN_LED)
SHADE_PRESET1_LED = ComponentGroup(name='SHADE_PRESET1_LED', desc='Shade Column Preset 1 LED', base_number=175, max_instances=3, stride=9)
_reg_group(SHADE_PRESET1_LED)
SHADE_CLOSE_LED = ComponentGroup(name='SHADE_CLOSE_LED', desc='Shade Column Close LED', base_number=211, max_instances=3, stride=9)
_reg_group(SHADE_CLOSE_LED)

# Shade Column Buttons (arbitrary mode - organized by button type across columns 1-3)
SHADE_OPEN = ComponentGroup(name='SHADE_OPEN', desc='Shade Column Open', numbers=(38, 44, 50))
_reg_group(SHADE_OPEN)
SHADE_PRESET = ComponentGroup(name='SHADE_PRESET', desc='Shade Column Preset', numbers=(39, 45, 51))
_reg_group(SHADE_PRESET)
SHADE_CLOSE = ComponentGroup(name='SHADE_CLOSE', desc='Shade Column Close', numbers=(40, 46, 56))
_reg_group(SHADE_CLOSE)
SHADE_LOWER = ComponentGroup(name='SHADE_LOWER', desc='Shade Column Lower', numbers=(41, 52, 57))
_reg_group(SHADE_LOWER)
SHADE_RAISE = ComponentGroup(name='SHADE_RAISE', desc='Shade Column Raise', numbers=(47, 53, 58))
_reg_group(SHADE_RAISE)

# Scene Buttons (arbitrary mode - irregular numbering)
SCENE_BUTTON = ComponentGroup(name='SCENE_BUTTON', desc='Scene Button', numbers=(70, 71, 76, 77))
_reg_group(SCENE_BUTTON)

# Individual components (special cases that don't fit into groups)
SCENE_OFF_BUTTON = DeviceComponent(name='SCENE_OFF_BUTTON', desc='Scene Off Button', number=83, group=None)
_reg_comp(SCENE_OFF_BUTTON)

# Scene Controller
SCENE_CONTROLLER = DeviceComponent(name='SCENE_CONTROLLER', desc='Scene Controller', number=141, group=None)
_reg_comp(SCENE_CONTROLLER)

# Local CCI
LOCAL_CCI = DeviceComponent(name='LOCAL_CCI', desc='Local CCI', number=163, group=None)
_reg_comp(LOCAL_CCI)

# Timeclock Controller
TIMECLOCK_CONTROLLER = DeviceComponent(name='TIMECLOCK_CONTROLLER', desc='Timeclock Controller', number=166, group=None)
_reg_comp(TIMECLOCK_CONTROLLER)

# Scene Off LED (not part of the SCENE_LED group due to different numbering)
SCENE_OFF_LED = DeviceComponent(name='SCENE_OFF_LED', desc='Scene Off LED', number=237, group=None)
_reg_comp(SCENE_OFF_LED)