import subprocess
from pathlib import Path
import os
import uuid
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from core.auto_text import generate_auto_style_lines
from core.beat_sync import get_beat_timestamps, map_clips_to_beats

FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Avenir.ttc",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]

def _load_font(index: int, size: int):
    existing_fonts = [font for font in FONT_CANDIDATES if Path(font).exists()]
    if not existing_fonts:
        return ImageFont.load_default()
    return ImageFont.truetype(existing_fonts[index % len(existing_fonts)], size)

def _wrap_text(draw, text: str, font, max_width: int):
    words = text.split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=3)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines

def _text_overlay_path(temp_dir: Path, text: str = None, clip_index: int = 0, edit_style: str = "title", canvas_size=(1920, 1080)):
    if not text or not text.strip():
        return None

    is_style_one = edit_style == "style1"
    canvas_w, canvas_h = canvas_size
    font = _load_font(clip_index, 54 if is_style_one else 58)
    display_text = text.strip() if is_style_one else text.strip().upper()
    image = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lines = _wrap_text(draw, display_text, font, int(canvas_w * 0.78) if is_style_one else int(canvas_w * 0.78))
    line_boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=3) for line in lines]
    line_heights = [(box[3] - box[1]) for box in line_boxes]
    total_height = sum(line_heights) + max(0, len(lines) - 1) * 18
    y = int((canvas_h - total_height) / 2) if is_style_one else int(canvas_h * 0.80)
    palettes = [
        ((255, 255, 255, 248), (0, 0, 0, 165)),
        ((255, 244, 214, 248), (50, 22, 0, 165)),
        ((226, 242, 255, 248), (3, 18, 35, 165)),
    ]
    fill, stroke = palettes[clip_index % len(palettes)] if is_style_one else ((255, 255, 255, 245), (0, 0, 0, 150))
    for line, box, line_height in zip(lines, line_boxes, line_heights):
        line_width = box[2] - box[0]
        x = (canvas_w - line_width) // 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
            stroke_width=4 if is_style_one else 3,
            stroke_fill=stroke,
        )
        y += line_height + 18
    overlay_path = temp_dir / f"text_overlay_{clip_index}.png"
    image.save(overlay_path)
    return overlay_path

def _lyric_for_audio_time(lyric_lines, timed_lyrics, audio_time: float, total_duration: float):
    if timed_lyrics:
        current = ""
        for item in timed_lyrics:
            try:
                start_time = float(item.get("start", item.get("time", 0)))
            except (TypeError, ValueError):
                continue
            if start_time <= audio_time:
                current = str(item.get("text", "")).strip()
            else:
                break
        if current:
            return current

    if not lyric_lines:
        return ""
    if total_duration <= 0:
        return lyric_lines[0]

    progress = min(max(audio_time / total_duration, 0.0), 0.999)
    line_index = int(progress * len(lyric_lines))
    return lyric_lines[min(line_index, len(lyric_lines) - 1)]

def _apply_dynamic_motion(motion: str, duration: float, is_preview: bool = False):
    w, h = (410, 729) if is_preview else (820, 1458)
    cw, ch = (360, 640) if is_preview else (720, 1280)
    fps = 15 if is_preview else 30
    
    cx = "(iw-ow)/2"
    cy = "(ih-oh)/2"
    
    if motion == "pan_left":
        x_expr = f"{cx} - (t/max({duration},0.1))*50"
        y_expr = cy
    elif motion == "pan_right":
        x_expr = f"{cx} + (t/max({duration},0.1))*50"
        y_expr = cy
    elif motion == "pan_up":
        x_expr = cx
        y_expr = f"{cy} - (t/max({duration},0.1))*50"
    elif motion == "pan_down":
        x_expr = cx
        y_expr = f"{cy} + (t/max({duration},0.1))*50"
    else:
        x_expr = cx
        y_expr = cy
        
    crop_filter = f"crop={cw}:{ch}:{x_expr}:{y_expr}"
    
    zoom_filter = ""
    frames = max(1, int(duration * fps))
    if motion == "zoom_in":
        zoom_filter = f",zoompan=z='min(zoom+0.0015,1.5)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={cw}x{ch}:fps={fps}"
    elif motion == "zoom_out":
        zoom_filter = f",zoompan=z='max(1.3-0.0015*on,1.0)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={cw}x{ch}:fps={fps}"

    filter_str = f"scale={w}:{h}:force_original_aspect_ratio=increase"
    if zoom_filter:
        filter_str += zoom_filter
    else:
        filter_str += f",{crop_filter},fps={fps}"
        
    filter_str += ",eq=contrast=1.1:saturation=1.2:brightness=-0.012,format=yuv420p"
    return filter_str

