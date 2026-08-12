"""IR receiver event platform for Leeventus IR."""

from __future__ import annotations

import logging
from typing import override

from homeassistant.components.event import EventEntity
from homeassistant.components.infrared import (
    InfraredReceivedSignal,
    InfraredReceiverConsumerEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_INFRARED_RECEIVER_ENTITY_ID,
    DOMAIN,
    MANUFACTURER,
)
from .controller import ToiletController
from .protocol import MODULATION_HZ, ToiletAction

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ToiletController],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the receiver event entity when a receiver is configured."""
    if receiver_entity_id := entry.data.get(CONF_INFRARED_RECEIVER_ENTITY_ID):
        async_add_entities([ToiletReceivedActionEvent(entry, receiver_entity_id)])


class ToiletReceivedActionEvent(InfraredReceiverConsumerEntity, EventEntity):
    """Fire an event for every valid action received from the physical remote."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "received_action"

    def __init__(
        self,
        entry: ConfigEntry[ToiletController],
        receiver_entity_id: str,
    ) -> None:
        """Initialize the received-action event entity."""
        self.controller = entry.runtime_data
        self._attr_event_types = [
            action.name.lower()
            for action in ToiletAction
            if action in self.controller.profile.supported_actions
        ]
        self._infrared_receiver_entity_id = receiver_entity_id
        self._attr_unique_id = f"{entry.entry_id}_received_action"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=self.controller.profile.device_model,
        )

    @callback
    @override
    def _handle_signal(self, signal: InfraredReceivedSignal) -> None:
        """Validate a received signal before scheduling its state update."""
        if (
            signal.modulation is not None
            and abs(signal.modulation - MODULATION_HZ) > 2_000
        ):
            _LOGGER.debug(
                "Ignoring IR signal with unsupported modulation %s Hz",
                signal.modulation,
            )
            return
        try:
            frame = self.controller.profile.raw_to_frame(signal.timings)
        except ValueError as err:
            _LOGGER.debug(
                "Ignoring invalid or unsupported IR signal received by %s: "
                "%s; modulation=%s Hz timing_count=%d timings=%s",
                self._infrared_receiver_entity_id,
                err,
                signal.modulation,
                len(signal.timings),
                signal.timings,
            )
            return
        self.hass.async_create_task(self._async_apply_frame(frame))

    async def _async_apply_frame(self, frame: bytes) -> None:
        """Apply a valid frame and publish an event without transmitting IR."""
        try:
            action = await self.controller.async_apply_received_frame(frame)
        except ValueError:
            _LOGGER.debug("Ignoring invalid decoded Leeventus IR frame")
            return
        if action is None:
            return
        self._trigger_event(action.name.lower())
        self.async_write_ha_state()
