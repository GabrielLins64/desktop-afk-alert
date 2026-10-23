#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
container_engine="${CONTAINER_ENGINE:-podman}"
image_name=localhost/desktop-afk-alert-builder:0.1.0
"$container_engine" build --file packaging/Containerfile --tag "$image_name" .
container_id="$("$container_engine" create "$image_name")"
trap '"$container_engine" rm "$container_id" >/dev/null' EXIT
mkdir -p dist build/gui build/helper
"$container_engine" cp "$container_id:/workspace/dist/." dist/
export_dir="$(mktemp -d build/export.XXXXXX)"
mkdir -p "$export_dir/gui" "$export_dir/helper"
"$container_engine" cp "$container_id:/workspace/build/gui/gui_entry.dist" "$export_dir/gui/"
"$container_engine" cp "$container_id:/workspace/build/helper/helper_entry.dist" "$export_dir/helper/"
if [[ -e build/gui/gui_entry.dist ]]; then
    mv build/gui/gui_entry.dist "$export_dir/previous-gui.dist"
fi
if [[ -e build/helper/helper_entry.dist ]]; then
    mv build/helper/helper_entry.dist "$export_dir/previous-helper.dist"
fi
mv "$export_dir/gui/gui_entry.dist" build/gui/
mv "$export_dir/helper/helper_entry.dist" build/helper/
echo "Previous standalone directories are preserved under $export_dir."
echo 'Ubuntu 22.04 standalone builds and packages are ready in build/ and dist/.'
