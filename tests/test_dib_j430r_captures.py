"""Validation against the complete learned Broadlink capture collection."""

from __future__ import annotations

import base64
import json
import os
import re
import unittest
from pathlib import Path

from protocol_loader import protocol

CAPTURE_FILE_ENV = "TOILET_CODES_FILE"
DIB_J430R_MODEL = "dib_j430r"
DIB_J430R_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "leeventus_dib_j430r_captures.json"
)
KNOWN_BAD_CAPTURES = {
    "wash1400",
    "wash2400",
    "wash3200",
    "wash3210",
}


def _capture_path() -> Path:
    """Use a private source export only when explicitly requested."""
    value = os.environ.get(CAPTURE_FILE_ENV)
    return Path(value) if value else DIB_J430R_FIXTURE


def _load_capture_codes(capture_path: Path) -> dict[str, str]:
    """Load either the sanitized fixture or an original Broadlink export."""
    with capture_path.open(encoding="utf-8") as file_handle:
        payload = json.load(file_handle)

    if "captures" in payload:
        if set(payload) != {"model", "captures"}:
            raise ValueError("sanitized fixture contains unexpected metadata")
        if payload["model"] != DIB_J430R_MODEL:
            raise ValueError(
                f"expected model {DIB_J430R_MODEL}, got {payload['model']}"
            )
        codes = payload["captures"]
    else:
        codes = payload["data"]["wc"]

    if not isinstance(codes, dict) or not all(
        isinstance(name, str) and isinstance(code, str)
        for name, code in codes.items()
    ):
        raise ValueError("capture collection must map names to Broadlink codes")
    return codes


def _decode_broadlink_capture(code: str) -> bytes:
    """Extract the logical LSB-first eight-byte frame from a Broadlink code."""
    packet = base64.b64decode(code, validate=True)
    if len(packet) < 8 or packet[0] != 0x26:
        raise ValueError("not a Broadlink IR packet")

    pulses: list[int] = []
    index = 4
    while index < len(packet):
        pulse = packet[index]
        index += 1
        if pulse == 0:
            if index + 1 >= len(packet):
                raise ValueError("truncated extended pulse")
            pulse = (packet[index] << 8) | packet[index + 1]
            index += 2
        pulses.append(pulse)
        if pulse > 1000:
            break

    if len(pulses) != 130:
        raise ValueError(f"expected 130 pulse durations, got {len(pulses)}")

    bits = [
        1 if pulses[index + 1] > 40 else 0
        for index in range(2, len(pulses), 2)
    ]
    if len(bits) != 64:
        raise ValueError(f"expected 64 bits, got {len(bits)}")

    return bytes(
        sum(bits[(byte_index * 8) + bit_index] << bit_index for bit_index in range(8))
        for byte_index in range(8)
    )


