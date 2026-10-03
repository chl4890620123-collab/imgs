from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO_URL = "https://github.com/chl4890620123-collab/imgs.git"
REPO_DIR = Path("/content/imgs")
COMFY_DIR = Path("/content/ComfyUI")
DRIVE_ROOT = Path("/content/drive/MyDrive/SASEOK_EP01")
MODEL_CACHE = Path(os.environ.get("SASEOK_MODEL_CACHE", "/content/wan22_model_cache"))
VENV_DIR = Path("/content/saseok-venv")
VENV_PY = VENV_DIR / "bin" / "python"
VENV_VERSION = "3"

WIDTH = int(os.environ.get("SASEOK_WIDTH", "832"))
HEIGHT = int(os.environ.get("SASEOK_HEIGHT", "480"))
FPS = int(os.environ.get("SASEOK_FPS", "24"))
FRAMES = int(os.environ.get("SASEOK_FRAMES", "121"))
STEPS = int(os.environ.get("SASEOK_STEPS", "20"))
CFG = float(os.environ.get("SASEOK_CFG", "5"))
MAX_SHOTS_PER_RUN = int(os.environ.get("SASEOK_MAX_SHOTS", "999"))
SCENE_START = int(os.environ.get("SASEOK_SCENE_START", "1"))
SCENE_END = int(os.environ.get("SASEOK_SCENE_END", "15"))

WORKFLOW_URL = (
    "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/"
    "refs/heads/main/templates/video_wan2_2_5B_ti2v.json"
)
MODEL_FILES = {
    "diffusion_models": ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"),
    "text_encoders": ("Comfy-Org/Wan_2.1_ComfyUI_repackaged", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    "vae": ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/vae/wan2.2_vae.safetensors"),
}

def sh(cmd, cwd=None, check=True, capture=False):
    print("$", " ".join(map(str, cmd)))
    return subprocess.run(list(map(str, cmd)), cwd=cwd, check=check, text=True, capture_output=capture)

def install_environment():
    print("\n=== 1/8 Colab GPU / isolated Python environment ===")
    if shutil.which("nvidia-smi") is None:
        raise RuntimeError("GPU 런타임이 아닙니다. Colab 메뉴에서 런타임 > 런타임 유형 변경 > GPU를 선택한 뒤 다시 실행하세요.")
    sh(["nvidia-smi"], check=False)
    sh(["apt-get", "-qq", "update"])
    sh(["apt-get", "-qq", "install", "-y", "ffmpeg", "git", "python3.12", "python3.12-venv"])

    # Colab's notebook kernel can be newer than the packages used by ComfyUI.
    # Recreate the venv when our environment recipe changes, so stale package
    # files can never survive between retries.
    if os.environ.get("SASEOK_VENV_ACTIVE") != "1":
        marker = VENV_DIR / ".saseok_venv_version"
        current = marker.read_text().strip() if marker.exists() else ""
        if current != VENV_VERSION:
            if VENV_DIR.exists():
                shutil.rmtree(VENV_DIR, ignore_errors=True)
            sh(["python3.12", "-m", "venv", str(VENV_DIR)])
            marker.write_text(VENV_VERSION)
        sh([str(VENV_PY), "-m", "pip", "install", "-q", "--no-cache-dir",
            "--upgrade", "pip", "setuptools", "wheel"])
        env = os.environ.copy()
        env["SASEOK_VENV_ACTIVE"] = "1"
        print("Re-launching renderer with:", VENV_PY)
        os.execve(str(VENV_PY), [str(VENV_PY), __file__], env)

    # All Python dependencies below are isolated from the Colab kernel.
    sh([sys.executable, "-m", "pip", "install", "-q", "--no-cache-dir",
        "comfy-cli",
        "huggingface_hub>=1.5,<2.0",
        "edge-tts",
        "pydub",
        "requests"])

def mount_drive():
    print("\n=== 2/8 Google Drive mount ===")
    from google.colab import drive
    if not Path("/content/drive/MyDrive").exists():
        drive.mount("/content/drive")
    DRIVE_ROOT.mkdir(parents=True, exist_ok=True)
    (DRIVE_ROOT / "clips").mkdir(exist_ok=True)
    (DRIVE_ROOT / "audio").mkdir(exist_ok=True)
    (DRIVE_ROOT / "scenes").mkdir(exist_ok=True)
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)

