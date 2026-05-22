import os
import subprocess
import tempfile
from pathlib import Path
from PIL import Image
import torch
from transformers import CLIPProcessor, CLIPModel

# Lazy load model to avoid locking up startup time
_model = None
_processor = None
_device = "mps" if torch.backends.mps.is_available() else "cpu"

def load_clip_model():
    global _model, _processor
    if _model is None:
        print(f"Loading CLIP model onto {_device}...")
        model_id = "openai/clip-vit-base-patch32"
        _model = CLIPModel.from_pretrained(model_id).to(_device)
        _processor = CLIPProcessor.from_pretrained(model_id)
        print("CLIP model loaded!")

def score_photo(photo_path: str) -> float:
    """
    Scores a single photo against the cinematic prompt using CLIP.
    """
    load_clip_model()
    prompt = "A highly cinematic, beautiful, well-framed hero shot, visually stunning, high quality"
    try:
        image = Image.open(photo_path)
        inputs = _processor(text=[prompt], images=[image], return_tensors="pt", padding=True)
        inputs = {k: v.to(_device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = _model(**inputs)
        return float(outputs.logits_per_image.squeeze().cpu().item())
    except Exception as e:
        print(f"Failed to score photo {photo_path}: {e}")
        return 0.0

def extract_hero_moment(video_path: str, media_id: str) -> tuple[float, float, float]:
    """
    Extracts frames from the video (1 frame every 3 seconds).
    Scores them against a "cinematic" prompt using CLIP.
    Returns (start_time, end_time, score) of the best 3-second segment.
    """
    load_clip_model()
    
    prompt = "A highly cinematic, beautiful, well-framed hero shot, visually stunning, high quality"
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract 1 frame every 3 seconds using ffmpeg
        # Output format: frame_0000.jpg, frame_0003.jpg
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", "fps=1/3",
            f"{temp_dir}/frame_%04d.jpg"
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception as e:
            print(f"Failed to extract frames for {video_path}: {e}")
            return (0.0, 3.0, 0.0)
            
        frames = sorted(Path(temp_dir).glob("frame_*.jpg"))
        if not frames:
            return (0.0, 3.0, 0.0)
            
        best_score = -100.0
        best_timestamp = 0.0
        
        # Batch process frames to be fast
        images = [Image.open(str(f)) for f in frames]
        timestamps = [i * 3.0 for i in range(len(frames))]
        
        # Process in batches of 8 to avoid OOM
        batch_size = 8
        for i in range(0, len(images), batch_size):
            batch_imgs = images[i:i+batch_size]
            batch_ts = timestamps[i:i+batch_size]
            
            inputs = _processor(text=[prompt], images=batch_imgs, return_tensors="pt", padding=True)
            # Move to device
            inputs = {k: v.to(_device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = _model(**inputs)
                
            # outputs.logits_per_image is shape [batch_size, 1]
            scores = outputs.logits_per_image.squeeze().cpu().tolist()
            
            if isinstance(scores, float):
                scores = [scores]
                
            for score, ts in zip(scores, batch_ts):
                if score > best_score:
                    best_score = score
                    best_timestamp = ts
                    
        # Segment is best_timestamp to best_timestamp + 3
        # But we need to make sure we don't go past the end of the video.
        # For MVP, we'll just trust ffmpeg trims it properly later.
        return (best_timestamp, best_timestamp + 3.0, best_score)
