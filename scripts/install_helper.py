"""Install a development helper into root-owned storage; never import the checkout as root."""

import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main():
    if os.geteuid() != 0 or len(sys.argv) != 3:
        raise SystemExit("Use scripts/install-dev-helper.sh as your normal user.")
    wheel, requirements = map(lambda value: Path(value).resolve(strict=True), sys.argv[1:])
    if wheel.suffix != ".whl" or not requirements.is_file():
        raise SystemExit("A wheel and locked helper requirements are required.")
    os.umask(0o022)
    destination = Path("/usr/local/lib/desktop-afk-alert-helper")
    if destination.exists():
        info = destination.lstat()
        if destination.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise SystemExit("The existing helper directory is not safe to update.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="desktop-afk-helper-", dir="/usr/local/lib") as staging:
        root_stage = Path(staging)
        copied_wheel = root_stage / wheel.name
        copied_requirements = root_stage / "requirements.txt"
        shutil.copyfile(wheel, copied_wheel)
        shutil.copyfile(requirements, copied_requirements)
        environment = root_stage / "environment"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = str(environment / "bin/python")
        safe_environment = {"PATH": "/usr/bin:/bin", "PIP_CONFIG_FILE": "/dev/null", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
        subprocess.run([python, "-I", "-m", "pip", "--isolated", "install", "-r", str(copied_requirements)], env=safe_environment, check=True)
        subprocess.run([python, "-I", "-m", "pip", "--isolated", "install", "--no-deps", str(copied_wheel)], env=safe_environment, check=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(environment), destination)
    launcher = Path("/usr/local/libexec/desktop-afk-alert-helper")
    launcher.parent.mkdir(parents=True, exist_ok=True)
    if launcher.is_symlink():
        raise SystemExit("Remove the existing helper launcher symlink before installing.")
    launcher.write_text('#!/bin/sh\nexec /usr/local/lib/desktop-afk-alert-helper/bin/python -I -m desktop_afk_alert.helper "$@"\n')
    launcher.chmod(0o755)
    print("Development helper installed. Run the GUI as your normal user.")


if __name__ == "__main__":
    main()
