import argparse
import hashlib
import fnmatch
import json
import subprocess
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from mg_ai.config import StrictModel


class TaskPolicy(StrictModel):
    task: str
    repository: str
    goal: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str]
    allow_schema_change: bool = False
    allow_infrastructure_change: bool = False
    allow_commit: bool = False
    allow_push: bool = False
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    relevant_tests: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def risk(path: str) -> str:
    parts = path.lower().replace("\\", "/").split("/")
    if any(p in {"prisma", "migrations", "auth", "permissions", "deploy", "production",
                 "infra", "infrastructure", ".github", "policies", "dockerfile",
                 "compose.yaml", "secrets", "schema.sql"} or p.startswith(".env")
           for p in parts):
        return "HIGH"
    if any(p in {"docs", "components", "ui", "styles"} for p in parts) or path.endswith(".md"):
        return "LOW"
    return "MEDIUM"


def matches(path: str, patterns: list[str]) -> bool:
    def parts_match(parts: list[str], pattern: list[str]) -> bool:
        if not pattern:
            return not parts
        if pattern[0] == "**":
            return parts_match(parts, pattern[1:]) or bool(
                parts and parts_match(parts[1:], pattern))
        return bool(parts and fnmatch.fnmatchcase(parts[0], pattern[0])
                    and parts_match(parts[1:], pattern[1:]))
    return any(parts_match(path.lower().split("/"), p.lower().split("/")) for p in patterns)


def check(paths: list[str], policy: TaskPolicy,
          action: Literal["edit", "commit", "push"] = "edit") -> list[dict[str, str]]:
    findings = []
    if action != "edit" and not getattr(policy, "allow_" + action):
        findings.append({"path": "<action>", "risk": "HIGH", "reason": action + " forbidden"})
    for original in sorted(set(paths)):
        path = original.replace("\\", "/")
        reason = None
        if path.startswith("/") or ":" in path or ".." in path.split("/"):
            reason = "unsafe path"
        elif matches(path, policy.forbidden_paths):
            reason = "forbidden path"
        elif not matches(path, policy.allowed_paths):
            reason = "outside task scope"
        elif not policy.allow_schema_change and any(
            p in {"prisma", "migrations"} or p.startswith("schema.")
            for p in path.lower().split("/")
        ):
            reason = "schema change forbidden"
        elif not policy.allow_infrastructure_change and any(
            p in {"deploy", "infra", "infrastructure", "production", ".github", "dockerfile",
                  "compose.yaml", "docker-compose.yml"} for p in path.lower().split("/")
        ):
            reason = "infrastructure change forbidden"
        findings.append({"path": path, "risk": risk(path), "reason": reason or "allowed"})
    return findings


def changed_paths(root: Path) -> list[str]:
    def git(*args: str) -> list[str]:
        result = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        return [p for p in result.stdout.decode("utf-8", errors="strict").split("\0") if p]
    return sorted(set(git("diff", "--name-only", "--no-renames", "-z") +
                      git("diff", "--cached", "--name-only", "--no-renames", "-z") +
                      git("ls-files", "--others", "--exclude-standard", "-z")))


def baseline(root: Path) -> dict[str, object]:
    files = {}
    for name in changed_paths(root):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("baseline contains symlink/path escape")
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return {"repository": str(root.resolve()), "files": files}


def changed_since(root: Path, previous: dict[str, object]) -> list[str]:
    if previous.get("repository") != str(root.resolve()) or not isinstance(previous.get("files"), dict):
        raise ValueError("baseline repository mismatch")
    current = baseline(root)["files"]
    assert isinstance(current, dict)
    old = previous["files"]
    assert isinstance(old, dict)
    return sorted(name for name in current.keys() | old.keys()
                  if name not in old or name not in current or current[name] != old[name])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--action", choices=["edit", "commit", "push"], default="edit")
    parser.add_argument("--baseline", type=Path,
                        help="Owner-reviewed pre-task snapshot; checks only changes since it")
    args = parser.parse_args()
    try:
        policy = TaskPolicy.model_validate(yaml.safe_load(args.policy.read_text(encoding="utf-8")))
        if policy.repository != "." and Path(policy.repository).resolve() != args.root.resolve():
            raise ValueError("task repository mismatch")
        paths = changed_since(args.root, json.loads(args.baseline.read_text())) if args.baseline else changed_paths(args.root)
        findings = check(paths, policy, args.action)
        for path in paths:
            target = args.root / path
            if target.is_symlink() or not target.resolve().is_relative_to(args.root.resolve()):
                findings.append({"path": path, "risk": "HIGH", "reason": "symlink/escape forbidden"})
        print(json.dumps(findings, indent=2))
        raise SystemExit(int(any(f["reason"] != "allowed" for f in findings)))
    except (ValueError, OSError, subprocess.CalledProcessError, yaml.YAMLError):
        print("Scope inspection failed; denied.")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
