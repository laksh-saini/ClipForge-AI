import json
import statistics
import subprocess
from pathlib import Path


def _video_duration(video_path: str):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout or "{}")
    return float(payload.get("format", {}).get("duration", 0) or 0)


def _scene_cut_times(video_path: str, threshold: float):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        video_path,
        "-filter:v",
        f"select='gt(scene,{threshold})',showinfo",
        "-an",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    times = []
    for line in result.stderr.splitlines():
        marker = "pts_time:"
        if marker not in line:
            continue
        tail = line.split(marker, 1)[1].split(" ", 1)[0]
        try:
            times.append(float(tail))
        except ValueError:
            continue
    return sorted(set(times))


def analyze_reference_style(video_path: str):
    """
    Infer a practical export rhythm from a finished reference edit.
    The result intentionally stays small: cut duration is the control this
    exporter can actually honor today.
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(video_path)

    duration = _video_duration(str(path))
    cuts = []
    for threshold in (0.35, 0.25, 0.18):
        cuts = _scene_cut_times(str(path), threshold)
        if len(cuts) >= 3:
            break

    cut_points = [0.0] + [time for time in cuts if 0.15 < time < duration - 0.15] + [duration]
    intervals = [
        round(cut_points[index + 1] - cut_points[index], 3)
        for index in range(len(cut_points) - 1)
        if cut_points[index + 1] - cut_points[index] >= 0.25
    ]

    if intervals:
        median_cut = statistics.median(intervals)
        average_cut = statistics.mean(intervals)
    else:
        median_cut = min(3.0, max(1.0, duration / 8 if duration else 2.0))
        average_cut = median_cut

    target_duration = max(0.45, min(4.0, median_cut))
    cuts_per_minute = (len(intervals) / duration * 60) if duration else 0
    if target_duration <= 1.25:
        energy = "hype"
    elif target_duration <= 2.25:
        energy = "dynamic"
    else:
        energy = "cinematic"

    return {
        "file_name": path.name,
        "duration": round(duration, 2),
        "detected_cuts": max(0, len(cut_points) - 2),
        "clip_count": len(intervals),
        "median_cut": round(median_cut, 2),
        "average_cut": round(average_cut, 2),
        "target_duration": round(target_duration, 2),
        "cuts_per_minute": round(cuts_per_minute, 1),
        "energy": energy,
    }
