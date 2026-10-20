"""Run once at a meaningful milestone; no live inference or deployment."""
import subprocess
import sys

commands = [
    [sys.executable, "scripts/prepare.py"],
    [sys.executable, "-m", "pytest", "-q"],
    [sys.executable, "-m", "ruff", "check", "mg_ai", "scripts", "tests"],
    [sys.executable, "-m", "mypy", "mg_ai"],
    [sys.executable, "-m", "build"],
    [sys.executable, "scripts/check_secrets.py"],
]
for command in commands:
    print("Running " + " ".join(command[1:]), flush=True)
    subprocess.run(command, check=True)
print("Repository validation passed. Run Docker health/contract checks separately.")
