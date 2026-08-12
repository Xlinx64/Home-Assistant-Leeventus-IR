"""Leeventus IR integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_MODEL,
    DOMAIN,
    STORAGE_VERSION,
)
from .controller import ToiletController
from .models import get_model_profile

PLATFORMS = (
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
)

type ToiletConfigEntry = ConfigEntry[ToiletController]

_LEGACY_MODIFIER_BUTTON_KEYS = ("oscillating_wash", "pulse_wash")


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: ToiletConfigEntry,
) -> bool:
    """Remove modifier buttons replaced by stateful switch entities."""
    if entry.version == 1 and entry.minor_version < 2:
        registry = er.async_get(hass)
        for key in _LEGACY_MODIFIER_BUTTON_KEYS:
            if entity_id := registry.async_get_entity_id(
                Platform.BUTTON,
                DOMAIN,
                f"{entry.entry_id}_{key}",
            ):
                registry.async_remove(entity_id)
        hass.config_entries.async_update_entry(
            entry,
            version=1,
            minor_version=2,
        )
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ToiletConfigEntry,
) -> bool:
    """Set up Leeventus IR from a config entry."""
    controller = ToiletController(
        hass,
        entry.entry_id,
        entry.data[CONF_INFRARED_ENTITY_ID],
        get_model_profile(entry.data[CONF_MODEL]),
    )
    await controller.async_load()
    entry.runtime_data = controller

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ToiletConfigEntry,
) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_shutdown()
    return True


async def async_remove_entry(
    hass: HomeAssistant,
    entry: ToiletConfigEntry,
) -> None:
    """Remove the persisted optimistic state with the config entry."""
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    await store.async_remove()
