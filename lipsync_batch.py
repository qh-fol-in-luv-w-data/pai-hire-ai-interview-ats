"""
Kling AI Lip-sync — Parallel Batch
1 ảnh × 256 audio → 256 video, chạy song song

Usage:
    python lipsync_batch.py              # full batch (8 workers)
    python lipsync_batch.py --workers 5  # ít hơn nếu bị rate-limit
    python lipsync_batch.py --dry-run    # xem danh sách task, không gọi API
"""

import argparse
import base64
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests

try:
    import jwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

os.chdir(Path(__file__).parent)

# ─── Config ───────────────────────────────────────────────────
BASE_URL      = "https://api.klingai.com"
KLING_API_KEY = os.getenv("KLING_API_KEY", "")   # key mới (Bearer trực tiếp)
KLING_AK      = os.getenv("KLING_AK", "")         # key cũ (JWT)
KLING_SK      = os.getenv("KLING_SK", "")
POLL_INTERVAL = 8    # giây giữa mỗi lần poll
MAX_WAIT      = 600  # 10 phút timeout mỗi task

AUDIO_DIR  = Path("inputs/audios")
IMAGE_DIR  = Path("inputs/images")
OUTPUT_DIR = Path("outputs/videos")

_log_lock = Lock()

def log(*args):
    with _log_lock:
        print(*args, flush=True)


# ─── Auth ─────────────────────────────────────────────────────
def auth_headers() -> dict:
    if KLING_API_KEY:
        return {
            "Authorization": f"Bearer {KLING_API_KEY}",
            "Content-Type":  "application/json",
        }
    if KLING_AK and KLING_SK:
        if not HAS_JWT:
            print("[Lỗi] Cần pip install pyjwt để dùng AK+SK")
            sys.exit(1)
        payload = {
            "iss": KLING_AK,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5,
        }
        token = jwt.encode(payload, KLING_SK, algorithm="HS256")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("[Lỗi] Chưa set KLING_API_KEY (hoặc KLING_AK + KLING_SK) trong .env")
    sys.exit(1)


