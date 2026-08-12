"""Test controller behavior without physical IR hardware."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.leeventus_ir.const import CONF_INFRARED_ENTITY_ID
from custom_components.leeventus_ir.controller import ToiletController
from custom_components.leeventus_ir.models import DIB_J430R
from custom_components.leeventus_ir.protocol import (
    ToiletAction,
    ToiletState,
    frame_to_raw_timings,
)
from custom_components.leeventus_ir.sensor import (
    ACTION_SENSOR_DEFINITIONS,
    ToiletActionSensor,
)


@pytest.mark.asyncio
async def test_state_change_sends_one_dynamic_apply_frame(hass: HomeAssistant) -> None:
    """Changing one setting transmits the complete candidate state once."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ) as send:
        await controller.async_set_state(water_intensity=2)

    assert controller.state.water_intensity == 2
    assert controller.last_sent_action is ToiletAction.APPLY
    assert controller.last_received_action is None
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_receiver_frame_updates_state_without_transmitting(
    hass: HomeAssistant,
) -> None:
    """A valid physical remote frame only updates optimistic state."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    received_state = ToiletState(jet_position=2, water_intensity=4, light=False)
    frame = controller.frame_for(ToiletAction.STOP)
    frame = bytes((frame[0], frame[1], 0x19, 0x20, 0x41, 0x15, 0x7A, 0x85))

    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ) as send:
        await controller.async_apply_received_frame(frame)

    assert controller.state == received_state
    assert controller.last_sent_action is None
    assert controller.last_received_action is ToiletAction.STOP
    send.assert_not_awaited()

    # Keep the receiver parser coupled to the same full frame shape.
    assert frame_to_raw_timings(frame)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "washing", "drying"),
    [
        (ToiletAction.WASH, True, False),
        (ToiletAction.FEMALE_WASH, True, False),
        (ToiletAction.INTENSE_WASH, True, False),
        (ToiletAction.PULSE_WASH, False, False),
        (ToiletAction.DRY, False, True),
        (ToiletAction.STOP, False, False),
        (ToiletAction.SELF_CLEAN, False, False),
    ],
)
async def test_received_actions_update_activity_without_transmitting(
    hass: HomeAssistant,
    action: ToiletAction,
    washing: bool,
    drying: bool,
) -> None:
    """Physical-remote actions update the same activity estimates as sends."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ) as send:
        await controller.async_apply_received_frame(
            DIB_J430R.encode(ToiletState(), action)
        )

    assert controller.is_washing is washing
    assert controller.is_drying is drying
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_received_apply_preserves_activity(hass: HomeAssistant) -> None:
    """A physical Apply frame must not incorrectly end a running wash."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    controller._set_activity_until(
        "washing", dt_util.utcnow() + timedelta(seconds=30)
    )
    washing_until = controller.washing_until

    await controller.async_apply_received_frame(
        DIB_J430R.encode(ToiletState(water_intensity=2), ToiletAction.APPLY)
    )

    assert controller.washing_until == washing_until


@pytest.mark.asyncio
async def test_failed_send_does_not_commit_candidate_state(
    hass: HomeAssistant,
) -> None:
    """An emitter failure leaves state and action history unchanged."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with (
        patch(
            "custom_components.leeventus_ir.controller.infrared.async_send_command",
            new=AsyncMock(side_effect=RuntimeError("emitter failed")),
        ),
        pytest.raises(RuntimeError, match="emitter failed"),
    ):
        await controller.async_set_state(water_intensity=2)

    assert controller.state == ToiletState()
    assert controller.last_sent_action is None


