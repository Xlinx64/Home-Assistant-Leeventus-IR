"""Test model-aware Leeventus IR entity platforms."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.leeventus_ir import (
    binary_sensor,
    button,
    number,
    select,
    sensor,
    switch,
)
from custom_components.leeventus_ir.const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
)
from custom_components.leeventus_ir.controller import ToiletController
from custom_components.leeventus_ir.models import DIB_J430R
from custom_components.leeventus_ir.protocol import ToiletAction


def _entry(
    hass: HomeAssistant,
    *,
    receiver: bool = False,
    profile=DIB_J430R,
):
    """Build the minimum config-entry surface used by entities."""
    data = {CONF_INFRARED_ENTITY_ID: "infrared.test_emitter"}
    if receiver:
        data[CONF_INFRARED_RECEIVER_ENTITY_ID] = "infrared.test_receiver"
    return SimpleNamespace(
        runtime_data=ToiletController(
            hass, "entry", "infrared.test_emitter", profile
        ),
        data=data,
        entry_id="entry",
        title="Bathroom toilet",
    )


@pytest.mark.asyncio
async def test_platforms_filter_entities_by_model_capabilities(
    hass: HomeAssistant,
) -> None:
    """A future model exposes only fields and actions declared by its profile."""
    profile = replace(
        DIB_J430R,
        supported_actions=frozenset({ToiletAction.APPLY, ToiletAction.STOP}),
        supported_state_fields=frozenset({"water_intensity"}),
    )
    entry = _entry(hass, profile=profile)

    async def entities_from(setup):
        added = []
        await setup(hass, entry, lambda entities: added.extend(entities))
        return added

    assert [entity.definition.key for entity in await entities_from(button.async_setup_entry)] == [
        "stop",
        "apply_settings",
    ]
    assert [entity.definition.key for entity in await entities_from(number.async_setup_entry)] == [
        "water_intensity"
    ]
    assert await entities_from(select.async_setup_entry) == []
    assert await entities_from(switch.async_setup_entry) == []
    assert await entities_from(binary_sensor.async_setup_entry) == []

    sensors = await entities_from(sensor.async_setup_entry)
    assert [entity.definition.key for entity in sensors] == [
        "last_home_assistant_action"
    ]
    assert sensors[0].options == ["apply", "stop"]
    assert sensors[0].entity_registry_enabled_default is False


@pytest.mark.asyncio
async def test_receiver_action_sensor_requires_receiver(
    hass: HomeAssistant,
) -> None:
    """Send-only installations do not get a permanently unknown receiver sensor."""
    entry = _entry(hass, receiver=True)
    added = []

    await sensor.async_setup_entry(
        hass, entry, lambda entities: added.extend(entities)
    )

    assert "last_ir_receiver_action" in [entity.definition.key for entity in added]


@pytest.mark.asyncio
async def test_setting_entities_delegate_complete_state_changes(
    hass: HomeAssistant,
) -> None:
    """Number, select, and switch controls use their shared controller."""
    entry = _entry(hass)
    controller = entry.runtime_data
    controller.async_set_state = AsyncMock()

    number_entity = number.ToiletNumber(entry, number.NUMBER_DEFINITIONS[1])
    assert number_entity.native_value == 5.0
    await number_entity.async_set_native_value(3.0)
    controller.async_set_state.assert_awaited_once_with(
        context=None, water_intensity=3
    )
    with pytest.raises(HomeAssistantError):
        await number_entity.async_set_native_value(2.5)

    controller.async_set_state.reset_mock()
    select_entity = select.ToiletSelect(entry, select.SELECT_DEFINITIONS[0])
    assert select_entity.current_option == "off"
    await select_entity.async_select_option("level_2")
    controller.async_set_state.assert_awaited_once_with(
        context=None, seat_temperature=2
    )

    controller.async_set_state.reset_mock()
    switch_entity = switch.ToiletLightSwitch(entry)
    assert switch_entity.is_on
    await switch_entity.async_turn_off()
    controller.async_set_state.assert_awaited_once_with(light=False, context=None)
    await switch_entity.async_turn_on()


@pytest.mark.asyncio
async def test_switch_platform_exposes_light_and_both_wash_modifiers(
    hass: HomeAssistant,
) -> None:
    """The DIB-J430R exposes the two modifiers as switches, not buttons."""
    entry = _entry(hass)
    added = []
    await switch.async_setup_entry(
        hass, entry, lambda entities: added.extend(entities)
    )

    assert [
        getattr(entity, "definition", None) and entity.definition.key
        or "light"
        for entity in added
    ] == ["light", "oscillating_wash", "pulse_wash"]
    assert [definition.key for definition in button.BUTTON_DEFINITIONS] == [
        "wash",
        "female_wash",
        "intense_wash",
        "dry",
        "stop",
        "self_clean",
        "apply_settings",
    ]


@pytest.mark.asyncio
async def test_action_and_activity_entities_expose_controller_state(
    hass: HomeAssistant,
) -> None:
    """Actions, modifiers, and activity entities use the shared controller."""
    entry = _entry(hass)
    controller = entry.runtime_data
    controller.async_send_action = AsyncMock()
    controller.async_set_oscillating = AsyncMock()
    controller.async_set_pulsing = AsyncMock()

    start_button = button.ToiletActionButton(entry, button.BUTTON_DEFINITIONS[0])
    await start_button.async_press()
    controller.async_send_action.assert_awaited_once_with(
        ToiletAction.WASH, context=None
    )

    oscillation_switch = switch.ToiletWashModifierSwitch(
        entry, switch.WASH_MODIFIER_SWITCH_DEFINITIONS[0]
    )
    assert not oscillation_switch.is_on
    await oscillation_switch.async_turn_on()
    await oscillation_switch.async_turn_off()
    assert controller.async_set_oscillating.await_args_list == [
        call(True, context=None),
        call(False, context=None),
    ]

    pulsing_switch = switch.ToiletWashModifierSwitch(
        entry, switch.WASH_MODIFIER_SWITCH_DEFINITIONS[1]
    )
    await pulsing_switch.async_turn_on()
    controller.async_set_pulsing.assert_awaited_once_with(True, context=None)

    controller.active_wash_program = ToiletAction.FEMALE_WASH
    controller.is_pulsing = True
    controller.is_oscillating = True
    controller._set_activity_until(
        "washing", dt_util.utcnow() + timedelta(seconds=30)
    )
    activity = binary_sensor.ToiletActivityBinarySensor(
        entry, binary_sensor.ACTIVITY_DEFINITIONS[0]
    )
    end_time = sensor.ToiletActivityEndSensor(
        entry, sensor.ACTIVITY_END_SENSOR_DEFINITIONS[0]
    )
    current_program = sensor.ToiletCurrentWashProgramSensor(
        entry, sensor.CURRENT_WASH_PROGRAM_SENSOR_DEFINITION
    )
    assert activity.is_on
    assert oscillation_switch.is_on
    assert pulsing_switch.is_on
    assert end_time.native_value == controller.washing_until
    assert current_program.native_value == "female_wash_pulsing_oscillating"
    assert len(current_program.options) == 13
