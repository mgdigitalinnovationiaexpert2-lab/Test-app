"""Create credentials locally without printing or overwriting them."""
import secrets
from pathlib import Path

path = Path(".env")
with path.open("x", encoding="utf-8") as out:
    for name in ("MG_PORTAL_TOKEN", "MG_LIFE_OS_TOKEN", "MG_DEV_TOKEN", "LITELLM_MASTER_KEY"):
        out.write(name + "=sk-mg-" + secrets.token_urlsafe(36) + "\n")
    for name in ("OPENROUTER_API_KEY", "NVIDIA_API_KEY", "DIRECT_API_KEY", "ANTHROPIC_API_KEY"):
        out.write(name + "=\n")
try:
    path.chmod(0o600)
except OSError:
    pass
print("Created .env with independent local tokens. Provider credentials remain empty.")
