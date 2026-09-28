import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("owner_inventory", Path(__file__).parents[1] / "scripts/owner_inventory.py")
assert spec and spec.loader
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_inventory_does_not_execute_and_preserves_nested_symbols(tmp_path):
    folder = tmp_path / "mg_ai"
    folder.mkdir()
    (folder / "sample.py").write_text("raise RuntimeError('must never run')\nclass A:\n    async def execute(self):\n        def nested():\n            pass\n")
    rows = tool.inventory(tmp_path)
    assert [(r["symbol"], r["kind"]) for r in rows] == [
        ("", "module"), ("A", "class"), ("A.execute", "async_function"),
        ("A.execute.nested", "function")]
    assert rows == tool.inventory(tmp_path)


def test_real_owner_doc_references():
    root = Path(__file__).parents[1]
    count, errors = tool.check_docs(root, tool.inventory(root))
    assert not errors
    assert count > 30


def test_missing_symbol_and_link_are_rejected(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "OWNER_CODE_MAP.md").write_text("<!-- symbol: mg_ai/no.py::fake -->\n[missing](missing.md)")
    _, errors = tool.check_docs(tmp_path, [])
    assert any("unknown symbol" in error for error in errors)
    assert any("missing link" in error for error in errors)
