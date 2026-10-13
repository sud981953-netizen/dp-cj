# -*- coding: utf-8 -*-
"""
一键提取抖音视频口播文案（无需外部付费服务）
归属：dp-cj 模板包

用法:
    python douyin_transcript.py "<分享文案或视频链接>" [--out-dir DIR] [--headed] [--vad] [--no-md]
    python douyin_transcript.py --file "本地视频或音频.mp4" [--author 作者] [--link 原链接]

流程:
    1. 解析分享链接得到视频ID
    2. 无头浏览器打开视频页, 拦截: a) 作品详情JSON b) 音频流地址 c) 官方字幕(.vtt)
    3. 优先直接使用官方字幕(最快, 无需语音识别); 否则下载音频流 -> PyAV 转 16k WAV
    4. SenseVoice 本地语音识别(模型缓存于 ~/.cache/modelscope)
    5. 输出 Markdown 到 config.json 配置的 archive_dir/{作者}/{标题}.md

--file 模式: 本地媒体文件直接转写(跳过浏览器), 元数据取自文件与可选参数;
    配合 --link 可补全视频ID/原链接, 供入库查重使用。

配置与安装见 skill 根目录 README_安装配置.md。
"""
import argparse
import datetime
import io
import json
import os
import re
import subprocess
from pathlib import Path
import sys
import time
import wave

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CONFIG = {}
TRANSCRIBE = ""
MODEL_DIR = os.path.expanduser(
    r"~/.cache/modelscope/models/poloniumrock--SenseVoiceSmallOnnx/snapshots/master"
)


def load_runtime_config(path=None):
    from config_util import load_config, resolve_path
    cfg, cfg_path = load_config(path)
    extraction = cfg.get("extraction", {})
    transcribe = extraction.get("transcribe_script")
    if transcribe and not str(transcribe).startswith("REPLACE_ME"):
        transcribe = str(resolve_path(cfg, transcribe, cfg_path))
    model_dir = extraction.get("model_dir")
    return cfg, cfg_path, transcribe or "", Path(model_dir).expanduser() if model_dir else Path(MODEL_DIR)


def fail(msg):
    print(f"[error] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def extract_link(text):
    m = re.search(r"https?://v\.douyin\.com/[\w-]+/?|https?://www\.douyin\.com/video/\d+", text)
    return m.group(0) if m else None


def resolve_video_id(url):
    if "/video/" in url:
        m = re.search(r"/video/(\d+)", url)
        if m:
            return m.group(1)
    r = requests.get(url, headers={"User-Agent": UA}, allow_redirects=False, timeout=15)
    m = re.search(r"/video/(\d+)", r.headers.get("Location", ""))
    if not m:
        fail(f"无法从链接解析视频ID: {url}")
    return m.group(1)


def open_in_browser(vid, headed=False):
    """返回 (found_dict, page_title)。found: audio_url / vtt_url / detail / media_urls"""
    from playwright.sync_api import sync_playwright

    found = {"audio_url": None, "video_url": None, "vtt_url": None, "detail": {}, "media_urls": []}
    args = [
        "--mute-audio",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-blink-features=AutomationControlled",
    ]
    with sync_playwright() as p:
        browser = None
        for channel in ("chrome", "msedge", None):
            try:
                kw = dict(headless=not headed, args=args,
                          ignore_default_args=["--enable-automation"])
                if channel:
                    kw["channel"] = channel
                browser = p.chromium.launch(**kw)
                print(f"[browser] channel={channel or 'chromium'}", flush=True)
                break
            except Exception:
                continue
        if browser is None:
            fail("未找到可用浏览器。请运行: python -m playwright install chromium")

        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1280, "height": 800})
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        page = ctx.new_page()

        def on_request(req):
            u = req.url
            if "douyinvod.com" in u and "/video/tos/" in u:
                if not found["audio_url"] and ("media-audio" in u or "/media/tos/" in u):
                    found["audio_url"] = u
                if not found["video_url"] and "media-video" in u:
                    found["video_url"] = u
                found["media_urls"].append(u)

        def on_response(resp):
            if "/aweme/v1/web/aweme/detail" in resp.url and not found["detail"]:
                try:
                    found["detail"] = resp.json()
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        try:
            page.goto(f"https://www.douyin.com/video/{vid}",
                      timeout=45000, wait_until="domcontentloaded")
            page.wait_for_selector("video", timeout=15000)
            page.evaluate(
                "document.querySelectorAll('video').forEach(v=>{v.muted=true;v.play().catch(()=>{})})"
            )
        except Exception as e:
            print(f"[warn] 页面加载异常: {e}", file=sys.stderr, flush=True)

        # 最多等 30 秒拿媒体流地址；抓到视频轨后再给音频轨 5 秒（优先语音识别）
        waited_video = 0
        for _ in range(30):
            if found["audio_url"]:
                break
            if found["video_url"]:
                waited_video += 1
                if waited_video >= 5:
                    break
            page.wait_for_timeout(1000)

        # 从详情 JSON 里找官方字幕
        try:
            s = json.dumps(found["detail"], ensure_ascii=False)
            m = re.search(r'https://[^\s"\\]+\.vtt', s)
            if m:
                found["vtt_url"] = m.group(0)
        except Exception:
            pass

        title = page.title()
        browser.close()
    return found, title


