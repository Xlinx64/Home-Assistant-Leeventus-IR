"""Diagnostics support for Leeventus IR."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ToiletConfigEntry
from .const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
)
from .protocol import ToiletAction

TO_REDACT = {
    CONF_INFRARED_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ToiletConfigEntry,
) -> dict[str, Any]:
    """Return privacy-conscious diagnostics for a config entry."""
    controller = entry.runtime_data

    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "profile": {
            "identifier": controller.profile.identifier.value,
            "device_model": controller.profile.device_model,
            "supported_actions": [
                action.name.lower()
                for action in ToiletAction
                if action in controller.profile.supported_actions
            ],
            "supported_state_fields": sorted(
                controller.profile.supported_state_fields
            ),
        },
        "state": controller.state.as_dict(),
        "activity": {
            "last_sent_action": _action_value(controller.last_sent_action),
            "last_received_action": _action_value(
                controller.last_received_action
            ),
            "washing_until": _timestamp_value(controller.washing_until),
            "drying_until": _timestamp_value(controller.drying_until),
            "active_wash_program": _action_value(
                controller.active_wash_program
            ),
            "wash_pulsing": controller.is_pulsing,
            "wash_oscillating": controller.is_oscillating,
        },
    }


def _action_value(action: ToiletAction | None) -> str | None:
    """Return a stable, human-readable action value."""
    return action.name.lower() if action is not None else None


def _timestamp_value(value: Any) -> str | None:
    """Serialize an optional activity timestamp."""
    return value.isoformat() if value is not None else None
