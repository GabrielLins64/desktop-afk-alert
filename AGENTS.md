# Project instructions

- Do not create automated tests unless explicitly requested.
- Do not run linters or formatters. Existing tests may be run for validation.
- Keep code, interface text, comments, and documentation in English.
- Keep camera, networking, and user-file operations out of the privileged helper.
- Fix missing native dependencies in `scripts/install-deps.sh`, the shared installer
  used by local setup, `packaging/Containerfile`, and `.github/workflows/build.yml`.
  Do not treat an error message or a manual package-install command as the fix.
- Keep dependency troubleshooting, the README setup commands, and contribution
  instructions aligned with the installer. Python dependencies belong in
  `pyproject.toml` and `uv.lock`; Arch dependencies belong in `PKGBUILD`.
- Preserve Fedora's `libatomic-static` build dependency: Nuitka reads the
  `-l:libatomic.a` requirement from uv-managed Python's `MODLIBS`. The shared
  `libatomic.so` library does not satisfy that requirement. Do not work around it
  by renaming libraries, creating fake archives, or patching the Python installation.
- Validate dependency changes with the shared installer and the affected build
  in disposable containers when available. Report any unverified distributions
  or builds; do not claim that an early prerequisite check proves compilation.
