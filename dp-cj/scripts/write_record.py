from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import requests

from config_util import ConfigError, config_root, load_config, require_value, resolve_path

CATEGORY_NUMBERS = {
    "1": "工厂实体店",
    "2": "情感(泛流量)",
    "3": "自媒体+AI",
    "4": "搞钱(干货)",
    "5": "人设",
    "6": "营销",
}
ATTACHMENT_FIELDS = {"cover", "title_screenshot", "likes_screenshot"}


def resolve_lark_cli() -> str:
    if os.name != "nt":
        return "lark-cli"
    return shutil.which("lark-cli.cmd") or shutil.which("lark-cli") or "lark-cli"


def run_cli(args: list[str], cwd: str | None = None) -> dict:
    env = os.environ.copy()
    env.pop("HERMES_HOME", None)
    r = subprocess.run([resolve_lark_cli(), *args, "--as", "user"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=cwd)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"lark-cli 输出无法解析（exit={r.returncode}）", "stdout": r.stdout[:2000], "stderr": r.stderr[:2000]}


def normalize_category(value) -> str:
    text = str(value or "").strip()
    return CATEGORY_NUMBERS.get(text, text)


def normalize_payload(raw: dict, category: str) -> dict:
    out = dict(raw)
    out["category"] = category
    if category != "工厂实体店":
        out["copy_type"] = category
    platform = str(out.get("platform") or "").strip()
    if platform in {"微信视频号", "视频号"}:
        out["platform"] = "视频号"
    date_val = out.get("published_date") or out.get("published_at")
    if date_val:
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", str(date_val))
        if m:
            out["published_date"] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    duration = out.get("duration") or out.get("duration_seconds")
    if isinstance(duration, (int, float)):
        seconds = int(duration)
        out["duration"] = f"{seconds // 60:02d}:{seconds % 60:02d}"
    elif str(duration or "").strip().isdigit():
        seconds = int(str(duration).strip())
        out["duration"] = f"{seconds // 60:02d}:{seconds % 60:02d}"
    elif duration:
        out["duration"] = str(duration)
    stat_aliases = {
        "likes": ("likes", "digg"),
        "comments": ("comments", "comment"),
        "collects": ("collects", "collect"),
        "shares": ("shares", "share"),
    }
    for logical, aliases in stat_aliases.items():
        value = next((out.get(a) for a in aliases if out.get(a) not in (None, "", "—")), 0)
        try:
            out[logical] = int(float(value or 0))
        except (TypeError, ValueError):
            out[logical] = 0
    if "likes_collects" not in out:
        out["likes_collects"] = int(out.get("likes", 0) or 0) + int(out.get("collects", 0) or 0)
    if not out.get("opening_and_golden"):
        opening = out.get("opening_line") or ""
        gold = out.get("golden_lines") or out.get("original_golden_lines") or ""
        if opening or gold:
            out["opening_and_golden"] = f"开头：{opening}\n金句：\n{gold}".strip()
    out.setdefault("full_text", out.get("original_text") or out.get("copy_text") or "")
    out["cover"] = out.get("cover") or out.get("cover_url") or ""
    return out


def remap_payload(payload: dict, field_map: dict) -> dict:
    mapped = {}
    for logical, value in payload.items():
        if logical in {"category"} or logical in ATTACHMENT_FIELDS or value in (None, ""):
            continue
        actual = field_map.get(logical)
        if not actual:
            continue
        mapped[actual] = value
    return mapped


