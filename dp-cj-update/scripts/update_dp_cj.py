from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "sud981953-netizen/dp-cj"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
USER_AGENT = "dp-cj-updater"


def http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def download(url: str, path: Path):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, path.open("wb") as f:
        shutil.copyfileobj(r, f)


def semver(value: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", value or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def read_local_version(skill_dir: Path) -> str:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"(?m)^\s*version:\s*[\"']?([^\n\"']+)", text)
    return m.group(1).strip() if m else "0.0.0"


def discover_target(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not (p / "SKILL.md").is_file():
            raise RuntimeError(f"目标目录没有 SKILL.md：{p}")
        return p
    env = os.environ.get("DP_CJ_SKILL_DIR")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "SKILL.md").is_file():
            return p
    sibling = Path(__file__).resolve().parents[2] / "dp-cj"
    candidates = [Path.cwd() / ".workbuddy" / "skills" / "dp-cj", sibling, Path.home() / ".workbuddy" / "skills" / "dp-cj"]
    seen = set()
    for p in candidates:
        p = p.resolve()
        if p in seen:
            continue
        seen.add(p)
        if (p / "SKILL.md").is_file():
            return p
    raise RuntimeError("找不到已安装的 dp-cj；请先安装，或使用 --target 指定目录。")


def find_release_asset(release: dict) -> dict:
    assets = release.get("assets") or []
    for a in assets:
        if a.get("name", "").endswith(".zip") and "dp-cj" in a.get("name", ""):
            return a
    for a in assets:
        if a.get("name", "").endswith(".zip"):
            return a
    raise RuntimeError("最新 Release 中没有可下载的 zip 资产。")


def verify_sha256(path: Path, asset_name: str, release: dict) -> str:
    expected = None
    for a in release.get("assets") or []:
        if a.get("name") == asset_name + ".sha256":
            tmp = path.with_suffix(".sha256")
            download(a["browser_download_url"], tmp)
            expected = tmp.read_text(encoding="utf-8").split()[0]
            tmp.unlink(missing_ok=True)
            break
    if expected is None:
        try:
            req = urllib.request.Request(f"{RAW_BASE}/{asset_name}.sha256", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as r:
                expected = r.read().decode("utf-8").split()[0]
        except Exception:
            expected = None
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected and expected.lower() != actual.lower():
        raise RuntimeError(f"SHA-256 校验失败：expected={expected}, actual={actual}")
    return actual


def locate_skill_sources(root: Path) -> dict[str, Path]:
    found = {}
    for skill_md in root.rglob("SKILL.md"):
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?m)^name:\s*[\"']?([^\n\"']+)", text)
        name = (m.group(1).strip() if m else skill_md.parent.name)
        if name in {"dp-cj", "dp-cj-update"}:
            found[name] = skill_md.parent
    return found


def sync_skill(src: Path, dst: Path):
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if "__pycache__" in rel.parts or p.suffix.lower() == ".pyc" or rel.name == "config.json":
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    if not (dst / "config.json").exists() and (src / "config.example.json").exists():
        shutil.copy2(src / "config.example.json", dst / "config.json")


def run_checks(skill_dir: Path) -> tuple[bool, str]:
    config = skill_dir / "config.json"
    if not config.exists():
        return False, "config.json 不存在"
    setup = subprocess.run([sys.executable, str(skill_dir / "scripts" / "setup_workspace.py"), "--config", str(config)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    doctor = subprocess.run([sys.executable, str(skill_dir / "scripts" / "doctor.py"), "--config", str(config), "--live"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = setup.returncode == 0 and doctor.returncode == 0
    detail = (doctor.stdout or doctor.stderr).strip()[-1200:]
    return ok, detail


def main() -> int:
    ap = argparse.ArgumentParser(description="从 GitHub 更新 WorkBuddy Skill dp-cj")
    ap.add_argument("--target", default=None, help="已安装 dp-cj 目录")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()
    try:
        target = discover_target(args.target)
        local = read_local_version(target)
        release = http_json(API_LATEST)
        remote = str(release.get("tag_name") or release.get("name") or "").lstrip("v")
        asset = find_release_asset(release)
        update_available = semver(remote) > semver(local)
        if args.check_only:
            print(json.dumps({"ok": True, "local": local, "remote": remote, "update_available": update_available, "release_url": release.get("html_url"), "asset": asset.get("name")}, ensure_ascii=False, indent=2))
            return 0
        if not update_available:
            print(json.dumps({"ok": True, "status": "already_latest", "local": local, "remote": remote}, ensure_ascii=False, indent=2))
            return 0
        with tempfile.TemporaryDirectory(prefix="dp-cj-update-") as td:
            td_path = Path(td)
            zip_path = td_path / asset["name"]
            download(asset["browser_download_url"], zip_path)
            sha = verify_sha256(zip_path, asset["name"], release)
            extract_dir = td_path / "extracted"
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(extract_dir)
            sources = locate_skill_sources(extract_dir)
            if "dp-cj" not in sources:
                raise RuntimeError("更新包中找不到 dp-cj Skill。")
            backup_path = None
            if not args.no_backup:
                backup_path = target.parent / f"{target.name}-backup-{time.strftime('%Y%m%d-%H%M%S')}"
                shutil.copytree(target, backup_path)
            sync_skill(sources["dp-cj"], target)
            updated = ["dp-cj"]
            if "dp-cj-update" in sources:
                update_target = target.parent / "dp-cj-update"
                update_target.mkdir(parents=True, exist_ok=True)
                sync_skill(sources["dp-cj-update"], update_target)
                updated.append("dp-cj-update")
            checks_ok, checks_detail = run_checks(target)
            cache = Path.home() / ".workbuddy" / "dp-cj"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "update_check_at").write_text(str(int(time.time())), encoding="utf-8")
            print(json.dumps({
                "ok": checks_ok,
                "status": "updated" if checks_ok else "updated_with_check_error",
                "local": local,
                "remote": remote,
                "updated_skills": updated,
                "backup": str(backup_path) if backup_path else None,
                "sha256": sha,
                "checks": checks_detail,
                "new_session_required": True,
            }, ensure_ascii=False, indent=2))
            return 0 if checks_ok else 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