@pytest.mark.asyncio
async def test_action_history_is_saved_and_restored(hass: HomeAssistant) -> None:
    """The two action histories persist independently."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    controller.last_sent_action = ToiletAction.DRY
    controller.last_received_action = ToiletAction.STOP

    assert controller._storage_data() == {
        "state": ToiletState().as_dict(),
        "last_sent_action": int(ToiletAction.DRY),
        "last_received_action": int(ToiletAction.STOP),
        "washing_until": None,
        "drying_until": None,
        "active_wash_program": None,
        "wash_pulsing": False,
        "wash_oscillating": False,
    }

    with patch.object(
        controller._store,
        "async_load",
        return_value={
            "state": ToiletState(light=False).as_dict(),
            "last_sent_action": int(ToiletAction.WASH),
            "last_received_action": int(ToiletAction.SELF_CLEAN),
        },
    ):
        await controller.async_load()

    assert controller.state == ToiletState(light=False)
    assert controller.last_sent_action is ToiletAction.WASH
    assert controller.last_received_action is ToiletAction.SELF_CLEAN


@pytest.mark.asyncio
async def test_profile_restores_its_own_state_format(hass: HomeAssistant) -> None:
    """Stored state decoding belongs to the selected model profile."""
    restored = ToiletState(light=False)
    restore_state = Mock(return_value=restored)
    profile = replace(DIB_J430R, restore_state=restore_state)
    controller = ToiletController(hass, "entry", "infrared.test_emitter", profile)

    with patch.object(
        controller._store,
        "async_load",
        return_value={"state": {"future_model_field": 3}},
    ):
        await controller.async_load()

    restore_state.assert_called_once_with({"future_model_field": 3})
    assert controller.state == restored


@pytest.mark.asyncio
async def test_receiver_rejects_action_unsupported_by_model(
    hass: HomeAssistant,
) -> None:
    """A valid protocol frame cannot introduce an unsupported model action."""
    profile = replace(
        DIB_J430R,
        supported_actions=frozenset({ToiletAction.APPLY, ToiletAction.STOP}),
    )
    controller = ToiletController(hass, "entry", "infrared.test_emitter", profile)
    frame = profile.encode(ToiletState(light=False), ToiletAction.WASH)

    with pytest.raises(ValueError, match="not supported by this model"):
        await controller.async_apply_received_frame(frame)

    assert controller.state == ToiletState()
    assert controller.last_received_action is None


@pytest.mark.asyncio
async def test_invalid_persisted_values_are_ignored(hass: HomeAssistant) -> None:
    """Untrusted storage cannot restore invalid state, actions, or timestamps."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch.object(
        controller._store,
        "async_load",
        return_value={
            "state": {"jet_position": 99},
            "last_sent_action": 99,
            "last_received_action": {"bad": "type"},
            "washing_until": 123,
            "drying_until": "not-a-timestamp",
            "active_wash_program": int(ToiletAction.DRY),
            "wash_pulsing": 1,
            "wash_oscillating": "yes",
        },
    ):
        await controller.async_load()

    assert controller.state == ToiletState()
    assert controller.last_sent_action is None
    assert controller.last_received_action is None
    assert controller.washing_until is None
    assert controller.drying_until is None
    assert controller.active_wash_program is None
    assert not controller.is_pulsing
    assert not controller.is_oscillating


@pytest.mark.asyncio
async def test_invalid_storage_shape_and_unsupported_history_are_ignored(
    hass: HomeAssistant,
) -> None:
    """Storage must match the selected model and expected JSON object shape."""
    profile = replace(
        DIB_J430R, supported_actions=frozenset({ToiletAction.APPLY})
    )
    controller = ToiletController(hass, "entry", "infrared.test_emitter", profile)
    with patch.object(controller._store, "async_load", return_value=["invalid"]):
        await controller.async_load()
    assert controller.state == ToiletState()

    with patch.object(
        controller._store,
        "async_load",
        return_value={
            "state": "invalid",
            "last_sent_action": int(ToiletAction.WASH),
        },
    ):
        await controller.async_load()

    assert controller.state == ToiletState()
    assert controller.last_sent_action is None


@pytest.mark.asyncio
async def test_send_validates_press_count_and_model_action(
    hass: HomeAssistant,
) -> None:
    """Invalid button repeats and unsupported model actions never reach IR."""
    profile = replace(
        DIB_J430R, supported_actions=frozenset({ToiletAction.APPLY})
    )
    controller = ToiletController(hass, "entry", "infrared.test_emitter", profile)

    with pytest.raises(ValueError, match="at least one"):
        await controller.async_send_action(ToiletAction.APPLY, presses=0)
    with pytest.raises(ValueError, match="not supported by this model"):
        await controller.async_send_action(ToiletAction.WASH)


