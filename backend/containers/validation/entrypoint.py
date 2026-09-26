"""Image-owned entrypoint; project code only executes inside the sandbox."""

import shutil
import subprocess
import sys

ALLOWED = {
    ("-m", "compileall", "-q", "."),
    ("-m", "ruff", "check", "--select", "F", "."),
    ("-m", "bandit", "-r", ".", "-f", "json", "-lll"),
    ("-m", "pytest", "-q"),
}

if tuple(sys.argv[1:]) not in ALLOWED:
    raise SystemExit("Unsupported validation command")
shutil.copytree("/input", "/workspace", dirs_exist_ok=True)
# argv was matched against fixed commands above; no shell is used.
result = subprocess.run([sys.executable, *sys.argv[1:]], check=False)  # noqa: S603
raise SystemExit(result.returncode)
