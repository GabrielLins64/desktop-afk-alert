# desktop-afk-alert

Keep your desktop visible. Warn unexpected visitors.

Sometimes you want to leave your computer without locking the screen: a dashboard,
a video, or a long-running task should remain visible. Desktop AFK Alert watches
for unexpected keyboard or mouse input and puts a clear warning across every
monitor when someone interacts with your desktop.

A Python and Qt application with a Matrix-inspired interface, optional camera
snapshots, Discord and Telegram alerts, and optional automatic shutdown.

![Desktop AFK Alert settings](docs/images/settings.png)

## Install

Download the x86-64 `.deb` or `.rpm` from [Releases](../../releases). Packages include
the GUI, its Python runtime, and an isolated privileged helper.

```bash
# Ubuntu 24.04+ / compatible Debian-based distributions
sudo apt install ./desktop-afk-alert_0.1.0-1_amd64.deb

# Fedora 41+
sudo dnf install ./desktop-afk-alert-0.1.0-1.x86_64.rpm
```

Use the filename of the release you downloaded. Open **Desktop AFK Alert** from
your application menu, or run `desktop-afk-alert` as your normal user.

The initial targets are GNOME and KDE, using native X11 or Wayland, on Linux with
glibc 2.39 or later. An active local desktop session, `sudo` privileges, and a
password-based account are required. A Secret Service keyring is needed to
remember alert credentials. See [validation status](docs/VALIDATION.md) for the
environments actually checked before treating a build as release-ready.

## Use

1. Set the warning message, or leave it blank for the default.
2. Keep or record a release shortcut with **1–3 simultaneous keys**. The default
   is **Ctrl+K**; left and right modifier keys are equivalent.
3. Optionally enable shutdown, a camera photo, Discord, or Telegram.
4. Click **Activate**, enter your sudo password, and step away during the startup
   countdown. The default delay is **5 seconds**.
5. To return, press the release shortcut and enter your sudo password again.

While armed, the desktop stays visible. An unexpected key release or mouse
button press triggers the warning. Mouse movement and scrolling do not trigger
it. Captured input is consumed, so it cannot operate the applications underneath.
Ordinary close requests and desktop exit shortcuts are ignored during protection.

The warning covers every connected monitor, uses uppercase green text on black,
and includes the camera photo if enabled. Each incident takes one photo and
dispatches alerts once per enabled provider; transient delivery failures have
bounded retries. Alerts are sent only to the configured Discord and Telegram
destinations.

Shutdown is off by default. When enabled, its default delay is **60 seconds** from
the incident. Opening password entry **pauses** the remaining time, including
while you type. Cancelling or submitting an incorrect password returns to the
previous state and resumes the countdown. Correct authentication cancels it.
An operating-system shutdown request already issued at expiry cannot be recalled.
Opening password entry therefore lets anyone who knows the shortcut postpone
shutdown while that dialogue remains open.

### Camera and alerts

- **Camera:** select a device and a writable directory. Photos default to your
  system Pictures directory under `desktop-afk-alert/`. Camera access starts only
  after an incident and is limited to five seconds, including a two-second warmup
  after the first video frame so automatic exposure can settle. Capture runs in a
  separate user process; camera failures leave the warning screen active. The
  saved photo appears beneath the warning on every monitor. If capture fails,
  protection continues and alerts are sent without a photo.
- **Discord:** create a webhook in the destination text channel's integrations
  settings, then paste its URL. Forum/media channels require a webhook URL that
  already includes the destination `thread_id` query parameter. Mentions are
  disabled.
- **Telegram:** create a bot with [BotFather](https://t.me/BotFather), paste its
  token and destination chat ID, and start a conversation with the bot or add it
  to the destination group. The bot must be allowed to send messages and photos.

Network delivery is best effort. A short shutdown delay can end the session
before photo capture or delivery finishes.

Settings are saved on activation and normal exit to
`$XDG_CONFIG_HOME/desktop-afk-alert/settings.json`, defaulting to
`~/.config/desktop-afk-alert/settings.json`. Webhook URLs and bot tokens go into
the system keyring. If the keyring is unavailable, newly entered credentials stay
in memory for the current run. Sudo passwords are never saved. Photos and new
settings files are private to your user.

### Logs

Application and notification results are written to the console and
`~/.local/state/desktop-afk-alert/logs/desktop-afk-alert.log`. If `XDG_STATE_HOME`
is set, it replaces `~/.local/state`. Logs are private to your user and rotate at
1 MiB, keeping three backups. If the file cannot be opened, console logging
continues.

Delivery failures stay in the logs and do not appear on the frozen screen. Logs
include the provider, incident ID, HTTP status/error code, and retry attempts;
webhook URLs, bot tokens, passwords, and notification bodies are excluded.
`--diagnose` also reports the log file location.

## Run from source

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/),
then install the native libraries and compiler:

