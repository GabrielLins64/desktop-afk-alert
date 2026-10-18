#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if [[ "$EUID" -eq 0 ]]; then
    echo 'Run this script as your normal user. It requests sudo only for installation.' >&2
    exit 1
fi

/usr/bin/python3 -I scripts/install_helper.py --check
uv build --wheel
mkdir -p build
uv export --frozen --only-group helper --no-emit-project --no-hashes --output-file build/helper-requirements.txt
version="$(uv run --no-sync python -c 'from desktop_afk_alert import __version__; print(__version__)')"
sudo -- /usr/bin/python3 -I scripts/install_helper.py \
    "$project_dir/dist/desktop_afk_alert-${version}-py3-none-any.whl" \
    "$project_dir/build/helper-requirements.txt"
