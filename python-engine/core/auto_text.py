import json
import re
import subprocess
from pathlib import Path


STOP_WORDS = {
    "official", "video", "audio", "lyrics", "lyric", "cinematic", "sonyalpha",
    "videography", "traveltheworld", "cinema", "mp3", "wav", "m4a", "feat",
    "ft", "remix", "edit", "shorts",
}

FALLBACK_LINES = [
    "living like there is no tomorrow",
    "lost in the moment",
    "we only get tonight",
    "chasing the light",
    "hold on to the feeling",
    "nothing else matters",
    "run until sunrise",
    "this is our movie",
    "feel it in your bones",
    "never looking back",
]


def _metadata_title(audio_path: str):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags=title,artist",
                "-of",
                "json",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        tags = json.loads(result.stdout or "{}").get("format", {}).get("tags", {})
        title = tags.get("title") or tags.get("TITLE")
        artist = tags.get("artist") or tags.get("ARTIST")
        return " ".join(value for value in (title, artist) if value)
    except Exception:
        return ""


def _keywords(seed_text: str):
    words = re.findall(r"[A-Za-z][A-Za-z']+", seed_text.lower())
    cleaned = []
    for word in words:
        if len(word) < 3 or word in STOP_WORDS:
            continue
        if word not in cleaned:
            cleaned.append(word)
    return cleaned[:8]


def generate_auto_style_lines(audio_path: str = None, title_text: str = None, count: int = 12):
    """
    Generate short caption lines for Style 1 when exact lyrics were not supplied.
    This avoids pretending we can fetch copyrighted lyrics for every song, while
    still giving the edit changing center text automatically.
    """
    seed = title_text or ""
    if audio_path:
        seed = f"{seed} {_metadata_title(audio_path)} {Path(audio_path).stem}"
    keys = _keywords(seed)

    lines = []
    if keys:
        primary = " ".join(keys[: min(4, len(keys))])
        lines.extend([
            primary,
            f"{keys[0]} in the air",
            f"lost in {keys[min(1, len(keys) - 1)]}",
            f"{keys[-1]} forever",
        ])
        for key in keys:
            lines.append(key)

    lines.extend(FALLBACK_LINES)

    output = []
    for line in lines:
        if line not in output:
            output.append(line)
        if len(output) >= count:
            break
    return output