def test_controller_listeners_can_be_removed(hass: HomeAssistant) -> None:
    """Shared state listeners are called until they unsubscribe."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    listener = Mock()
    remove = controller.async_add_listener(listener)

    controller._notify_listeners()
    remove()
    controller._notify_listeners()

    listener.assert_called_once()


@pytest.mark.asyncio
async def test_restore_activity_deadlines_and_shutdown(hass: HomeAssistant) -> None:
    """Expired timers are dropped, active timers restored, and shutdown persists."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    now = dt_util.utcnow()
    with (
        patch.object(
            controller._store,
            "async_load",
            return_value={
                "washing_until": (now - timedelta(seconds=1)).isoformat(),
                "drying_until": (now + timedelta(seconds=30)).isoformat(),
            },
        ),
        patch.object(controller._store, "async_save", new=AsyncMock()) as save,
    ):
        await controller.async_load()
        assert controller.washing_until is None
        assert controller.drying_until is not None
        assert controller._drying_timer_task is not None
        await controller.async_shutdown()

    assert controller._drying_timer_task is None
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_expiry_ignores_replaced_or_future_deadline(
    hass: HomeAssistant,
) -> None:
    """A stale timer task cannot clear a replacement activity deadline."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    future = dt_util.utcnow() + timedelta(seconds=30)
    controller.washing_until = future

    await controller._async_expire_activity(
        "washing", future - timedelta(seconds=1)
    )
    await controller._async_expire_activity("washing", future)

    assert controller.washing_until == future


@pytest.mark.asyncio
async def test_activity_timers_follow_successfully_sent_actions(
    hass: HomeAssistant,
) -> None:
    """Wash and dry actions set their estimated activity periods exclusively."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ):
        await controller.async_send_action(ToiletAction.WASH)

        assert controller.is_washing
        assert controller.active_wash_program is ToiletAction.WASH
        assert controller.current_wash_program == "wash"
        assert not controller.is_drying
        assert controller.washing_until is not None
        assert controller.washing_until - dt_util.utcnow() <= timedelta(seconds=70)

        await controller.async_send_action(ToiletAction.DRY)

        assert not controller.is_washing
        assert controller.active_wash_program is None
        assert controller.current_wash_program == "idle"
        assert controller.is_drying
        assert controller.drying_until is not None
        assert controller.drying_until - dt_util.utcnow() <= timedelta(seconds=185)

        await controller.async_send_action(ToiletAction.STOP)

    assert not controller.is_washing
    assert not controller.is_drying
    assert controller.washing_until is None
    assert controller.drying_until is None


@pytest.mark.asyncio
async def test_modifier_switches_are_hard_noops_while_idle(
    hass: HomeAssistant,
) -> None:
    """Idle modifier switches do not transmit or alter action history."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    listener = Mock()
    controller.async_add_listener(listener)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ) as send:
        await controller.async_set_pulsing(True)
        await controller.async_set_oscillating(True)

    send.assert_not_awaited()
    listener.assert_not_called()
    assert controller.last_sent_action is None
    assert controller.current_wash_program == "idle"


@pytest.mark.asyncio
async def test_sent_modifiers_set_independently_without_extending_wash(
    hass: HomeAssistant,
) -> None:
    """Pulsing and oscillation combine and preserve the original deadline."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ) as send:
        await controller.async_send_action(ToiletAction.WASH)
        washing_until = controller.washing_until

        await controller.async_set_pulsing(True)
        assert controller.current_wash_program == "wash_pulsing"
        await controller.async_set_pulsing(True)
        await controller.async_set_oscillating(True)
        assert controller.current_wash_program == "wash_pulsing_oscillating"
        await controller.async_set_oscillating(True)
        await controller.async_set_pulsing(False)
        assert controller.current_wash_program == "wash_oscillating"
        await controller.async_set_pulsing(False)
        await controller.async_set_oscillating(False)
        assert controller.current_wash_program == "wash"
        await controller.async_set_oscillating(False)

    assert controller.washing_until == washing_until
    assert [call.args[2].action for call in send.await_args_list] == [
        ToiletAction.WASH,
        ToiletAction.PULSE_WASH,
        ToiletAction.WASH,
        ToiletAction.PULSE_WASH,
        ToiletAction.WASH,
    ]


@pytest.mark.asyncio
async def test_receiver_consumes_one_recent_transmission_echo(
    hass: HomeAssistant,
) -> None:
    """A receiver echo cannot toggle a Home Assistant command a second time."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    frame = DIB_J430R.encode(ToiletState(), ToiletAction.WASH)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ):
        await controller.async_send_action(ToiletAction.WASH)

    assert await controller.async_apply_received_frame(frame) is None
    assert controller.current_wash_program == "wash"
    assert controller.last_received_action is None

    # Suppression is single-use: a subsequent physical press remains visible.
    assert await controller.async_apply_received_frame(frame) is ToiletAction.WASH
    assert controller.current_wash_program == "wash_oscillating"


@pytest.mark.asyncio
async def test_echo_suppression_expires_before_a_later_remote_press(
    hass: HomeAssistant,
) -> None:
    """A matching physical press outside the narrow echo window is accepted."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    frame = DIB_J430R.encode(ToiletState(), ToiletAction.FEMALE_WASH)
    with patch(
        "custom_components.leeventus_ir.controller.monotonic",
        side_effect=(100.0, 100.501),
    ):
        controller._remember_transmission(frame)
        action = await controller.async_apply_received_frame(frame)

    assert action is ToiletAction.FEMALE_WASH
    assert controller.current_wash_program == "female_wash"


