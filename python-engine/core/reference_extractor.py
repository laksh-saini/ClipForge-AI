import os
import subprocess
import json
import uuid
import statistics
import cv2
import string
import difflib
from pathlib import Path

# EasyOCR is imported locally inside functions to prevent slow startup if not used
_reader = None

def get_easyocr_reader():
    global _reader
    if _reader is None:
        import easyocr
        import torch
        import ssl
        # macOS python often lacks SSL certs out of the box, breaking the model download
        try:
            _create_unverified_https_context = ssl._create_unverified_context
        except AttributeError:
            pass
        else:
            ssl._create_default_https_context = _create_unverified_https_context
            
        device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        _reader = easyocr.Reader(['en'], gpu=(device == 'mps' or torch.cuda.is_available()))
    return _reader

def extract_audio(video_path: str, output_dir: Path) -> str:
    audio_path = output_dir / f"extracted_{uuid.uuid4().hex}.mp3"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-q:a", "0", "-map", "a", str(audio_path)
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if audio_path.exists() and audio_path.stat().st_size > 0:
            return str(audio_path)
    except subprocess.CalledProcessError:
        pass
    return None

def detect_transitions(video_path: str, duration: float):
    # Try progressively softer thresholds to find all cuts
    from core.reference_style import _scene_cut_times
    cuts = []
    for threshold in (0.35, 0.25, 0.18, 0.12, 0.08, 0.05):
        cuts = _scene_cut_times(video_path, threshold)
        if len(cuts) >= 3:
            break
            
    transitions = []
    for t in cuts:
        if 0.15 < t < duration - 0.15:
            # We'll mark all scene changes as hard cuts for now
            transitions.append({"time": t, "type": "hard"})
            
    return transitions

def extract_text(video_path: str, duration: float, roi_x=0.2, roi_y=0.4, roi_w=0.6, roi_h=0.2):
    reader = get_easyocr_reader()
    
    fps = 12.0
    temp_dir = Path(video_path).parent / f"ocr_frames_{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    crop_filter = f"crop=iw*{roi_w}:ih*{roi_h}:iw*{roi_x}:ih*{roi_y}"
    vf_chain = f"fps={fps},{crop_filter},format=gray,eq=contrast=1.5,unsharp=5:5:1.0:5:5:0.0,scale=iw*2:ih*2"
    
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf_chain,
        f"{temp_dir}/frame_%04d.jpg"
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    frames = sorted(temp_dir.glob("frame_*.jpg"))
    raw_texts = []
    
    for i, frame_path in enumerate(frames):
        time_sec = float(i) / fps
        if not frame_path.exists():
            continue
            
        results = reader.readtext(str(frame_path), text_threshold=0.5, low_text=0.3)
        text_lines = []
        max_prob = 0.0
        for bbox, text, prob in results:
            text = text.strip()
            if prob > 0.35 and len(text) > 1:
                if text in ["01", "00", "02"]:
                    continue
                text_lines.append(text)
                max_prob = max(max_prob, prob)
                
        if text_lines:
            combined = " ".join(text_lines)
            clean_text = combined.lower().strip()
            clean_text = clean_text.translate(str.maketrans('', '', string.punctuation))
            clean_text = " ".join(clean_text.split())
            if clean_text:
                raw_texts.append({"time": time_sec, "text": clean_text, "prob": max_prob})
                
    stableSegments = []
    currentText = None
    currentStart = 0.0
    lastTime = 0.0
    
    for i, r in enumerate(raw_texts):
        cleanText = r["text"]
        timestamp = r["time"]
        lastTime = timestamp
        
        if currentText is None:
            currentText = cleanText
            currentStart = timestamp
            continue
            
        similarity = difflib.SequenceMatcher(None, currentText, cleanText).ratio()
        
        if similarity < 0.75:
            is_stable = False
            if i + 1 < len(raw_texts):
                nextText = raw_texts[i+1]["text"]
                nextSim = difflib.SequenceMatcher(None, cleanText, nextText).ratio()
                if nextSim >= 0.75:
                    is_stable = True
            else:
                is_stable = True
                
            if r["prob"] > 0.8:
                is_stable = True
                
            if is_stable:
                stableSegments.append({
                    "start": currentStart,
                    "end": timestamp,
                    "text": currentText,
                    "confidence": r["prob"]
                })
                currentText = cleanText
                currentStart = timestamp

    if currentText is not None:
        stableSegments.append({
            "start": currentStart,
            "end": lastTime + (1.0/fps),
            "text": currentText,
            "confidence": 1.0
        })
            
    # Cleanup
    for f in frames:
        try:
            f.unlink()
        except OSError:
            pass
    try:
        temp_dir.rmdir()
    except OSError:
        pass
    
    return stableSegments

def deep_analyze_reference(video_path: str, project_id: str, roi_x=0.2, roi_y=0.4, roi_w=0.6, roi_h=0.2):
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(video_path)

    # 1. Video Duration
    from core.reference_style import _video_duration, analyze_reference_style
    duration = _video_duration(str(path))
    
    # 2. Extract Audio
    app_dir = Path.home() / ".clipforge" / "projects" / project_id
    app_dir.mkdir(parents=True, exist_ok=True)
    audio_path = extract_audio(str(path), app_dir)
    
    # 3. Transitions
    transitions = detect_transitions(str(path), duration)
    
    # 4. Text and Motion
    timed_texts = extract_text(str(path), duration, roi_x, roi_y, roi_w, roi_h)
    
    from core.motion_extractor import analyze_segment_motion
    timed_texts = analyze_segment_motion(str(path), timed_texts)
    
    # 5. Pacing details
    basic_stats = analyze_reference_style(str(path))
    
    return {
        "file_name": path.name,
        "duration": duration,
        "audio_path": audio_path,
        "transitions": transitions,
        "texts": timed_texts,
        "detected_cuts": len(transitions) + 1,  # Number of clips needed
        "target_duration": basic_stats["target_duration"],
        "energy": basic_stats["energy"]
    }
