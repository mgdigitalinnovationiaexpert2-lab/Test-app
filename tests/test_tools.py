import subprocess
from pathlib import Path

import pytest

from mg_ai.discovery import free_model, proposal
from mg_ai.evals import CATEGORIES, fixtures, run
from mg_ai.scope_guard import TaskPolicy, baseline, changed_paths, changed_since, check, risk


def policy(**kwargs):
    return TaskPolicy(repository=".", goal="Synthetic task", acceptance_criteria=["Scoped change"], **kwargs)


def test_scope_guard_paths_and_actions():
    task = policy(task="test", allowed_paths=["src/**", "docs/**"],
                        forbidden_paths=["src/auth/**", ".env*"])
    found = check(["src/components/a.tsx", "src/auth/a.ts", ".env", "deploy/a", "../a"], task)
    assert sum(f["reason"] == "allowed" for f in found) == 1
    assert check([], task, "commit")[0]["reason"] == "commit forbidden"
    assert check([], task, "push")[0]["reason"] == "push forbidden"
    assert risk("docs/a.md") == "LOW" and risk("services/a.py") == "MEDIUM"
    assert risk("prisma/schema.prisma") == "HIGH"
    broad = policy(task="test", allowed_paths=["**"], forbidden_paths=[])
    assert check(["prisma/schema.prisma"], broad)[0]["reason"] == "schema change forbidden"
    narrow = policy(task="test", allowed_paths=["src/*.py"], forbidden_paths=[])
    assert check(["src/nested/a.py"], narrow)[0]["reason"] == "outside task scope"


def test_git_diff_includes_staged_untracked(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "staged.txt").write_text("first")
    subprocess.run(["git", "-C", str(tmp_path), "add", "staged.txt"], check=True)
    (tmp_path / "staged.txt").write_text("changed")
    (tmp_path / "space name.txt").write_text("untracked")
    assert changed_paths(tmp_path) == ["space name.txt", "staged.txt"]


def test_scope_baseline_preserves_existing_work_and_detects_edits(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    existing = tmp_path / "existing.md"
    existing.write_text("owner work")
    snapshot = baseline(tmp_path)
    assert changed_since(tmp_path, snapshot) == []
    (tmp_path / "new.md").write_text("task work")
    assert changed_since(tmp_path, snapshot) == ["new.md"]
    existing.write_text("modified owner work")
    assert changed_since(tmp_path, snapshot) == ["existing.md", "new.md"]
    existing.unlink()
    assert "existing.md" in changed_since(tmp_path, snapshot)
    with pytest.raises(ValueError, match="repository mismatch"):
        changed_since(tmp_path / "other", snapshot)


def test_infrastructure_flag_cannot_be_bypassed_by_broad_allowlist():
    task = policy(task="docs", allowed_paths=["**"], forbidden_paths=[])
    for path in ["Dockerfile", "compose.yaml", "deploy/server.md", ".github/workflows/ci.yml"]:
        assert check([path], task)[0]["reason"] == "infrastructure change forbidden"


@pytest.mark.parametrize("pricing", [{"prompt": "0", "completion": "1"}, {},
                                      {"prompt": "0", "completion": "0", "request": "1"},
                                      {"prompt": "NaN", "completion": "0"}])
def test_discovery_rejects_uncertain_prices(pricing):
    assert not free_model({"id": "model:free", "pricing": pricing})


def test_discovery_proposals_disabled():
    data = proposal([{"id": "model:free", "pricing": {"prompt": "0", "completion": "0"}}],
                    [{"model": "removed:free"}])
    assert data["removed_or_no_longer_free"] == ["removed:free"]
    assert data["candidates"][0]["enabled"] is False


def test_benchmark_fixture_execution():
    data = fixtures(Path("evals/fixtures/synthetic.jsonl"))
    assert {f.category for f in data} == CATEGORIES
    report = run(data)
    assert report["not_a_model_quality_claim"]
    assert all(r["dimensions"]["correctness"] == 1 for r in report["results"])
    wrong = run(data, {f.id: "incorrect" for f in data})
    assert all(r["dimensions"]["correctness"] == 0 for r in wrong["results"])
