"""Activity binary sensors for Leeventus IR."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controller import ToiletController
from .entity import ToiletEntity
from .protocol import WASH_ACTIONS, ToiletAction


@dataclass(frozen=True, slots=True)
class ActivityDefinition:
    """Describe one locally tracked toilet activity."""

    key: str
    controller_attribute: str
    actions: frozenset[ToiletAction]


ACTIVITY_DEFINITIONS = (
    ActivityDefinition(
        "washing",
        "is_washing",
        WASH_ACTIONS,
    ),
    ActivityDefinition("drying", "is_drying", frozenset({ToiletAction.DRY})),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ToiletController],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up locally tracked activity sensors."""
    async_add_entities(
        ToiletActivityBinarySensor(entry, definition)
        for definition in ACTIVITY_DEFINITIONS
        if definition.actions & entry.runtime_data.profile.supported_actions
    )


class ToiletActivityBinarySensor(ToiletEntity, BinarySensorEntity):
    """Expose the estimated running state of one locally started activity."""

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        definition: ActivityDefinition,
    ) -> None:
        """Initialize the activity sensor."""
        super().__init__(entry, definition.key)
        self.definition = definition
        self._attr_translation_key = definition.key

    @property
    def is_on(self) -> bool:
        """Return whether this activity is currently expected to run."""
        return bool(getattr(self.controller, self.definition.controller_attribute))