def _camera_flash_filter(duration: float):
    flash_duration = min(0.075, max(0.035, duration * 0.18))
    out_start = max(0.0, duration - flash_duration)
    return (
        f"fade=t=in:st=0:d={flash_duration:.3f}:color=white,"
        f"fade=t=out:st={out_start:.3f}:d={flash_duration:.3f}:color=white"
    )

def generate_thumbnail(video_path: str, project_id: str) -> str:
    """Generates a proxy thumbnail for a video and returns the path."""
    app_dir = Path.home() / ".clipforge" / "projects" / project_id / "thumbnails"
    app_dir.mkdir(parents=True, exist_ok=True)
    
    thumb_name = f"{uuid.uuid4().hex}.jpg"
    thumb_path = app_dir / thumb_name
    
    # ffmpeg -y -i input.mp4 -vf scale=320:-1 -vframes 1 thumb.jpg
    cmd = [
        "ffmpeg",
        "-y",               # Overwrite
        "-i", str(video_path),
        "-vf", "scale=320:-1",
        "-vframes", "1",
        str(thumb_path)
    ]
    
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return str(thumb_path)
    except FileNotFoundError:
        print("ERROR: FFmpeg is not installed or not in PATH.")
        return ""
    except subprocess.CalledProcessError:
        print(f"ERROR: Failed to generate thumbnail for {video_path}")
        return ""

