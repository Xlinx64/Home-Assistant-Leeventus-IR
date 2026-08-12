"""Encoder and decoder for the bidet toilet infrared protocol.

The protocol was reverse engineered from 475 Broadlink captures. Each command
contains the complete desired device state in an eight-byte, LSB-first frame.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from math import ceil
from typing import Any, Final

FRAME_LENGTH: Final = 8
FRAME_HEADER: Final = bytes((0x4C, 0x84))

MODULATION_HZ: Final = 38_000

# Timings are canonical medians of 471 valid Broadlink RM pro+ captures.
# One Broadlink tick is 32.84 microseconds on that emitter generation.
BROADLINK_TICK_US: Final = 32.84
# Broadlink converts microseconds back to device ticks with floor division.
# Rounding down would therefore turn some exact medians (notably 156 ticks)
# into a value one tick too short. Ceil keeps every generated pulse on the
# intended canonical tick.
LEADER_MARK_US: Final = ceil(290 * BROADLINK_TICK_US)
LEADER_SPACE_US: Final = ceil(156 * BROADLINK_TICK_US)
BIT_MARK_US: Final = ceil(19 * BROADLINK_TICK_US)
BIT_ZERO_SPACE_US: Final = ceil(19 * BROADLINK_TICK_US)
BIT_ONE_SPACE_US: Final = ceil(58 * BROADLINK_TICK_US)
END_GAP_US: Final = ceil(3333 * BROADLINK_TICK_US)

# ESPHome's remote receiver ends a capture after its idle timeout and reports
# that timeout as the final space instead of preserving the transmitter's full
# end gap. Its default 10 ms idle period is still clearly separated from the
# longest data-bit space, while allowing the complete frame to be validated.
MIN_RECEIVED_END_GAP_US: Final = 10_000

# Consumer IR receivers do not report timings as precisely as the Broadlink
# transmitter stores them. These bounds accept normal receiver jitter, while
# still rejecting a different protocol before any state can be changed.
TIMING_TOLERANCE: Final = 0.35


class ToiletAction(IntEnum):
    """Command/action values encoded in the low five bits of byte four."""

    APPLY = 0x00
    STOP = 0x01
    WASH = 0x02
    FEMALE_WASH = 0x03
    INTENSE_WASH = 0x04
    DRY = 0x05
    PULSE_WASH = 0x06
    SELF_CLEAN = 0x0A


WASH_ACTIONS: Final[frozenset[ToiletAction]] = frozenset(
    {
        ToiletAction.WASH,
        ToiletAction.FEMALE_WASH,
        ToiletAction.INTENSE_WASH,
    }
)


@dataclass(frozen=True, slots=True)
class ToiletState:
    """Complete desired toilet state carried by every IR command."""

    jet_position: int = 5
    water_intensity: int = 5
    seat_temperature: int = 0
    water_temperature: int = 2
    dryer_temperature: int = 3
    eco_level: int = 0
    light: bool = True

    def __post_init__(self) -> None:
        """Validate values before they can be encoded."""
        _validate_range("jet_position", self.jet_position, 1, 5)
        _validate_range("water_intensity", self.water_intensity, 1, 5)
        _validate_range("seat_temperature", self.seat_temperature, 0, 3)
        _validate_range("water_temperature", self.water_temperature, 0, 3)
        _validate_range("dryer_temperature", self.dryer_temperature, 1, 5)
        _validate_range("eco_level", self.eco_level, 0, 2)
        if not isinstance(self.light, bool):
            raise TypeError("light must be a boolean")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ToiletState:
        """Create a validated state from persisted data."""
        return cls(
            jet_position=int(value.get("jet_position", 5)),
            water_intensity=int(value.get("water_intensity", 5)),
            seat_temperature=int(value.get("seat_temperature", 0)),
            water_temperature=int(value.get("water_temperature", 2)),
            dryer_temperature=int(value.get("dryer_temperature", 3)),
            eco_level=int(value.get("eco_level", 0)),
            light=value.get("light", True),
        )


def encode_frame(
    state: ToiletState,
    action: ToiletAction = ToiletAction.APPLY,
) -> bytes:
    """Encode a complete state and action into the logical eight-byte frame."""
    byte_2 = (state.jet_position - 1) | ((state.water_intensity - 1) << 3)
    byte_3 = (
        state.eco_level
        | (state.seat_temperature << 2)
        | (state.water_temperature << 4)
    )
    byte_4 = ((state.dryer_temperature - 1) << 5) | int(action)
    byte_5 = 0x1D if state.light else 0x15
    byte_6 = (byte_2 + byte_3 + byte_4) & 0xFF
    byte_7 = 0x80 | ((~byte_6) & 0x7F)

    return bytes(
        (
            FRAME_HEADER[0],
            FRAME_HEADER[1],
            byte_2,
            byte_3,
            byte_4,
            byte_5,
            byte_6,
            byte_7,
        )
    )


def decode_frame(frame: bytes) -> tuple[ToiletState, ToiletAction]:
    """Decode and validate a logical eight-byte frame."""
    if len(frame) != FRAME_LENGTH:
        raise ValueError(f"expected {FRAME_LENGTH} bytes, got {len(frame)}")
    if frame[:2] != FRAME_HEADER:
        raise ValueError(
            f"unexpected frame header {frame[:2].hex()}, expected {FRAME_HEADER.hex()}"
        )

    byte_2, byte_3, byte_4, byte_5, byte_6, byte_7 = frame[2:]

    if byte_2 & 0xC0:
        raise ValueError("reserved bits in byte 2 must be zero")
    if byte_3 & 0xC0:
        raise ValueError("reserved bits in byte 3 must be zero")

    expected_byte_6 = (byte_2 + byte_3 + byte_4) & 0xFF
    if byte_6 != expected_byte_6:
        raise ValueError(
            f"checksum byte 6 is 0x{byte_6:02x}, expected 0x{expected_byte_6:02x}"
        )

    expected_byte_7 = 0x80 | ((~byte_6) & 0x7F)
    if byte_7 != expected_byte_7:
        raise ValueError(
            f"checksum byte 7 is 0x{byte_7:02x}, expected 0x{expected_byte_7:02x}"
        )

    if byte_5 == 0x1D:
        light = True
    elif byte_5 == 0x15:
        light = False
    else:
        raise ValueError(f"unexpected light byte 0x{byte_5:02x}")

    try:
        action = ToiletAction(byte_4 & 0x1F)
    except ValueError as err:
        raise ValueError(f"unknown action 0x{byte_4 & 0x1F:02x}") from err

    state = ToiletState(
        jet_position=(byte_2 & 0x07) + 1,
        water_intensity=((byte_2 >> 3) & 0x07) + 1,
        seat_temperature=(byte_3 >> 2) & 0x03,
        water_temperature=(byte_3 >> 4) & 0x03,
        dryer_temperature=((byte_4 >> 5) & 0x07) + 1,
        eco_level=byte_3 & 0x03,
        light=light,
    )
    return state, action


def frame_to_raw_timings(frame: bytes) -> list[int]:
    """Convert a logical frame to signed microsecond mark/space timings."""
    # Validate before producing an IR command. This also guarantees that the
    # final bit is one because byte 7 always has its top bit set.
    decode_frame(frame)

    bits = [
        (byte_value >> bit_position) & 1
        for byte_value in frame
        for bit_position in range(8)
    ]

    timings = [LEADER_MARK_US, -LEADER_SPACE_US]
    for index, bit in enumerate(bits):
        timings.append(BIT_MARK_US)
        if index == len(bits) - 1:
            timings.append(-END_GAP_US)
        else:
            timings.append(-(BIT_ONE_SPACE_US if bit else BIT_ZERO_SPACE_US))
    return timings


def raw_timings_to_frame(timings: list[int]) -> bytes:
    """Decode a received Home Assistant raw IR signal into a toilet frame.

    The native infrared receiver API uses positive marks and negative spaces,
    matching :func:`frame_to_raw_timings`. Receiver hardware can prepend a
    short noise pulse, so the frame leader is located rather than assumed to
    be at index zero.
    """
    normalized = [duration for duration in timings if duration]
    required_durations = 2 + (FRAME_LENGTH * 8 * 2)

    for leader_index in range(len(normalized)):
        remaining = normalized[leader_index:]
        if len(remaining) < required_durations:
            break
        if not _matches_timing(remaining[0], LEADER_MARK_US):
            continue
        if not _matches_timing(remaining[1], -LEADER_SPACE_US):
            continue

        bits: list[int] = []
        for bit_index in range(FRAME_LENGTH * 8):
            mark = remaining[2 + (bit_index * 2)]
            space = remaining[3 + (bit_index * 2)]
            if not _matches_timing(mark, BIT_MARK_US):
                break
            if bit_index == (FRAME_LENGTH * 8) - 1:
                if space > -MIN_RECEIVED_END_GAP_US:
                    break
                bits.append(1)
                continue
            if _matches_timing(space, -BIT_ZERO_SPACE_US):
                bits.append(0)
            elif _matches_timing(space, -BIT_ONE_SPACE_US):
                bits.append(1)
            else:
                break
        else:
            frame = bytes(
                sum(bits[(byte_index * 8) + bit] << bit for bit in range(8))
                for byte_index in range(FRAME_LENGTH)
            )
            decode_frame(frame)
            return frame

    raise ValueError("received timings do not contain a valid toilet frame")


def _validate_range(name: str, value: int, minimum: int, maximum: int) -> None:
    """Validate an integer protocol field."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def _matches_timing(actual: int, expected: int) -> bool:
    """Return whether a signed timing is within the receiver tolerance."""
    if actual == 0 or (actual > 0) != (expected > 0):
        return False
    return abs(abs(actual) - abs(expected)) <= abs(expected) * TIMING_TOLERANCE
