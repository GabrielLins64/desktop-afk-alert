# Manual validation

Use disposable desktop VMs for exclusive input capture and shutdown checks. Keep
the VM console available for recovery. Never validate actual shutdown on a work
machine. Use your own test webhook and bot destinations for alert delivery.

## Release matrix

Record the distribution, desktop, session type, package version, and outcome for
each run. An implementation target is not a verified compatibility claim.

| Environment | Full activation/release | Monitor/device changes | Camera/alerts | Package lifecycle |
| --- | --- | --- | --- | --- |
| Ubuntu 22.04, GNOME, X11 | Pending | Pending | Pending | Pending |
| Ubuntu 22.04, GNOME, Wayland | Pending | Pending | Pending | Pending |
| Ubuntu 24.04+, GNOME, X11 | Pending | Pending | Pending | Container checks passed |
| Ubuntu 24.04+, GNOME, Wayland | Pending | Pending | Pending | Container checks passed |
| Fedora 41+, KDE, X11 | Pending | Pending | Pending | Container checks passed |
| Fedora 41+, KDE, Wayland | Pending | Pending | Pending | Container checks passed |
| Arch Linux rolling, GNOME/KDE, X11/Wayland | Pending | Pending | Pending | Container checks passed |

## Checks completed for 0.1.1-2

- Reproduced the installed `0.1.1-1` startup failure on Ubuntu 22.04.5 with glibc
  2.35: the GUI and helper required `GLIBC_2.38`, and the package depended on glibc
  2.39 and the Ubuntu 24.04-only `libglib2.0-0t64` package.
- Built both standalone applications and the `.deb`/`.rpm` packages in the Ubuntu
  22.04 container with managed Python 3.11.13. All 99 bundled ELF files required
  at most glibc 2.34; the package declares the build baseline of glibc 2.35.
  Both the GUI's `--version` and the helper's `--help` succeeded on Ubuntu 22.04.
- GUI startup passed with Qt's offscreen backend on Ubuntu 22.04. The application
  remained in its event loop until the eight-second validation timeout, with
  isolated settings and no activation, camera capture, or notification delivery.
- An APT simulation using `--fix-broken` accepted the local `.deb` as a direct
  upgrade from the unpacked `0.1.1-1` installation, with no additional packages
  installed or removed. The simulation without that flag refused to proceed
  because of the previous package's unmet dependencies.
- Package metadata, root ownership and executable modes of both binaries and
  launchers, both package checksums, shell syntax, and workflow/package YAML
  parsing passed. No automated tests, linters, or formatters were added or run.

Actual package installation, clean Ubuntu 22.04/24.04 package lifecycle checks,
and application-menu startup on X11/Wayland remain pending for this revision.
The container lifecycle results below describe earlier builds.

## Checks completed for 0.1.0

- Source wheel and source archive builds, Python syntax/import checks, and shell
  syntax checks passed. No automated tests, linters, or formatters were added or run.
- The settings, warning, and authentication surfaces were rendered and visually
  inspected. GUI startup also passed with Qt's offscreen backend in clean Ubuntu
  24.04 and Fedora 41 containers, without a checkout or development environment.
- `.deb` and `.rpm` dependency resolution, installation, local package-revision
  upgrade, reinstallation, and removal were exercised. User configuration markers
  survived removal. Required shared-library dependencies were checked.
- On a clean Arch Linux container, `makepkg -sif --noconfirm` installed the
  dependencies, built the local checkout, and installed the resulting package.
  The installed GUI started with Qt's offscreen backend outside the checkout;
  the helper launcher, lookup, icon, root ownership, removal, and reinstallation
  were checked. A user configuration marker survived removal. Clean builds with
  `makepkg -C` and a custom `BUILDDIR` preserved the checkout's `src/` directory.
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
- On the Arch Linux development host, a black-camera regression was traced to
  Qt's V4L2 exposure setters leaving the UVC camera in manual mode at its minimum
  exposure time. After removing those calls and restoring the device's automatic
  exposure once, three local captures with system Qt 6.12.0 and two with Qt 6.8.3
  produced nonblack `0600` JPEGs. Workers exited normally, automatic exposure
  remained enabled, and a separate FFmpeg capture succeeded without rebooting.
  An unavailable camera and an unwritable photo directory returned bounded
  text-only failures through the normal worker completion flow.
  Temporary photos were removed. The Qt 6.8.3 run used an isolated Python 3.12
  environment on Arch; it does not replace a Fedora desktop validation run.
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
  On V4L2 cameras, compare exposure mode/time before and after capture: automatic
  exposure must stay enabled if it was enabled initially. Repeat captures, then
  open the camera in another application without rebooting. Check that the worker
  exits normally after releasing the camera, rather than being killed on success.
- Check Discord, Telegram, and both together, with and without photos. Verify
  long messages, disabled Discord mentions, invalid credentials, offline
  connections, rate limits, retries, and independent provider failures.
- Save/reopen settings and credentials. Check locked/unavailable keyrings and
  current-run-only credentials. Verify no credentials or sudo passwords appear
  in settings, logs, or process arguments.
- Install, launch, upgrade, and uninstall `.deb`, `.rpm`, and Arch packages. Confirm
  root ownership, desktop launcher/icon, helper lookup, preserved user data, and
  successful launch without a development checkout or Python environment.