class DIBJ430RCaptureValidationTest(unittest.TestCase):
    """Verify the DIB-J430R protocol against all supplied captures."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the sanitized model fixture or an explicit source export."""
        cls.codes = _load_capture_codes(_capture_path())

    def test_sanitized_model_fixture_is_complete(self) -> None:
        """Keep the committed fixture model-specific and free of HA metadata."""
        with DIB_J430R_FIXTURE.open(encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        self.assertEqual(set(payload), {"model", "captures"})
        self.assertEqual(payload["model"], DIB_J430R_MODEL)
        self.assertEqual(len(payload["captures"]), 477)

    def test_all_captures_have_expected_validity(self) -> None:
        """Accept all 473 valid captures and identify only four corrupt ones."""
        invalid: set[str] = set()
        valid_count = 0

        for name, code in self.codes.items():
            try:
                frame = _decode_broadlink_capture(code)
                protocol.decode_frame(frame)
            except ValueError:
                invalid.add(name)
            else:
                valid_count += 1

        self.assertEqual(valid_count, 473)
        self.assertEqual(invalid, KNOWN_BAD_CAPTURES)

    def test_wash_matrix(self) -> None:
        """Validate position, intensity, seat, and water temperature matrix."""
        pattern = re.compile(r"wash([1-5])([1-5])([0-3])([0-3])$")
        checked = 0

        for name, code in self.codes.items():
            match = pattern.fullmatch(name)
            if match is None or name in KNOWN_BAD_CAPTURES:
                continue

            state, action = protocol.decode_frame(_decode_broadlink_capture(code))
            self.assertEqual(
                state,
                protocol.ToiletState(
                    jet_position=int(match.group(1)),
                    water_intensity=int(match.group(2)),
                    seat_temperature=int(match.group(3)),
                    water_temperature=int(match.group(4)),
                    dryer_temperature=1,
                    eco_level=0,
                    light=True,
                ),
                name,
            )
            self.assertEqual(action, protocol.ToiletAction.APPLY, name)
            checked += 1

        self.assertEqual(checked, 396)

    def test_dryer_matrix(self) -> None:
        """Validate all dryer and water-temperature combinations."""
        pattern = re.compile(r"dry([1-5])([0-3])$")
        checked = 0

        for name, code in self.codes.items():
            match = pattern.fullmatch(name)
            if match is None:
                continue

            state, action = protocol.decode_frame(_decode_broadlink_capture(code))
            self.assertEqual(
                state,
                protocol.ToiletState(
                    jet_position=5,
                    water_intensity=5,
                    seat_temperature=0,
                    water_temperature=int(match.group(2)),
                    dryer_temperature=int(match.group(1)),
                    eco_level=0,
                    light=True,
                ),
                name,
            )
            self.assertEqual(action, protocol.ToiletAction.APPLY, name)
            checked += 1

        self.assertEqual(checked, 20)

    def test_standby_matrix(self) -> None:
        """Validate all seat and water-temperature combinations."""
        pattern = re.compile(r"stby([0-3])([0-3])$")
        checked = 0

        for name, code in self.codes.items():
            match = pattern.fullmatch(name)
            if match is None:
                continue

            state, action = protocol.decode_frame(_decode_broadlink_capture(code))
            self.assertEqual(
                state,
                protocol.ToiletState(
                    jet_position=5,
                    water_intensity=5,
                    seat_temperature=int(match.group(1)),
                    water_temperature=int(match.group(2)),
                    dryer_temperature=1,
                    eco_level=0,
                    light=True,
                ),
                name,
            )
            self.assertEqual(action, protocol.ToiletAction.APPLY, name)
            checked += 1

        self.assertEqual(checked, 16)

    def test_individual_setting_captures(self) -> None:
        """Validate every individually learned setting value."""
        field_patterns = (
            (re.compile(r"seat_heat([0-3])$"), "seat_temperature"),
            (re.compile(r"energy_save([0-2])$"), "eco_level"),
            (re.compile(r"water_temp([0-3])$"), "water_temperature"),
            (re.compile(r"dryer_temp([1-5])$"), "dryer_temperature"),
            (re.compile(r"water_intensity([1-5])$"), "water_intensity"),
            (re.compile(r"jet_position([1-5])$"), "jet_position"),
        )

        checked = 0
        for pattern, field_name in field_patterns:
            for name, code in self.codes.items():
                match = pattern.fullmatch(name)
                if match is None:
                    continue
                state, action = protocol.decode_frame(
                    _decode_broadlink_capture(code)
                )
                self.assertEqual(getattr(state, field_name), int(match.group(1)), name)
                self.assertEqual(action, protocol.ToiletAction.APPLY, name)
                checked += 1

        self.assertEqual(checked, 26)

    def test_light_and_action_captures(self) -> None:
        """Validate light state and all known momentary actions."""
        light_expectations = {
            "led_on": True,
            "led_off": False,
            "stop_led_on": True,
            "stop_led_off": False,
        }
        for name, expected_light in light_expectations.items():
            state, _ = protocol.decode_frame(
                _decode_broadlink_capture(self.codes[name])
            )
            self.assertEqual(state.light, expected_light, name)

        action_expectations = {
            "wash": protocol.ToiletAction.WASH,
            "female wash": protocol.ToiletAction.FEMALE_WASH,
            "intense": protocol.ToiletAction.INTENSE_WASH,
            "stop": protocol.ToiletAction.STOP,
            "dry": protocol.ToiletAction.DRY,
            "pulse": protocol.ToiletAction.PULSE_WASH,
            "self_clean": protocol.ToiletAction.SELF_CLEAN,
        }
        for name, expected_action in action_expectations.items():
            _, action = protocol.decode_frame(
                _decode_broadlink_capture(self.codes[name])
            )
            self.assertEqual(action, expected_action, name)


if __name__ == "__main__":
    unittest.main()
