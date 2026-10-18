# Architecture

The GUI always runs as the desktop user. A root-owned helper starts through sudo
for one protection session and exits after disarming, cancellation, or failure.
There is no background system service and no sudoers modification.

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Settings window | English form, validation, camera discovery, shortcut recording |
| Controller | Session preflight, helper transport, overlays, incident services |
| Native keyboard | Native XKB map and local password text/compose handling |
| Session inhibitor | Desktop portal request scoped to a dedicated bus connection |
| Helper | Authoritative state, exclusive device capture, PAM, monotonic deadlines |
| Camera and notifications | User-owned JPEGs and bounded provider requests |
| Application logs | Console and private rotating XDG state files; delivery results stay off warning windows |

The helper receives only protection delays, the cursor-freeze setting, and physical shortcut codes. It never
receives photo paths, webhook URLs, bot tokens, or commands to execute. Its shutdown
command is fixed. Authentication runs in a short-lived subprocess so PAM cannot
block input processing or heartbeat supervision.

## State and authentication

`IDLE → COUNTDOWN → ARMED → FROZEN`

The release shortcut enters `AUTHENTICATING` from `ARMED` or `FROZEN`. The helper
stores the preceding state and remaining shutdown time. Correct PAM authentication
releases protection after all keys/buttons are up. Cancellation or failure restores
the preceding state and resumes its remaining time.

Initial elevation uses sudo; an additional password-only PAM conversation with
the `sudo` service validates the initiating user's password before countdown.
This also covers cached or passwordless sudo authorization. Unlock repeats PAM
authentication for that same user. PAM success without a password challenge does
not count as password validation. Account restrictions are checked as well.

Messages are newline-delimited JSON with protocol version 2 and a 32 KiB limit.
Inherited stdin/stdout pipes are the only control channel. The root helper accepts
no unauthenticated disarm request. Keyboard events are translated inside the GUI
and never reinjected into the compositor. Passwords remain
transient; Python and Qt do not offer a guarantee that every temporary allocation
can be erased from process memory.

## Input and failure handling

pyudev selects keyboard and pointer devices from the initiating user's active
logind seat. evdev grabs every selected event device, and hotplug events update
capture. Wheel events are discarded. With `freeze_cursor=false` (the default), a
seat0 uinput pointer forwards only `REL_X`/`REL_Y` motion while `ARMED`. Physical
clicks and keyboard input stay grabbed. Touchpad contacts become relative mouse
motion; touch/button events are never forwarded, preventing synthesized desktop
taps. The virtual device is excluded from capture and closed on release/failure.
Motion is discarded in `FROZEN`/`AUTHENTICATING` or with cursor freezing enabled.
Keys trigger on release;
pointer buttons trigger on press. Key repeats do not trigger incidents. Shortcuts
use physical key codes and equivalent left/right modifiers.

All keys/buttons must be released before capture completes. Shortcut releases
and authentication control keys are consumed. The helper emits only the keyboard
events needed for local state/typing and incident metadata; it does not record a
key history. Device removal clears held-key state in both the helper and local
translator so disconnected keyboards cannot leave password modifiers stuck.

The GUI sends heartbeats every 750 ms. Five seconds without one, closed pipes,
lost session ownership/activity, a locked session, or capture failure closes all
device descriptors and cancels the helper's shutdown deadline. Closing the helper
also releases kernel grabs. Portal inhibition prevents ordinary idle/suspend
transitions; loss of that connection stops protection.

The overlay is a fullscreen application surface on each Qt screen, not a system
lock. Compositor-owned UI, other same-user processes, and remote/synthetic input
remain outside the application's boundary. Device hotplug cannot eliminate the
race before the newly discovered device is grabbed.
