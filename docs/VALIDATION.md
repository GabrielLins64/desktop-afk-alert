# Manual validation

Use disposable desktop VMs for exclusive input capture and shutdown checks. Keep
the VM console available for recovery. Never validate actual shutdown on a work
machine. Use your own test webhook and bot destinations for alert delivery.

## Release matrix

Record the distribution, desktop, session type, package version, and outcome for
each run. An implementation target is not a verified compatibility claim.

| Environment | Full activation/release | Monitor/device changes | Camera/alerts | Package lifecycle |
| --- | --- | --- | --- | --- |
| Ubuntu 24.04+, GNOME, X11 | Pending | Pending | Pending | Container checks passed |
| Ubuntu 24.04+, GNOME, Wayland | Pending | Pending | Pending | Container checks passed |
| Fedora 41+, KDE, X11 | Pending | Pending | Pending | Container checks passed |
| Fedora 41+, KDE, Wayland | Pending | Pending | Pending | Container checks passed |

## Checks completed for 0.1.0

- Source wheel and source archive builds, Python syntax/import checks, and shell
  syntax checks passed. No automated tests, linters, or formatters were added or run.
- The settings, warning, and authentication surfaces were rendered and visually
  inspected. GUI startup also passed with Qt's offscreen backend in clean Ubuntu
  24.04 and Fedora 41 containers, without a checkout or development environment.
- `.deb` and `.rpm` dependency resolution, installation, local package-revision
  upgrade, reinstallation, and removal were exercised. User configuration markers
  survived removal. Required shared-library dependencies were checked.
- Correct and incorrect passwords were accepted/rejected by the real `sudo` PAM
  service using a temporary Ubuntu container account. The source helper installer
  and its relocated, root-owned Python environment were also exercised.
- On Fedora 41, the source installer detected missing system Python headers,
  compiler, and Linux input headers before installation. After installing the
  suggested packages, `evdev` compiled and the installed helper launched successfully.
- On the GNOME/X11 development host, read-only diagnostics identified the
  Brazilian keyboard layout and camera. Desktop idle/suspend inhibition was
  acquired and released without activating protection.
- A real UVC camera capture was exercised with warning windows on a virtual X11
  display, without input grabs or shutdown. The JPEG was saved with mode `0600`
  and displayed while the interface stayed in `FROZEN`. Waiting two seconds after
  the first frame increased mean image luminance from 3.5 to 29.0 (0–255) in a
  local comparison; lighting and camera results vary.
  Force-stopping the camera worker also left the warning visible in `FROZEN`
  and reported a photo failure without stopping the interface.
- Discord text and synthetic-image delivery passed against an explicitly
  authorized webhook from the GUI's background delivery flow (HTTP 200).
  First-use TLS initialization in the delivery thread reproduced an `SSLError`;
  creating and reusing the verified TLS context on the GUI thread resolved it.
  A refused local connection exercised all three attempts while the warning
  remained visible without delivery notices. Console/file logging, URL/token
  redaction, log rotation, and `0600` file/backup permissions were checked.
- The **Freeze cursor** control was visually checked, including its off default,
  saved on value, and off fallback for older settings. Motion filtering was
  inspected with synthetic mouse/touchpad events: only relative movement and
  synchronization were emitted, and pending movement was discarded on freezing.
  No host input grabs or kernel uinput devices were used for these checks.

Containers were not given physical input devices, cameras, or desktop sessions.
These checks do not validate exclusive capture, Wayland stacking, monitor/device
changes, Telegram delivery, or shutdown. The pending desktop VM scenarios
above must be completed before claiming a fully validated release.

## Scenarios

- Open the GUI at normal and small window sizes. Check scrolling, the fixed
  footer, focus indicators, disabled shutdown delay, and conditional settings.
- Check blank/default and custom warning messages. Confirm uppercase rendering,
  readable wrapping, photo aspect ratio, and coverage of every monitor, including
  mixed scaling, primary-screen changes, monitor removal, and monitor addition.
- Reject incorrect activation passwords. Confirm countdown starts only after
  fresh authentication, including with cached or NOPASSWD sudo authorization.
  Cancel countdown and confirm input was never left grabbed.
- Arm, move the mouse, and scroll: no incident. Release an unexpected key or
  press a mouse button: one incident, with no action in underlying applications.
  Check media keys and the pointer devices available on the target hardware.
- Check **Freeze cursor**, initially off, with mouse and touchpad movement on
  X11 and Wayland. Movement must work only in `ARMED` with the switch off; clicks
  and scrolling must not reach underlying applications. Check that movement stops
  immediately in `FROZEN`/`AUTHENTICATING`, and resumes after cancelling password
  entry back to `ARMED`. Check hotplug and virtual-device cleanup. With `/dev/uinput`
  unavailable or another seat selected, activation must give an actionable error
  unless **Freeze cursor** is on. These kernel/compositor scenarios remain pending.
- Record one-, two-, and three-key shortcuts; check modifier equivalence, partial
  presses while assembling a chord, held-key repeats, and consumed releases.
- Release from both armed and frozen states. Check correct, wrong, empty, and
  cancelled passwords, repeated attempts, Backspace/Delete/cursor editing, Caps
  Lock, Num Lock, US and Brazilian layouts, AltGr, and composed characters.
- Confirm shutdown pauses while password entry is open, resumes its remaining
  duration on cancellation/failure, and is cancelled after success. Validate
  actual normal shutdown once inside a disposable VM. A rejected shutdown must
  leave the warning visible without repeated poweroff requests.
- Connect/disconnect keyboards and pointers. Check held keys during activation,
  device contention, lost input synchronization, and all-keyboard removal.
- Force-stop the GUI and then the helper in separate runs. Check input recovery
  within the heartbeat limit, no pending shutdown, and no persistent root process.
  Also check session locking, switching, portal loss, and display disconnection.
- Capture a camera photo. Check its private permissions and unique name. Repeat
  with a busy/disconnected camera and an unwritable directory: protection and
  text-only notifications must continue without waiting indefinitely.
- Check Discord, Telegram, and both together, with and without photos. Verify
  long messages, disabled Discord mentions, invalid credentials, offline
  connections, rate limits, retries, and independent provider failures.
- Save/reopen settings and credentials. Check locked/unavailable keyrings and
  current-run-only credentials. Verify no credentials or sudo passwords appear
  in settings, logs, or process arguments.
- Install, launch, upgrade, and uninstall `.deb` and `.rpm` packages. Confirm
  root ownership, desktop launcher/icon, helper lookup, preserved user data, and
  successful launch without a development checkout or Python environment.
