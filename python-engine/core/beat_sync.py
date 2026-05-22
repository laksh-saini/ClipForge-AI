import librosa
import numpy as np

def get_beat_timestamps(audio_path: str):
    """
    Uses librosa to load the audio file and extract the timestamps of the beats.
    Returns a numpy array of beat timestamps in seconds.
    """
    try:
        # Load audio (mono, default sample rate)
        y, sr = librosa.load(audio_path)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        # Extract beats. Higher tightness keeps the grid closer to the song's pulse.
        _, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env,
            sr=sr,
            trim=False,
            tightness=120,
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        return beat_times
    except Exception as e:
        print(f"Error extracting beats: {e}")
        return np.array([])

def densify_beat_grid(beat_timestamps: np.ndarray, target_dur: float):
    """
    Beat trackers sometimes return a half-time grid. For fast cuts, add musical
    subdivisions between detected beats so the editor can cut near 1 second.
    """
    if len(beat_timestamps) < 2:
        return beat_timestamps

    grid = [0.0]
    for start, end in zip(beat_timestamps[:-1], beat_timestamps[1:]):
        interval = end - start
        if interval <= 0:
            continue

        subdivisions = max(1, int(round(interval / target_dur)))
        step = interval / subdivisions
        for sub_idx in range(subdivisions):
            grid.append(start + (step * sub_idx))

    grid.append(float(beat_timestamps[-1]))
    return np.array(sorted(set(round(t, 4) for t in grid)))

def get_target_duration(pacing: str = "dynamic", target_duration: float = None):
    if target_duration is not None:
        return max(0.35, min(float(target_duration), 6.0))
    pacing_map = {"fast": 1.0, "dynamic": 2.0, "cinematic": 3.0}
    return pacing_map.get(pacing, 2.0)

def map_clips_to_beats(storyboard_items: list, beat_timestamps: np.ndarray, pacing: str = "dynamic", target_duration: float = None):
    """
    Calculates the precise duration each clip should be played to match the music beats.
    
    Pacing targets:
    - fast: ~1.0s
    - dynamic: ~2.0s
    - cinematic: ~3.0s
    
    Returns a list of dicts:
      { "media": item, "duration": float }
    """
    if len(beat_timestamps) == 0:
        # Fallback to defaults if no beats detected or no audio provided
        target_dur = get_target_duration(pacing, target_duration)
        current_audio_time = 0.0
        mapped = []
        for item in storyboard_items:
            mapped.append({
                "media": item,
                "duration": target_dur,
                "audio_start": current_audio_time,
                "audio_end": current_audio_time + target_dur,
            })
            current_audio_time += target_dur
        return mapped
        
    target_dur = get_target_duration(pacing, target_duration)
    cut_grid = densify_beat_grid(beat_timestamps, target_dur)
    
    mapped_clips = []
    current_audio_time = 0.0
    
    for item in storyboard_items:
        # We want the next cut to be at a beat closest to current_audio_time + target_dur
        desired_cut_time = current_audio_time + target_dur
        
        # Find all beats strictly after current_audio_time
        future_beats = cut_grid[cut_grid > current_audio_time + 0.25] # At least 0.25s minimum clip
        
        if len(future_beats) == 0:
            # Run out of beats, just use target duration
            mapped_clips.append({
                "media": item,
                "duration": target_dur,
                "audio_start": current_audio_time,
                "audio_end": current_audio_time + target_dur,
            })
            current_audio_time += target_dur
            continue
            
        # Find the beat closest to desired_cut_time
        closest_beat = future_beats[np.argmin(np.abs(future_beats - desired_cut_time))]
        
        duration = closest_beat - current_audio_time
        if duration > target_dur * 1.5:
            duration = target_dur
            closest_beat = current_audio_time + target_dur
        mapped_clips.append({
            "media": item,
            "duration": duration,
            "audio_start": current_audio_time,
            "audio_end": closest_beat,
        })
        
        current_audio_time = closest_beat
        
    return mapped_clips
