from __future__ import annotations

import argparse
from pathlib import Path

from config_util import ConfigError, config_root, load_config
from migrate_config import migrate_config

def main() -> int:
    ap = argparse.ArgumentParser(description="初始化短视频文案提取工作区")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    try:
        if migrate_config(args.config):
            print("[OK] 已补充官方 Base 的新分类与行业映射；原配置已备份，本地路径与自定义配置保留。")
        cfg, cfg_path = load_config(args.config)
        root = config_root(cfg, cfg_path)
    except ConfigError as e:
        print(f"[FAIL] {e}")
        return 2
    dirs = [root, root / str(cfg.get("archive_dir", "01_口播文案库")), root / str(cfg.get("tmp_dir", "_tmp"))]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"[OK] 工作区：{root}")
    for d in dirs[1:]:
        print(f"[OK] 目录：{d}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
