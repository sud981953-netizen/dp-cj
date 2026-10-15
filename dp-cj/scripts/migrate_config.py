"""Add official Base mappings without replacing user paths or custom settings."""
from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path

from config_util import find_config


def migrate_config(path=None) -> bool:
    target = find_config(path)
    if not target.is_file():
        return False
    cfg = json.loads(target.read_text(encoding="utf-8-sig"))
    defaults = json.loads((Path(__file__).resolve().parents[1] / "config.example.json").read_text(encoding="utf-8-sig"))
    if cfg.get("feishu", {}).get("base_token") != defaults["feishu"]["base_token"]:
        return False  # Never inject official table IDs into another Base.
    updated = copy.deepcopy(cfg)
    tables = updated["feishu"].setdefault("tables", {})
    for name in ("工厂实体店", "情感共鸣型（泛流量）"):
        default = defaults["feishu"]["tables"][name]
        if name not in tables:
            tables[name] = copy.deepcopy(default)
        elif tables[name].get("table_id") == default["table_id"]:
            tables[name].setdefault("field_map", {}).setdefault("industry", "行业")
    routing = updated.setdefault("routing", {})
    routing.setdefault("ask_before_processing", True)
    options = routing.setdefault("options", list(defaults["routing"]["options"]))
    new_category = "情感共鸣型（泛流量）"
    if new_category not in options:
        options.append(new_category)
    if updated == cfg:
        return False
    backup = target.with_name(target.name + ".pre-v1.4.0.bak")
    if not backup.exists():
        shutil.copy2(target, backup)
    temporary = target.with_name(target.name + ".migration.tmp")
    try:
        temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return True
