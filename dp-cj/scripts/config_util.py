from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PLACEHOLDER_PREFIX = "REPLACE_ME"

class ConfigError(RuntimeError):
    pass

def find_config(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()
    env = os.environ.get("DP_CJ_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / "config.json").resolve()

def load_config(explicit: str | os.PathLike[str] | None = None) -> tuple[dict[str, Any], Path]:
    path = find_config(explicit)
    if not path.is_file():
        raise ConfigError(f"配置文件不存在：{path}。请复制 config.example.json 为 config.json。")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"配置 JSON 解析失败：{path}: {e}") from e
    if not isinstance(cfg, dict):
        raise ConfigError("配置文件必须是 JSON 对象。")
    cfg["_config_path"] = str(path)
    return cfg, path

def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX)

def config_root(cfg: dict[str, Any], config_path: Path) -> Path:
    raw = cfg.get("workspace_root")
    if not raw or is_placeholder(raw):
        raise ConfigError("workspace_root 未配置。")
    p = Path(str(raw)).expanduser()
    if not p.is_absolute():
        p = (config_path.parent / p).resolve()
    return p

def resolve_path(cfg: dict[str, Any], value: str | os.PathLike[str], config_path: Path, base: Path | None = None) -> Path:
    p = Path(str(value)).expanduser()
    if p.is_absolute():
        return p.resolve()
    root = base or config_root(cfg, config_path)
    return (root / p).resolve()

def require_value(cfg: dict[str, Any], dotted: str) -> Any:
    cur: Any = cfg
    for part in dotted.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            raise ConfigError(f"缺少配置项：{dotted}")
        cur = cur[part]
    if cur is None or is_placeholder(cur):
        raise ConfigError(f"配置项仍是占位符：{dotted}")
    return cur
