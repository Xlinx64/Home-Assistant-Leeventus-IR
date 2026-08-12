"""Test the Leeventus IR config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.leeventus_ir.config_flow import LeeventusIRConfigFlow
from custom_components.leeventus_ir.const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
    CONF_MODEL,
    DOMAIN,
)
from custom_components.leeventus_ir.models import ToiletModel


def _flow(hass: HomeAssistant) -> LeeventusIRConfigFlow:
    """Create an initialized config-flow instance."""
    flow = LeeventusIRConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow.flow_id = "test"
    flow._async_abort_entries_match = Mock()
    return flow


def test_config_entry_schema_uses_backward_compatible_minor_version() -> None:
    """Stateful wash modifiers extend the v1 entry schema compatibly."""
    assert LeeventusIRConfigFlow.VERSION == 1
    assert LeeventusIRConfigFlow.MINOR_VERSION == 2


@pytest.mark.asyncio
async def test_user_flow_creates_model_entry_with_generated_title(
    hass: HomeAssistant,
) -> None:
    """The UI persists the model and IR endpoints without a random ID."""
    hass.states.async_set(
        "infrared.test_emitter",
        "unknown",
        {"friendly_name": "Bathroom emitter"},
    )
    flow = _flow(hass)
    result = await flow.async_step_user()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await flow.async_step_user(
        {
            CONF_MODEL: ToiletModel.DIB_J430R,
            CONF_INFRARED_ENTITY_ID: "infrared.test_emitter",
            CONF_INFRARED_RECEIVER_ENTITY_ID: "infrared.test_receiver",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Leeventus DIB-J430R"
    assert result["data"] == {
        CONF_MODEL: ToiletModel.DIB_J430R,
        CONF_INFRARED_ENTITY_ID: "infrared.test_emitter",
        CONF_INFRARED_RECEIVER_ENTITY_ID: "infrared.test_receiver",
    }
    assert "entity_unique_id" not in result["data"]
    assert flow._async_abort_entries_match.call_count == 2


@pytest.mark.asyncio
async def test_user_flow_aborts_without_emitter(hass: HomeAssistant) -> None:
    """Setup is impossible when HA has no native IR emitter."""
    with patch(
        "custom_components.leeventus_ir.config_flow.infrared.async_get_emitters",
        return_value=(),
    ):
        result = await _flow(hass).async_step_user()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_emitters"


@pytest.mark.asyncio
async def test_receiver_is_optional(hass: HomeAssistant) -> None:
    """A send-only setup omits the receiver key entirely."""
    result = await _flow(hass).async_step_user(
        {
            CONF_MODEL: ToiletModel.DIB_J430R,
            CONF_INFRARED_ENTITY_ID: "infrared.test_emitter",
        }
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_INFRARED_RECEIVER_ENTITY_ID not in result["data"]


@pytest.mark.asyncio
async def test_flow_manager_rejects_duplicate_emitter(hass: HomeAssistant) -> None:
    """Home Assistant's real flow manager enforces config-entry uniqueness."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Existing toilet",
        data={
            CONF_MODEL: ToiletModel.DIB_J430R,
            CONF_INFRARED_ENTITY_ID: "infrared.test_emitter",
        },
        version=1,
        minor_version=2,
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODEL: ToiletModel.DIB_J430R,
            CONF_INFRARED_ENTITY_ID: "infrared.test_emitter",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_flow_manager_reconfigures_and_reloads_entry(
    hass: HomeAssistant,
) -> None:
    """The native reconfigure flow updates endpoints and returns its abort reason."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Existing toilet",
        data={
            CONF_MODEL: ToiletModel.DIB_J430R,
            CONF_INFRARED_ENTITY_ID: "infrared.old_emitter",
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    with patch.object(
        hass.config_entries,
        "async_reload",
        new=AsyncMock(return_value=True),
    ) as reload_entry:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_MODEL: ToiletModel.DIB_J430R,
                CONF_INFRARED_ENTITY_ID: "infrared.test_emitter",
                CONF_INFRARED_RECEIVER_ENTITY_ID: "infrared.test_receiver",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_INFRARED_ENTITY_ID] == "infrared.test_emitter"
    assert entry.data[CONF_INFRARED_RECEIVER_ENTITY_ID] == "infrared.test_receiver"
    reload_entry.assert_awaited_once_with(entry.entry_id)
