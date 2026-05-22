import cv2
import numpy as np

def analyze_segment_motion(video_path: str, segments: list):
    """
    Analyzes optical flow of a video across specific segment time boundaries.
    Returns a list of segment dicts with an added 'motion' key.
    Valid motions: 'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down', 'static'
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        for seg in segments:
            seg["motion"] = "static"
        return segments

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    output_segments = []
    
    for seg in segments:
        start_t = seg.get("start", seg.get("time", 0.0))
        end_t = seg.get("end", start_t + 2.0)
        
        # Ensure we don't try to analyze zero-duration segments
        if end_t - start_t <= 0.1:
            seg["motion"] = "static"
            output_segments.append(seg)
            continue
            
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_t * fps))
        ret, frame1 = cap.read()
        if not ret:
            seg["motion"] = "static"
            output_segments.append(seg)
            continue
            
        prvs = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        
        num_samples = min(10, max(3, int((end_t - start_t) * fps / 4)))
        step = max(1, int((end_t - start_t) * fps / num_samples))
        
        total_dx = 0.0
        total_dy = 0.0
        total_dz = 0.0 
        valid_samples = 0
        
        for i in range(1, num_samples):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_t * fps) + i * step)
            ret, frame2 = cap.read()
            if not ret:
                break
                
            next_frame = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
            
            # Use Good Features to Track + Lucas Kanade Optical Flow for speed
            p0 = cv2.goodFeaturesToTrack(prvs, mask=None, maxCorners=100, qualityLevel=0.3, minDistance=7, blockSize=7)
            if p0 is not None:
                p1, st, err = cv2.calcOpticalFlowPyrLK(prvs, next_frame, p0, None, winSize=(15, 15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
                
                if p1 is not None:
                    good_new = p1[st == 1]
                    good_old = p0[st == 1]
                    
                    if len(good_new) > 5:
                        dx = np.mean(good_new[:, 0] - good_old[:, 0])
                        dy = np.mean(good_new[:, 1] - good_old[:, 1])
                        
                        h, w = prvs.shape
                        cx, cy = w / 2.0, h / 2.0
                        
                        old_dist = np.mean(np.sqrt((good_old[:, 0] - cx)**2 + (good_old[:, 1] - cy)**2))
                        new_dist = np.mean(np.sqrt((good_new[:, 0] - cx)**2 + (good_new[:, 1] - cy)**2))
                        
                        if old_dist > 0:
                            dz = (new_dist - old_dist) / old_dist
                            total_dz += dz
                            
                        total_dx += dx
                        total_dy += dy
                        valid_samples += 1
                        
            prvs = next_frame
            
        motion = "static"
        if valid_samples > 0:
            avg_dx = total_dx / valid_samples
            avg_dy = total_dy / valid_samples
            avg_dz = total_dz / valid_samples
            
            # Determine dominant motion
            if abs(avg_dz) > 0.015 and abs(avg_dz) > abs(avg_dx) * 0.005 and abs(avg_dz) > abs(avg_dy) * 0.005:
                motion = "zoom_in" if avg_dz > 0 else "zoom_out"
            else:
                if abs(avg_dx) > abs(avg_dy) and abs(avg_dx) > 1.5:
                    motion = "pan_right" if avg_dx < 0 else "pan_left"
                elif abs(avg_dy) > 1.5:
                    motion = "pan_down" if avg_dy < 0 else "pan_up"
                    
        seg["motion"] = motion
        output_segments.append(seg)
        
    cap.release()
    return output_segments
