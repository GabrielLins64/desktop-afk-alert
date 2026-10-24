#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if [[ "$(uname -m)" != x86_64 ]]; then
    echo 'Binary releases currently target x86-64 Linux.' >&2
    exit 1
fi

uv sync --frozen --group build --group helper

uv run --no-sync python - <<'PY'
import os
import shlex
import subprocess
import sysconfig
from pathlib import Path

if "-l:libatomic.a" in (sysconfig.get_config_var("MODLIBS") or "").split():
    compiler = shlex.split(os.environ.get("CC") or "gcc")
    try:
        archive = subprocess.check_output(
            [*compiler, "-print-file-name=libatomic.a"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Cannot check libatomic.a with {shlex.join(compiler)}: {error}")
    if archive == "libatomic.a" or not Path(archive).is_file():
        raise SystemExit(
            "Cannot build: this Python requires libatomic.a, but the C compiler cannot find it.\n"
            "Run scripts/install-deps.sh to install the native build dependencies,\n"
            "then re-run scripts/build.sh. For release builds, you can also use\n"
            "scripts/build-container.sh with the Ubuntu 22.04 toolchain."
        )
PY

mkdir -p build/helper build/gui dist
build_jobs="${BUILD_JOBS:-2}"

uv run --no-sync python -m nuitka \
    --mode=standalone \
    --output-dir=build/helper \
    --output-filename=desktop-afk-alert-helper.bin \
    --jobs="$build_jobs" \
    --assume-yes-for-downloads \
    --report=build/helper-report.xml \
    packaging/helper_entry.py

uv run --no-sync python scripts/collect_notices.py build/helper/helper_entry.dist --helper

if [[ "${1:-}" == --helper-only ]]; then
    echo 'Helper build: build/helper/helper_entry.dist/'
    exit 0
fi

uv run --no-sync python -m nuitka \
    --mode=standalone \
    --output-dir=build/gui \
    --output-filename=desktop-afk-alert.bin \
    --enable-plugin=pyside6 \
    --include-qt-plugins=platforms,imageformats,multimedia,iconengines,platforminputcontexts,wayland-shell-integration,wayland-decoration-client,wayland-graphics-integration-client,xcbglintegrations \
    --noinclude-qt-plugins=platformthemes,printsupport,egldeviceintegrations \
    --include-package=pywayland.protocol.wayland \
    --include-module=keyring.backends.SecretService \
    --include-data-files=resources/desktop-afk-alert.svg=desktop_afk_alert/icon.svg \
    --noinclude-qt-translations \
    --jobs="$build_jobs" \
    --assume-yes-for-downloads \
    --report=build/gui-report.xml \
    packaging/gui_entry.py

if [[ -f build/gui/gui_entry.dist/PySide6/qt-plugins/imageformats/libqpdf.so ]]; then
    excluded_plugins="$(mktemp -d build/excluded-plugins.XXXXXX)"
    mv build/gui/gui_entry.dist/PySide6/qt-plugins/imageformats/libqpdf.so "$excluded_plugins/"
fi
uv run --no-sync python scripts/collect_notices.py build/gui/gui_entry.dist

echo 'GUI build: build/gui/gui_entry.dist/'
echo 'Helper build: build/helper/helper_entry.dist/'
