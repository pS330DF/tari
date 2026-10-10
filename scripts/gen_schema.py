"""Export the v1 Pydantic models to JSON Schema (source of truth for TypeScript types)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

from tari_schema import EXPORTED_MODELS, SCHEMA_VERSION

OUT = Path(__file__).resolve().parents[1] / "packages" / "event-schema" / "schemas" / "v1"


def main() -> None:
    _, top = models_json_schema([(m, "serialization") for m in EXPORTED_MODELS], ref_template="#/$defs/{model}")
    defs = top.get("$defs", {})
    bundle = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://tari.local/schemas/v1/tari.schema.json",
        "title": "TariSchemaV1",
        "description": f"TARI event schema {SCHEMA_VERSION}. Generated from tari_schema; do not edit.",
        "type": "object",
        "properties": {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in EXPORTED_MODELS},
        "$defs": defs,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tari.schema.json").write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    (OUT / "VERSION").write_text(SCHEMA_VERSION + "\n")
    print(f"wrote {len(defs)} definitions to {OUT / 'tari.schema.json'}")


if __name__ == "__main__":
    main()
