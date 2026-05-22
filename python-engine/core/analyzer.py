import cv2
import numpy as np

def analyze_thumbnail(image_path: str):
    """
    Analyzes an image frame using simple OpenCV heuristics.
    Returns (is_rejected: bool, reject_reason: str)
    """
    if not image_path:
        return (False, "")
        
    try:
        img = cv2.imread(image_path)
        if img is None:
            return (False, "")
            
        # Convert to grayscale for both checks
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Blur Detection (Variance of Laplacian)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        # For thumbnails, a variance < 50 usually means it's blurry or completely flat
        if blur_score < 40:
            return (True, "blurry")
            
        # 2. Exposure / Brightness Detection
        brightness = np.mean(gray)
        if brightness < 20:
            return (True, "too_dark")
        elif brightness > 235:
            return (True, "too_bright")
            
        return (False, "")
    except Exception as e:
        print(f"Error analyzing image {image_path}: {e}")
        return (False, "")
