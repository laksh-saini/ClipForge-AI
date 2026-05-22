from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import sys
import os
from pathlib import Path
from typing import List, Dict

from db.database import init_db, get_or_create_default_project, insert_media_file, update_media_thumbnail, update_media_rejection, get_all_media, get_good_media_with_segments, insert_segment, get_storyboard, reorder_storyboard, delete_from_storyboard, ensure_storyboard_segments_for_ready_media, media_has_segments, clear_current_project, dedupe_storyboard_by_media
from core.ffmpeg import generate_thumbnail, export_montage
from core.analyzer import analyze_thumbnail
from core.hero_extractor import extract_hero_moment, score_photo
from core.reference_style import analyze_reference_style
from core.reference_extractor import deep_analyze_reference
from core.lyrics import parse_lyrics_file, lookup_lyrics

VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'm4v'}
PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'heic', 'heif'}

def find_live_photo_video(photo_path: str):
    """
    iOS Live Photo exports often use a shared asset id before the first
    underscore. If the paired MOV is present beside the JPEG, prefer it.
    """
    path = Path(photo_path)
    asset_id = path.stem.split("_")[0]
    candidates = []
    for ext in VIDEO_EXTENSIONS:
        candidates.extend(path.parent.glob(f"{asset_id}*.{ext}"))
        candidates.extend(path.parent.glob(f"{asset_id}*.{ext.upper()}"))
    return str(candidates[0]) if candidates else None

# Initialize SQLite database
init_db()

app = FastAPI(title="ClipForge Engine")

# Mount ~/.clipforge/projects as static route for thumbnails
os.makedirs(Path.home() / ".clipforge" / "projects", exist_ok=True)
app.mount("/projects", StaticFiles(directory=str(Path.home() / ".clipforge" / "projects")), name="projects")

# Global state for status polling
status_state = {
    "ingesting_count": 0,
    "is_exporting": False,
    "export_progress": ""
}

# Allow CORS so Tauri React frontend can call it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local dev, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
def ping():
    return {"status": "ok", "message": "ClipForge Engine is running"}

class IngestRequest(BaseModel):
    file_paths: List[str]

def process_ingestion(source_path: str, project_id: str):
    # Determine if photo or video
    ext = source_path.lower().split('.')[-1]
    media_type = "video" if ext in VIDEO_EXTENSIONS else "photo"
    
    # Save to DB
    media_id = insert_media_file(project_id, source_path, type=media_type)
    
    # Generate thumbnail
    thumb_path = generate_thumbnail(source_path, project_id)
    if thumb_path:
        update_media_thumbnail(media_id, thumb_path)
        
        # Analyze the thumbnail with OpenCV heuristics
        is_rejected, reject_reason = analyze_thumbnail(thumb_path)
        update_media_rejection(media_id, is_rejected, reject_reason)
        
        if not is_rejected and not media_has_segments(media_id):
            if media_type == "video":
                # If it's a good video, find the best 3-second hero moment.
                start_time, end_time, score = extract_hero_moment(source_path, media_id)
                insert_segment(media_id, start_time, end_time, score)
            else:
                # Photos are already a complete visual moment; make them exportable.
                score = score_photo(source_path)
                insert_segment(media_id, 0.0, 3.0, score)
            
    else:
        update_media_rejection(media_id, True, "Thumbnail missing")

@app.post("/api/ingest")
def ingest_media(req: IngestRequest, background_tasks: BackgroundTasks):
    project_id = get_or_create_default_project()
    status_state["ingesting_count"] += len(req.file_paths)
    
    def process_queue(paths):
        processed = set()
        try:
            for path in paths:
                # Resolve live photo paths early to deduplicate
                ext = path.lower().split('.')[-1]
                media_type = "video" if ext in VIDEO_EXTENSIONS else "photo"
                source_path = path
                if media_type == "photo":
                    live_video_path = find_live_photo_video(path)
                    if live_video_path:
                        source_path = live_video_path
                
                if source_path in processed:
                    continue
                processed.add(source_path)
                
                process_ingestion(source_path, project_id)
        finally:
            status_state["ingesting_count"] = max(0, status_state["ingesting_count"] - len(paths))

    background_tasks.add_task(process_queue, req.file_paths)
    return {"status": "processing", "count": len(req.file_paths)}

@app.get("/api/media")
def get_media():
    return get_all_media()

from fastapi.responses import FileResponse

@app.get("/api/media/stream")
def stream_media(path: str):
    if os.path.exists(path):
        return FileResponse(path)
    return {"error": "File not found"}

@app.get("/api/status")
def get_status():
    return status_state

@app.get("/api/storyboard")
def get_storyboard_api():
    project_id = get_or_create_default_project()
    ensure_storyboard_segments_for_ready_media(project_id)
    dedupe_storyboard_by_media(project_id)
    return get_storyboard()

class ReorderRequest(BaseModel):
    storyboard_ids: List[str]

@app.post("/api/storyboard/reorder")
def reorder_storyboard_api(req: ReorderRequest):
    reorder_storyboard(req.storyboard_ids)
    return {"status": "ok"}

@app.delete("/api/storyboard/{sb_id}")
def delete_storyboard_api(sb_id: str):
    delete_from_storyboard(sb_id)
    return {"status": "ok"}

@app.post("/api/project/clear")
def clear_project_api():
    result = clear_current_project()
    status_state["ingesting_count"] = 0
    status_state["is_exporting"] = False
    status_state["export_progress"] = "Session cleared. Add new media to start fresh."
    return result

