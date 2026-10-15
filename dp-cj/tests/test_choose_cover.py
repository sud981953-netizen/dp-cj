# -*- coding: utf-8 -*-
"""choose_cover 回归验证：用 2026-10 实测元数据形态复现选图场景"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD_PATH = os.path.join(os.path.dirname(HERE), "scripts", "douyin_transcript.py")
spec = importlib.util.spec_from_file_location("dyt", MOD_PATH)
dyt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dyt)

def node(w, h, url):
    return {"width": w, "height": h, "url_list": [url]}

# 实测元数据尺寸：origin_cover 360x640、cover 720x720(实下440x330)、
# cover_original_scale 360x640(实下360x480)、dynamic_cover 720x720(实下724x966+)
FULL = {
    "origin_cover": node(360, 640, "U_ORIGIN"),
    "cover": node(720, 720, "U_COVER"),
    "cover_original_scale": node(360, 640, "U_COS"),
    "dynamic_cover": node(720, 720, "U_DYN"),
}

cases = [
    ("四字段齐全(本次踩坑场景)", FULL, None, "U_DYN"),
    ("无 dynamic_cover", {k: v for k, v in FULL.items() if k != "dynamic_cover"}, None, "U_COS"),
    ("仅横裁和截帧时留空", {"cover": FULL["cover"], "origin_cover": FULL["origin_cover"]}, None, ""),
    ("仅 origin_cover 不再错误兜底", {"origin_cover": FULL["origin_cover"]}, None, ""),
    ("图文 note(images[0] 优先, jpeg 变体)", FULL,
     {"images": [{"width": 1080, "height": 1920,
                  "url_list": ["https://p3.douyinpic.com/a~tplv-dy-aweme-images:q75.webp?lk=1",
                               "https://p9.douyinpic.com/a~tplv-dy-aweme-images:q75.webp?lk=1",
                               "https://p3.douyinpic.com/a~tplv-dy-aweme-images:q75.jpeg?lk=1"]}]},
     "https://p3.douyinpic.com/a~tplv-dy-aweme-images:q75.jpeg?lk=1"),
    ("图文 note 无 jpeg 变体回退首图", FULL,
     {"images": [{"width": 1080, "height": 1920,
                  "url_list": ["https://p3.douyinpic.com/a~tplv-dy-aweme-images:q75.webp?lk=1"]}]},
     "https://p3.douyinpic.com/a~tplv-dy-aweme-images:q75.webp?lk=1"),
    ("全缺", {}, None, ""),
]

failed = 0
for name, video, item, expect in cases:
    url, w, h = dyt.choose_cover(video, item)
    ok = url == expect
    failed += 0 if ok else 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={url!r} expect={expect!r} ({w}x{h})")

print("----")
print("ALL PASS" if failed == 0 else f"{failed} FAILED")
sys.exit(1 if failed else 0)
