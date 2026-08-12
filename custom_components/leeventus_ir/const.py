"""Constants for the Leeventus IR integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "leeventus_ir"

CONF_INFRARED_ENTITY_ID: Final = "infrared_entity_id"
CONF_INFRARED_RECEIVER_ENTITY_ID: Final = "infrared_receiver_entity_id"
CONF_MODEL: Final = "model"

MANUFACTURER: Final = "Leeventus"

STORAGE_VERSION: Final = 1
STORAGE_SAVE_DELAY: Final = 1.0

# A colocated IR receiver can hear the integration's own transmitter. Keep a
# deliberately short correlation window so one matching receiver echo can be
# ignored without hiding a later press of the physical remote.
IR_ECHO_SUPPRESSION_WINDOW: Final = 0.5

WASHING_DURATION: Final = timedelta(seconds=70)
DRYING_DURATION: Final = timedelta(seconds=185)
