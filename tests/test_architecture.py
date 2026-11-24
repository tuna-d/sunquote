"""Architecture rules from CLAUDE.md, enforced by reading the source, not by importing it."""

import ast
from pathlib import Path

import pytest

DOMAIN_DIR = Path(__file__).resolve().parents[1] / "src" / "sunquote" / "domain"

# The domain is pure calculation: no web framework, no Pydantic models, no config loader,
# and no dependency on the layers that depend on it.
FORBIDDEN_IN_DOMAIN = (
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_settings",
    "sunquote.api",
    "sunquote.adapters",
    "sunquote.config",
)


def forbidden_imports(source_dir: Path, forbidden: tuple[str, ...]) -> list[str]:
    """Return 'file: module' for every import under `source_dir` that hits a forbidden package."""
    violations: list[str] = []
    for path in sorted(source_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                continue
            violations.extend(
                f"{path.name}: {module}"
                for module in modules
                if any(module == bad or module.startswith(f"{bad}.") for bad in forbidden)
            )
    return violations


def test_domain_imports_no_framework_or_outer_layer() -> None:
    assert DOMAIN_DIR.is_dir()
    assert forbidden_imports(DOMAIN_DIR, FORBIDDEN_IN_DOMAIN) == []


@pytest.mark.parametrize(
    "statement",
    [
        "import fastapi",
        "from fastapi import FastAPI",
        "from pydantic import BaseModel",
        "import pydantic.v1",
        "from sunquote.api.app import create_app",
        "import sunquote.adapters",
        "from sunquote.config import Settings",
    ],
)
def test_checker_flags_forbidden_import(tmp_path: Path, statement: str) -> None:
    (tmp_path / "bad.py").write_text(f"{statement}\n", encoding="utf-8")
    assert forbidden_imports(tmp_path, FORBIDDEN_IN_DOMAIN) != []


def test_checker_allows_standard_library_and_domain_imports(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text(
        "from decimal import Decimal\nfrom sunquote.domain import money\n", encoding="utf-8"
    )
    assert forbidden_imports(tmp_path, FORBIDDEN_IN_DOMAIN) == []
