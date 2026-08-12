# Leeventus IR for Home Assistant

Leeventus IR lets Home Assistant control supported Leeventus toilets through a
compatible infrared emitter. Commands are generated from the selected settings,
so no learned Broadlink command storage is required.

> [!NOTE]
> The integration can operate wash, dry, and nozzle-cleaning functions. Ensure
> the selected IR emitter is aimed at the toilet and keep the **Stop** control
> available.

## Requirements

- Home Assistant 2026.6 or newer
- An `infrared.*` emitter entity, for example a Broadlink or ESPHome IR emitter

## Supported models

- Leeventus DIB-J430R

Optionally, an `infrared.*` receiver entity can be selected during setup or
**Reconfigure**. Valid signals from the physical remote then update every
integration entity without emitting an IR command. Invalid or unrelated IR
signals are ignored.

Only models whose infrared protocol has been verified are available during
setup.

## Entities

All entities are grouped under one Home Assistant device. Home Assistant
restores the last known settings after a restart.

| Domain | Entity | Range / behavior |
|---|---|---|
| `select` | Seat temperature | Off, levels 1–3 |
| `select` | Water temperature | Off, levels 1–3 |
| `select` | Eco | Off, automatic, comprehensive |
| `number` | Jet position | 1–5 |
| `number` | Water intensity | 1–5 |
| `number` | Dryer temperature | 1–5 |
| `switch` | Light | On/off |
| `sensor` | Last Home Assistant IR action | Last protocol action successfully sent by Home Assistant |
| `sensor` | Last IR receiver action | Last valid action received by the optional IR receiver |
| `binary_sensor` | Washing | Estimated active washing cycle |
| `binary_sensor` | Drying | Estimated active drying cycle |
| `sensor` | Washing until | Estimated washing-cycle end time |
| `sensor` | Drying until | Estimated drying-cycle end time |
| `sensor` | Current wash program | Estimated base program plus pulsing and oscillating modifiers |
| `event` | Received action | Fires for every valid physical-remote action; available only with a receiver |
| `button` | Wash | Sends normal-wash action |
| `button` | Female wash | Sends female-wash action |
| `button` | Intense wash | Sends intense-wash action |
| `switch` | Oscillating | Controls oscillation during an active wash program |
| `switch` | Pulsing | Controls pulsing during an active wash program |
| `button` | Dry | Sends dryer action |
| `button` | Stop | Sends stop action |
| `button` | Self-clean | Sends self-clean action |
| `button` | Apply settings | Sends the state without starting an action |

Changing a select, number, or the light switch immediately sends the complete
set of settings. Action buttons send their action together with those settings.
If the IR emitter reports an error, the unsuccessful change is not retained.

The pulsing and oscillation switches are modifiers for a running Wash, Female
wash, or Intense wash program. They remain off and do not transmit anything
while no wash is active. Setting a switch to its current state also sends
nothing. Oscillation repeats the active base program when its state must change;
pulsing sends the dedicated pulse action. Neither extends the estimated end
time, and both modifiers can be active together. A valid signal received from
the physical remote updates the switches. Starting a different base program,
Stop, Dry, Self-clean, or the wash timeout turns both switches off.

The action-history sensor reports the underlying IR protocol action. Therefore,
changing oscillation appears there as the repeated active base program, while
the stateful modifier switches and Current wash program sensor expose the
user-facing result.

Without an optional receiver, infrared is one-way and the entities use assumed
state. With a configured receiver, a recognized signal from the original
remote synchronizes the integration's settings. The two action-history sensors
retain their separate last values across Home Assistant restarts; the receiver
sensor remains unknown until it receives a valid frame. Received wash and dry
actions also update the activity estimates; Stop and Self-clean clear them,
while Apply settings preserves an already active estimate.
An exact receiver echo received within 500 ms of a frame just sent by Home
Assistant is ignored once, so a colocated receiver cannot apply the same
command twice or fire a false physical-remote event. A second matching frame
and every non-matching frame are always processed normally.

The received-action event supports `apply`, `stop`, `wash`, `female_wash`,
`intense_wash`, `dry`, `pulse_wash`, and `self_clean`. Unlike a last-action
sensor, it fires again when the same remote button is received repeatedly, so
it is the preferred automation trigger. It becomes unavailable together with
the selected receiver and reconnects automatically when the receiver returns.

## Limitations

- The toilet does not provide a status channel. Without an IR receiver, Home
  Assistant can only show the last state it sent.
- The modifier switches represent the integration's best estimate, not feedback
  from the toilet. If the toilet misses a transmitted command or the receiver
  misses a physical-remote command, their displayed state can temporarily be
  wrong. Stop or starting a different wash program resets both modifiers to a
  known off state.
- Only the models listed under **Supported models** have verified protocol
  support. Do not use the integration with another model unless its protocol
  has been independently verified.
- Washing and drying states are time estimates derived from successful sends
  and valid received frames, not direct operating feedback from the toilet.

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

Select the `infrared.*` emitter aimed at the toilet. The receiver is optional;
select it only when an IR receiver is also pointed at the original remote.

## Safe first test

1. Add the integration and select the correct IR emitter.
2. Press **Stop**.
3. Change a non-water setting, such as the light.
4. Verify the toilet reacts to setting changes.
5. Test wash and dry actions only after the stop path has been confirmed.

## Troubleshooting

### The integration cannot be added

Leeventus IR requires at least one `infrared.*` emitter entity. Configure a
compatible Broadlink, ESPHome, ZHA, or other infrared provider first, then
reload Home Assistant and try adding the integration again.

### The toilet does not react

1. Confirm that the selected emitter is available in Home Assistant.
2. Reconfigure Leeventus IR and verify that the correct emitter is selected.
3. Check the emitter's line of sight and distance to the toilet's IR receiver.
4. Use **Stop** as the first supervised test command.
5. Review the Home Assistant logs and download the integration diagnostics
   from **Settings → Devices & services → Leeventus IR**.

Do not repeatedly test wash, dry, or temperature functions while diagnosing a
connection problem. A transmitter can report an error even if a partial signal
has already reached the toilet, so keep the physical remote available.

### State differs from the physical remote

Without a configured receiver, state is optimistic and can differ when the
physical remote is used or an IR command is missed. Configure a compatible
`infrared.*` receiver and point it at the remote and toilet, or send **Stop**
and then **Apply settings** to establish a known state.

### Receiver events are missing

Verify that the configured receiver entity is available and receives raw IR
signals. Leeventus IR intentionally ignores invalid frames and one exact echo
of a command it has just transmitted. Enable debug logging for
`custom_components.leeventus_ir` when collecting diagnostics, but review logs
for private information before sharing them.

## Removal

1. Open **Settings → Devices & services → Leeventus IR** and delete every
   Leeventus IR config entry. This also removes its persisted optimistic state.
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
