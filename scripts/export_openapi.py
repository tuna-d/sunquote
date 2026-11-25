"""Write the FastAPI app's OpenAPI schema to a file, without starting a server.

    uv run python scripts/export_openapi.py [target]

The default target is `web/openapi.json`. The web app generates its API types from that file
(`npm run api:types`), and CI regenerates both and fails when they differ from what is committed.
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_TARGET = Path(__file__).resolve().parents[1] / "web" / "openapi.json"


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    target = Path(args[0]) if args else DEFAULT_TARGET

    # Imported here: building the app reads the data files, so keep `--help`-style failures cheap.
    from sunquote.api.app import create_app

    schema = create_app().openapi()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Sorted keys and a fixed indent keep the file byte-identical between runs and platforms.
    text = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True)
    target.write_text(text + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
