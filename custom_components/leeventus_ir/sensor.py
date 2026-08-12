"""Action-history sensors for Leeventus IR."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_INFRARED_RECEIVER_ENTITY_ID
from .controller import ToiletController
from .entity import ToiletEntity
from .protocol import WASH_ACTIONS, ToiletAction

PARALLEL_UPDATES = 1


@dataclass(frozen=True, slots=True)
class ActionSensorDefinition:
    """Describe an action value maintained by the controller."""

    key: str
    action_attribute: str


ACTION_SENSOR_DEFINITIONS = (
    ActionSensorDefinition("last_home_assistant_action", "last_sent_action"),
    ActionSensorDefinition("last_ir_receiver_action", "last_received_action"),
)


@dataclass(frozen=True, slots=True)
class ActivityEndSensorDefinition:
    """Describe the end-time sensor for one locally tracked activity."""

    key: str
    controller_attribute: str
    actions: frozenset[ToiletAction]


@dataclass(frozen=True, slots=True)
class CurrentWashProgramSensorDefinition:
    """Describe the combined wash-program sensor."""

    key: str


ACTIVITY_END_SENSOR_DEFINITIONS = (
    ActivityEndSensorDefinition(
        "washing_until",
        "washing_until",
        WASH_ACTIONS,
    ),
    ActivityEndSensorDefinition(
        "drying_until", "drying_until", frozenset({ToiletAction.DRY})
    ),
)

CURRENT_WASH_PROGRAM_SENSOR_DEFINITION = CurrentWashProgramSensorDefinition(
    "current_wash_program"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ToiletController],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up action-history sensors."""
    action_definitions = [ACTION_SENSOR_DEFINITIONS[0]]
    if CONF_INFRARED_RECEIVER_ENTITY_ID in entry.data:
        action_definitions.append(ACTION_SENSOR_DEFINITIONS[1])
    async_add_entities(
        [
            *(ToiletActionSensor(entry, definition) for definition in action_definitions),
            *(
                ToiletActivityEndSensor(entry, definition)
                for definition in ACTIVITY_END_SENSOR_DEFINITIONS
                if definition.actions & entry.runtime_data.profile.supported_actions
            ),
            *(
                [
                    ToiletCurrentWashProgramSensor(
                        entry, CURRENT_WASH_PROGRAM_SENSOR_DEFINITION
                    )
                ]
                if WASH_ACTIONS & entry.runtime_data.profile.supported_actions
                else []
            ),
        ]
    )


class ToiletActionSensor(ToiletEntity, SensorEntity):
    """Expose the last valid action for one IR signal source."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        definition: ActionSensorDefinition,
    ) -> None:
        """Initialize the action sensor."""
        super().__init__(entry, definition.key)
        self.definition = definition
        self._attr_translation_key = definition.key
        self._attr_options = [
            action.name.lower()
            for action in ToiletAction
            if action in self.controller.profile.supported_actions
        ]

    @property
    def native_value(self) -> str | None:
        """Return the action's stable, translatable enum value."""
        action: ToiletAction | None = getattr(
            self.controller, self.definition.action_attribute
        )
        return action.name.lower() if action is not None else None


class ToiletActivityEndSensor(ToiletEntity, SensorEntity):
    """Expose the expected end time of one locally started activity."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        definition: ActivityEndSensorDefinition,
    ) -> None:
        """Initialize the activity end-time sensor."""
        super().__init__(entry, definition.key)
        self.definition = definition
        self._attr_translation_key = definition.key

    @property
    def native_value(self):
        """Return the UTC end time, or unknown when the activity is inactive."""
        return getattr(self.controller, self.definition.controller_attribute)


class ToiletCurrentWashProgramSensor(ToiletEntity, SensorEntity):
    """Expose the estimated base wash program and both modifiers."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "current_wash_program"

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        definition: CurrentWashProgramSensorDefinition,
    ) -> None:
        """Initialize the current wash-program sensor."""
        super().__init__(entry, definition.key)
        self.definition = definition
        options = ["idle"]
        for action in ToiletAction:
            if (
                action not in WASH_ACTIONS
                or action not in self.controller.profile.supported_actions
            ):
                continue
            base = action.name.lower()
            options.extend(
                (
                    base,
                    f"{base}_pulsing",
                    f"{base}_oscillating",
                    f"{base}_pulsing_oscillating",
                )
            )
        self._attr_options = options

    @property
    def native_value(self) -> str:
        """Return the current wash-program enum state."""
        return self.controller.current_wash_program
