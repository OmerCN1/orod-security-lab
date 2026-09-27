"""Image-owned entrypoint; project code only executes inside the sandbox."""

import shutil
import subprocess
import sys

# Mirrors orod.adapters.repository.validation_checks.CHECKS; a backend test keeps them equal.
ALLOWED = {
    ("-m", "compileall", "-q", "--invalidation-mode", "checked-hash", "."),
    ("-m", "ruff", "check", "--select", "F", "--output-format", "json", "--no-cache", "."),
    ("-B", "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider"),
}

if tuple(sys.argv[1:]) not in ALLOWED:
    raise SystemExit("Unsupported validation command")
shutil.copytree("/input", "/workspace", dirs_exist_ok=True)
# argv was matched against fixed commands above; no shell is used.
result = subprocess.run([sys.executable, *sys.argv[1:]], check=False)  # noqa: S603
raise SystemExit(result.returncode)
