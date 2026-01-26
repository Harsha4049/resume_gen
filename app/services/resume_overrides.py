from __future__ import annotations

from pathlib import Path
from typing import Optional
import json

from app.models.schemas import OverridesRequest


def overrides_path(root_dir: Path, resume_id: str) -> Path:
    return root_dir / resume_id / "overrides.json"


def save_overrides(root_dir: Path, resume_id: str, overrides: OverridesRequest) -> Path:
    path = overrides_path(root_dir, resume_id)
    path.write_text(overrides.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_overrides(root_dir: Path, resume_id: str) -> Optional[OverridesRequest]:
    path = overrides_path(root_dir, resume_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return OverridesRequest(**data)
