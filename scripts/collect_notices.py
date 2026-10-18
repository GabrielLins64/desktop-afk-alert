"""Preserve upstream wheel notices alongside the standalone applications."""

import shutil
import sys
from importlib.metadata import distributions
from pathlib import Path

destination = Path(sys.argv[1]) / "third-party-licenses"
destination.mkdir(parents=True, exist_ok=True)
helper_only = "--helper" in sys.argv[2:]
excluded = {"desktop-afk-alert", "ordered-set", "zstandard", "patchelf"}
index = []
for item in distributions():
    name = item.metadata["Name"].lower().replace("_", "-")
    if name in excluded or helper_only and name not in {"evdev", "pyudev", "nuitka"}:
        continue
    index.append(f"{item.metadata['Name']} {item.version}")
    for entry in item.files or ():
        if not any(word in str(entry).lower() for word in ("license", "copying", "notice")):
            continue
        source = Path(item.locate_file(entry))
        if not source.is_file():
            continue
        parts = list(entry.parts)
        metadata_index = next((index for index, part in enumerate(parts) if part.endswith(".dist-info")), None)
        relative = Path(*parts[metadata_index + 1:]) if metadata_index is not None else Path(source.name)
        target = destination / name / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
(destination / "INDEX.txt").write_text("Upstream Python distributions; their original license notices are preserved here.\n\n" + "\n".join(sorted(index)) + "\n")
shutil.copyfile("LICENSE", Path(sys.argv[1]) / "LICENSE.desktop-afk-alert")
if not helper_only:
    shutil.copytree("third_party", destination / "native-libraries", dirs_exist_ok=True)
