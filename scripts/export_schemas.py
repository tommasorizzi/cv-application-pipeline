"""Generate checked-in JSON schemas from the authoritative Pydantic contracts."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models import SCHEMAS
from app.utils import ROOT

if __name__ == "__main__":
    for name, model in SCHEMAS.items():
        (ROOT / "schemas" / f"{name}.schema.json").write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
