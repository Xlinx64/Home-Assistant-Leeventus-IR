"""Unit tests for dynamic toilet frame generation."""

from __future__ import annotations

import unittest
from dataclasses import replace

from protocol_loader import protocol


class ProtocolTest(unittest.TestCase):
    """Verify all protocol fields, checksums, and raw timings."""

    def test_known_action_frames(self) -> None:
        """Reproduce the captured action frames exactly."""
        state = protocol.ToiletState(
            jet_position=5,
            water_intensity=4,
            seat_temperature=3,
            water_temperature=2,
            dryer_temperature=4,
            eco_level=0,
            light=True,
        )
        expected = {
            protocol.ToiletAction.WASH: "4c 84 1c 2c 62 1d aa d5",
            protocol.ToiletAction.FEMALE_WASH: "4c 84 1c 2c 63 1d ab d4",
            protocol.ToiletAction.INTENSE_WASH: "4c 84 1c 2c 64 1d ac d3",
            protocol.ToiletAction.STOP: "4c 84 1c 2c 61 1d a9 d6",
            protocol.ToiletAction.DRY: "4c 84 1c 2c 65 1d ad d2",
            protocol.ToiletAction.PULSE_WASH: "4c 84 1c 2c 66 1d ae d1",
            protocol.ToiletAction.SELF_CLEAN: "4c 84 1c 2c 6a 1d b2 cd",
        }

        for action, expected_hex in expected.items():
            with self.subTest(action=action):
                self.assertEqual(
                    protocol.encode_frame(state, action),
                    bytes.fromhex(expected_hex),
                )

    def test_new_learned_actions_match_their_captures(self) -> None:
        """Reproduce the supplied female and intense wash captures."""
        state = protocol.ToiletState(
            jet_position=4,
            water_intensity=5,
            seat_temperature=0,
            water_temperature=2,
            dryer_temperature=3,
            eco_level=0,
            light=True,
        )
        self.assertEqual(
            protocol.encode_frame(state, protocol.ToiletAction.FEMALE_WASH),
            bytes.fromhex("4c 84 23 20 43 1d 86 f9"),
        )
        self.assertEqual(
            protocol.encode_frame(state, protocol.ToiletAction.INTENSE_WASH),
            bytes.fromhex("4c 84 23 20 44 1d 87 f8"),
        )

    def test_every_supported_state_round_trips(self) -> None:
        """Encode/decode every state combination and every known action."""
        checked = 0
        for jet_position in range(1, 6):
            for water_intensity in range(1, 6):
                for seat_temperature in range(4):
                    for water_temperature in range(4):
                        for dryer_temperature in range(1, 6):
                            for eco_level in range(3):
                                for light in (False, True):
                                    state = protocol.ToiletState(
                                        jet_position=jet_position,
                                        water_intensity=water_intensity,
                                        seat_temperature=seat_temperature,
                                        water_temperature=water_temperature,
                                        dryer_temperature=dryer_temperature,
                                        eco_level=eco_level,
                                        light=light,
                                    )
                                    for action in protocol.ToiletAction:
                                        frame = protocol.encode_frame(state, action)
                                        decoded_state, decoded_action = (
                                            protocol.decode_frame(frame)
                                        )
                                        self.assertEqual(decoded_state, state)
                                        self.assertEqual(decoded_action, action)
                                        checked += 1

        self.assertEqual(checked, 96_000)

    def test_light_is_not_part_of_checksum(self) -> None:
        """Confirm the observed independent light byte."""
        state = protocol.ToiletState()
        on = protocol.encode_frame(state)
        off = protocol.encode_frame(replace(state, light=False))

        self.assertEqual(on[5], 0x1D)
        self.assertEqual(off[5], 0x15)
        self.assertEqual(on[:5] + on[6:], off[:5] + off[6:])

    def test_raw_timings_match_canonical_broadlink_ticks(self) -> None:
        """Generate the same 130-duration shape as valid captures."""
        frame = protocol.encode_frame(protocol.ToiletState())
        timings = protocol.frame_to_raw_timings(frame)
        ticks = [
            int(abs(duration) // protocol.BROADLINK_TICK_US)
            for duration in timings
        ]

        self.assertEqual(len(timings), 130)
        self.assertEqual(ticks[:2], [290, 156])
        self.assertEqual(ticks[-1], 3333)
        self.assertTrue(all(tick == 19 for tick in ticks[2:-1:2]))

        bits = [
            (frame[byte_index] >> bit_index) & 1
            for byte_index in range(8)
            for bit_index in range(8)
        ]
        for bit_index, bit in enumerate(bits[:-1]):
            expected_space = 58 if bit else 19
            self.assertEqual(ticks[3 + (bit_index * 2)], expected_space)

        self.assertEqual(bits[-1], 1)

    def test_received_raw_timings_update_the_full_state(self) -> None:
        """Decode a jittered receiver signal into the physical remote frame."""
        state = protocol.ToiletState(
            jet_position=2,
            water_intensity=4,
            seat_temperature=1,
            water_temperature=3,
            dryer_temperature=2,
            eco_level=2,
            light=False,
        )
        frame = protocol.encode_frame(state, protocol.ToiletAction.SELF_CLEAN)
        timings = protocol.frame_to_raw_timings(frame)
        jittered = [
            duration + (max(1, abs(duration) // 10) * (1 if index % 2 else -1))
            for index, duration in enumerate(timings)
        ]

        self.assertEqual(protocol.raw_timings_to_frame([250, -250, *jittered]), frame)
        self.assertEqual(protocol.decode_frame(protocol.raw_timings_to_frame(jittered)), (state, protocol.ToiletAction.SELF_CLEAN))

    def test_esphome_receiver_idle_timeout_terminates_frame(self) -> None:
        """Accept ESPHome's 10 ms idle timeout in place of the full end gap."""
        frame = protocol.encode_frame(
            protocol.ToiletState(
                jet_position=4,
                water_intensity=5,
                water_temperature=2,
                dryer_temperature=3,
                light=True,
            ),
            protocol.ToiletAction.STOP,
        )
        timings = protocol.frame_to_raw_timings(frame)
        timings[-1] = -protocol.MIN_RECEIVED_END_GAP_US

        self.assertEqual(protocol.raw_timings_to_frame(timings), frame)

    def test_received_end_gap_shorter_than_idle_timeout_is_rejected(self) -> None:
        """Keep the terminal space distinct from all data-bit spaces."""
        frame = protocol.encode_frame(protocol.ToiletState())
        timings = protocol.frame_to_raw_timings(frame)
        timings[-1] = -(protocol.MIN_RECEIVED_END_GAP_US - 1)

        with self.assertRaises(ValueError):
            protocol.raw_timings_to_frame(timings)

    def test_non_toilet_received_timings_are_rejected(self) -> None:
        """Do not accept a receiver signal unless it contains a valid frame."""
        with self.assertRaises(ValueError):
            protocol.raw_timings_to_frame([9000, -5000, 500, -500])

    def test_reserved_state_bits_are_rejected_with_valid_checksums(self) -> None:
        """Reject unknown fields even when both checksum bytes are consistent."""
        for byte_index, reserved_bit in ((2, 0x40), (3, 0x80)):
            with self.subTest(byte_index=byte_index):
                frame = bytearray(protocol.encode_frame(protocol.ToiletState()))
                frame[byte_index] |= reserved_bit
                frame[6] = (frame[2] + frame[3] + frame[4]) & 0xFF
                frame[7] = 0x80 | ((~frame[6]) & 0x7F)

                with self.assertRaisesRegex(ValueError, "reserved bits"):
                    protocol.decode_frame(bytes(frame))

    def test_invalid_values_are_rejected(self) -> None:
        """Reject values that cannot be represented safely."""
        invalid_changes = (
            {"jet_position": 0},
            {"jet_position": 6},
            {"water_intensity": 0},
            {"water_intensity": 6},
            {"seat_temperature": -1},
            {"seat_temperature": 4},
            {"water_temperature": -1},
            {"water_temperature": 4},
            {"dryer_temperature": 0},
            {"dryer_temperature": 6},
            {"eco_level": -1},
            {"eco_level": 3},
            {"light": 1},
        )

        for changes in invalid_changes:
            with self.subTest(changes=changes), self.assertRaises(
                (TypeError, ValueError)
            ):
                protocol.ToiletState(**changes)


if __name__ == "__main__":
    unittest.main()
