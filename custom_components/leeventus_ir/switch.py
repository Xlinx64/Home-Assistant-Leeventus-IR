"""Switch entities for Leeventus IR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controller import ToiletController
from .entity import ToiletEntity
from .protocol import WASH_ACTIONS, ToiletAction

PARALLEL_UPDATES = 1


@dataclass(frozen=True, slots=True)
class WashModifierSwitchDefinition:
    """Describe one stateful wash modifier."""

    key: str
    controller_attribute: str


WASH_MODIFIER_SWITCH_DEFINITIONS = (
    WashModifierSwitchDefinition("oscillating_wash", "is_oscillating"),
    WashModifierSwitchDefinition("pulse_wash", "is_pulsing"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ToiletController],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the toilet switches."""
    entities: list[SwitchEntity] = []
    if "light" in entry.runtime_data.profile.supported_state_fields:
        entities.append(ToiletLightSwitch(entry))
    supported_actions = entry.runtime_data.profile.supported_actions
    if WASH_ACTIONS & supported_actions:
        entities.append(
            ToiletWashModifierSwitch(entry, WASH_MODIFIER_SWITCH_DEFINITIONS[0])
        )
        if ToiletAction.PULSE_WASH in supported_actions:
            entities.append(
                ToiletWashModifierSwitch(entry, WASH_MODIFIER_SWITCH_DEFINITIONS[1])
            )
    async_add_entities(entities)


class ToiletLightSwitch(ToiletEntity, SwitchEntity):
    """Optimistic light state included in every command."""

    _attr_translation_key = "light"

    def __init__(self, entry: ConfigEntry[ToiletController]) -> None:
        """Initialize the light switch."""
        super().__init__(entry, "light")

    @property
    def is_on(self) -> bool:
        """Return the optimistic light state."""
        return self.controller.state.light

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on and send the complete state."""
        await self.controller.async_set_state(light=True, context=self._context)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off and send the complete state."""
        await self.controller.async_set_state(light=False, context=self._context)


class ToiletWashModifierSwitch(ToiletEntity, SwitchEntity):
    """Expose one modifier of the currently active wash program."""

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        definition: WashModifierSwitchDefinition,
    ) -> None:
        """Initialize a wash modifier switch."""
        super().__init__(entry, definition.key)
        self.definition = definition
        self._attr_translation_key = definition.key

    @property
    def is_on(self) -> bool:
        """Return the received or optimistic modifier state."""
        return self.controller.is_washing and bool(
            getattr(self.controller, self.definition.controller_attribute)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable this modifier when a wash program is active."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable this modifier when a wash program is active."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Set the modifier to the requested state without double toggling."""
        if self.definition.controller_attribute == "is_oscillating":
            await self.controller.async_set_oscillating(
                enabled, context=self._context
            )
        else:
            await self.controller.async_set_pulsing(enabled, context=self._context)