def choose_cover(video):
    candidates = []
    for key in ("origin_cover", "cover", "dynamic_cover"):
        node = video.get(key)
        if not isinstance(node, dict):
            continue
        urls = node.get("url_list") or []
        if not urls:
            continue
        width = int(node.get("width") or 0)
        height = int(node.get("height") or 0)
        vertical_bonus = 1_000_000 if height > width * 1.15 else 0
        score = vertical_bonus + width * height
        candidates.append((score, key, urls[0], width, height))
    if not candidates:
        return "", 0, 0
    _score, _key, url, width, height = max(candidates, key=lambda x: x[0])
    return url, width, height


def parse_detail(detail, page_title):
    item = detail.get("aweme_detail") or {}
    author = (item.get("author") or {}).get("nickname", "")
    desc = item.get("desc", "") or page_title.replace(" - 抖音", "")
    st = item.get("statistics") or {}
    ts = item.get("create_time")
    pub = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "—"
    video = item.get("video") or {}
    dur_ms = item.get("duration") or video.get("duration") or 0
    cover_url, cover_width, cover_height = choose_cover(video)
    return {
        "author": author,
        "desc": desc,
        "publish": pub,
        "duration": round(dur_ms / 1000),
        "digg": st.get("digg_count", "—"),
        "comment": st.get("comment_count", "—"),
        "collect": st.get("collect_count", "—"),
        "share": st.get("share_count", "—"),
        "cover_url": cover_url,
        "cover_width": cover_width,
        "cover_height": cover_height,
    }


def vtt_to_paragraphs(vtt_text):
    lines = []
    for raw in vtt_text.splitlines():
        t = raw.strip()
        if (not t or t.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or "-->" in t or t.isdigit()):
            continue
        clean = re.sub(r"<[^>]+>", "", t)
        if clean and (not lines or clean != lines[-1]):
            lines.append(clean)
    # 每 5 行合成一段
    return ["".join(lines[i:i + 5]) for i in range(0, len(lines), 5)]


def download(url, dst):
    r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"},
                     timeout=180, stream=True)
    r.raise_for_status()
    total = 0
    with open(dst, "wb") as f:
        for chunk in r.iter_content(256 * 1024):
            if chunk:
                f.write(chunk)
                total += len(chunk)
    if total < 4096:
        fail(f"下载内容过小({total}B), 地址可能已过期: {url}")
    return total


