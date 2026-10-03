from pathlib import Path
import asyncio, subprocess, yaml, shutil
import edge_tts

ROOT=Path(__file__).parent
WORK=ROOT/"build"; OUT=ROOT/"output"
WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)

def run(cmd):
    print(" ".join(map(str,cmd)))
    subprocess.run(cmd, check=True)

async def tts(text, voice, path):
    await edge_tts.Communicate(text, voice).save(str(path))

def main():
    cfg=yaml.safe_load((ROOT/"project.yaml").read_text(encoding="utf-8"))
    w,h=map(int,cfg.get("resolution","1080x1920").split("x"))
    fps=int(cfg.get("fps",30)); default_voice=cfg.get("voice","ko-KR-InJoonNeural")
    clips=[]
    for i,s in enumerate(cfg["scenes"],1):
        src=ROOT/s["image"]; dur=float(s.get("duration",5))
        if not src.exists():
            raise FileNotFoundError(f"Missing asset: {src}")
        audio=WORK/f"{i:03}.mp3"; clip=WORK/f"{i:03}.mp4"
        asyncio.run(tts(s["text"],s.get("voice",default_voice),audio))
        frames=max(1,int(dur*fps))
        vf=(f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},zoompan=z='min(zoom+0.0008,1.10)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={fps},"
            f"fade=t=in:st=0:d=0.35,fade=t=out:st={max(0,dur-0.4)}:d=0.4")
        run(["ffmpeg","-y","-loop","1","-i",str(src),"-i",str(audio),"-vf",vf,
             "-t",str(dur),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",
             "-shortest",str(clip)])
        clips.append(clip)
    concat=WORK/"concat.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for p in clips),encoding="utf-8")
    final=OUT/"video.mp4"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(final)])
    print(f"Created: {final}")

if __name__=="__main__":
    main()