def materialize_attachment(value, logical: str, cfg: dict, cfg_path: Path) -> tuple[Path | None, str]:
    if isinstance(value, list):
        value = value[0] if value else ""
    text = str(value or "").strip()
    if not text:
        return None, "empty"
    root = config_root(cfg, cfg_path)
    tmp_dir = resolve_path(cfg, str(cfg.get("tmp_dir", "_tmp")), cfg_path, root)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    local = Path(text).expanduser()
    if local.is_file():
        return local.resolve(), "local"
    if text.startswith(("http://", "https://")):
        try:
            r = requests.get(text, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            suffix = Path(text.split("?", 1)[0]).suffix or ".jpg"
            if suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
                suffix = ".jpg"
            path = tmp_dir / f"{logical}_{uuid.uuid4().hex}{suffix}"
            path.write_bytes(r.content)
            return path, "downloaded"
        except Exception as e:
            return None, f"download_failed: {e}"
    return None, "unsupported_value"


def collect_file_tokens(value) -> list[str]:
    tokens = []
    if isinstance(value, dict):
        token = value.get("file_token")
        if token:
            tokens.append(str(token))
        for v in value.values():
            tokens.extend(collect_file_tokens(v))
    elif isinstance(value, list):
        for v in value:
            tokens.extend(collect_file_tokens(v))
    return tokens


def replace_attachment(payload: dict, logical: str, actual: str, record_id: str, table_cfg: dict, feishu: dict, cfg: dict, cfg_path: Path) -> dict:
    existing = run_cli([
        "base", "+record-get",
        "--base-token", feishu["base_token"],
        "--table-id", table_cfg["table_id"],
        "--record-id", record_id,
        "--field-id", actual,
        "--format", "json",
    ])
    tokens = list(dict.fromkeys(collect_file_tokens(existing))) if existing.get("ok") else []
    removed = None
    if tokens:
        removed = run_cli([
            "base", "+record-remove-attachment",
            "--base-token", feishu["base_token"],
            "--table-id", table_cfg["table_id"],
            "--record-id", record_id,
            "--field-id", actual,
            "--file-token", *tokens,
            "--yes",
            "--format", "json",
        ])
        if not removed.get("ok"):
            return {"ok": False, "error": "旧附件清理失败", "existing_tokens": tokens, "response": removed}
    path, status = materialize_attachment(payload.get(logical), logical, cfg, cfg_path)
    if not path:
        return {"ok": False, "error": status, "existing_tokens": tokens}
    uploaded = run_cli([
        "base", "+record-upload-attachment",
        "--base-token", feishu["base_token"],
        "--table-id", table_cfg["table_id"],
        "--record-id", record_id,
        "--field-id", actual,
        "--file", f"./{path.name}",
        "--format", "json",
    ], cwd=str(path.parent))
    return {
        "ok": bool(uploaded.get("ok")),
        "status": status,
        "file": str(path),
        "removed_tokens": tokens,
        "response": uploaded,
    }


def upload_attachments(payload: dict, field_map: dict, record_id: str | None, cfg: dict, cfg_path: Path, table_cfg: dict, feishu: dict) -> dict:
    results = {}
    if not record_id:
        for logical in ATTACHMENT_FIELDS:
            if payload.get(logical):
                results[logical] = {"ok": False, "error": "记录 ID 缺失，无法上传附件"}
        return results
    for logical in ATTACHMENT_FIELDS:
        value = payload.get(logical)
        if not value:
            continue
        actual = field_map.get(logical)
        if not actual:
            results[logical] = {"ok": True, "skipped": "目标表没有该附件字段"}
            continue
        results[logical] = replace_attachment(payload, logical, actual, record_id, table_cfg, feishu, cfg, cfg_path)
    return results


def find_existing(url: str, table_cfg: dict, feishu: dict) -> str | None:
    url_field = table_cfg.get("dedupe_field") or table_cfg.get("field_map", {}).get("source_url")
    if not url_field:
        return None
    response = run_cli([
        "base", "+record-search",
        "--base-token", feishu["base_token"],
        "--table-id", table_cfg["table_id"],
        "--keyword", url,
        "--search-field", url_field,
        "--field-id", url_field,
        "--limit", "5",
        "--format", "json",
    ])
    if not response.get("ok"):
        return None
    data = response.get("data") or {}
    ids = data.get("record_id_list") or []
    rows = data.get("data") or []
    for record_id, row in zip(ids, rows):
        values = row if isinstance(row, list) else [row]
        for value in values:
            text = str(value or "")
            if text == url or f"({url})" in text:
                return record_id
    return None


def extract_new_record_id(response: dict) -> str | None:
    data = response.get("data") or {}
    record = data.get("record") or {}
    ids = record.get("record_id_list") or record.get("record_ids") or []
    return ids[0] if ids else data.get("record_id")


def main() -> int:
    ap = argparse.ArgumentParser(description="按用户确认的分类表提取字段并写入飞书 Base")
    ap.add_argument("--config", default=None)
    ap.add_argument("--payload", required=True)
    ap.add_argument("--category", default=None, help="分类表名称或编号 1-6；优先于 payload.category")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        cfg, cfg_path = load_config(args.config)
        feishu = require_value(cfg, "feishu")
        raw = json.loads(Path(args.payload).read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ConfigError("payload 必须是 JSON 对象。")
        category = normalize_category(args.category or raw.get("category"))
        if not category:
            raise ConfigError("缺少 category。必须先由用户确认分类表。")
        tables = require_value(cfg, "feishu.tables")
        if category not in tables:
            raise ConfigError(f"未知分类表：{category}。可选：{'、'.join(CATEGORY_NUMBERS.values())}")
        table_cfg = tables[category]
        field_map = require_value(cfg, f"feishu.tables.{category}.field_map")
        payload = normalize_payload(raw, category)
        source_url = payload.get("source_url") or payload.get("link")
        if not source_url:
            raise ConfigError("payload 缺少 source_url/链接。")
    except (ConfigError, json.JSONDecodeError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2

    mapped = remap_payload(payload, field_map)
    source_field = table_cfg.get("dedupe_field") or field_map.get("source_url")
    if source_field:
        mapped[source_field] = source_url
    attachment_jobs = {k: payload.get(k) for k in ATTACHMENT_FIELDS if payload.get(k) and field_map.get(k)}
    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "category": category, "table_id": table_cfg["table_id"], "mapped_payload": mapped, "attachment_jobs": attachment_jobs}, ensure_ascii=False, indent=2))
        return 0

    record_id = find_existing(str(source_url), table_cfg, feishu)
    args_list = ["base", "+record-upsert", "--base-token", feishu["base_token"], "--table-id", table_cfg["table_id"], "--json", json.dumps(mapped, ensure_ascii=False)]
    if record_id:
        args_list += ["--record-id", record_id]
    response = run_cli(args_list)
    final_record_id = record_id or extract_new_record_id(response)
    attachments = upload_attachments(payload, field_map, final_record_id, cfg, cfg_path, table_cfg, feishu)
    record_ok = bool(response.get("ok"))
    attachments_ok = all(v.get("ok") for v in attachments.values())
    outcome = {
        "ok": record_ok and attachments_ok,
        "category": category,
        "action": "updated" if record_id else "created",
        "record_id": final_record_id,
        "attachments": attachments,
        "response": response,
    }
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0 if outcome["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
