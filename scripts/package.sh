#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

nfpm_command="${NFPM_BIN:-nfpm}"
if ! command -v "$nfpm_command" >/dev/null; then
    echo 'Install nFPM first: https://nfpm.goreleaser.com/docs/install/' >&2
    exit 1
fi
if [[ ! -x build/gui/gui_entry.dist/desktop-afk-alert.bin || ! -x build/helper/helper_entry.dist/desktop-afk-alert-helper.bin ]]; then
    echo 'Build both standalone applications with scripts/build.sh first.' >&2
    exit 1
fi

VERSION="$(uv run --no-sync python -c 'from desktop_afk_alert import __version__; print(__version__)')"
export VERSION
mkdir -p dist
"$nfpm_command" package --config packaging/nfpm.yaml --packager deb --target dist/
"$nfpm_command" package --config packaging/nfpm.yaml --packager rpm --target dist/
(cd dist && sha256sum ./*.deb ./*.rpm > SHA256SUMS)
