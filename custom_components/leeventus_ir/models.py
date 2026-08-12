"""Supported Leeventus IR model profiles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .protocol import (
    ToiletAction,
    ToiletState,
    decode_frame,
    encode_frame,
    frame_to_raw_timings,
    raw_timings_to_frame,
)


class ToiletModel(StrEnum):
    """Stable identifiers for supported toilet models."""

    DIB_J430R = "dib_j430r"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """All model-specific protocol behavior used by the integration."""

    identifier: ToiletModel
    display_name: str
    device_model: str
    default_state: Callable[[], ToiletState]
    encode: Callable[[ToiletState, ToiletAction], bytes]
    decode: Callable[[bytes], tuple[ToiletState, ToiletAction]]
    raw_to_frame: Callable[[list[int]], bytes]
    frame_to_raw: Callable[[bytes], list[int]]
    supported_actions: frozenset[ToiletAction]
    supported_state_fields: frozenset[str]
    restore_state: Callable[[dict[str, Any]], ToiletState]


DIB_J430R = ModelProfile(
    identifier=ToiletModel.DIB_J430R,
    display_name="Leeventus DIB-J430R",
    device_model="DIB-J430R",
    default_state=ToiletState,
    encode=encode_frame,
    decode=decode_frame,
    raw_to_frame=raw_timings_to_frame,
    frame_to_raw=frame_to_raw_timings,
    supported_actions=frozenset(ToiletAction),
    supported_state_fields=frozenset(ToiletState.__dataclass_fields__),
    restore_state=ToiletState.from_dict,
)

MODEL_PROFILES: dict[ToiletModel, ModelProfile] = {
    ToiletModel.DIB_J430R: DIB_J430R,
}


def get_model_profile(model: str | ToiletModel) -> ModelProfile:
    """Return the profile for a stable model identifier."""
    return MODEL_PROFILES[ToiletModel(model)]
