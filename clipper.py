"""Long video in -> captioned 9:16 clips out.

Env vars:
  INPUT_PATH     path to the video (default input.mp4)
  OUT_DIR        output folder (default clips)
  WHISPER_MODEL  tiny | base | small | medium (default base)
  KEYWORDS       extra comma-separated words that make a moment score higher
  MAX_CLIPS      how many clips to export (default 8)
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

INPUT = os.environ.get("INPUT_PATH", "input.mp4")
OUT = Path(os.environ.get("OUT_DIR", "clips"))
MODEL = os.environ.get("WHISPER_MODEL", "base")
MAX_CLIPS = int(os.environ.get("MAX_CLIPS", "8"))
MIN_LEN, MAX_LEN = 30.0, 58.0

DEFAULT_KEYWORDS = [
    "insane", "crazy", "wtf", "no way", "unbelievable", "shocking", "secret",
    "mistake", "biggest", "worst", "best", "truth", "never", "game changer",
    "leak", "gta 6", "gameplay", "here's the thing", "the problem",
]
EXTRA = [k.strip().lower() for k in os.environ.get("KEYWORDS", "").split(",") if k.strip()]
KEYWORDS = DEFAULT_KEYWORDS + EXTRA * 3  # user words count triple


def run(cmd, **kw):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def video_duration():
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", INPUT,
    ])
    return float(out.strip())


def transcribe():
    print("Transcribing with", MODEL, flush=True)
    model = WhisperModel(MODEL, device="cpu", compute_type="int8")
    seg_iter, info = model.transcribe(INPUT, word_timestamps=True, vad_filter=True)
    segments = []
    for s in seg_iter:
        words = [
            {"start": w.start, "end": w.end, "word": w.word.strip()}
            for w in (s.words or [])
        ]
        segments.append({"start": s.start, "end": s.end, "text": s.text.strip(), "words": words})
    print(f"Language: {info.language}, segments: {len(segments)}", flush=True)
    return segments


def score(group):
    text = " ".join(s["text"] for s in group).lower()
    dur = max(group[-1]["end"] - group[0]["start"], 1.0)
    keyword_hits = sum(text.count(k) for k in KEYWORDS)
    emphasis = text.count("!") + text.count("?")
    pace = len(text.split()) / dur  # words per second, ~2-3 is normal speech
    return keyword_hits * 3 + emphasis * 0.5 + pace


def pick_moments(segments, total):
    cands = []
    for i, s in enumerate(segments):
        j = i
        while j + 1 < len(segments) and segments[j + 1]["end"] - s["start"] <= MAX_LEN:
            j += 1
        group = segments[i:j + 1]
        if group[-1]["end"] - s["start"] >= MIN_LEN:
            cands.append((score(group), s["start"], group[-1]["end"], group))
    cands.sort(key=lambda c: -c[0])

    chosen = []
    for sc, st, en, group in cands:
        if all(en <= c["start"] or st >= c["end"] for c in chosen):
            chosen.append({"start": st, "end": en, "hook": group[0]["text"]})
        if len(chosen) >= MAX_CLIPS:
            break

    if not chosen:  # fallback: fixed chunks (short video or sparse speech)
        step = 45.0
        t = 0.0
        while t < total and len(chosen) < MAX_CLIPS:
            end = min(t + step, total)
            if end - t >= 10:
                chosen.append({"start": t, "end": end, "hook": f"Part {len(chosen) + 1}"})
            t += step

    chosen.sort(key=lambda c: c["start"])
    return chosen


def ass_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,78,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(path, segments, start, end):
    words = [
        w for s in segments for w in s["words"]
        if w["start"] >= start - 0.05 and w["end"] <= end + 0.5
    ]
    lines = [ASS_HEADER]
    for i in range(0, len(words), 3):
        grp = words[i:i + 3]
        text = " ".join(w["word"] for w in grp).upper()
        text = text.replace("\\", "").replace("{", "").replace("}", "")
        lines.append(
            f"Dialogue: 0,{ass_time(grp[0]['start'] - start)},"
            f"{ass_time(grp[-1]['end'] - start)},Default,,0,0,0,,{text}\n"
        )
    Path(path).write_text("".join(lines), encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    total = video_duration()
    print(f"Video length: {total / 60:.1f} min", flush=True)

    segments = transcribe()
    moments = pick_moments(segments, total)
    print(f"Selected {len(moments)} moments", flush=True)

    manifest = []
    with tempfile.TemporaryDirectory() as tmp:
        for idx, m in enumerate(moments, start=1):
            name = f"clip_{idx:02d}.mp4"
            ass_name = f"clip_{idx:02d}.ass"
            write_ass(Path(tmp) / ass_name, segments, m["start"], m["end"])
            vf = (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,ass={ass_name}"
            )
            run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{m['start']:.2f}", "-i", str(Path(INPUT).resolve()),
                "-t", f"{m['end'] - m['start']:.2f}",
                "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                str((OUT / name).resolve()),
            ], cwd=tmp)
            manifest.append({
                "file": name,
                "start": round(m["start"], 2),
                "end": round(m["end"], 2),
                "hook": m["hook"][:90],
            })

    (OUT / "manifest.json").write_text(json.dumps({"clips": manifest}, indent=2))
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
