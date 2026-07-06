import argparse
import base64
import json
import os
import sys
import time
import unicodedata
from pathlib import Path
import requests

BASE_URL      = "https://api.klingai.com"
KLING_API_KEY = os.environ.get("KLING_API_KEY", "")
POLL_INTERVAL = 5
MAX_WAIT      = 600

def auth_headers() -> dict:
    if not KLING_API_KEY:
        print("[Lỗi] Chưa set KLING_API_KEY")
        sys.exit(1)
    return {"Authorization": f"Bearer {KLING_API_KEY}", "Content-Type": "application/json"}

def call_api_with_retry(method, url, **kwargs):
    max_retries = 10
    for i in range(max_retries):
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 429:
            print(f"       [Rate Limit] 429 Too Many Requests. Chờ {15 * (i+1)}s...")
            time.sleep(15 * (i+1))
            continue
        resp.raise_for_status()
        return resp
    raise Exception("Max retries exceeded for 429")

def image_to_video_kling(image_path: Path) -> str:
    print(f"  [1/3] Tạo video từ ảnh: {image_path.name}")
    img_b64 = base64.b64encode(image_path.read_bytes()).decode()
    suffix  = image_path.suffix.lower().lstrip(".")
    mime    = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"

    payload = {
        "model_name": "kling-v1",
        "image":       f"data:{mime};base64,{img_b64}",
        "duration":    5,
        "cfg_scale":   0.5,
    }
    resp = call_api_with_retry("POST", f"{BASE_URL}/v1/videos/image2video", headers=auth_headers(), json=payload, timeout=30)
    task_id = resp.json()["data"]["task_id"]
    print(f"       image2video task: {task_id} — đang chờ...")
    return _poll_video_task(task_id, endpoint="image2video")

def _poll_video_task(task_id: str, endpoint: str) -> str:
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        resp = call_api_with_retry("GET", f"{BASE_URL}/v1/videos/{endpoint}/{task_id}", headers=auth_headers(), timeout=15)
        data   = resp.json()["data"]
        status = data.get("task_status", "")

        if status == "succeed":
            video_id = data["task_result"]["videos"][0]["id"]
            print(f"       Video ID: {video_id}")
            return video_id
        if status == "failed":
            print(f"[Lỗi] Task {task_id} thất bại: {data}")
            sys.exit(1)

        print(f"       Trạng thái: {status} — chờ {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)
    print(f"[Lỗi] Timeout sau {MAX_WAIT}s")
    sys.exit(1)

def create_lipsync(video_id: str, audio_path: Path) -> str:
    print(f"  [2/3] Lip-sync: video_id={video_id} + {audio_path.name}")
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()
    suffix    = audio_path.suffix.lower().lstrip(".")
    mime      = "audio/mpeg" if suffix == "mp3" else f"audio/{suffix}"

    payload = {
        "input": {
            "video_id":   video_id,
            "audio_type": "file",
            "audio_file": f"data:{mime};base64,{audio_b64}",
        }
    }
    resp = call_api_with_retry("POST", f"{BASE_URL}/v1/videos/lip-sync", headers=auth_headers(), json=payload, timeout=30)
    task_id = resp.json()["data"]["task_id"]
    print(f"       Lip-sync task: {task_id}")
    return task_id

def poll_lipsync(task_id: str) -> str:
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        resp = call_api_with_retry("GET", f"{BASE_URL}/v1/videos/lip-sync/{task_id}", headers=auth_headers(), timeout=15)
        data   = resp.json()["data"]
        status = data.get("task_status", "")

        if status == "succeed":
            url = data["task_result"]["videos"][0]["url"]
            print(f"       Video URL nhận được.")
            return url
        if status == "failed":
            print(f"[Lỗi] Lip-sync task thất bại: {data}")
            sys.exit(1)

        print(f"       Trạng thái: {status} — chờ {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)
    print(f"[Lỗi] Timeout sau {MAX_WAIT}s")
    sys.exit(1)

def download_video(url: str, out_path: Path) -> None:
    print(f"  [3/3] Download → {out_path.name}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"       Đã lưu ({size_mb:.1f} MB)")

def process_one(image_path: Path, audio_path: Path, out_path: Path) -> None:
    if out_path.exists():
        print(f"  [BỎ QUA] {out_path.name} đã có.")
        return
    print(f"\n{'='*55}")
    print(f"  Ảnh : {image_path.name}")
    print(f"  Audio: {audio_path.name}")
    print(f"  Output: {out_path.name}")
    print(f"{'='*55}")
    video_id = image_to_video_kling(image_path)
    task_id  = create_lipsync(video_id, audio_path)
    url      = poll_lipsync(task_id)
    download_video(url, out_path)

def batch_run(image_dir: Path, audio_dir: Path, out_dir: Path) -> None:
    images = sorted(f for f in image_dir.glob("*") if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    audios = sorted(f for f in audio_dir.glob("*") if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac"})
    pairs = []
    for audio in audios:
        img = next((i for i in images if i.stem == audio.stem), images[0])
        out = out_dir / f"{img.stem}_{audio.stem}.mp4"
        pairs.append((img, audio, out))
    pairs = pairs[:1]
    print(f"[Batch] {len(pairs)} cặp cần xử lý")
    done = 0
    for img, audio, out in pairs:
        try:
            process_one(img, audio, out)
            done += 1
        except Exception as e:
            print(f"  [LỖI] {audio.name}: {e}")
    print(f"\nHoàn tất: {done}/{len(pairs)}")

if __name__ == "__main__":
    for d in ["inputs/images", "inputs/audios", "outputs"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    batch_run(Path("inputs/images"), Path("inputs/audios"), Path("outputs"))
