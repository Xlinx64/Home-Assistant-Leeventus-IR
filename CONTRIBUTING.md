# Contributing

Bug reports, documentation improvements, and code contributions are welcome.

## Reporting a problem

Open a GitHub issue and include:

- the exact Leeventus model;
- the Home Assistant version;
- the infrared emitter and receiver integrations in use;
- the action or setting that behaved unexpectedly;
- relevant Home Assistant log messages, with private information removed.

For safety, do not test wash, dry, or temperature functions unless the toilet
can be supervised and stopped immediately.

## Development setup

Use Python 3.14. The integration requires Home Assistant 2026.6 or newer, and
the pinned test environment tracks Home Assistant 2026.8.1.

Create a virtual environment and install the test dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements_test.txt
```

Run the Home Assistant integration tests, protocol tests, and lint checks:

```bash
pytest tests/components/leeventus_ir -v
python -m unittest discover -s tests -v
ruff check .
```

The capture regression tests run by default against the committed, sanitized
DIB-J430R fixture. To additionally validate an original private Broadlink
export, set `TOILET_CODES_FILE`:

```bash
TOILET_CODES_FILE=/path/to/broadlink_remote_codes \
  python -m unittest discover -s tests -v
```

Original capture files may contain private Home Assistant data and should
remain local. Never commit them; only the sanitized fixture under
`tests/fixtures` belongs in the repository.

## Pull requests

- Keep each pull request focused on one change.
- Add regression tests for behavior changes and bug fixes.
- Keep the English and German translations synchronized (AI assistance is OK).
- Update the integration version for changes intended for release.
- Explain user-visible changes and any safety implications in the pull request.

Before changing the infrared protocol or adding a model, open an issue to
discuss the available protocol observations and how the model was verified.
