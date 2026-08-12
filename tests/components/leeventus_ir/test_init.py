"""Test Leeventus IR config-entry lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.leeventus_ir import (
    PLATFORMS,
    async_migrate_entry,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.leeventus_ir.const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_MODEL,
    DOMAIN,
)
from custom_components.leeventus_ir.models import DIB_J430R, ToiletModel


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Bathroom toilet",
        data={
            CONF_MODEL: ToiletModel.DIB_J430R,
            CONF_INFRARED_ENTITY_ID: "infrared.test_emitter",
        },
        version=1,
        minor_version=2,
    )


@pytest.mark.asyncio
async def test_setup_loads_controller_and_forwards_platforms(
    hass: HomeAssistant,
) -> None:
    """Setup restores state before entities are created."""
    entry = _entry()
    controller = Mock()
    controller.async_load = AsyncMock()
    with (
        patch(
            "custom_components.leeventus_ir.ToiletController",
            return_value=controller,
        ) as controller_class,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward,
    ):
        assert await async_setup_entry(hass, entry)

    controller_class.assert_called_once_with(
        hass,
        entry.entry_id,
        "infrared.test_emitter",
        DIB_J430R,
    )
    controller.async_load.assert_awaited_once()
    forward.assert_awaited_once_with(entry, PLATFORMS)
    assert entry.runtime_data is controller


@pytest.mark.asyncio
async def test_unload_only_shuts_down_after_platform_success(
    hass: HomeAssistant,
) -> None:
    """State is flushed only after every platform unloads successfully."""
    entry = _entry()
    entry.runtime_data = Mock(async_shutdown=AsyncMock())
    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new=AsyncMock(side_effect=(False, True)),
    ):
        assert not await async_unload_entry(hass, entry)
        entry.runtime_data.async_shutdown.assert_not_awaited()
        assert await async_unload_entry(hass, entry)
        entry.runtime_data.async_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_deletes_only_entry_storage(hass: HomeAssistant) -> None:
    """Removing an entry removes its own optimistic-state store."""
    entry = _entry()
    store = Mock(async_remove=AsyncMock())
    with patch("custom_components.leeventus_ir.Store", return_value=store) as store_class:
        await async_remove_entry(hass, entry)

    store_class.assert_called_once_with(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    store.async_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_migration_removes_modifier_buttons_replaced_by_switches(
    hass: HomeAssistant,
) -> None:
    """An upgrade does not leave unavailable legacy buttons in the registry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bathroom toilet",
        data={
            CONF_MODEL: ToiletModel.DIB_J430R,
            CONF_INFRARED_ENTITY_ID: "infrared.test_emitter",
        },
        version=1,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for key in ("oscillating_wash", "pulse_wash"):
        registry.async_get_or_create(
            Platform.BUTTON,
            DOMAIN,
            f"{entry.entry_id}_{key}",
            suggested_object_id=key,
        )

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 1
    assert entry.minor_version == 2
    for key in ("oscillating_wash", "pulse_wash"):
        assert (
            registry.async_get_entity_id(
                Platform.BUTTON,
                DOMAIN,
                f"{entry.entry_id}_{key}",
            )
            is None
        )