def ensure_repo():
    print("\n=== 3/8 Project checkout ===")
    if not REPO_DIR.exists():
        sh(["git", "clone", "--depth", "1", REPO_URL, str(REPO_DIR)])
    else:
        sh(["git", "fetch", "origin", "main"], cwd=REPO_DIR, check=False)
        sh(["git", "checkout", "main"], cwd=REPO_DIR, check=False)
        sh(["git", "reset", "--hard", "origin/main"], cwd=REPO_DIR, check=False)

def ensure_comfyui():
    print("\n=== 4/8 ComfyUI setup ===")
    if not COMFY_DIR.exists():
        sh(["git", "clone", "--depth", "1", "https://github.com/Comfy-Org/ComfyUI.git", str(COMFY_DIR)])
    else:
        sh(["git", "pull", "--ff-only"], cwd=COMFY_DIR, check=False)
    sh([sys.executable, "-m", "pip", "install", "-q", "--no-cache-dir",
        "-r", str(COMFY_DIR / "requirements.txt")])

    # ComfyUI has an unpinned Pillow dependency. On Colab we have seen mixed
    # Pillow files survive an upgrade, so remove both package metadata and PIL
    # module directories before installing one known-good wheel.
    sh([sys.executable, "-m", "pip", "uninstall", "-y", "Pillow"], check=False)
    site = sh([sys.executable, "-c",
        "import site; print(site.getsitepackages()[0])"], capture=True).stdout.strip()
    if site:
        site_dir = Path(site)
        for pat in ("PIL", "Pillow-*", "pillow-*"):
            for p in site_dir.glob(pat):
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
    sh([sys.executable, "-m", "pip", "install", "-q", "--no-cache-dir",
        "Pillow==10.4.0", "huggingface_hub>=1.5,<2.0"])

    # Do not capture stderr here: if this ever fails, the exact import error is
    # written into saseok_run.log for remote diagnosis.
    sh([sys.executable, "-c",
        "from PIL import Image, ImageDraw, ImageText; import PIL, huggingface_hub; "
        "print('Python OK / Pillow', PIL.__version__, '/ huggingface_hub', huggingface_hub.__version__)"])

def ensure_models():
    print("\n=== 5/8 Wan 2.2 5B models (ephemeral Colab disk) ===")
    from huggingface_hub import hf_hub_download
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    for kind, (repo_id, remote_path) in MODEL_FILES.items():
        filename = Path(remote_path).name
        repo_cache = MODEL_CACHE / repo_id.replace("/", "__")
        repo_cache.mkdir(parents=True, exist_ok=True)
        downloaded = Path(hf_hub_download(
            repo_id=repo_id,
            filename=remote_path,
            local_dir=str(repo_cache),
        ))
        target_dir = COMFY_DIR / "models" / kind
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(downloaded)
        print("Model ready:", target)

