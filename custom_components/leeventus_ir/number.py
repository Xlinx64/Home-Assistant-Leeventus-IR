"""Number entities for Leeventus IR."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .controller import ToiletController
from .entity import ToiletEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, slots=True)
class NumberDefinition:
    """Describe one discrete numeric protocol field."""

    key: str
    state_field: str
    minimum: int
    maximum: int


NUMBER_DEFINITIONS = (
    NumberDefinition(
        key="jet_position",
        state_field="jet_position",
        minimum=1,
        maximum=5,
    ),
    NumberDefinition(
        key="water_intensity",
        state_field="water_intensity",
        minimum=1,
        maximum=5,
    ),
    NumberDefinition(
        key="dryer_temperature",
        state_field="dryer_temperature",
        minimum=1,
        maximum=5,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ToiletController],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all numeric toilet controls."""
    async_add_entities(
        ToiletNumber(entry, definition)
        for definition in NUMBER_DEFINITIONS
        if definition.state_field in entry.runtime_data.profile.supported_state_fields
    )


class ToiletNumber(ToiletEntity, NumberEntity):
    """A discrete numeric field that transmits the complete state."""

    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        definition: NumberDefinition,
    ) -> None:
        """Initialize a number entity."""
        super().__init__(entry, definition.key)
        self.definition = definition
        self._attr_translation_key = definition.key
        self._attr_native_min_value = float(definition.minimum)
        self._attr_native_max_value = float(definition.maximum)

    @property
    def native_value(self) -> float:
        """Return the optimistic value from shared state."""
        return float(getattr(self.controller.state, self.definition.state_field))

    async def async_set_native_value(self, value: float) -> None:
        """Set one field and transmit the resulting complete state."""
        integer_value = int(value)
        if value != integer_value:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="whole_number_required",
            )
        await self.controller.async_set_state(
            context=self._context,
            **{self.definition.state_field: integer_value},
        )
