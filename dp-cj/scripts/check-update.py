from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

UPDATE_URL = "https://raw.githubusercontent.com/sud981953-netizen/dp-cj/main/UPDATE.json"
CACHE = Path.home() / ".workbuddy" / "dp-cj" / "update_check_at"
TTL = 86400


def semver(value: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", value or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def main() -> int:
    skill_dir = Path(__file__).resolve().parents[1]
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"(?m)^\s*version:\s*[\"']?([^\n\"']+)", text)
    local = m.group(1).strip() if m else "0.0.0"
    now = int(time.time())
    if CACHE.exists():
        try:
            last = int(CACHE.read_text(encoding="utf-8").strip())
            if now - last < TTL:
                return 0
        except Exception:
            pass
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(str(now), encoding="utf-8")
    try:
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": "dp-cj-update-check"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        remote = str(data.get("version") or "")
        notice = str(data.get("notice") or "").strip()
        if semver(remote) > semver(local):
            print(f"dp-cj v{remote}：{notice} 输入 /dp-cj-update 更新。")
    except Exception:
        return 0
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

