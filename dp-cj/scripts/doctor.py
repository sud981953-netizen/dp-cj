from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from config_util import ConfigError, config_root, is_placeholder, load_config

EXPECTED_TABLES = ["工厂实体店", "情感(泛流量)", "自媒体+AI", "搞钱(干货)", "人设", "营销"]
COMMON_FIELDS = ["标题", "文案全文", "开头+金句", "选题", "链接", "平台", "发布日期", "视频时长", "点赞数", "评论数", "收藏数", "分享数"]


def resolve_lark_cli() -> str:
    if os.name != "nt":
        return "lark-cli"
    return shutil.which("lark-cli.cmd") or shutil.which("lark-cli") or "lark-cli"


def run_cli(args: list[str]) -> dict:
    env = os.environ.copy()
    env.pop("HERMES_HOME", None)
    r = subprocess.run([resolve_lark_cli(), *args, "--as", "user", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"lark-cli 输出无法解析（exit={r.returncode}）", "stdout": r.stdout[:1000], "stderr": r.stderr[:1000]}


def main() -> int:
    ap = argparse.ArgumentParser(description="检查 dp-cj 配置、运行环境和飞书字段")
    ap.add_argument("--config", default=None)
    ap.add_argument("--live", action="store_true", help="实时读取飞书表字段并校验字段映射")
    args = ap.parse_args()
    results: list[tuple[str, bool, str, str]] = []

    def check(name: str, ok: bool, detail: str = "", level: str = "FAIL"):
        results.append((name, bool(ok), detail, level))

    try:
        cfg, cfg_path = load_config(args.config)
        root = config_root(cfg, cfg_path)
    except ConfigError as e:
        print(f"[FAIL] 配置：{e}")
        return 2

    check("workspace_root", root.is_dir(), str(root), "WARN")
    py = str(cfg.get("python_executable", "python"))
    py_path = Path(py).expanduser()
    py_ok = py_path.is_file() if py_path.is_absolute() else bool(shutil.which(py))
    check("Python 解释器", py_ok, py)
    for mod in ("requests", "av", "playwright", "sherpa_onnx"):
        ok = False; detail = ""
        if py_ok:
            exe = str(py_path) if py_path.is_absolute() else (shutil.which(py) or py)
            try:
                r = subprocess.run([exe, "-c", f"import {mod}"], capture_output=True, text=True, timeout=20)
                ok = r.returncode == 0
                detail = "可导入" if ok else (r.stderr or r.stdout).strip()[:300]
            except Exception as e:
                detail = str(e)
        check(f"依赖 {mod}", ok, detail)

    extraction = cfg.get("extraction", {})
    transcribe = extraction.get("transcribe_script")
    if transcribe and not is_placeholder(transcribe):
        tp = Path(str(transcribe)).expanduser()
        if not tp.is_absolute():
            tp = root / tp
        check("转写内核 transcribe.py", tp.is_file(), str(tp), "WARN")
    else:
        check("转写内核 transcribe.py", True, "未配置，将依赖官方字幕/OCR", "WARN")
    lark_ok = bool(shutil.which("lark-cli.cmd") or shutil.which("lark-cli"))
    check("lark-cli", lark_ok, "PATH 查找", "WARN")

    routing = cfg.get("routing", {})
    options = routing.get("options", [])
    check("分类确认开关", routing.get("ask_before_processing") is True, str(routing.get("ask_before_processing")))
    check("分类选项", options == EXPECTED_TABLES, " / ".join(options))
    feishu = cfg.get("feishu", {})
    for key in ("base_token", "base_url"):
        val = feishu.get(key)
        check(f"飞书 {key}", bool(val) and not is_placeholder(val), str(val))
    tables = feishu.get("tables", {})
    for name in EXPECTED_TABLES:
        t = tables.get(name)
        ok = isinstance(t, dict) and bool(t.get("table_id")) and isinstance(t.get("field_map"), dict)
        check(f"分类表 {name}", ok, t.get("table_id") if isinstance(t, dict) else "缺失")
        if not ok:
            continue
        mapped = set(t.get("field_map", {}).values())
        missing = [f for f in COMMON_FIELDS if f not in mapped]
        check(f"配置字段 {name}", not missing, "缺少：" + "、".join(missing) if missing else "齐全")
        if args.live and lark_ok:
            response = run_cli(["base", "+field-list", "--base-token", feishu["base_token"], "--table-id", t["table_id"]])
            actual = {f.get("name") for f in (response.get("data", {}).get("fields") or [])} if response.get("ok") else set()
            required_missing = sorted({f for f in COMMON_FIELDS if f not in actual})
            optional_missing = sorted((mapped - actual) - set(COMMON_FIELDS))
            check(f"飞书字段 {name}", response.get("ok") and not required_missing, "缺少：" + "、".join(required_missing) if required_missing else "齐全")
            if optional_missing:
                check(f"可选字段 {name}", True, "未提供：" + "、".join(optional_missing), "WARN")

    fails = warns = 0
    for name, ok, detail, level in results:
        if ok:
            tag = "OK"
        elif level == "WARN":
            tag = "WARN"; warns += 1
        else:
            tag = "FAIL"; fails += 1
        print(f"[{tag:4}] {name}: {detail}")
    print()
    if fails:
        print(f"结论：{fails} FAIL、{warns} WARN。先修复 FAIL。")
        return 1
    suffix = "，含飞书实时字段校验" if args.live else ""
    print(f"结论：核心配置通过{suffix}，{warns} WARN 为可选能力。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