# ─── Bước 1: ảnh → video (chạy 1 lần duy nhất) ───────────────
def image_to_video(image_path: Path) -> str:
    log(f"[IMG→VID] Tạo base video từ {image_path.name} ...")
    suffix = image_path.suffix.lower().lstrip(".")
    mime   = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
    img_b64 = base64.b64encode(image_path.read_bytes()).decode()

    for attempt in range(5):
        resp = requests.post(
            f"{BASE_URL}/v1/videos/image2video",
            headers=auth_headers(),
            json={
                "model_name": "kling-v1",
                "image":       f"data:{mime};base64,{img_b64}",
                "duration":    5,
                "cfg_scale":   0.5,
            },
            timeout=30,
        )
        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            log(f"[IMG→VID] 429 rate-limit, thử lại sau {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        resp.raise_for_status()
    task_id = resp.json()["data"]["task_id"]
    log(f"[IMG→VID] task={task_id} — đang chờ...")

    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        r = requests.get(
            f"{BASE_URL}/v1/videos/image2video/{task_id}",
            headers=auth_headers(), timeout=15,
        )
        r.raise_for_status()
        data   = r.json()["data"]
        status = data.get("task_status", "")
        if status == "succeed":
            vid_id = data["task_result"]["videos"][0]["id"]
            log(f"[IMG→VID] ✓ video_id={vid_id}")
            return vid_id
        if status == "failed":
            raise RuntimeError(f"image2video thất bại: {data}")
        time.sleep(POLL_INTERVAL)

    raise TimeoutError("image2video timeout")


# ─── Bước 2+3: lip-sync + download (chạy song song) ──────────
def process_one(base_video_id: str, audio_path: Path, out_path: Path) -> str:
    """Trả về 'ok' | 'skip' | 'fail'."""
    if out_path.exists():
        log(f"  [SKIP] {audio_path.stem}")
        return "skip"

    stem   = audio_path.stem
    suffix = audio_path.suffix.lower().lstrip(".")
    mime   = "audio/mpeg" if suffix == "mp3" else f"audio/{suffix}"
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()

    # Submit
    resp = requests.post(
        f"{BASE_URL}/v1/videos/lip-sync",
        headers=auth_headers(),
        json={"input": {
            "video_id":   base_video_id,
            "audio_type": "file",
            "audio_file": f"data:{mime};base64,{audio_b64}",
        }},
        timeout=30,
    )
    resp.raise_for_status()
    task_id = resp.json()["data"]["task_id"]
    log(f"  [SUB] {stem} → task={task_id}")

    # Poll
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        r = requests.get(
            f"{BASE_URL}/v1/videos/lip-sync/{task_id}",
            headers=auth_headers(), timeout=15,
        )
        r.raise_for_status()
        data   = r.json()["data"]
        status = data.get("task_status", "")
        if status == "succeed":
            url = data["task_result"]["videos"][0]["url"]
            # Download
            out_path.parent.mkdir(parents=True, exist_ok=True)
            dl = requests.get(url, stream=True, timeout=180)
            dl.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in dl.iter_content(8192):
                    f.write(chunk)
            size_mb = out_path.stat().st_size / 1024 / 1024
            log(f"  [OK]   {stem} → {out_path} ({size_mb:.1f} MB)")
            return "ok"
        if status == "failed":
            log(f"  [FAIL] {stem}: {data.get('task_status_msg','')}")
            return "fail"
        time.sleep(POLL_INTERVAL)

    log(f"  [TOUT] {stem} — timeout sau {MAX_WAIT}s")
    return "fail"


# ─── Helpers ──────────────────────────────────────────────────
def get_position(stem: str) -> str:
    """
    Junior_AIML_Engineer_03_Soft Skill → Junior_AIML_Engineer
    Junior_Account_Executive_(Agency)_01_Technical → Junior_Account_Executive_(Agency)
    """
    m = re.match(r"^(.+)_(\d{2})_", stem)
    return m.group(1) if m else stem


def find_image() -> Path:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    imgs = [f for f in IMAGE_DIR.glob("*") if f.suffix.lower() in exts]
    if not imgs:
        print(f"[Lỗi] Không có ảnh trong {IMAGE_DIR}/"); sys.exit(1)
    return sorted(imgs)[0]


# ─── Main ─────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers",  type=int, default=8, help="Số luồng song song")
    ap.add_argument("--image",    default=None, help="Override ảnh avatar")
    ap.add_argument("--dry-run",  action="store_true", help="In task list, không gọi API")
    args = ap.parse_args()

    image_path = Path(args.image) if args.image else find_image()

    audios = sorted(AUDIO_DIR.glob("*.mp3"))
    if not audios:
        print(f"[Lỗi] Không có mp3 trong {AUDIO_DIR}/"); sys.exit(1)

    # Build task list
    tasks = []
    for audio in audios:
        pos     = get_position(audio.stem)
        out     = OUTPUT_DIR / pos / f"{audio.stem}.mp4"
        tasks.append((audio, out))

    pending = [(a, o) for a, o in tasks if not o.exists()]
    done_pre = len(tasks) - len(pending)

    log(f"\n{'='*60}")
    log(f"  Ảnh avatar : {image_path.name}")
    log(f"  Audio files: {len(audios)}")
    log(f"  Đã có      : {done_pre} video")
    log(f"  Cần tạo    : {len(pending)} video")
    log(f"  Workers    : {args.workers}")
    log(f"  Output     : {OUTPUT_DIR}/{{Position}}/{{stem}}.mp4")
    log(f"{'='*60}\n")

    if args.dry_run:
        for audio, out in pending[:20]:
            print(f"  {audio.name} → {out}")
        if len(pending) > 20:
            print(f"  ... và {len(pending)-20} file nữa")
        return

    if not pending:
        log("Tất cả đã xong!"); return

    # Step 1: tạo base video 1 lần
    base_video_id = image_to_video(image_path)
    log(f"\n[BATCH] Bắt đầu {len(pending)} tasks với {args.workers} workers...\n")

    counts = {"ok": 0, "skip": 0, "fail": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {
            pool.submit(process_one, base_video_id, audio, out): audio.stem
            for audio, out in pending
        }
        for fut in as_completed(future_map):
            stem = future_map[fut]
            try:
                result = fut.result()
                counts[result] += 1
            except Exception as e:
                log(f"  [ERR] {stem}: {e}")
                counts["fail"] += 1

    log(f"\n{'='*60}")
    log(f"Kết quả: {counts['ok']} OK  |  {done_pre + counts['skip']} skip  |  {counts['fail']} lỗi")
    log(f"Videos tại: {OUTPUT_DIR}/")
    log(f"{'='*60}")


if __name__ == "__main__":
    main()