def to_wav_16k(src, dst):
    import av
    import av.audio.resampler

    inp = av.open(src)
    try:
        astreams = [s for s in inp.streams if s.type == "audio"]
        if not astreams:
            fail("该文件不含音轨")
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        with wave.open(dst, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            for frame in inp.decode(astreams[0]):
                rf = rs.resample(frame)
                if rf is None:
                    continue
                for of in (rf if isinstance(rf, list) else [rf]):
                    data = bytes(of.planes[0])
                    if data:
                        w.writeframes(data)
    finally:
        inp.close()


def run_asr(wav_path, txt_path, use_vad=False):
    if not TRANSCRIBE or not os.path.isfile(TRANSCRIBE):
        fail("未配置可用的 transcribe.py；请在 config.json 的 extraction.transcribe_script 中填写路径")
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(
        p for p in env["PATH"].split(os.pathsep)
        if "resources\\app\\bin" not in p.lower()
    )
    cmd = [sys.executable, TRANSCRIBE, wav_path, "--out", txt_path,
           "--lang", "zh", "--num-threads", "8"]
    if use_vad:
        vad = os.path.expanduser(r"~\.cache\silero_vad.onnx")
        if os.path.isfile(vad):
            cmd += ["--vad", vad]
    if os.path.isfile(os.path.join(MODEL_DIR, "model.int8.onnx")):
        cmd += ["--model-dir", MODEL_DIR]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 or not os.path.isfile(txt_path):
        fail(f"语音识别失败: {r.stdout} {r.stderr}")


def paragraphs_from_text(text, group=4):
    parts = re.split(r"(?<=[。！？；])", text)
    parts = [p for p in parts if p.strip()]
    return ["".join(parts[i:i + group]) for i in range(0, len(parts), group)]


OCR_PS1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_frames.ps1")


def ocr_subtitles(video_path, vid):
    """第三级兜底：视频轨 1fps 抽帧 → 裁底部字幕带 → Windows OCR → 去重成段落"""
    import shutil

    import av
    work = os.path.join(os.environ.get("TEMP", "."), f"dy_{vid}_frames")
    os.makedirs(work, exist_ok=True)
    container = av.open(video_path)
    stream = container.streams.video[0]
    next_t, idx = 0.0, 0
    for frame in container.decode(stream):
        t = float(frame.time or 0)
        if t + 1e-3 >= next_t:
            img = frame.to_image()
            w, h = img.size
            img.crop((0, int(h * 0.60), w, h)).save(
                os.path.join(work, f"f_{idx + 1:03d}.jpg"), quality=90)
            idx += 1
            next_t += 1.0
    container.close()
    if idx == 0:
        fail("视频轨抽帧失败")
    print(f"[ocr] {idx} frames", flush=True)

    out_txt = os.path.join(work, "ocr.txt")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         OCR_PS1, "-FramesDir", work, "-OutputFile", out_txt],
        capture_output=True, text=True, encoding="utf-8")
    if not os.path.isfile(out_txt):
        fail(f"OCR失败: {r.stdout} {r.stderr}")

    lines = []
    for raw in open(out_txt, encoding="utf-8-sig").read().splitlines():
        parts = raw.split("|", 1)
        text = parts[1].strip() if len(parts) == 2 else ""
        if not text or len(text) < 4:
            continue
        if "@" in text or "<<" in text or ">>" in text:  # 水印/装饰符
            continue
        if lines and (text == lines[-1] or text in lines[-1] or lines[-1] in text):
            continue
        lines.append(text)
    shutil.rmtree(work, ignore_errors=True)
    if not lines:
        fail("OCR未识别到字幕(视频可能无硬字幕)")
    return ["".join(lines[i:i + 5]) for i in range(0, len(lines), 5)]


def sanitize(name):
    return re.sub(r'[\\/:*?"<>|#，。\s！？—-]+', "", name)[:50] or "douyin_video"


def write_md(path, meta, paragraphs, method, link, vid):
    dur = meta["duration"]
    dur_s = f"{dur // 60:02d}:{dur % 60:02d}" if dur else "—"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {meta['desc']}\n\n")
        f.write("| 项目 | 内容 |\n| --- | --- |\n")
        f.write(f"| 作者 | {meta['author'] or '—'} |\n")
        f.write(f"| 发布时间 | {meta['publish']} |\n")
        f.write(f"| 时长 | {dur_s} |\n")
        f.write(f"| 互动数据 | 点赞 {meta['digg']} / 评论 {meta['comment']} "
                f"/ 收藏 {meta['collect']} / 分享 {meta['share']} |\n")
        f.write(f"| 视频ID | {vid} |\n")
        f.write(f"| 转写方式 | {method} |\n")
        f.write(f"| 原链接 | {link} |\n")
        if meta.get("cover_url"):
            f.write(f"| 封面 | {meta['cover_url']} |\n")
        f.write("\n")
        f.write("## 口播文案\n\n")
        for p in paragraphs:
            f.write(f"{p}\n\n")
        if method.startswith("语音识别"):
            f.write("> 机器转写，个别同音字可能有误差，引用前建议对照视频复核。\n")