def restore_character_assets():
    print("\n=== 6/8 Character references / exact Go board ===")
    from PIL import Image, ImageDraw, ImageOps
    import requests

    # The four character sheets supplied in this project. These URLs are only
    # used as free reference-asset hosting; no paid video-generation API is called.
    character_urls = {
        "ria": os.environ.get("SASEOK_RIA_URL", "https://d2ol7oe51mr4n9.cloudfront.net/user_3K8w3qnBf69HOE6x120lAtgx9I2/028dc793-f7df-491e-a1b1-79170818f443.jpg"),
        "theo": os.environ.get("SASEOK_THEO_URL", "https://d2ol7oe51mr4n9.cloudfront.net/user_3K8w3qnBf69HOE6x120lAtgx9I2/9fc3f353-0447-4986-a86f-84bd34723ef0.jpg"),
        "karman": os.environ.get("SASEOK_KARMAN_URL", "https://d2ol7oe51mr4n9.cloudfront.net/user_3K8w3qnBf69HOE6x120lAtgx9I2/67bb030d-14f0-441f-940a-d0d209cf6208.jpg"),
        "jinwoo": os.environ.get("SASEOK_JINWOO_URL", "https://d2ol7oe51mr4n9.cloudfront.net/user_3K8w3qnBf69HOE6x120lAtgx9I2/f6361669-d210-4669-8350-aab51adaa293.jpg"),
    }

    input_dir = COMFY_DIR / "input" / "saseok"
    input_dir.mkdir(parents=True, exist_ok=True)
    for name, url in character_urls.items():
        src = input_dir / f"{name}.jpg"
        if not src.exists():
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            src.write_bytes(r.content)
        im = Image.open(src).convert("RGB")
        w, h = im.size
        left_sheet = im.crop((0, 0, int(w * 0.64), h))
        full = ImageOps.fit(left_sheet, (960, 540), method=Image.Resampling.LANCZOS, centering=(0.48, 0.46))
        full.save(input_dir / f"{name}_fullbody.jpg", quality=94)
        face_sheet = im.crop((int(w * 0.55), 0, w, int(h * 0.44)))
        portrait = ImageOps.fit(face_sheet, (960, 540), method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))
        portrait.save(input_dir / f"{name}_portrait.jpg", quality=94)

    W, H = 1280, 704
    board = Image.new("RGB", (W, H), (41, 34, 29))
    draw = ImageDraw.Draw(board)
    size = 620
    bx = (W - size) // 2
    by = (H - size) // 2
    draw.rounded_rectangle((bx - 20, by - 20, bx + size + 20, by + size + 20), 18, fill=(169, 119, 62))
    margin = 32
    step = (size - 2 * margin) / 18
    for i in range(19):
        x = bx + margin + i * step
        y = by + margin + i * step
        draw.line((x, by + margin, x, by + size - margin), fill=(31, 22, 15), width=2)
        draw.line((bx + margin, y, bx + size - margin, y), fill=(31, 22, 15), width=2)
    for ix, iy in [(3,3),(3,9),(3,15),(9,3),(9,9),(9,15),(15,3),(15,9),(15,15)]:
        x = bx + margin + ix * step
        y = by + margin + iy * step
        r = 5
        draw.ellipse((x-r,y-r,x+r,y+r), fill=(25,18,12))
    stones = [(9,9,"B"),(10,9,"W"),(8,10,"B"),(10,10,"W"),(7,8,"B"),(11,8,"W"),
              (4,4,"B"),(14,14,"W"),(5,14,"B"),(13,4,"W")]
    for ix, iy, c in stones:
        x = bx + margin + ix * step
        y = by + margin + iy * step
        r = 15
        fill = (15,15,18) if c == "B" else (238,235,226)
        outline = (4,4,6) if c == "B" else (180,175,165)
        draw.ellipse((x-r,y-r,x+r,y+r), fill=fill, outline=outline, width=2)
    board.save(input_dir / "go_board.png", quality=95)
    print("Character assets ready:", input_dir)

REF_MAP = {
    "jinwoo_portrait": "saseok/jinwoo_portrait.jpg",
    "jinwoo_fullbody": "saseok/jinwoo_fullbody.jpg",
    "ria_portrait": "saseok/ria_portrait.jpg",
    "ria_fullbody": "saseok/ria_fullbody.jpg",
    "theo_portrait": "saseok/theo_portrait.jpg",
    "theo_fullbody": "saseok/theo_fullbody.jpg",
    "karman_portrait": "saseok/karman_portrait.jpg",
    "karman_fullbody": "saseok/karman_fullbody.jpg",
    "go_board": "saseok/go_board.png",
}

