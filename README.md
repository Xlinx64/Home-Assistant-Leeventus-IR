# Leeventus IR for Home Assistant

Leeventus IR lets Home Assistant control supported Leeventus toilets through a
compatible infrared emitter. An optional infrared receiver can synchronize
Home Assistant when the physical remote is used. The integration generates
commands directly from the selected settings, so individual remote-control
commands do not need to be learned or stored first.

> [!NOTE]
> The integration can operate wash, dry, and nozzle-cleaning functions. Ensure
> the selected IR emitter is aimed at the toilet and keep the **Stop** control
> available.

## Requirements

- Home Assistant 2026.6 or newer
- An `infrared.*` emitter entity, for example a Broadlink or ESPHome IR emitter

## Supported models

- Leeventus DIB-J430R

Only models whose infrared protocol has been verified are available during
setup.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Add `https://github.com/Xlinx64/Home-Assistant-Leeventus-IR` as a custom
   repository of type **Integration**.
3. Install **Leeventus IR** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Leeventus IR**.

### Manual

Copy `custom_components/leeventus_ir` to:

```text
/config/custom_components/leeventus_ir
```

Restart Home Assistant. Then open:

```text
Settings → Devices & services → Add integration → Leeventus IR
```

## Setup

Select the `infrared.*` emitter aimed at the toilet. You can also select an
optional receiver that can receive signals from the physical remote and the IR
emitter. You can change either selection later through **Reconfigure**.

Without a receiver, Home Assistant shows the last state it sent. With a
receiver, commands from the physical remote can update the displayed settings.

## Safe first test

1. Add the integration and select the correct IR emitter.
2. Press **Stop**.
3. Change a non-water setting, such as the light.
4. Verify that the toilet reacts to the setting change.
5. Keep **Stop** available when testing wash and dry actions.

## Everyday use

All entities are grouped under one Home Assistant device. The main controls
and sensors are:

| Group | Included entities |
|---|---|
| Settings | Seat and water temperature, eco mode, jet position, water intensity, dryer temperature, and light |
| Wash controls | Wash, Female wash, Intense wash, Pulsing, and Oscillating |
| Other actions | Dry, Stop, Self-clean, and Apply settings |
| Activity | Washing, Drying, their estimated end times, and Current wash program |
| History and receiver | Last sent action, last received action, and Received action event |

Changing a setting sends the complete set of selected settings immediately.
Action buttons send their action together with those settings. **Apply
settings** resends the selected settings without starting wash or dry. If the
IR emitter reports an error, Home Assistant keeps the previous setting.

**Pulsing** and **Oscillating** modify an active wash program. They can be used
together and return to off when the wash ends or another main action starts.

For the complete entity list, automation events, and exact state behavior, see
[Entity and behavior reference](docs/entity-and-behavior-reference.md).

## Optional IR receiver

A receiver lets the integration recognize valid commands from the physical
remote and update Home Assistant without sending another IR command. Invalid
or unrelated signals are ignored.

The **Received action** event is the recommended automation trigger for remote
button presses because it also fires when the same button is pressed repeatedly.

## Limitations

- The toilet does not report its actual status. Without a receiver, Home
  Assistant can only show the last state it sent.
- Washing and drying states are time estimates, not direct feedback from the
  toilet.
- If the toilet or receiver misses an IR command, the displayed state can
  temporarily differ from the toilet.
- Do not use the integration with an unlisted model unless its infrared
  protocol has been independently verified.

## Troubleshooting

### The integration cannot be added

Leeventus IR requires at least one `infrared.*` emitter entity. Configure a
compatible Broadlink, ESPHome, ZHA, or other infrared provider first, then
reload Home Assistant and try adding the integration again.

## Removal

1. Open **Settings → Devices & services → Leeventus IR** and delete every
   Leeventus IR config entry. This also removes its saved state.
2. If installed through HACS, uninstall **Leeventus IR** in HACS. For a manual
   installation, delete `/config/custom_components/leeventus_ir`.
3. Restart Home Assistant.

Removing the integration does not modify the selected infrared provider or
its entities.

## Contributing

Bug reports and contributions are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and test commands.

## Development

This project is developed with assistance from AI coding tools, including
OpenAI Codex. AI-assisted changes are reviewed by the maintainer and must pass
the same tests, linting, and security checks as manually written changes. The
maintainer remains responsible for the project's design, correctness,
licensing, and releases.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

This project is not affiliated with or endorsed by Leeventus. Use it at your
own risk. To the maximum extent permitted by law, the author is not liable for
personal injury, property damage, or other loss arising from use of the
integration, including from incorrect temperature or other settings. The
Leeventus name and artwork belong to their respective owner.
