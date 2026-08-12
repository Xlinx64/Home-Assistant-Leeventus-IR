"""Test the receiver event entity."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from homeassistant.components.infrared import InfraredReceivedSignal
from homeassistant.core import HomeAssistant

from custom_components.leeventus_ir.const import CONF_INFRARED_ENTITY_ID
from custom_components.leeventus_ir.controller import ToiletController
from custom_components.leeventus_ir.event import (
    ToiletReceivedActionEvent,
    async_setup_entry,
)
from custom_components.leeventus_ir.models import DIB_J430R
from custom_components.leeventus_ir.protocol import ToiletAction, ToiletState


@pytest.mark.asyncio
async def test_repeated_received_actions_each_fire_an_event(
    hass: HomeAssistant,
) -> None:
    """Two identical remote presses remain two automation events."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    entry = SimpleNamespace(
        runtime_data=controller,
        data={CONF_INFRARED_ENTITY_ID: "infrared.test_emitter"},
        entry_id="entry",
        title="Leeventus DIB-J430R",
    )
    entity = ToiletReceivedActionEvent(entry, "infrared.test_receiver")
    entity._trigger_event = Mock()
    entity.async_write_ha_state = Mock()
    frame = DIB_J430R.encode(ToiletState(), ToiletAction.WASH)

    await entity._async_apply_frame(frame)
    await entity._async_apply_frame(frame)

    assert entity._trigger_event.call_args_list == [
        (("wash",),),
        (("wash",),),
    ]
    assert controller.last_received_action is ToiletAction.WASH
    assert controller.current_wash_program == "wash_oscillating"


@pytest.mark.asyncio
async def test_receiver_echo_does_not_fire_a_physical_remote_event(
    hass: HomeAssistant,
) -> None:
    """A frame just sent by Home Assistant is not exposed as a remote press."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    entry = SimpleNamespace(
        runtime_data=controller,
        data={CONF_INFRARED_ENTITY_ID: "infrared.test_emitter"},
        entry_id="entry",
        title="Leeventus DIB-J430R",
    )
    entity = ToiletReceivedActionEvent(entry, "infrared.test_receiver")
    entity._trigger_event = Mock()
    entity.async_write_ha_state = Mock()
    frame = DIB_J430R.encode(ToiletState(), ToiletAction.WASH)
    controller._remember_transmission(frame)

    await entity._async_apply_frame(frame)

    entity._trigger_event.assert_not_called()
    entity.async_write_ha_state.assert_not_called()
    assert controller.last_received_action is None


@pytest.mark.asyncio
async def test_event_platform_requires_receiver(hass: HomeAssistant) -> None:
    """The receiver consumer entity exists only for receiver-enabled entries."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    entry = SimpleNamespace(
        runtime_data=controller,
        data={CONF_INFRARED_ENTITY_ID: "infrared.test_emitter"},
        entry_id="entry",
        title="Bathroom toilet",
    )
    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
    assert added == []

    entry.data["infrared_receiver_entity_id"] = "infrared.test_receiver"
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
    assert len(added) == 1


@pytest.mark.asyncio
async def test_receiver_handler_filters_and_applies_signals(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Wrong modulation and malformed timings are ignored before state changes."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    entry = SimpleNamespace(
        runtime_data=controller,
        data={CONF_INFRARED_ENTITY_ID: "infrared.test_emitter"},
        entry_id="entry",
        title="Bathroom toilet",
    )
    entity = ToiletReceivedActionEvent(entry, "infrared.test_receiver")
    entity.hass = hass
    entity._trigger_event = Mock()
    entity.async_write_ha_state = Mock()

    entity._handle_signal(InfraredReceivedSignal([1, -1], modulation=30_000))
    with caplog.at_level(logging.DEBUG):
        entity._handle_signal(InfraredReceivedSignal([1, -1], modulation=38_000))
    entity._handle_signal(
        InfraredReceivedSignal(
            DIB_J430R.frame_to_raw(
                DIB_J430R.encode(ToiletState(), ToiletAction.STOP)
            ),
            modulation=None,
        )
    )
    await hass.async_block_till_done()

    entity._trigger_event.assert_called_once_with("stop")
    assert (
        "received timings do not contain a valid toilet frame; "
        "modulation=38000 Hz timing_count=2 timings=[1, -1]"
    ) in caplog.text


@pytest.mark.asyncio
async def test_decoded_model_error_does_not_fire_event(hass: HomeAssistant) -> None:
    """A decoder/model rejection remains silent to automations."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    entry = SimpleNamespace(
        runtime_data=controller,
        data={CONF_INFRARED_ENTITY_ID: "infrared.test_emitter"},
        entry_id="entry",
        title="Bathroom toilet",
    )
    entity = ToiletReceivedActionEvent(entry, "infrared.test_receiver")
    entity._trigger_event = Mock()
    with patch.object(
        controller, "async_apply_received_frame", side_effect=ValueError
    ):
        await entity._async_apply_frame(b"invalid")

    entity._trigger_event.assert_not_called()
