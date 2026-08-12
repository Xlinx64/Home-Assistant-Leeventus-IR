"""Shared state and transmission controller for Leeventus IR."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from time import monotonic
from typing import Any

from homeassistant.components import infrared
from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    DRYING_DURATION,
    IR_ECHO_SUPPRESSION_WINDOW,
    STORAGE_SAVE_DELAY,
    STORAGE_VERSION,
    WASHING_DURATION,
)
from .ir_command import ToiletIRCommand
from .models import ModelProfile
from .protocol import WASH_ACTIONS, ToiletAction, ToiletState

_LOGGER = logging.getLogger(__name__)


class ToiletController:
    """Own the complete optimistic state and serialize all IR transmissions."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        infrared_entity_id: str,
        profile: ModelProfile,
    ) -> None:
        """Initialize the controller."""
        self.hass = hass
        self.entry_id = entry_id
        self.infrared_entity_id = infrared_entity_id
        self.profile = profile
        self.state = profile.default_state()
        self.last_sent_action: ToiletAction | None = None
        self.last_received_action: ToiletAction | None = None
        self.washing_until: datetime | None = None
        self.drying_until: datetime | None = None
        self.active_wash_program: ToiletAction | None = None
        self.is_pulsing = False
        self.is_oscillating = False
        self._recent_transmissions: list[tuple[bytes, float]] = []

        self._listeners: set[Callable[[], None]] = set()
        self._send_lock = asyncio.Lock()
        self._washing_timer_task: asyncio.Task[None] | None = None
        self._drying_timer_task: asyncio.Task[None] | None = None
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
        )

    async def async_load(self) -> None:
        """Restore the last successfully transmitted state."""
        stored = await self._store.async_load()
        if stored:
            if not isinstance(stored, dict):
                _LOGGER.warning("Ignoring invalid stored toilet data: %r", stored)
                return
            try:
                state_data = stored.get("state", {})
                if not isinstance(state_data, dict):
                    raise TypeError("stored state must be an object")
                self.state = self.profile.restore_state(state_data)
            except (TypeError, ValueError) as err:
                _LOGGER.warning("Ignoring invalid stored toilet state: %s", err)
            self.last_sent_action = self._stored_profile_action(
                stored.get("last_sent_action"), "last sent action"
            )
            self.last_received_action = self._stored_profile_action(
                stored.get("last_received_action"), "last received action"
            )
            self.washing_until = self._stored_timestamp(
                stored.get("washing_until"), "washing end time"
            )
            self.drying_until = self._stored_timestamp(
                stored.get("drying_until"), "drying end time"
            )
            self.active_wash_program = self._stored_wash_program(
                stored.get("active_wash_program")
            )
            self.is_pulsing = self._stored_bool(
                stored.get("wash_pulsing", False), "wash pulsing state"
            )
            self.is_oscillating = self._stored_bool(
                stored.get("wash_oscillating", False),
                "wash oscillating state",
            )
            self._restore_activity_timers()

    async def async_set_state(
        self,
        *,
        context: Context | None = None,
        **changes: Any,
    ) -> None:
        """Change settings, send the full state, then commit on success."""
        async with self._send_lock:
            candidate = replace(self.state, **changes)
            await self._async_send(candidate, ToiletAction.APPLY, context)
            self.state = candidate
            self._schedule_save()
            self._notify_listeners()

    async def async_send_action(
        self,
        action: ToiletAction,
        *,
        context: Context | None = None,
        presses: int = 1,
    ) -> None:
        """Send an action one or more times using the complete current state."""
        if presses < 1:
            raise ValueError("presses must be at least one")
        if action not in self.profile.supported_actions:
            raise ValueError(f"Action {action.name} is not supported by this model")
        async with self._send_lock:
            if action is ToiletAction.PULSE_WASH and not self._has_active_wash:
                return
            changed = False
            try:
                for press in range(presses):
                    await self._async_send(self.state, action, context)
                    self._apply_activity_action(action)
                    changed = True
                    if press < presses - 1:
                        await asyncio.sleep(0.2)
            finally:
                if changed:
                    self._schedule_save()
                    self._notify_listeners()

    async def async_set_oscillating(
        self,
        enabled: bool,
        *,
        context: Context | None = None,
    ) -> None:
        """Set oscillation by repeating the active wash program if needed."""
        async with self._send_lock:
            if not self._has_active_wash or self.is_oscillating is enabled:
                return
            action = self.active_wash_program
            assert action is not None
            await self._async_send(self.state, action, context)
            # Do not re-evaluate the deadline after transmission. If it elapsed
            # while the emitter was busy, its waiting timer clears this flag as
            # soon as the lock is released instead of restarting the wash.
            self.is_oscillating = enabled
            self._schedule_save()
            self._notify_listeners()

    async def async_set_pulsing(
        self,
        enabled: bool,
        *,
        context: Context | None = None,
    ) -> None:
        """Set pulsing during an active wash program if needed."""
        async with self._send_lock:
            if not self._has_active_wash or self.is_pulsing is enabled:
                return
            await self._async_send(self.state, ToiletAction.PULSE_WASH, context)
            self.is_pulsing = enabled
            self._schedule_save()
            self._notify_listeners()

    async def _async_send(
        self,
        state: ToiletState,
        action: ToiletAction,
        context: Context | None,
    ) -> None:
        """Generate and transmit one command through HA's infrared layer."""
        if action not in self.profile.supported_actions:
            raise ValueError(f"Action {action.name} is not supported by this model")
        command = ToiletIRCommand(self.profile, state, action)
        await infrared.async_send_command(
            self.hass,
            self.infrared_entity_id,
            command,
            context=context,
        )
        self._remember_transmission(command.frame)
        self.last_sent_action = action
        _LOGGER.debug(
            "Sent toilet IR action=%s frame=%s via %s",
            action.name,
            command.frame.hex(" "),
            self.infrared_entity_id,
        )

    async def async_apply_received_frame(
        self, frame: bytes
    ) -> ToiletAction | None:
        """Apply a verified received frame without transmitting anything."""
        state, action = self.profile.decode(frame)
        if action not in self.profile.supported_actions:
            raise ValueError(f"Action {action.name} is not supported by this model")
        async with self._send_lock:
            if self._consume_transmission_echo(frame):
                _LOGGER.debug(
                    "Ignoring receiver echo of a recently sent toilet IR frame=%s",
                    frame.hex(" "),
                )
                return None
            self.state = state
            self.last_received_action = action
            self._apply_activity_action(action)
            self._schedule_save()
            self._notify_listeners()
        _LOGGER.debug("Applied received toilet IR action=%s frame=%s", action.name, frame.hex(" "))
        return action

    def _remember_transmission(self, frame: bytes) -> None:
        """Remember one successful transmission for receiver-echo suppression."""
        now = monotonic()
        self._prune_recent_transmissions(now)
        self._recent_transmissions.append((frame, now))

    def _consume_transmission_echo(self, frame: bytes) -> bool:
        """Consume one matching recent transmission if this frame is its echo."""
        now = monotonic()
        self._prune_recent_transmissions(now)
        for index, (sent_frame, _) in enumerate(self._recent_transmissions):
            if sent_frame == frame:
                del self._recent_transmissions[index]
                return True
        return False

    def _prune_recent_transmissions(self, now: float) -> None:
        """Discard transmissions too old to be receiver echoes."""
        self._recent_transmissions = [
            item
            for item in self._recent_transmissions
            if now - item[1] <= IR_ECHO_SUPPRESSION_WINDOW
        ]

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Subscribe an entity to shared-state changes."""
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    @callback
    def _notify_listeners(self) -> None:
        """Notify all entities after a successful state change."""
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _schedule_save(self) -> None:
        """Persist state through Home Assistant's managed storage helper."""
        self._store.async_delay_save(self._storage_data, STORAGE_SAVE_DELAY)

    @property
    def is_washing(self) -> bool:
        """Return whether a locally started wash is still expected to run."""
        return self.washing_until is not None and self.washing_until > dt_util.utcnow()

    @property
    def current_wash_program(self) -> str:
        """Return the stable enum state for the active wash and modifiers."""
        if not self._has_active_wash:
            return "idle"
        program = self.active_wash_program
        assert program is not None
        suffix = ""
        if self.is_pulsing:
            suffix += "_pulsing"
        if self.is_oscillating:
            suffix += "_oscillating"
        return f"{program.name.lower()}{suffix}"

    @property
    def is_drying(self) -> bool:
        """Return whether a locally started dry cycle is still expected to run."""
        return self.drying_until is not None and self.drying_until > dt_util.utcnow()

    def _apply_activity_action(self, action: ToiletAction) -> None:
        """Update local activity timers after a command was successfully sent."""
        now = dt_util.utcnow()
        if action in WASH_ACTIONS:
            if self._has_active_wash and self.active_wash_program is action:
                self.is_oscillating = not self.is_oscillating
                return
            self.active_wash_program = action
            self.is_pulsing = False
            self.is_oscillating = False
            self._set_activity_until("washing", now + WASHING_DURATION)
            self._set_activity_until("drying", None)
        elif action is ToiletAction.PULSE_WASH:
            if self._has_active_wash:
                self.is_pulsing = not self.is_pulsing
        elif action is ToiletAction.DRY:
            self._clear_wash_activity()
            self._set_activity_until("drying", now + DRYING_DURATION)
        elif action in {ToiletAction.STOP, ToiletAction.SELF_CLEAN}:
            self._clear_wash_activity()
            self._set_activity_until("drying", None)

    @property
    def _has_active_wash(self) -> bool:
        """Return whether a known wash program is currently expected to run."""
        return self.is_washing and self.active_wash_program in WASH_ACTIONS

    def _clear_wash_activity(self) -> None:
        """Clear the wash deadline, base program, and both modifiers."""
        self._set_activity_until("washing", None)
        self.active_wash_program = None
        self.is_pulsing = False
        self.is_oscillating = False

    def _restore_activity_timers(self) -> None:
        """Restore only still-active timers after Home Assistant restarts."""
        now = dt_util.utcnow()
        changed = False
        if (
            self.washing_until is not None
            and self.washing_until > now
            and self.active_wash_program is None
        ):
            # Releases before wash-program persistence can still have a valid
            # future deadline. Recover only when the two action histories give
            # one unambiguous base program; conflicting histories are unsafe.
            legacy_programs = {
                action
                for action in (self.last_sent_action, self.last_received_action)
                if action in WASH_ACTIONS
            }
            if len(legacy_programs) == 1:
                self.active_wash_program = legacy_programs.pop()
                changed = True
        if (
            self.washing_until is not None
            and self.washing_until > now
            and self.active_wash_program in WASH_ACTIONS
        ):
            self._set_activity_timer("washing", self.washing_until)
        else:
            if (
                self.washing_until is not None
                or self.active_wash_program is not None
                or self.is_pulsing
                or self.is_oscillating
            ):
                changed = True
            self.washing_until = None
            self.active_wash_program = None
            self.is_pulsing = False
            self.is_oscillating = False

        if self.active_wash_program in WASH_ACTIONS:
            if self.drying_until is not None:
                self._set_activity_until("drying", None)
                changed = True
        elif self.drying_until is not None and self.drying_until > now:
            self._set_activity_timer("drying", self.drying_until)
        elif self.drying_until is not None:
            self.drying_until = None
            changed = True
        if changed:
            self._schedule_save()

    def _set_activity_until(self, activity: str, until: datetime | None) -> None:
        """Set one activity's absolute deadline and schedule its expiry."""
        self._cancel_activity_timer(activity)

        setattr(self, f"{activity}_until", until)
        if until is not None:
            self._set_activity_timer(activity, until)

    def _set_activity_timer(self, activity: str, until: datetime) -> None:
        """Schedule one activity deadline."""
        task = self.hass.async_create_task(
            self._async_wait_for_activity_expiry(activity, until)
        )
        setattr(self, f"_{activity}_timer_task", task)

    def _cancel_activity_timer(self, activity: str) -> None:
        """Cancel an obsolete activity deadline without cancelling this task."""
        task_attr = f"_{activity}_timer_task"
        task = getattr(self, task_attr)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        setattr(self, task_attr, None)

    async def _async_wait_for_activity_expiry(
        self,
        activity: str,
        expected_until: datetime,
    ) -> None:
        """Wait until a deadline, then clear it if it has not been replaced."""
        try:
            delay = max(0.0, (expected_until - dt_util.utcnow()).total_seconds())
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        await self._async_expire_activity(activity, expected_until)

    async def _async_expire_activity(self, activity: str, expected_until: datetime) -> None:
        """Clear an activity only if its scheduled deadline is still current."""
        async with self._send_lock:
            until_attr = f"{activity}_until"
            if getattr(self, until_attr) != expected_until:
                return
            if expected_until > dt_util.utcnow():
                return
            if activity == "washing":
                self._clear_wash_activity()
            else:
                self._set_activity_until(activity, None)
            self._schedule_save()
            self._notify_listeners()

    @callback
    def _storage_data(self) -> dict[str, Any]:
        """Return storage data."""
        return {
            "state": self.state.as_dict(),
            "last_sent_action": self._stored_action_value(self.last_sent_action),
            "last_received_action": self._stored_action_value(
                self.last_received_action
            ),
            "washing_until": self._stored_timestamp_value(self.washing_until),
            "drying_until": self._stored_timestamp_value(self.drying_until),
            "active_wash_program": self._stored_action_value(
                self.active_wash_program
            ),
            "wash_pulsing": self.is_pulsing,
            "wash_oscillating": self.is_oscillating,
        }

    @staticmethod
    def _stored_action(
        value: Any,
        description: str,
    ) -> ToiletAction | None:
        """Restore one optional action value without trusting storage."""
        if value is None:
            return None
        try:
            return ToiletAction(value)
        except (TypeError, ValueError):
            _LOGGER.warning("Ignoring invalid stored %s: %r", description, value)
            return None

    def _stored_profile_action(
        self,
        value: Any,
        description: str,
    ) -> ToiletAction | None:
        """Restore an action only when the selected model supports it."""
        action = self._stored_action(value, description)
        if action is not None and action not in self.profile.supported_actions:
            _LOGGER.warning(
                "Ignoring unsupported stored %s: %s", description, action.name
            )
            return None
        return action

    def _stored_wash_program(self, value: Any) -> ToiletAction | None:
        """Restore only a supported base wash action."""
        action = self._stored_profile_action(value, "active wash program")
        if action is not None and action not in WASH_ACTIONS:
            _LOGGER.warning(
                "Ignoring invalid stored active wash program: %s", action.name
            )
            return None
        return action

    @staticmethod
    def _stored_bool(value: Any, description: str) -> bool:
        """Restore an exact boolean without accepting integers or strings."""
        if isinstance(value, bool):
            return value
        _LOGGER.warning("Ignoring invalid stored %s: %r", description, value)
        return False

    @staticmethod
    def _stored_action_value(action: ToiletAction | None) -> int | None:
        """Convert an optional action to its JSON-safe protocol value."""
        return int(action) if action is not None else None

    @staticmethod
    def _stored_timestamp(value: Any, description: str) -> datetime | None:
        """Parse a persisted UTC timestamp without trusting storage."""
        if value is None:
            return None
        if not isinstance(value, str):
            _LOGGER.warning("Ignoring invalid stored %s: %r", description, value)
            return None
        timestamp = dt_util.parse_datetime(value)
        if timestamp is None:
            _LOGGER.warning("Ignoring invalid stored %s: %r", description, value)
            return None
        return timestamp.astimezone(dt_util.UTC)

    @staticmethod
    def _stored_timestamp_value(value: datetime | None) -> str | None:
        """Serialize an optional timestamp in UTC."""
        return value.isoformat() if value is not None else None

    async def async_shutdown(self) -> None:
        """Flush current state before the config entry unloads."""
        for activity in ("washing", "drying"):
            self._cancel_activity_timer(activity)
        await self._store.async_save(self._storage_data())

    def frame_for(self, action: ToiletAction) -> bytes:
        """Return a frame for diagnostics or tests without transmitting it."""
        return self.profile.encode(self.state, action)
