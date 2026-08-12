# Entity and behavior reference

This reference describes the entities and exact state behavior of Leeventus IR.
For installation and normal use, see the [README](../README.md).

## Entities

All entities are grouped under one Home Assistant device. Home Assistant
restores the last known settings after a restart.

| Domain | Entity | Range or behavior |
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
| `button` | Apply settings | Resends the selected settings without starting wash or dry |

## Sending commands

Changing a select, number, or the light switch immediately sends the complete
set of settings. Action buttons send their action together with those settings.
If the IR emitter reports an error, the unsuccessful change is not retained.

## Wash modifiers

The pulsing and oscillation switches modify a running **Wash**, **Female wash**,
or **Intense wash** program.

- They remain off and transmit nothing while no wash is active.
- Setting a switch to its current state sends nothing.
- Oscillation repeats the active base program when its state changes.
- Pulsing sends the dedicated pulse action.
- Both modifiers can be active together.
- Neither modifier extends the estimated end time.
- A valid signal from the physical remote updates both switches.
- Starting a different base program, **Stop**, **Dry**, **Self-clean**, or the
  wash timeout turns both switches off.

The action-history sensor reports the underlying IR protocol action. Changing
oscillation therefore appears as the repeated active base program. The modifier
switches and **Current wash program** sensor show the user-facing result.

## Receiver and state synchronization

Without an optional receiver, infrared is one-way and entities show the last
state sent by Home Assistant. With a receiver, a recognized signal from the
physical remote synchronizes the integration's settings.

The two action-history sensors retain their separate last values across Home
Assistant restarts. The receiver sensor remains unknown until it receives a
valid frame.

Received wash and dry actions update the activity estimates. **Stop** and
**Self-clean** clear them. **Apply settings** does not interrupt an active wash
or dry estimate.

An exact receiver echo received within 500 ms of a frame just sent by Home
Assistant is ignored once. This prevents a colocated receiver from applying the
same command twice or firing a false physical-remote event. A second matching
frame and every non-matching frame are processed normally.

## Received action event

The event supports these action values:

- `apply`
- `stop`
- `wash`
- `female_wash`
- `intense_wash`
- `dry`
- `pulse_wash`
- `self_clean`

Unlike a last-action sensor, the event fires again when the same remote button
is received repeatedly, so it is the preferred automation trigger. It becomes
unavailable together with the selected receiver and reconnects automatically
when the receiver returns.

## State accuracy

- The modifier switches represent the integration's best estimate, not
  feedback from the toilet. If the toilet misses a transmitted command or the
  receiver misses a physical-remote command, their displayed state can
  temporarily be wrong. **Stop** or starting a different wash program resets
  both modifiers to off.
- Washing and drying states are time estimates derived from successful sends
  and valid received frames, not direct operating feedback from the toilet.
