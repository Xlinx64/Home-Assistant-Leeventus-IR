"""Action buttons for Leeventus IR."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controller import ToiletController
from .entity import ToiletEntity
from .protocol import ToiletAction

PARALLEL_UPDATES = 1


@dataclass(frozen=True, slots=True)
class ButtonDefinition:
    """Describe one stateless toilet action."""

    key: str
    action: ToiletAction


BUTTON_DEFINITIONS = (
    ButtonDefinition("wash", ToiletAction.WASH),
    ButtonDefinition("female_wash", ToiletAction.FEMALE_WASH),
    ButtonDefinition("intense_wash", ToiletAction.INTENSE_WASH),
    ButtonDefinition("dry", ToiletAction.DRY),
    ButtonDefinition("stop", ToiletAction.STOP),
    ButtonDefinition("self_clean", ToiletAction.SELF_CLEAN),
    ButtonDefinition("apply_settings", ToiletAction.APPLY),
)


def _is_supported(
    definition: ButtonDefinition,
    supported_actions: frozenset[ToiletAction],
) -> bool:
    """Return whether a model can perform this button action."""
    return definition.action in supported_actions


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ToiletController],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all stateless action buttons."""
    async_add_entities(
        ToiletActionButton(entry, definition)
        for definition in BUTTON_DEFINITIONS
        if _is_supported(definition, entry.runtime_data.profile.supported_actions)
    )


class ToiletActionButton(ToiletEntity, ButtonEntity):
    """Send an action with the complete current state."""

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        definition: ButtonDefinition,
    ) -> None:
        """Initialize an action button."""
        super().__init__(entry, definition.key)
        self.definition = definition
        self._attr_translation_key = definition.key

    async def async_press(self) -> None:
        """Send the button action."""
        await self.controller.async_send_action(
            self.definition.action, context=self._context
        )
