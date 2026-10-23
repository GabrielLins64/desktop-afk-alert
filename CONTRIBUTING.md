# Contributing

Issues and focused pull requests are welcome. Keep code, UI text, comments, and
documentation in English. Prefer small changes with a clear user benefit.

## Development

Follow the source setup in the [README](README.md). Use `uv sync --frozen`; update
`uv.lock` intentionally when changing dependencies. The privileged helper is a
separate installation: run `scripts/install-dev-helper.sh` after helper changes,
with protection disabled. Do not run the GUI as root.

The application uses PySide6 Widgets and Qt Multimedia. `app.py` coordinates
unprivileged services; `helper.py` owns input capture, PAM authentication, state,
and shutdown timing. See [architecture](docs/ARCHITECTURE.md) before changing the
helper protocol or authentication flow.

Do not add automated tests unless explicitly requested. Do not run linters or
formatters. Existing tests may be run when present. Use syntax/import checks,
normal builds, visual inspection, and the [manual validation guide](docs/VALIDATION.md).

## Pull requests

Describe the problem, resulting behavior, environments checked, and remaining
limitations. Include screenshots for visual changes. Never include passwords,
webhook URLs, bot tokens, private photos, or personal settings in a patch or log.

Keep network, camera, and user-file operations out of the privileged helper.
Retain bounded messages, fresh password authentication, seat-local capture, and
failure cleanup. A helper protocol change must update both sides and its protocol
version when incompatible.

## Releases

Update the version in `pyproject.toml` and `src/desktop_afk_alert/__init__.py`, then
refresh `uv.lock`. Keep `pkgver` in the root `PKGBUILD` in sync and reset `pkgrel`
to `1` for a new version; increment `pkgrel` for Arch packaging-only updates.
Validate the Arch package with `makepkg -sif` from the checkout root.
Build on Ubuntu 24.04 x86-64, complete the manual validation
matrix, and push a matching `vX.Y.Z` tag. Actions creates a draft release. Check
package installation, upgrade, removal, notices, and checksums before publishing.
