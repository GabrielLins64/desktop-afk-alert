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

## Native dependencies

Run `scripts/install-deps.sh` before source setup or standalone compilation on
Ubuntu, Debian, or Fedora. Use `--dry-run` to inspect its package-manager commands.
The installer is the single source for native source/build dependencies; the
Ubuntu release container and GitHub Actions call it directly. uv and nFPM remain
separate tool installations. Arch source packages declare their dependencies in
`PKGBUILD`; Python dependencies belong in `pyproject.toml` and `uv.lock`.

When a missing header, library, or compiler breaks setup or compilation, identify
the distribution package and update the shared installer in the same change.
Keep the README, relevant error messages, and validation notes aligned. A clearer
error or a manual package-install instruction alone does not fix provisioning.
Keep distribution package lists out of the workflow and Containerfile.

For `cannot find -l:libatomic.a`, retain `libatomic-static` in Fedora's package
list. Nuitka reads `-l:libatomic.a` from uv-managed Python's `MODLIBS`; the
installed shared `libatomic.so` cannot satisfy this explicit archive request.
On Ubuntu and Debian, `build-essential` pulls in GCC's development libraries.
Do not rename a shared library to `.a`, create fake archives, or edit the managed
Python installation to bypass the requirement.

Validate package installation in disposable containers for affected distributions,
rerun the installer to check repeatability, and compile the affected target. Use
the real installer and build scripts; do not add automated tests unless requested.
Record completed checks and pending coverage in [validation](docs/VALIDATION.md).

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
Build on Ubuntu 22.04 x86-64 (glibc 2.35), complete the manual validation
matrix, and push a matching `vX.Y.Z` tag. Actions creates a draft release. Check
package installation, upgrade, removal, notices, and checksums before publishing.