@pytest.mark.asyncio
async def test_modifier_does_not_restart_wash_if_deadline_expires_during_send(
    hass: HomeAssistant,
) -> None:
    """An in-flight modifier never turns an elapsed wash into a new program."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    controller.active_wash_program = ToiletAction.WASH
    original_deadline = dt_util.utcnow() + timedelta(seconds=30)
    controller._set_activity_until("washing", original_deadline)
    expired_deadline = dt_util.utcnow() - timedelta(seconds=1)

    async def expire_during_send(*args, **kwargs) -> None:
        controller.washing_until = expired_deadline

    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(side_effect=expire_during_send),
    ):
        await controller.async_set_oscillating(True)

    assert controller.washing_until == expired_deadline
    await controller._async_expire_activity("washing", expired_deadline)
    assert controller.current_wash_program == "idle"


@pytest.mark.asyncio
async def test_sent_different_wash_program_restarts_without_modifiers(
    hass: HomeAssistant,
) -> None:
    """Switching the base wash resets modifiers and starts a new deadline."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ):
        await controller.async_send_action(ToiletAction.INTENSE_WASH)
        await controller.async_set_pulsing(True)
        await controller.async_set_oscillating(True)
        previous_until = controller.washing_until

        await controller.async_send_action(ToiletAction.FEMALE_WASH)

    assert controller.active_wash_program is ToiletAction.FEMALE_WASH
    assert controller.current_wash_program == "female_wash"
    assert not controller.is_pulsing
    assert not controller.is_oscillating
    assert controller.washing_until is not None
    assert previous_until is not None
    assert controller.washing_until > previous_until


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_action",
    [ToiletAction.DRY, ToiletAction.STOP, ToiletAction.SELF_CLEAN],
)
async def test_terminal_actions_clear_active_program_and_modifiers(
    hass: HomeAssistant,
    terminal_action: ToiletAction,
) -> None:
    """Leaving a wash clears its base program and both modifier flags."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ):
        await controller.async_send_action(ToiletAction.WASH)
        await controller.async_set_pulsing(True)
        await controller.async_set_oscillating(True)
        await controller.async_send_action(terminal_action)

    assert controller.current_wash_program == "idle"
    assert controller.active_wash_program is None
    assert not controller.is_pulsing
    assert not controller.is_oscillating


@pytest.mark.asyncio
async def test_received_modifiers_and_program_switch_use_the_same_state_machine(
    hass: HomeAssistant,
) -> None:
    """Validated receiver frames mirror Home Assistant button semantics."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    state = ToiletState(water_intensity=4)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ) as send:
        await controller.async_apply_received_frame(
            DIB_J430R.encode(state, ToiletAction.INTENSE_WASH)
        )
        washing_until = controller.washing_until
        await controller.async_apply_received_frame(
            DIB_J430R.encode(state, ToiletAction.PULSE_WASH)
        )
        await controller.async_apply_received_frame(
            DIB_J430R.encode(state, ToiletAction.INTENSE_WASH)
        )

        assert controller.current_wash_program == (
            "intense_wash_pulsing_oscillating"
        )
        assert controller.washing_until == washing_until

        await controller.async_apply_received_frame(
            DIB_J430R.encode(state, ToiletAction.FEMALE_WASH)
        )

    send.assert_not_awaited()
    assert controller.state == state
    assert controller.active_wash_program is ToiletAction.FEMALE_WASH
    assert controller.current_wash_program == "female_wash"
    assert not controller.is_pulsing
    assert not controller.is_oscillating
    assert controller.washing_until is not None
    assert washing_until is not None
    assert controller.washing_until > washing_until