def to_int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def build_payload(meta, paragraphs, method, link, vid, category, default_platform):
    desc = str(meta.get("desc") or "").strip()
    title = re.sub(r"#\S+", "", desc).strip() or desc
    full_text = "\n\n".join(paragraphs)
    flat = re.sub(r"\s+", "", full_text)
    sentences = [s.strip() for s in re.split(r"(?<=[。！？])", flat) if s.strip()]
    first = sentences[0] if sentences else flat[:60]
    title_pos = first.find(title) if title else -1
    if title_pos >= 0:
        prefix = first[:title_pos].strip("，：；")
        opening = f"{prefix}，{title}。" if prefix else f"{title}。"
        remainder = first[title_pos + len(title):].strip("，：；")
    else:
        clauses = [s.strip() for s in re.split(r"(?<=[，：；])", first) if s.strip()]
        opening = ""
        for clause in clauses:
            if opening and len(opening + clause) > 60:
                break
            opening += clause
        opening = opening or first[:60]
        remainder = first[len(opening):].strip("，：；")
    candidates = ([remainder] if remainder else []) + [s.strip("，：；") for s in sentences[1:]]
    gold = [s for s in candidates if 8 <= len(s) <= 60][:2]
    opening_and_golden = f"开头：{opening}\n金句：\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(gold, 1))
    platform = "抖音" if "douyin.com" in str(link) else (default_platform or "抖音")
    publish = str(meta.get("publish") or "")
    published_date = publish[:10] if re.match(r"\d{4}-\d{2}-\d{2}", publish) else ""
    seconds = to_int(meta.get("duration"))
    return {
        "category": category or "",
        "title": title,
        "full_text": full_text,
        "opening_and_golden": opening_and_golden,
        "topic": title[:30],
        "source_url": link if str(link).startswith(("http://", "https://")) else "",
        "platform": platform,
        "published_date": published_date,
        "duration": f"{seconds // 60:02d}:{seconds % 60:02d}" if seconds else "",
        "likes": to_int(meta.get("digg")),
        "comments": to_int(meta.get("comment")),
        "collects": to_int(meta.get("collect")),
        "shares": to_int(meta.get("share")),
        "cover": meta.get("cover_url") or "",
    }


