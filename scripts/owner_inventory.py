"""Extract source symbols without importing application modules or contacting providers."""
import argparse
import ast
import json
import re
from pathlib import Path


def inventory(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    def walk(node: ast.AST, path: str, parents: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = parents + [child.name]
                rows.append({"file": path, "symbol": ".".join(name), "line": child.lineno,
                             "kind": "class" if isinstance(child, ast.ClassDef) else
                             "async_function" if isinstance(child, ast.AsyncFunctionDef) else "function"})
                walk(child, path, name)
            else:
                walk(child, path, parents)

    for folder in ("mg_ai", "scripts"):
        for path in sorted((root / folder).glob("*.py")):
            relative = path.relative_to(root).as_posix()
            rows.append({"file": relative, "symbol": "", "line": 1, "kind": "module"})
            walk(ast.parse(path.read_text(encoding="utf-8-sig")), relative, [])
    return rows


def check_docs(root: Path, rows: list[dict[str, object]]) -> tuple[int, list[str]]:
    known = {(row["file"], row["symbol"]) for row in rows}
    documented = set()
    errors = []
    names = ("OWNER_SYSTEM_MAP", "OWNER_CODE_MAP", "REQUEST_FLOWS", "SECURITY_BOUNDARIES",
             "FAILURE_AND_RECOVERY", "OPERATIONS_RUNBOOK", "OWNER_APPROVAL_POINTS")
    for name in names:
        path = root / "docs" / (name + ".md")
        if not path.is_file():
            errors.append(f"missing document: {name}")
            continue
        content = path.read_text(encoding="utf-8")
        for file, symbol in re.findall(r"<!-- symbol: ([^\s]+)::([^\s]+) -->", content):
            if (file, symbol) not in known:
                errors.append(f"{name}: unknown symbol {file}::{symbol}")
            documented.add((file, symbol))
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#", 1)[0]
            if not (path.parent / target).is_file():
                errors.append(f"{name}: missing link {target}")
    return len(documented), errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path(".runtime/owner-handover/inventory.json"))
    parser.add_argument("--check-docs", action="store_true")
    args = parser.parse_args()
    rows = inventory(args.root)
    count, errors = check_docs(args.root, rows) if args.check_docs else (0, [])
    if errors:
        raise SystemExit("\n".join(errors))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"inventory_entries": len(rows), "documented_symbols": count,
                      "references_valid": not errors, "output": str(args.output)}))


if __name__ == "__main__":
    main()