```bash
# Ubuntu 24.04
sudo apt install python3-dev python3-venv build-essential linux-libc-dev libffi-dev libwayland-dev \
  libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-shape0 libxrandr2 libegl1 libgl1 libdbus-1-3 \
  libasound2t64 libgssapi-krb5-2 xdg-desktop-portal

# Fedora
sudo dnf install python3-devel python3-pip gcc kernel-headers libffi-devel wayland-devel \
  libxkbcommon libxkbcommon-x11 xcb-util-cursor mesa-libGL mesa-libEGL \
  dbus-libs krb5-libs libXrandr xdg-desktop-portal
```

From the checkout:

```bash
uv sync --frozen
scripts/install-dev-helper.sh
uv run desktop-afk-alert
```

The helper installer asks for sudo and copies the wheel and only its two helper
dependencies into root-owned storage under `/usr/local`. It uses `/usr/bin/python3`,
which also needs to be Python 3.11+, and checks its development headers and compiler
before requesting sudo. Installing Python through uv does not provide the system
headers needed to compile `evdev`. It does not import the
checkout as root. Re-run it after changing helper code. Distribution packages use
`/usr/libexec/desktop-afk-alert-helper` and take precedence over a development
helper. Disarm and close the application before replacing either installation.

To inspect your environment without activating protection:

```bash
uv run desktop-afk-alert --diagnose
```

The GUI opens without an installed helper; activation requires one.

## Build releases

Use Ubuntu 24.04 x86-64 for the glibc baseline. Install the source dependencies,
`patchelf`, and [nFPM](https://nfpm.goreleaser.com/docs/install/), then:

```bash
scripts/build.sh
scripts/package.sh
```

Alternatively, build in an isolated Ubuntu 24.04 container using Podman:

```bash
scripts/build-container.sh
```

Set `CONTAINER_ENGINE=docker` to use Docker. The build container has no access to
your input devices, camera, credentials, or desktop session. A native Fedora
build using uv-managed Python may additionally need `libatomic-static`.

Nuitka produces separate standalone GUI and helper directories under `build/`.
nFPM writes `.deb`, `.rpm`, and `SHA256SUMS` files under `dist/`. Dependencies are
locked in `uv.lock`. `BUILD_JOBS=4 scripts/build.sh` changes compilation parallelism.

The GitHub Actions workflow builds packages on manual dispatch. A `v0.1.0`-style
tag matching the package version also creates a **draft** release with both
installers and checksums. Review the manual validation matrix before publishing.

## Troubleshooting and limits

- **An alert was not delivered:** check the log file above. Connection failures
  include their error type; provider rejections include HTTP and API error codes.
  For Discord, check that the webhook still exists and has access to the channel.
  Forum/media channels also need a `thread_id` in the webhook URL. Delivery uses
  at most three attempts and never stops protection.
- **Helper installation reports missing `Python.h`:** install the headers for
  `/usr/bin/python3`: `sudo dnf install python3-devel` on Fedora, or
  `sudo apt install python3-dev` on Ubuntu. Then re-run
  `scripts/install-dev-helper.sh`. Headers from uv or another virtual environment
  cannot replace the system Python headers used by the helper.
- **Cannot activate:** run `--diagnose`; check that the helper is installed and
  the session is local, active, and unlocked. Install the matching GNOME or KDE
  desktop portal. The application refuses to arm when essential preflight checks
  fail.
- **Password fails:** use your own account password. PAM account restrictions
  apply. Passwordless-only, fingerprint-only, and multi-factor PAM configurations
  are not supported. Accounts using a different sudo target/root password policy
  are outside the initial support target.
  Password entry supports printable XKB characters; control-character passwords
  are rejected before activation.
- **Unexpected keyboard layout:** select an XKB keyboard source. Wayland with
  multiple sources requires GNOME or KDE's active-layout information; activation
  is refused when it cannot be determined. IBus/IME password input is unsupported.
- **No saved credentials:** unlock the Secret Service keyring, or re-enter the
  credentials for this run. Plaintext storage is never used as a fallback.
- **Protection stops:** device-grab failures, session changes, lost desktop
  inhibition, and missing GUI heartbeats release input and cancel pending
  shutdown. Restore the cause and activate again.

This is a desktop interaction guard. Other programs running as your user,
administrative process termination, compositor-owned surfaces, system failures,
new-device capture races, remote/synthetic input that bypasses captured devices,
and physical power controls remain outside its guarantee. Wayland compositors
control window stacking; fullscreen windows cannot provide a universal compositor
security boundary. A session lock remains appropriate when that boundary is
required. The app never changes sudoers, starts at login, or runs a persistent
system service.

Uninstall with `sudo apt remove desktop-afk-alert` or
`sudo dnf remove desktop-afk-alert`. User settings, keyring entries, and photos
remain yours. For a source-only helper, remove
`/usr/local/libexec/desktop-afk-alert-helper` and
`/usr/local/lib/desktop-afk-alert-helper` after disarming and closing the app.

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md) for development and manual validation.
The application is [MIT licensed](LICENSE); bundled dependencies retain their
own licenses. The visual theme uses the community [Matrix reference palette](https://www.colorspalette.org/color-scheme/matrix-code-green-color)
with a teal accent and original artwork.
