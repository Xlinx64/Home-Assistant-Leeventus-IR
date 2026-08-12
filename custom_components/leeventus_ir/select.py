"""Select entities for Leeventus IR."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controller import ToiletController
from .entity import ToiletEntity

PARALLEL_UPDATES = 1

LEVELS_0_TO_3 = ("off", "level_1", "level_2", "level_3")
ECO_MODES = ("off", "automatic", "comprehensive")


@dataclass(frozen=True, slots=True)
class SelectDefinition:
    """Describe one multi-state protocol field."""

    key: str
    state_field: str
    options: tuple[str, ...]


SELECT_DEFINITIONS = (
    SelectDefinition(
        key="seat_temperature",
        state_field="seat_temperature",
        options=LEVELS_0_TO_3,
    ),
    SelectDefinition(
        key="water_temperature",
        state_field="water_temperature",
        options=LEVELS_0_TO_3,
    ),
    SelectDefinition(
        key="eco_level",
        state_field="eco_level",
        options=ECO_MODES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ToiletController],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all select controls."""
    async_add_entities(
        ToiletSelect(entry, definition)
        for definition in SELECT_DEFINITIONS
        if definition.state_field in entry.runtime_data.profile.supported_state_fields
    )


class ToiletSelect(ToiletEntity, SelectEntity):
    """A finite setting that transmits the complete state."""

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        definition: SelectDefinition,
    ) -> None:
        """Initialize a select entity."""
        super().__init__(entry, definition.key)
        self.definition = definition
        self._attr_translation_key = definition.key
        self._attr_options = list(definition.options)

    @property
    def current_option(self) -> str:
        """Return the optimistic option from shared state."""
        level = getattr(self.controller.state, self.definition.state_field)
        return self.definition.options[level]

    async def async_select_option(self, option: str) -> None:
        """Set one field and transmit the resulting complete state."""
        level = self.definition.options.index(option)
        await self.controller.async_set_state(
            context=self._context,
            **{self.definition.state_field: level},
        )
