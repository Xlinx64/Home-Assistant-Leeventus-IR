"""Test Leeventus IR diagnostics."""

from __future__ import annotations

from datetime import datetime

import pytest
from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.leeventus_ir.const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
    CONF_MODEL,
    DOMAIN,
)
from custom_components.leeventus_ir.controller import ToiletController
from custom_components.leeventus_ir.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.leeventus_ir.models import DIB_J430R, ToiletModel
from custom_components.leeventus_ir.protocol import ToiletAction


@pytest.mark.asyncio
async def test_diagnostics_redact_entity_ids_and_report_controller_state(
    hass: HomeAssistant,
) -> None:
    """Diagnostics expose useful state without leaking configured entity IDs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bathroom toilet",
        data={
            CONF_MODEL: ToiletModel.DIB_J430R,
            CONF_INFRARED_ENTITY_ID: "infrared.private_emitter",
            CONF_INFRARED_RECEIVER_ENTITY_ID: "infrared.private_receiver",
        },
        version=1,
        minor_version=2,
    )
    controller = ToiletController(
        hass,
        entry.entry_id,
        entry.data[CONF_INFRARED_ENTITY_ID],
        DIB_J430R,
    )
    controller.last_sent_action = ToiletAction.WASH
    controller.last_received_action = ToiletAction.APPLY
    controller.washing_until = datetime(2026, 8, 12, 14, 30, tzinfo=dt_util.UTC)
    controller.active_wash_program = ToiletAction.WASH
    controller.is_pulsing = True
    entry.runtime_data = controller

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["config"] == {
        CONF_MODEL: ToiletModel.DIB_J430R,
        CONF_INFRARED_ENTITY_ID: REDACTED,
        CONF_INFRARED_RECEIVER_ENTITY_ID: REDACTED,
    }
    assert diagnostics["profile"]["identifier"] == "dib_j430r"
    assert diagnostics["profile"]["device_model"] == "DIB-J430R"
    assert diagnostics["state"] == controller.state.as_dict()
    assert diagnostics["activity"] == {
        "last_sent_action": "wash",
        "last_received_action": "apply",
        "washing_until": "2026-08-12T14:30:00+00:00",
        "drying_until": None,
        "active_wash_program": "wash",
        "wash_pulsing": True,
        "wash_oscillating": False,
    }