def start_comfyui():
    import requests
    print("\n=== 7/8 Start ComfyUI ===")
    log = open("/content/comfyui.log", "w", buffering=1)
    proc = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188", "--lowvram"],
                            cwd=COMFY_DIR, stdout=log, stderr=subprocess.STDOUT)
    url = "http://127.0.0.1:8188/object_info"
    for _ in range(180):
        if proc.poll() is not None:
            log.flush()
            tail = Path("/content/comfyui.log").read_text(errors="ignore")[-6000:]
            raise RuntimeError("ComfyUI 시작 실패:\n" + tail)
        try:
            if requests.get(url, timeout=2).ok:
                os.environ["COMFY_LOCAL_URL"] = "http://127.0.0.1:8188"
                print("ComfyUI ready")
                return proc
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError("ComfyUI가 6분 안에 시작되지 않았습니다. /content/comfyui.log를 확인하세요.")

def load_episode():
    sys.path.insert(0, str(REPO_DIR / "colab"))
    from saseok_episode import EPISODE, VISUAL_STYLE, NEGATIVE_PROMPT, VOICE_MAP
    return EPISODE, VISUAL_STYLE, NEGATIVE_PROMPT, VOICE_MAP

def fetch_workflow():
    import requests
    r = requests.get(WORKFLOW_URL, timeout=60)
    r.raise_for_status()
    return r.json()

def set_widget(node, index, value):
    values = node.setdefault("widgets_values", [])
    while len(values) <= index:
        values.append(None)
    values[index] = value

def make_workflow(template, scene, shot_idx, shot, visual_style, negative_prompt):
    ref_key, shot_prompt = shot
    wf = copy.deepcopy(template)
    nodes = {str(n["id"]): n for n in wf["nodes"]}
    identity_note = ""
    if ref_key.startswith("jinwoo"):
        identity_note = " Preserve Seo Jin-woo identity: 28-year-old Korean man, black hair, slim build, calm intelligent eyes, restrained emotion."
    elif ref_key.startswith("ria"):
        identity_note = " Preserve Ria identity: 25-year-old red-haired female frontline commander, athletic build, battle-worn practical steel armor, red cloth, fierce eyes."
    elif ref_key.startswith("theo"):
        identity_note = " Preserve Theo identity: 17-year-old brown-haired male messenger, youthful face, slim agile build, weathered messenger clothes and light armor."
    elif ref_key.startswith("karman"):
        identity_note = " Preserve Karman identity: 52-year-old gray-haired male commander, short beard, old scar near one eye, imposing dark command armor."
    elif ref_key == "go_board":
        identity_note = " Exact 19x19 Go board with black and white round Go stones only. Never chess, never checkerboard, never chess pieces. Keep grid geometry recognizable."
    positive = (f"{visual_style}. Scene: {scene['title']}. {scene['base']}. Shot: {shot_prompt}."
                f"{identity_note} Real temporal motion, moving camera, natural parallax, no slideshow.")
    set_widget(nodes["6"], 0, positive)
    set_widget(nodes["7"], 0, negative_prompt)
    set_widget(nodes["55"], 0, WIDTH)
    set_widget(nodes["55"], 1, HEIGHT)
    set_widget(nodes["55"], 2, FRAMES)
    set_widget(nodes["55"], 3, 1)
    if ref_key in REF_MAP:
        set_widget(nodes["56"], 0, REF_MAP[ref_key])
        nodes["56"]["mode"] = 0
    else:
        nodes["56"]["mode"] = 4
    seed = 100000 + scene["id"] * 100 + shot_idx
    set_widget(nodes["3"], 0, seed)
    set_widget(nodes["3"], 1, "fixed")
    set_widget(nodes["3"], 2, STEPS)
    set_widget(nodes["3"], 3, CFG)
    prefix = f"SASEOK/ep01/scene_{scene['id']:02d}/shot_{shot_idx:02d}"
    set_widget(nodes["58"], 0, prefix)
    return wf