class ExportRequest(BaseModel):
    audio_path: str = None
    pacing: str = "dynamic"
    reference_path: str = None
    target_duration: float = None
    title_text: str = None
    edit_style: str = "title"
    lyrics_text: str = None
    auto_lyrics: bool = False
    lyrics_timed_lines: List[Dict] = None
    reference_transitions: List[Dict] = None
    reference_texts: List[Dict] = None

class ReferenceStyleRequest(BaseModel):
    reference_path: str
    roi_x: float = 0.2
    roi_y: float = 0.4
    roi_w: float = 0.6
    roi_h: float = 0.2

class LyricsImportRequest(BaseModel):
    lyrics_path: str

class LyricsSearchRequest(BaseModel):
    song_name: str
    api_key: str = None
    engine_id: str = None

@app.post("/api/reference-style")
def reference_style_api(req: ReferenceStyleRequest):
    try:
        project_id = get_or_create_default_project()
        return deep_analyze_reference(
            req.reference_path, 
            project_id,
            roi_x=req.roi_x,
            roi_y=req.roi_y,
            roi_w=req.roi_w,
            roi_h=req.roi_h
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        global status_state
        status_state["export_progress"] = f"Reference analysis failed: {str(e)}"
        return {"error": str(e)}

@app.get("/api/reference/audio")
def get_reference_audio(path: str):
    if path and os.path.exists(path):
        from fastapi.responses import FileResponse
        return FileResponse(path)
    return {"error": "Audio file not found"}

@app.post("/api/lyrics/import")
def lyrics_import_api(req: LyricsImportRequest):
    try:
        return parse_lyrics_file(req.lyrics_path)
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/lyrics/search")
def lyrics_search_api(req: LyricsSearchRequest):
    try:
        return lookup_lyrics(req.song_name, req.api_key, req.engine_id)
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/export")
def export_media(req: ExportRequest, background_tasks: BackgroundTasks):
    if status_state["is_exporting"]:
        return {"status": "already_exporting"}
        
    project_id = get_or_create_default_project()
    ensure_storyboard_segments_for_ready_media(project_id)
    dedupe_storyboard_by_media(project_id)
    storyboard_items = get_storyboard()
    if not storyboard_items:
        status_state["export_progress"] = "No timeline clips to export. Add videos or photos to the timeline first."
        return {"status": "no_clips", "message": status_state["export_progress"], "clip_count": 0}
    
    desktop = Path.home() / "Desktop"
    output_path = desktop / "clipforge_montage.mp4"
    
    status_state["is_exporting"] = True
    status_state["export_progress"] = "Starting export..."
    
    def run_export():
        try:
            target_duration = req.target_duration
            if req.reference_path and req.pacing == "reference" and target_duration is None:
                try:
                    target_duration = analyze_reference_style(req.reference_path)["target_duration"]
                except Exception as e:
                    print(f"Failed to analyze reference style during export: {e}")
            style_label = f"reference-style {target_duration:.2f}s cuts" if req.pacing == "reference" and target_duration else f"{req.pacing} pacing"
            if req.edit_style == "style1":
                style_label = f"Style 1 lyric edit, {target_duration or 0.65:.2f}s cuts"
            status_state["export_progress"] = f"Exporting {len(storyboard_items)} clips with {style_label}..."
            success = export_montage(
                storyboard_items,
                project_id,
                str(output_path),
                req.audio_path,
                req.pacing,
                target_duration,
                req.title_text,
                req.edit_style,
                req.lyrics_text,
                req.auto_lyrics,
                req.lyrics_timed_lines,
                req.reference_transitions,
                req.reference_texts,
            )
            status_state["export_progress"] = f"Export {'succeeded' if success else 'failed'}: {output_path}"
        finally:
            status_state["is_exporting"] = False

    background_tasks.add_task(run_export)
    return {"status": "exporting", "output_path": str(output_path), "clip_count": len(storyboard_items)}

@app.post("/api/preview")
def preview_media(req: ExportRequest, background_tasks: BackgroundTasks):
    if status_state["is_exporting"]:
        return {"status": "already_exporting"}
        
    project_id = get_or_create_default_project()
    ensure_storyboard_segments_for_ready_media(project_id)
    dedupe_storyboard_by_media(project_id)
    storyboard_items = get_storyboard()
    if not storyboard_items:
        status_state["export_progress"] = "No timeline clips to preview."
        return {"status": "no_clips", "message": status_state["export_progress"], "clip_count": 0}
    
    app_dir = Path.home() / ".clipforge" / "projects" / project_id
    output_path = app_dir / "preview.mp4"
    
    status_state["is_exporting"] = True
    status_state["export_progress"] = "Generating quick preview..."
    
    def run_preview():
        try:
            target_duration = req.target_duration
            if req.reference_path and req.pacing == "reference" and target_duration is None:
                try:
                    target_duration = analyze_reference_style(req.reference_path)["target_duration"]
                except Exception:
                    pass
            success = export_montage(
                storyboard_items,
                project_id,
                str(output_path),
                req.audio_path,
                req.pacing,
                target_duration,
                req.title_text,
                req.edit_style,
                req.lyrics_text,
                req.auto_lyrics,
                req.lyrics_timed_lines,
                req.reference_transitions,
                req.reference_texts,
                is_preview=True
            )
            import time
            if success:
                status_state["export_progress"] = f"Preview ready|/projects/{project_id}/preview.mp4?t={int(time.time())}"
            else:
                status_state["export_progress"] = "Preview generation failed."
        finally:
            status_state["is_exporting"] = False

    background_tasks.add_task(run_preview)
    return {"status": "exporting", "clip_count": len(storyboard_items)}

if __name__ == "__main__":
    # In production, Tauri will pass a dynamic port, but for now we hardcode or read sys.argv
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    print(f"Starting Python engine on port {port}...")
    uvicorn.run(app, host="127.0.0.1", port=port)
