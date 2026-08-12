# Agent guide

## Scope

This repository is a Home Assistant custom integration for supported Leeventus
bidet toilets. It dynamically generates complete IR state frames and never
writes Broadlink learned-code storage. The currently supported model is the
Leeventus DIB-J430R.

## Development rules

- Do not send a real IR command or operate the toilet while developing or
  testing unless the user explicitly asks for it.
- Keep protocol parsing in `custom_components/leeventus_ir/protocol.py` pure so
  it remains testable without a Home Assistant installation.
- Treat receiver input as untrusted. Only update state after header, checksum,
  field-range, and timing validation succeed. Receiver handling must never
  transmit an IR command in response.
- Preserve the original Leeventus artwork in `brand/`
- keep English and German config-flow translations in sync.


## Required checks

Run these before completing a change:

```bash
pytest tests/components/leeventus_ir -v
python3 -m unittest discover -s tests -v
uvx ruff check .
```

The committed DIB-J430R fixture is validated by the normal unittest command.
To validate an original private Broadlink export instead, run:

```bash
TOILET_CODES_FILE=/path/to/broadlink_remote_codes \
  python3 -m unittest discover -s tests -v
```