@pytest.mark.asyncio
async def test_active_wash_program_and_modifiers_restore_with_future_deadline(
    hass: HomeAssistant,
) -> None:
    """A still-running combined program survives a Home Assistant restart."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    future = dt_util.utcnow() + timedelta(seconds=30)
    with (
        patch.object(
            controller._store,
            "async_load",
            return_value={
                "washing_until": future.isoformat(),
                "active_wash_program": int(ToiletAction.FEMALE_WASH),
                "wash_pulsing": True,
                "wash_oscillating": True,
            },
        ),
        patch.object(controller._store, "async_save", new=AsyncMock()),
    ):
        await controller.async_load()
        assert controller.current_wash_program == (
            "female_wash_pulsing_oscillating"
        )
        await controller.async_shutdown()


@pytest.mark.asyncio
async def test_legacy_active_wash_is_restored_only_when_program_is_unambiguous(
    hass: HomeAssistant,
) -> None:
    """Upgrade old storage without inventing a program from conflicting history."""
    future = dt_util.utcnow() + timedelta(seconds=30)
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch.object(
        controller._store,
        "async_load",
        return_value={
            "washing_until": future.isoformat(),
            "last_sent_action": int(ToiletAction.WASH),
            "last_received_action": int(ToiletAction.PULSE_WASH),
        },
    ):
        await controller.async_load()

    assert controller.active_wash_program is ToiletAction.WASH
    assert controller.current_wash_program == "wash"
    await controller.async_shutdown()

    conflicting = ToiletController(
        hass, "conflicting", "infrared.test_emitter", DIB_J430R
    )
    with patch.object(
        conflicting._store,
        "async_load",
        return_value={
            "washing_until": future.isoformat(),
            "last_sent_action": int(ToiletAction.WASH),
            "last_received_action": int(ToiletAction.FEMALE_WASH),
        },
    ):
        await conflicting.async_load()

    assert conflicting.current_wash_program == "idle"
    assert conflicting.washing_until is None


@pytest.mark.asyncio
async def test_restore_never_keeps_washing_and_drying_active_together(
    hass: HomeAssistant,
) -> None:
    """Corrupt or legacy storage cannot expose two exclusive activities."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    future = dt_util.utcnow() + timedelta(seconds=30)
    with patch.object(
        controller._store,
        "async_load",
        return_value={
            "washing_until": future.isoformat(),
            "drying_until": future.isoformat(),
            "active_wash_program": int(ToiletAction.INTENSE_WASH),
        },
    ):
        await controller.async_load()

    assert controller.is_washing
    assert not controller.is_drying
    assert controller.drying_until is None
    await controller.async_shutdown()


@pytest.mark.asyncio
async def test_settings_change_keeps_running_activity(hass: HomeAssistant) -> None:
    """Changing a setting does not make a running activity appear finished."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    with patch(
        "custom_components.leeventus_ir.controller.infrared.async_send_command",
        new=AsyncMock(),
    ):
        await controller.async_send_action(ToiletAction.WASH)
        washing_until = controller.washing_until
        await controller.async_set_state(water_intensity=2)

    assert controller.is_washing
    assert controller.washing_until == washing_until


@pytest.mark.asyncio
async def test_activity_timer_expires_at_its_deadline(hass: HomeAssistant) -> None:
    """An elapsed timer clears its activity and end timestamp."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    expired_at = dt_util.utcnow() - timedelta(seconds=1)
    controller.active_wash_program = ToiletAction.WASH
    controller.is_pulsing = True
    controller.is_oscillating = True
    controller._set_activity_until("washing", expired_at)
    await hass.async_block_till_done()

    assert not controller.is_washing
    assert controller.washing_until is None
    assert controller.active_wash_program is None
    assert not controller.is_pulsing
    assert not controller.is_oscillating


def test_action_sensors_expose_their_respective_action_history(
    hass: HomeAssistant,
) -> None:
    """Each sensor reads only the action history selected for its source."""
    controller = ToiletController(hass, "entry", "infrared.test_emitter", DIB_J430R)
    controller.last_sent_action = ToiletAction.DRY
    controller.last_received_action = ToiletAction.STOP
    entry = SimpleNamespace(
        runtime_data=controller,
        data={CONF_INFRARED_ENTITY_ID: "infrared.test_emitter"},
        unique_id="toilet",
        entry_id="entry",
        title="WC",
    )

    sent_sensor = ToiletActionSensor(entry, ACTION_SENSOR_DEFINITIONS[0])
    received_sensor = ToiletActionSensor(entry, ACTION_SENSOR_DEFINITIONS[1])

    assert sent_sensor.native_value == "dry"
    assert received_sensor.native_value == "stop"