def find_generated_video(scene_id, shot_idx, after_ts):
    out_dir = COMFY_DIR / "output" / "SASEOK" / "ep01" / f"scene_{scene_id:02d}"
    candidates = []
    if out_dir.exists():
        for p in out_dir.glob(f"shot_{shot_idx:02d}*"):
            if p.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"} and p.stat().st_mtime >= after_ts - 3:
                candidates.append(p)
    if not candidates:
        for p in (COMFY_DIR / "output").rglob(f"shot_{shot_idx:02d}*"):
            if p.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"} and p.stat().st_mtime >= after_ts - 3:
                candidates.append(p)
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None

def render_pending_shots():
    EPISODE, VISUAL_STYLE, NEGATIVE_PROMPT, VOICE_MAP = load_episode()
    template = fetch_workflow()
    tmp_wf_dir = Path("/content/saseok_workflows")
    tmp_wf_dir.mkdir(exist_ok=True)
    new_count = 0
    total = sum(len(s["shots"]) for s in EPISODE["scenes"])
    def clip_exists(sid, shid):
        d = DRIVE_ROOT / "clips" / f"scene_{sid:02d}"
        return any(d.glob(f"shot_{shid:02d}.*"))
    done_before = sum(clip_exists(s["id"], i) for s in EPISODE["scenes"] for i in range(1, len(s["shots"]) + 1))
    print(f"\n=== 8/8 Wan 2.2 render: {done_before}/{total} clips already on Drive ===")
    for scene in EPISODE["scenes"]:
        sid = scene["id"]
        if not (SCENE_START <= sid <= SCENE_END):
            continue
        scene_drive = DRIVE_ROOT / "clips" / f"scene_{sid:02d}"
        scene_drive.mkdir(parents=True, exist_ok=True)
        for shot_idx, shot in enumerate(scene["shots"], 1):
            if list(scene_drive.glob(f"shot_{shot_idx:02d}.*")):
                continue
            if new_count >= MAX_SHOTS_PER_RUN:
                done_now = sum(clip_exists(s["id"], i) for s in EPISODE["scenes"] for i in range(1, len(s["shots"]) + 1))
                print(f"이번 실행 한도 {MAX_SHOTS_PER_RUN}개 완료. 현재 {done_now}/{total}. 셀을 다시 실행하면 이어서 생성합니다.")
                return EPISODE, VOICE_MAP, False
            print(f"\nRendering scene {sid:02d} shot {shot_idx:02d}: {shot[1]}")
            wf = make_workflow(template, scene, shot_idx, shot, VISUAL_STYLE, NEGATIVE_PROMPT)
            wf_path = tmp_wf_dir / f"scene_{sid:02d}_shot_{shot_idx:02d}.json"
            wf_path.write_text(json.dumps(wf, ensure_ascii=False), encoding="utf-8")
            before = time.time()
            result = sh(["comfy", "run", "--workflow", str(wf_path), "--wait", "--where", "local"],
                        cwd=COMFY_DIR, check=False, capture=True)
            if result.returncode != 0:
                print(result.stdout[-3000:] if result.stdout else "")
                print(result.stderr[-3000:] if result.stderr else "")
                raise RuntimeError(f"scene {sid} shot {shot_idx} ComfyUI 렌더 실패")
            generated = find_generated_video(sid, shot_idx, before)
            if generated is None:
                raise FileNotFoundError(f"렌더는 끝났지만 scene {sid} shot {shot_idx} 영상 파일을 찾지 못했습니다.")
            dest = scene_drive / f"shot_{shot_idx:02d}{generated.suffix.lower()}"
            shutil.copy2(generated, dest)
            print("Saved to Drive:", dest)
            new_count += 1
    done_now = sum(clip_exists(s["id"], i) for s in EPISODE["scenes"] for i in range(1, len(s["shots"]) + 1))
    all_done = done_now == total
    print(f"Render progress: {done_now}/{total}")
    return EPISODE, VOICE_MAP, all_done

