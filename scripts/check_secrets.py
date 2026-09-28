"""Small deterministic repository scan; never print matching secret values."""
import re
import subprocess
from pathlib import Path

result = subprocess.run(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
    check=True, capture_output=True,
)
paths = set(result.stdout.decode().split("\0")) - {""}
local_secrets = []
if Path(".env").exists():
    for line in Path(".env").read_text().splitlines():
        if "=" in line:
            value = line.split("=", 1)[1].strip()
            if len(value) >= 20:
                local_secrets.append(value)
patterns = [r"sk-or-v1-[A-Za-z0-9]{20,}", r"sk-ant-[A-Za-z0-9_-]{20,}",
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"]
for secret_path in [Path('.runtime/deep/client-token'), Path('.runtime/deep/omni-api-token')]:
    if secret_path.is_file():
        value = secret_path.read_text(encoding='utf-8').strip()
        if len(value) >= 20:
            local_secrets.append(value)
findings = []
for name in paths:
    path = Path(name)
    if not path.is_file() or path.is_symlink():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    if any(secret in text for secret in local_secrets) or any(re.search(p, text) for p in patterns):
        findings.append(name)
if findings:
    print("Potential secrets detected in: " + ", ".join(sorted(findings)))
    raise SystemExit(1)
print(f"Repository secret check passed ({len(paths)} paths; no secret values printed).")
