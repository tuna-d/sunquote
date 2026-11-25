"""The files that make the FastAPI app a Vercel function: `api/index.py` and `vercel.json`."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = ROOT / "api" / "index.py"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    # The entry point sets defaults in `os.environ`. Set then delete, so that monkeypatch
    # removes whatever the entry point added once the test is over.
    for name in ("SUNQUOTE_MIGRATE_ON_STARTUP", "SUNQUOTE_DATABASE_CLIENT_POOL"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    # `sunquote.api.app` builds its `app` when first imported: import it afresh, as on a cold
    # start, and put the original module back afterwards.
    monkeypatch.delitem(sys.modules, "sunquote.api.app", raising=False)


def load_entry_point() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vercel_entry_point", ENTRY_POINT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("vercel_entry_point", None)
    spec.loader.exec_module(module)
    return module


def test_the_entry_point_exposes_the_fastapi_app() -> None:
    assert isinstance(load_entry_point().app, FastAPI)


def test_on_vercel_the_app_does_not_migrate_at_startup_and_keeps_no_client_pool() -> None:
    app = load_entry_point().app

    assert app.state.settings.migrate_on_startup is False
    assert app.state.settings.database_client_pool is False
    # No startup hook: CI migrates, not the first cold start.
    assert app.state.dependencies.startup == ()


def test_the_environment_can_still_override_the_vercel_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUNQUOTE_MIGRATE_ON_STARTUP", "true")
    monkeypatch.setenv("SUNQUOTE_DATABASE_CLIENT_POOL", "true")

    app = load_entry_point().app

    assert app.state.settings.migrate_on_startup is True
    assert app.state.settings.database_client_pool is True


def test_vercel_runs_the_entry_point_for_every_path_for_up_to_300_seconds() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    assert config["functions"]["api/index.py"]["maxDuration"] == 300
    assert {"source": "/(.*)", "destination": "/api/index"} in config["rewrites"]


def test_the_python_version_is_pinned_to_one_vercel_supports() -> None:
    pinned = (ROOT / ".python-version").read_text(encoding="utf-8").strip()

    assert pinned == "3.13"


def test_only_the_main_branch_is_built_so_the_api_gets_no_previews() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    # Vercel skips a build when the command exits 0: that is, for every branch except `main`.
    assert config["ignoreCommand"] == '[ "$VERCEL_GIT_COMMIT_REF" != "main" ]'