async def _tts_one(text, voice, rate, pitch, out_mp3):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_mp3))

def generate_scene_audio(scene, voice_map, out_wav):
    from pydub import AudioSegment
    duration_ms = int(scene["duration"] * 1000)
    track = AudioSegment.silent(duration=duration_ms)
    cursor = 2200
    line_gap = 2200
    tmp_dir = DRIVE_ROOT / "audio" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for idx, (speaker, text) in enumerate(scene.get("dialogue", []), 1):
        voice, rate, pitch = voice_map.get(speaker, ("ko-KR-InJoonNeural", "+0%", "+0Hz"))
        mp3 = tmp_dir / f"s{scene['id']:02d}_{idx:02d}.mp3"
        try:
            asyncio.run(_tts_one(text, voice, rate, pitch, mp3))
            audio = AudioSegment.from_file(mp3)
        except Exception as e:
            print("TTS fallback to silence:", speaker, e)
            audio = AudioSegment.silent(duration=1800)
        if cursor + len(audio) > duration_ms:
            cursor = max(0, duration_ms - len(audio) - 500)
        track = track.overlay(audio, position=cursor)
        cursor += len(audio) + line_gap
    track.export(out_wav, format="wav")

def concatenate_scene_motion(scene):
    sid = scene["id"]
    clip_dir = DRIVE_ROOT / "clips" / f"scene_{sid:02d}"
    clips = []
    for i in range(1, len(scene["shots"]) + 1):
        matches = sorted(clip_dir.glob(f"shot_{i:02d}.*"))
        if not matches:
            raise FileNotFoundError(f"Missing scene {sid} shot {i}")
        clips.append(matches[0])
    list_file = Path(f"/content/scene_{sid:02d}_clips.txt")
    list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips), encoding="utf-8")
    base = Path(f"/content/scene_{sid:02d}_base.mp4")
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-vf", f"scale={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(base)])
    return base

def assemble_final(episode, voice_map):
    print("\n=== All motion clips complete: building 20-minute episode ===")
    scene_outputs = []
    for scene in episode["scenes"]:
        sid = scene["id"]
        out_scene = DRIVE_ROOT / "scenes" / f"scene_{sid:02d}.mp4"
        if out_scene.exists():
            scene_outputs.append(out_scene)
            continue
        audio = DRIVE_ROOT / "audio" / f"scene_{sid:02d}.wav"
        if not audio.exists():
            generate_scene_audio(scene, voice_map, audio)
        base = concatenate_scene_motion(scene)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(base)],
            check=True, text=True, capture_output=True
        )
        base_duration = max(0.1, float(probe.stdout.strip()))
        stretch = float(scene["duration"]) / base_duration
        # Do not repeat the same 8-shot sequence. Time-stretch its real Wan motion
        # to the scripted scene duration, then upscale the final edit to 720p.
        vf = (
            f"setpts={stretch:.8f}*PTS,"
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        )
        sh(["ffmpeg", "-y", "-i", str(base), "-i", str(audio),
            "-vf", vf, "-t", str(scene["duration"]),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", str(out_scene)])
        scene_outputs.append(out_scene)
    final_list = Path("/content/saseok_final_concat.txt")
    final_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in scene_outputs), encoding="utf-8")
    final = DRIVE_ROOT / "SASEOK_EP01_WAN22_20min.mp4"
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(final_list),
        "-c", "copy", "-movflags", "+faststart", str(final)])
    print("\n완성:", final)
    return final

def main():
    install_environment()
    ensure_repo()
    ensure_comfyui()
    mount_drive()
    ensure_models()
    restore_character_assets()
    proc = start_comfyui()
    try:
        episode, voice_map, all_done = render_pending_shots()
        if all_done:
            assemble_final(episode, voice_map)
        else:
            print("\n아직 모든 컷이 끝나지 않았습니다. 같은 Colab 실행 셀을 다시 실행하면 Drive의 기존 컷을 건너뛰고 다음 컷부터 이어집니다.")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    main()
