from dataclasses import dataclass
from enum import Enum
import re
from . import types

# These are DEVICE actions.  OUTPUT actions are different.
class Action(Enum):
    ENABLE = 1
    DISABLE = 2
    PRESS_CLOSE_UNOCC = 3
    RELEASE_OPEN_OCC = 4
    HOLD = 5
    DOUBLE_TAP = 6
    CURRENT_SCENE = 7
    LED_STATE = 9
    SCENE_SAVE = 12
    LIGHT_LEVEL = 14
    ZONE_LOCK = 15
    SCENE_LOCK = 16
    SEQUENCE_STATE = 17
    START_RAISING = 18
    START_LOWERING = 19
    STOP_RAISING_LOWERING = 20
    HOLD_RELEASE = 32 # for keypads -- I have no idea what it does
    TIMECLOCK_STATE = 34 # 0 = disabled, 1 = enabled

    # 21 is a mysterious property of the SHADE component of shades.
    # It seems to have the value 0 most of the time but has other values when the shade
    # is moving.
    MOTOR_MYSTERY = 21
    
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

    def component_number(self, index: int) -> int | None:
        """Get the component number for a 1-based index.

        Args:
            index: 1-based index into this component group

        Returns:
            Component number if index is valid, None otherwise.
        """
        if index < 1 or index > self.count:
            return None

        if self.numbers is not None:
            # Arbitrary mode
            return self.numbers[index - 1]
        else:
            # Array mode
            assert self.array_spec is not None
            return self.array_spec.base + (index - 1) * self.array_spec.stride

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
    
FAMILY_TO_CLASS: dict[bytes, DeviceClass] = {}

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

        # These components are not documented.
        # TODO: Confirm the behavior of the zone buttons on a 16-zone unit
        ComponentGroup(name='MASTER_RAISE', desc='Master Raise Button', numbers=(74,)),
        ComponentGroup(name='MASTER_LOWER', desc='Master Lower Button', numbers=(75,)),
        ComponentGroup(name='ZONE_RAISE', desc='Zone Raise Button', array_spec=ArraySpec(count=8, base=36, stride=6)),
        ComponentGroup(name='ZONE_LOWER', desc='Zone Lower Button', array_spec=ArraySpec(count=8, base=37, stride=6)),

        ComponentGroup(name='TIMECLOCK_BUTTON', desc='Timeclock Button', numbers=(68,)),
        ComponentGroup(name='OK_BUTTON', desc='OK Button', numbers=(69,)),
        ComponentGroup(name='SWITCH_GROUP_BUTTON', desc='Swich Group Button', numbers=(80,)),
    ]
)

Shade = DeviceClass(
    groups=[
        # Yes, Lutron really did not document any components!
        # Shades accept a target position as "light level" (action 14)
        # on component 0 and report their position via this action as well.
        ComponentGroup(name='SHADE', desc='Shade Position', numbers=(0,),),
    ]
)

FAMILY_TO_CLASS[b'GRAFIK_EYE(2)'] = GrafikEyeQS
FAMILY_TO_CLASS[b'SHADES(3)'] = Shade

def action_to_friendly_str(action: int):
    try:
        return Action(action).name
    except ValueError:
        return str(action)

from . import qse
def decode_device_update(message: bytes, universe: qse.LutronUniverse):
    m = re.compile(b'~DEVICE,([^,]*),(\\d+),(\\d+)(?:,([^\\r]*))?\\r\\n', re.S).fullmatch(message)
    if not m:
        print(f'Regex fail: {message!r}')
        return None

    device_identifier = m[1]
    try:
        sn = types.SerialNumber(device_identifier)
        device = universe.devices_by_sn[sn]
    except ValueError:
        if device_identifier in universe.devices_by_iid:
            device = universe.devices_by_iid[device_identifier]
        else:
            print(f'Unknown device {m[1]!r}')
            return # not a serial number

    if device.family in FAMILY_TO_CLASS:
        devclass = FAMILY_TO_CLASS[device.family]
        comp = devclass.lookup_component(int(m[2]))
        if comp is not None:
            cg, idx = comp
            print(f'{cg.name} {idx} {action_to_friendly_str(int(m[3]))} {m[4]!r}')
        else:
            print(f'Unknown component in {message!r}: from {device.family.decode()} / {device.product.decode()}')
    else:
        print(f'Unknown family in {message!r}: from {device.family.decode()} / {device.product.decode()}')

