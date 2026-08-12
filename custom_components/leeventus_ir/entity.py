"""Base entity for Leeventus IR."""

from __future__ import annotations

from homeassistant.components.infrared import InfraredEmitterConsumerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_INFRARED_ENTITY_ID,
    DOMAIN,
    MANUFACTURER,
)
from .controller import ToiletController


class ToiletEntity(InfraredEmitterConsumerEntity):
    """Common entity bound to one shared toilet controller."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        entity_key: str,
    ) -> None:
        """Initialize a toilet entity."""
        self.controller = entry.runtime_data
        self._infrared_emitter_entity_id = entry.data[CONF_INFRARED_ENTITY_ID]

        self._attr_unique_id = f"{entry.entry_id}_{entity_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=self.controller.profile.device_model,
        )

    async def async_added_to_hass(self) -> None:
        """Track emitter availability and shared state."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.controller.async_add_listener(self._async_state_changed)
        )

    @callback
    def _async_state_changed(self) -> None:
        """Publish the new shared state."""
        self.async_write_ha_state()
