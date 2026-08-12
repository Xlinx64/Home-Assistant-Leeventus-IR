"""Home Assistant infrared command for the bidet toilet."""

from __future__ import annotations

from infrared_protocols.commands import Command

from .models import ModelProfile
from .protocol import MODULATION_HZ, ToiletAction, ToiletState


class ToiletIRCommand(Command):
    """Dynamically generated 64-bit, LSB-first toilet IR command."""

    def __init__(
        self,
        profile: ModelProfile,
        state: ToiletState,
        action: ToiletAction,
    ) -> None:
        """Initialize the command from a complete desired state."""
        super().__init__(modulation=MODULATION_HZ, repeat_count=0)
        self.state = state
        self.action = action
        self._profile = profile
        self.frame = profile.encode(state, action)

    def get_raw_timings(self) -> list[int]:
        """Return signed raw timings in microseconds."""
        return self._profile.frame_to_raw(self.frame)
