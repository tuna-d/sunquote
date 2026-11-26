"""`scripts/export_openapi.py` writes the OpenAPI schema the web app's types are generated from."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_openapi.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_writes_the_schema_of_the_fastapi_app_without_a_server(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"

    load_script().main([str(target)])

    schema = json.loads(target.read_text(encoding="utf-8"))
    assert schema["info"]["title"] == "sunquote"
    assert "/quotes" in schema["paths"]
    assert "QuoteListResponse" in schema["components"]["schemas"]


def test_two_runs_write_identical_bytes(tmp_path: Path) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    script = load_script()

    script.main([str(first)])
    script.main([str(second)])

    assert first.read_bytes() == second.read_bytes()


def test_the_file_ends_with_a_newline_and_is_indented(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"

    load_script().main([str(target)])

    text = target.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert '\n  "info"' in text