def export_montage(media_files: list, project_id: str, output_path: str, audio_path: str = None, pacing: str = "dynamic", target_duration: float = None, title_text: str = None, edit_style: str = "title", lyrics_text: str = None, auto_lyrics: bool = True, lyrics_timed_lines: list = None, reference_transitions: list = None, reference_texts: list = None, is_preview: bool = False):
    """
    Takes a list of media dicts. Trims the hero segment of each video,
    normalizes them to 1080p 30fps to ensure concat works safely,
    and concatenates them into output_path.
    If audio_path is provided, replaces the original audio with the new track.
    Maps clips to audio beats based on the selected pacing.
    """
    app_dir = Path.home() / ".clipforge" / "projects" / project_id
    temp_dir = app_dir / "temp_export"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    if reference_texts and not lyrics_timed_lines:
        lyrics_timed_lines = reference_texts
        edit_style = "style1"
        auto_lyrics = False
        
    lyric_lines = [line.strip() for line in (lyrics_text or "").splitlines() if line.strip()]
    if edit_style == "style1" and target_duration is None:
        target_duration = 0.65
    is_style_one = edit_style == "style1"
    canvas_size = (720, 1280) if is_style_one else (1920, 1080)
    if is_preview:
        canvas_size = (360, 640) if is_style_one else (854, 480)
    
    # 0. Beat Mapping
    if pacing == "reference" and (reference_transitions or reference_texts):
        beat_timestamps = np.array([])
        if audio_path and Path(audio_path).exists():
            beat_timestamps = get_beat_timestamps(audio_path)
            
        cut_events = []
        if reference_texts:
            for seg in reference_texts:
                motion = seg.get("motion", "static")
                start_t = round(seg.get("start", seg.get("time", 0.0)), 3)
                cut_events.append((start_t, motion))
                if "end" in seg:
                    cut_events.append((round(seg["end"], 3), "static"))
                    
        if reference_transitions:
            for t in reference_transitions:
                cut_events.append((round(t["time"], 3), "static"))
                
        # Deduplicate by time, keeping the first motion encountered
        unique_cuts = {}
        for t, m in sorted(cut_events, key=lambda x: x[0]):
            if t not in unique_cuts or unique_cuts[t] == "static":
                unique_cuts[t] = m
                
        cut_events = sorted([(t, m) for t, m in unique_cuts.items()], key=lambda x: x[0])
        
        if len(beat_timestamps) > 0:
            snapped_events = []
            for t, motion in cut_events:
                closest_beat = beat_timestamps[np.argmin(np.abs(beat_timestamps - t))]
                if abs(closest_beat - t) < 0.2:
                    snapped_events.append((round(float(closest_beat), 3), motion))
                else:
                    snapped_events.append((t, motion))
            
            # Re-deduplicate after snapping
            unique_snapped = {}
            for t, m in snapped_events:
                if t not in unique_snapped or unique_snapped[t] == "static":
                    unique_snapped[t] = m
            cut_events = sorted([(t, m) for t, m in unique_snapped.items()], key=lambda x: x[0])
        
        # Filter out flash cuts (less than 0.25s apart) to prevent strobe effect
        final_cuts = []
        last_cut = 0.0
        for t, motion in cut_events:
            if t > 0 and t - last_cut >= 0.25:
                final_cuts.append({"time": t, "motion": motion})
                last_cut = t
                
        mapped_clips = []
        current_time = 0.0
        
        # In a reference template, we want to match the full video length.
        # If the user didn't provide enough clips, we loop them (like TikTok templates do).
        total_slots = len(final_cuts) + 1
        
        for i in range(total_slots):
            item = media_files[i % len(media_files)]
            if i < len(final_cuts):
                dur = final_cuts[i]["time"] - current_time
                motion = final_cuts[i]["motion"]
            else:
                dur = target_duration or 2.0
                motion = "static"
            
            if dur <= 0: dur = 0.5
            mapped_clips.append({
                "media": item,
                "duration": dur,
                "audio_start": current_time,
                "audio_end": current_time + dur,
                "motion": motion
            })
            current_time += dur
    else:
        beat_timestamps = np.array([])
        if audio_path and Path(audio_path).exists():
            beat_timestamps = get_beat_timestamps(audio_path)
            
        mapped_clips = map_clips_to_beats(media_files, beat_timestamps, pacing, target_duration)
        
    total_montage_duration = sum(float(item.get("duration", 0)) for item in mapped_clips)
    if edit_style == "style1" and auto_lyrics and not lyric_lines:
        lyric_lines = generate_auto_style_lines(audio_path, title_text, len(mapped_clips))
    
    # 1. Trim and Normalize
    processed_clips = []
    for i, mapped_data in enumerate(mapped_clips):
        media = mapped_data["media"]
        target_duration = mapped_data["duration"]
        
        file_path = media["file_path"]
        temp_clip_path = temp_dir / f"clip_{i}.mp4"
        
        # We re-encode to a standard format (1080p 30fps) so concatenation doesn't break
        start_t = media.get("start_time")
        
        cmd = ["ffmpeg", "-y"]
        
        if media.get("type") == "photo":
            cmd.extend(["-loop", "1", "-i", str(file_path)])
        elif start_t is None:
            cmd.extend(["-i", str(file_path)])
        else:
            cmd.extend(["-ss", str(start_t), "-i", str(file_path)])
            
        if is_style_one:
            motion = mapped_data.get("motion", "static")
            base_filter = _apply_dynamic_motion(motion, duration, is_preview=is_preview)
        else:
            w, h = (854, 480) if is_preview else (1920, 1080)
            fps = 15 if is_preview else 30
            base_filter = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                f"fps={fps},"
                "format=yuv420p"
            )
        overlay_text = title_text
        if edit_style == "style1":
            audio_midpoint = float(mapped_data.get("audio_start", 0)) + (target_duration / 2)
            overlay_text = _lyric_for_audio_time(
                lyric_lines,
                lyrics_timed_lines or [],
                audio_midpoint,
                total_montage_duration,
            ) or title_text
        text_overlay = _text_overlay_path(temp_dir, overlay_text, i, edit_style, canvas_size)
        
        has_transition = False
        if reference_transitions:
            audio_end = float(mapped_data.get("audio_end", 0))
            for rt in reference_transitions:
                if abs(rt["time"] - audio_end) < 0.3:
                    has_transition = True
                    break
                    
        if is_style_one:
            final_filter = _camera_flash_filter(target_duration)
        elif has_transition:
            # Apply a brief dip to black to simulate a transition
            out_start = max(0.0, target_duration - 0.2)
            final_filter = f"fade=t=out:st={out_start:.2f}:d=0.2"
        else:
            final_filter = "format=yuv420p"

        if text_overlay:
            cmd.extend([
                "-loop", "1",
                "-i", str(text_overlay),
                "-filter_complex", f"[0:v]{base_filter}[base];[base][1:v]overlay=0:0:format=auto[withtext];[withtext]{final_filter},format=yuv420p[v]",
                "-map", "[v]",
                "-t", str(target_duration),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-an",
                str(temp_clip_path)
            ])
        else:
            cmd.extend([
                "-vf", f"{base_filter},{final_filter},format=yuv420p",
                "-t", str(target_duration),
                "-c:v", "libx264",
                "-preset", "ultrafast", # Fast for MVP
                "-an",
                str(temp_clip_path)
            ])
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            processed_clips.append(temp_clip_path)
        except subprocess.CalledProcessError:
            print(f"Failed to process {file_path} for export")
            
    if not processed_clips:
        return False
        
    # 2. Concat
    concat_list_path = temp_dir / "concat.txt"
    with open(concat_list_path, "w") as f:
        for clip_path in processed_clips:
            f.write(f"file '{clip_path}'\n")
            
    if audio_path and Path(audio_path).exists():
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_path)
        ]
    else:
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-c", "copy",
            str(output_path)
        ]
        
    try:
        subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except subprocess.CalledProcessError:
        print("Failed to concatenate montage")
        return False