def emit_payload(args, meta, paragraphs, method, link, vid):
    if not args.payload_out:
        return
    default_platform = (CONFIG.get("extraction") or {}).get("default_platform", "抖音")
    payload = build_payload(meta, paragraphs, method, link, vid, args.category or "", default_platform)
    out = Path(args.payload_out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[payload] {out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("link", nargs="?", default=None,
                    help="抖音分享文案或视频链接（--file 模式下省略）")
    ap.add_argument("--file", dest="local_file", default=None,
                    help="本地视频/音频文件路径, 直接转写(跳过浏览器)")
    ap.add_argument("--author", default=None, help="--file 模式: 作者名(用于分目录)")
    ap.add_argument("--title", default=None, help="--file 模式: 标题(默认取文件名)")
    ap.add_argument("--link", dest="manual_link", default=None,
                    help="--file 模式: 原视频链接(供入库查重)")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--headed", action="store_true", help="有头模式(无头被风控时使用)")
    ap.add_argument("--vad", action="store_true",
                    help="VAD分段识别(背景音乐多的音频会被误切, 默认关闭)")
    ap.add_argument("--no-md", action="store_true", help="只在控制台输出文稿")
    ap.add_argument("--config", default=None, help="config.json 路径")
    ap.add_argument("--category", default=None, help="用户确认的分类表，写入 payload.category")
    ap.add_argument("--payload-out", default=None, help="输出结构化 payload JSON，减少手工整理字段")
    args = ap.parse_args()

    global CONFIG, TRANSCRIBE, MODEL_DIR
    CONFIG, _cfg_path, TRANSCRIBE, MODEL_DIR = load_runtime_config(args.config)

    t0 = time.time()

    # ---------- 模式A: 本地文件直接转写 ----------
    if args.local_file:
        src = os.path.abspath(args.local_file)
        if not os.path.isfile(src):
            fail(f"文件不存在: {src}")
        vid = ""
        url = args.manual_link or ""
        m = re.search(r"/video/(\d+)", url)
        if m:
            vid = m.group(1)

        # 时长取自容器(微秒), 发布时间以文件修改时间近似
        import av
        probe = av.open(src)
        dur = float(probe.duration or 0) / 1_000_000 if probe.duration else 0.0
        if not dur:
            for s in probe.streams:
                if s.duration:
                    dur = max(dur, float(s.duration) * float(s.time_base))
        probe.close()
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(src))
        meta = {
            "author": args.author or "本地导入",
            "desc": args.title or os.path.splitext(os.path.basename(src))[0],
            "publish": mtime.strftime("%Y-%m-%d %H:%M"),
            "duration": round(dur),
            "digg": "—", "comment": "—", "collect": "—", "share": "—",
        }
        print(f"[file] {os.path.basename(src)} | 时长≈{round(dur)}s", flush=True)

        tmp_wav = os.path.join(os.environ.get("TEMP", "."), f"dy_local_{int(t0)}.wav")
        method = "语音识别(SenseVoice本地)"
        paragraphs = None

        # 音频轨优先, 视频轨 OCR 兜底
        try:
            to_wav_16k(src, tmp_wav)
            txt = tmp_wav.replace(".wav", ".txt")
            run_asr(tmp_wav, txt, use_vad=args.vad)
            text = open(txt, encoding="utf-8").read().strip()
            paragraphs = paragraphs_from_text(text)
            os.remove(txt)
        except SystemExit:
            # 无音轨或 ASR 失败 → 落到视频轨 OCR 兜底
            print("[warn] 音频链路失败, 尝试视频轨 OCR 兜底", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[warn] 音频轨转写失败({e}), 尝试视频轨 OCR 兜底", file=sys.stderr, flush=True)
        if not paragraphs:
            try:
                paragraphs = ocr_subtitles(src, "local")
                method = "字幕OCR(本地)"
            except (IndexError, Exception) as e:
                fail(f"本地文件转写失败(无音轨且无视频字幕轨): {e}")
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)
        if not paragraphs:
            fail("未取得任何文稿内容")

        full = "\n\n".join(paragraphs)
        if args.no_md:
            print(full)
        else:
            # 默认输出到 config.json 配置的 archive_dir/{作者}/
            from config_util import config_root, load_config
            _cfg, _cfg_path = load_config(args.config)
            default_root = str(config_root(_cfg, _cfg_path))
            out_dir = args.out_dir or os.path.join(default_root, str(_cfg.get("archive_dir", "01_口播文案库")),
                                                   sanitize(meta["author"]) or "未知作者")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, sanitize(meta["desc"]) + ".md")
            write_md(path, meta, paragraphs, method, url or src, vid)
            print(f"[saved] {path}", flush=True)
        emit_payload(args, meta, paragraphs, method, url or src, vid)
        print(f"[done] 方式={method} | 段落={len(paragraphs)} | 字数≈{len(full.replace(chr(10),''))} | 耗时{time.time()-t0:.0f}s", flush=True)
        return

    # ---------- 模式B: 在线链接提取 ----------
    url = extract_link(args.link) or fail("未在输入中找到抖音链接")
    vid = resolve_video_id(url)
    print(f"[video] id={vid}", flush=True)

    found, page_title = open_in_browser(vid, headed=args.headed)
    meta = parse_detail(found["detail"], page_title)
    print(f"[meta] {meta['author']} | {meta['desc'][:40]} | 发布 {meta['publish']}", flush=True)

    tmp_wav = os.path.join(os.environ.get("TEMP", "."), f"dy_{vid}.wav")
    method = None
    paragraphs = None

    # 优先官方字幕
    if found["vtt_url"]:
        try:
            vtt = requests.get(found["vtt_url"], headers={"User-Agent": UA},
                               timeout=30).text
            paragraphs = vtt_to_paragraphs(vtt)
            if paragraphs:
                method = "官方字幕"
        except Exception as e:
            print(f"[warn] 字幕获取失败: {e}", file=sys.stderr, flush=True)

    # 回退1: 音频流 + 本地语音识别
    if not paragraphs and found["audio_url"]:
        tmp_mp4 = os.path.join(os.environ.get("TEMP", "."), f"dy_{vid}.m4a")
        try:
            n = download(found["audio_url"], tmp_mp4)
            print(f"[audio] {n} bytes", flush=True)
            to_wav_16k(tmp_mp4, tmp_wav)
            txt = tmp_wav.replace(".wav", ".txt")
            run_asr(tmp_wav, txt, use_vad=args.vad)
            text = open(txt, encoding="utf-8").read().strip()
            paragraphs = paragraphs_from_text(text)
            method = "语音识别(SenseVoice本地)"
            if os.path.exists(txt):
                os.remove(txt)
        except SystemExit:
            print("[warn] 音频流失败, 尝试视频轨音轨识别/OCR", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[warn] 音频流失败({e}), 尝试视频轨音轨识别/OCR", file=sys.stderr, flush=True)
        finally:
            if os.path.exists(tmp_mp4):
                os.remove(tmp_mp4)

    video_url = found["video_url"] or next(
        (u for u in found["media_urls"]
         if "media-video" in u or "mime_type=video_mp4" in u), None)
    tmp_v = None
    if not paragraphs:
        if not video_url:
            fail("未捕获到任何媒体流(可能被风控或需要登录)。可加 --headed 重试。")
        tmp_v = os.path.join(os.environ.get("TEMP", "."), f"dy_{vid}_v.mp4")
        n = download(video_url, tmp_v)
        print(f"[video-track] {n} bytes", flush=True)

        # 回退2: 从视频轨提取音频后本地语音识别（比 OCR 更准确）
        try:
            to_wav_16k(tmp_v, tmp_wav)
            txt = tmp_wav.replace(".wav", ".txt")
            run_asr(tmp_wav, txt, use_vad=args.vad)
            text = open(txt, encoding="utf-8").read().strip()
            paragraphs = paragraphs_from_text(text)
            method = "语音识别(SenseVoice本地·视频音轨)"
            if os.path.exists(txt):
                os.remove(txt)
        except SystemExit:
            print("[warn] 视频音轨识别失败, 尝试抽帧OCR硬字幕", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[warn] 视频音轨识别失败({e}), 尝试抽帧OCR硬字幕", file=sys.stderr, flush=True)

        # 回退3: 视频流 + 抽帧OCR硬字幕
        if not paragraphs:
            paragraphs = ocr_subtitles(tmp_v, vid)
            method = "字幕OCR(本地)"
    if tmp_v and os.path.exists(tmp_v):
        os.remove(tmp_v)
    if os.path.exists(tmp_wav):
        os.remove(tmp_wav)

    if not paragraphs:
        fail("未取得任何文稿内容")

    full = "\n\n".join(paragraphs)
    if args.no_md:
        print(full)
    else:
        # 默认输出到 config.json 配置的 archive_dir/{作者}/
        from config_util import config_root, load_config
        _cfg, _cfg_path = load_config(args.config)
        default_root = str(config_root(_cfg, _cfg_path))
        out_dir = args.out_dir or os.path.join(default_root, str(_cfg.get("archive_dir", "01_口播文案库")),
                                               sanitize(meta["author"]) or "未知作者")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, sanitize(meta["desc"]) + ".md")
        write_md(path, meta, paragraphs, method, url, vid)
        print(f"[saved] {path}", flush=True)

    emit_payload(args, meta, paragraphs, method, url, vid)
    print(f"[done] 方式={method} | 段落={len(paragraphs)} | 字数≈{len(full.replace(chr(10),''))} | 耗时{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
