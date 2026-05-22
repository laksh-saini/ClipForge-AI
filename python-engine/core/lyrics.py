import re
import os
from pathlib import Path

try:
    from lyrics_extractor import SongLyrics
except ImportError:
    SongLyrics = None


def parse_lyrics_file(path: str):
    source = Path(path)
    text = source.read_text(encoding="utf-8", errors="ignore")
    suffix = source.suffix.lower()

    lines = []
    timed_lines = []
    if suffix == ".srt":
        for block in re.split(r"\n\s*\n", text.strip()):
            block_lines = [line.strip() for line in block.splitlines() if line.strip()]
            timing_index = next((idx for idx, line in enumerate(block_lines) if "-->" in line), None)
            if timing_index is None:
                continue
            start_text = block_lines[timing_index].split("-->")[0].strip()
            caption = " ".join(block_lines[timing_index + 1:]).strip()
            if not caption:
                continue
            start_time = _parse_srt_time(start_text)
            lines.append(caption)
            if start_time is not None:
                timed_lines.append({"time": start_time, "text": caption})
    elif suffix == ".lrc":
        for raw in text.splitlines():
            timestamps = _parse_lrc_times(raw)
            line = re.sub(r"\[[0-9:.]+\]", "", raw).strip()
            if line:
                lines.append(line)
                for start_time in timestamps:
                    timed_lines.append({"time": start_time, "text": line})
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip()]

    deduped = []
    for line in lines:
        if line not in deduped:
            deduped.append(line)
    timed_lines = sorted(timed_lines, key=lambda item: item["time"])
    return {"file_name": source.name, "lines": deduped, "timed_lines": timed_lines}


def _parse_lrc_times(raw: str):
    times = []
    for minutes, seconds in re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", raw):
        times.append((int(minutes) * 60) + float(seconds))
    return times


def _parse_srt_time(raw: str):
    match = re.match(r"(\d+):(\d+):(\d+),(\d+)", raw)
    if not match:
        return None
    hours, minutes, seconds, milliseconds = match.groups()
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


def _clean_lyrics_lines(text: str):
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^\[.*\]$", line):
            continue
        lines.append(line)

    deduped = []
    for line in lines:
        if line not in deduped:
            deduped.append(line)
    return deduped


def lookup_lyrics(song_name: str, api_key: str = None, engine_id: str = None):
    query = (song_name or "").strip()
    if not query:
        raise ValueError("Enter a song name first.")
    if SongLyrics is None:
        raise RuntimeError("lyrics-extractor is not installed in the Python engine.")

    gcs_api_key = (
        api_key
        or os.environ.get("CLIPFORGE_LYRICS_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    gcs_engine_id = (
        engine_id
        or os.environ.get("CLIPFORGE_LYRICS_ENGINE_ID")
        or os.environ.get("GOOGLE_CSE_ID")
    )
    if not gcs_api_key or not gcs_engine_id:
        raise RuntimeError(
            "Lyrics search needs CLIPFORGE_LYRICS_API_KEY and CLIPFORGE_LYRICS_ENGINE_ID set before starting the engine."
        )

    payload = SongLyrics(gcs_api_key, gcs_engine_id).get_lyrics(query)
    lyrics = (payload or {}).get("lyrics", "")
    if not lyrics.strip():
        raise RuntimeError(f"No lyrics found for '{query}'.")

    lines = _clean_lyrics_lines(lyrics)
    if not lines:
        raise RuntimeError(f"Lyrics were found for '{query}', but no usable lines were returned.")

    return {
        "song_name": query,
        "title": (payload or {}).get("title") or query,
        "lyrics": lyrics,
        "lines": lines,
    }
