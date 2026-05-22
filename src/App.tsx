import { useState, useEffect } from "react";
import { Dropzone } from "./components/Dropzone";
import { MediaGallery } from "./components/MediaGallery";
import { Storyboard } from "./components/Storyboard";
import { TextSyncAnalysis } from "./components/TextSyncAnalysis";
import { open } from '@tauri-apps/plugin-dialog';
import { invoke } from '@tauri-apps/api/core';
import {
  Activity,
  BadgePlus,
  Bell,
  Clapperboard,
  Crown,
  Film,
  Home,
  LogOut,
  Music2,
  Search,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Upload,
  Wand2,
} from 'lucide-react';
import "./App.css";

interface ReferenceStyle {
  file_name: string;
  duration: number;
  detected_cuts: number;
  target_duration: number;
  cuts_per_minute: number;
  energy: string;
}

interface TimedLyricLine {
  time: number;
  text: string;
}

function App() {
  const [pythonStatus, setPythonStatus] = useState<string>("Checking...");
  const [ingestCount, setIngestCount] = useState(0);
  const [isExporting, setIsExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState("");
  const [audioPath, setAudioPath] = useState<string | null>(null);
  const [referencePath, setReferencePath] = useState<string | null>(null);
  const [referenceStyle, setReferenceStyle] = useState<ReferenceStyle | null>(null);
  const [referenceTransitions, setReferenceTransitions] = useState<any[]>([]);
  const [referenceTexts, setReferenceTexts] = useState<any[]>([]);
  const [pacing, setPacing] = useState<string>("dynamic");
  const [titleText, setTitleText] = useState<string>("");
  const [editStyle, setEditStyle] = useState<string>("title");
  const [lyricsText, setLyricsText] = useState<string>("");
  const [autoLyrics, setAutoLyrics] = useState<boolean>(false);
  const [lyricsFileName, setLyricsFileName] = useState<string | null>(null);
  const [lyricsSearch, setLyricsSearch] = useState<string>("");
  const [isLyricsLoading, setIsLyricsLoading] = useState<boolean>(false);
  const [lyricsTimedLines, setLyricsTimedLines] = useState<TimedLyricLine[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [lastPreviewUrl, setLastPreviewUrl] = useState<string | null>(null);
  const [isAnalyzingRef, setIsAnalyzingRef] = useState(false);
  const engineReady = pythonStatus.startsWith("Connected");

  useEffect(() => {
    const checkServer = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/ping");
        if (res.ok) {
          const data = await res.json();
          setPythonStatus(`Connected: ${data.message}`);
        } else {
          setPythonStatus("Error: Bad response from server.");
        }
      } catch (e) {
        setPythonStatus("Error: Could not connect to Python engine.");
      }
    };
    
    const fetchStatus = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/api/status");
        if (res.ok) {
          const data = await res.json();
          setIngestCount(data.ingesting_count);
          setIsExporting(data.is_exporting);
          if (data.export_progress) {
            if (data.export_progress.startsWith("Preview ready|")) {
              const url = data.export_progress.split("|")[1];
              if (url !== lastPreviewUrl) {
                setPreviewUrl(`http://127.0.0.1:8000${url}`);
                setLastPreviewUrl(url);
                setExportMessage("Preview generated!");
              }
            } else {
              setExportMessage(data.export_progress);
            }
          }
        }
      } catch (e) {
        // ignore
      }
    };
    
    const interval = setInterval(() => {
      checkServer();
      fetchStatus();
    }, 2000);
    checkServer();
    fetchStatus();

    return () => clearInterval(interval);
  }, []);

  const handleIngest = async (paths: string[]) => {
    try {
      await fetch("http://127.0.0.1:8000/api/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_paths: paths }),
      });
      // Polling will pick up the status change
    } catch (e) {
      console.error("Failed to ingest", e);
    }
  };

  const handleSelectAudio = async () => {
    try {
      const selected = await open({
        multiple: false,
        directory: false,
        filters: [{ name: 'Audio', extensions: ['mp3', 'wav'] }]
      });
      if (selected && typeof selected === 'string') {
        setAudioPath(selected);
      }
    } catch (e) {
      console.error("Failed to select audio", e);
    }
  };

  const analyzeReference = async (path: string, roi?: {x: number, y: number, w: number, h: number}) => {
    setIsAnalyzingRef(true);
    setExportMessage("Analyzing reference edit...");
    try {
      const body: any = { reference_path: path };
      if (roi) {
        body.roi_x = roi.x;
        body.roi_y = roi.y;
        body.roi_w = roi.w;
        body.roi_h = roi.h;
      }
      const res = await fetch("http://127.0.0.1:8000/api/reference-style", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.error) {
        setExportMessage(`Reference analysis failed: ${data.error}`);
        return;
      }
      setReferencePath(path);
      setReferenceStyle(data);
      if (data.audio_path) {
          setAudioPath(data.audio_path);
      }
      setReferenceTransitions(data.transitions || []);
      setReferenceTexts(data.texts || []);
      setExportMessage(`Analyzed reference video. (Select 'Match Reference' pacing if you want its exact cut speed)`);
    } catch (e) {
      setExportMessage("Failed to analyze reference edit.");
    } finally {
      setIsAnalyzingRef(false);
    }
  };

  const handleSelectReference = async () => {
    try {
      const selected = await open({
        multiple: false,
        directory: false,
        filters: [{ name: 'Reference Video', extensions: ['mp4', 'mov', 'm4v'] }]
      });
      if (!selected || typeof selected !== 'string') return;
      const staged = await invoke<string[]>('stage_media_files', { paths: [selected] });
      const stagedPath = staged[0] || selected;
      await analyzeReference(stagedPath);
    } catch (e) {
      setExportMessage("Failed to select reference video.");
    }
  };

  const handleImportLyrics = async () => {
    try {
      const selected = await open({
        multiple: false,
        directory: false,
        filters: [{ name: 'Lyrics', extensions: ['lrc', 'srt', 'txt'] }]
      });
      if (!selected || typeof selected !== 'string') return;

      const res = await fetch("http://127.0.0.1:8000/api/lyrics/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lyrics_path: selected }),
      });
      const data = await res.json();
      if (data.error) {
        setExportMessage(`Lyrics import failed: ${data.error}`);
        return;
      }
      setAutoLyrics(false);
      setLyricsText((data.lines || []).join("\n"));
      setLyricsTimedLines(data.timed_lines || []);
      setLyricsFileName(data.file_name);
      const timingNote = data.timed_lines?.length ? ` with ${data.timed_lines.length} timestamp${data.timed_lines.length === 1 ? "" : "s"}` : "";
      setExportMessage(`Imported ${data.lines?.length || 0} lyric line${data.lines?.length === 1 ? "" : "s"}${timingNote}.`);
    } catch (e) {
      setExportMessage("Failed to import lyrics.");
    }
  };

  const handleFindLyrics = async () => {
    const songName = lyricsSearch.trim();
    if (!songName) {
      setExportMessage("Enter a song name before searching lyrics.");
      return;
    }

    setIsLyricsLoading(true);
    setExportMessage(`Searching lyrics for ${songName}...`);
    try {
      const res = await fetch("http://127.0.0.1:8000/api/lyrics/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ song_name: songName }),
      });
      const data = await res.json();
      if (data.error) {
        setExportMessage(`Lyrics search failed: ${data.error}`);
        return;
      }
      const lines = data.lines || [];
      setAutoLyrics(false);
      setLyricsText(lines.join("\n"));
      setLyricsTimedLines([]);
      setLyricsFileName(data.title || songName);
      setExportMessage(`Loaded ${lines.length} lyric line${lines.length === 1 ? "" : "s"} for ${data.title || songName}. Plain searched lyrics will be paced across the song; import .lrc/.srt for exact timestamps.`);
    } catch (e) {
      setExportMessage("Lyrics search failed.");
    } finally {
      setIsLyricsLoading(false);
    }
  };

  const handleExport = async () => {
    setExportMessage("Starting export...");
    try {
      const res = await fetch("http://127.0.0.1:8000/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_path: audioPath,
          pacing: pacing,
          reference_path: referencePath,
          target_duration: pacing === "reference" ? referenceStyle?.target_duration : editStyle === "style1" ? 0.65 : undefined,
          title_text: titleText.trim() || undefined,
          edit_style: editStyle,
          lyrics_text: autoLyrics ? undefined : lyricsText.trim() || undefined,
          auto_lyrics: autoLyrics,
          lyrics_timed_lines: autoLyrics ? undefined : lyricsTimedLines,
          reference_transitions: referenceTransitions,
          reference_texts: referenceTexts,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setExportMessage(data.message || "Failed to start export.");
        return;
      }
      if (data.status === "already_exporting") {
        setExportMessage("Export already in progress...");
      } else if (data.status === "no_clips") {
        setExportMessage(data.message);
      } else if (data.status === "exporting") {
        setExportMessage(`Export started with ${data.clip_count} clip${data.clip_count === 1 ? "" : "s"}...`);
      }
    } catch (e) {
      setExportMessage("Failed to start export.");
    }
  };

  const handlePreview = async () => {
    setExportMessage("Starting quick preview render...");
    try {
      const res = await fetch("http://127.0.0.1:8000/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_path: audioPath,
          pacing: pacing,
          reference_path: referencePath,
          target_duration: pacing === "reference" ? referenceStyle?.target_duration : editStyle === "style1" ? 0.65 : undefined,
          title_text: titleText.trim() || undefined,
          edit_style: editStyle,
          lyrics_text: autoLyrics ? undefined : lyricsText.trim() || undefined,
          auto_lyrics: autoLyrics,
          lyrics_timed_lines: autoLyrics ? undefined : lyricsTimedLines,
          reference_transitions: referenceTransitions,
          reference_texts: referenceTexts,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setExportMessage(data.message || "Failed to start preview.");
      }
    } catch (e) {
      setExportMessage("Failed to start preview.");
    }
  };

  const handleClearSession = async () => {
    const confirmed = window.confirm("Clear the current ClipForge session? This removes the timeline and ingested media from the app, but leaves your original files alone.");
    if (!confirmed) return;

    try {
      const res = await fetch("http://127.0.0.1:8000/api/project/clear", {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) {
        setExportMessage("Failed to clear session.");
        return;
      }
      setReferencePath(null);
      setReferenceStyle(null);
      setReferenceTransitions([]);
      setReferenceTexts([]);
      setTitleText("");
      setLyricsText("");
      setLyricsFileName(null);
      setLyricsSearch("");
      setLyricsTimedLines([]);
      setAutoLyrics(false);
      setPacing("dynamic");
      setExportMessage(`Session cleared: removed ${data.media_deleted ?? 0} media item${data.media_deleted === 1 ? "" : "s"}.`);
      setTimeout(() => window.location.reload(), 300);
    } catch (e) {
      setExportMessage("Failed to clear session.");
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#5d5d5b] px-4 py-5 text-white sm:px-7 lg:px-10">
      <div className="app-backdrop fixed inset-0 pointer-events-none" />
      <div className="relative mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[1760px] gap-6 rounded-[34px] bg-[#1e1f1f] p-4 shadow-[0_28px_90px_rgba(0,0,0,0.42)] ring-1 ring-white/10 md:p-7">
        <aside className="hidden w-[82px] shrink-0 flex-col items-center justify-between rounded-[30px] bg-[#263030]/80 px-3 py-6 md:flex">
          <div className="flex flex-col items-center gap-7">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-[#1e1f1f] shadow-lg">
              <Clapperboard className="h-6 w-6" />
            </div>
            <nav className="flex flex-col gap-4">
              <button className="dashboard-icon dashboard-icon-active" title="Home">
                <Home className="h-5 w-5" />
              </button>
              <button className="dashboard-icon" title="Media">
                <Film className="h-5 w-5" />
              </button>
              <button className="dashboard-icon" title="Audio">
                <Music2 className="h-5 w-5" />
              </button>
              <button className="dashboard-icon" title="Settings">
                <Settings className="h-5 w-5" />
              </button>
              <button className="dashboard-icon" title="Alerts">
                <Bell className="h-5 w-5" />
              </button>
            </nav>
          </div>
          <div className="flex flex-col items-center gap-5">
            <button onClick={handleClearSession} className="dashboard-icon" title="Clear session">
              <LogOut className="h-5 w-5" />
            </button>
            <div className="h-12 w-12 rounded-full bg-gradient-to-br from-[#4f6cf0] to-[#cfff45] p-[2px]">
              <div className="h-full w-full rounded-full bg-[#262929]" />
            </div>
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-hidden">
          <header className="mb-6 flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="mb-2 text-sm font-medium text-[#cfff45]">ClipForge AI</p>
              <h1 className="text-3xl font-semibold tracking-normal text-white md:text-4xl">
                Hello, creator.
              </h1>
              <p className="mt-1 text-base text-white/70">Ready to build today&apos;s montage?</p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="flex h-14 min-w-[260px] items-center gap-3 rounded-[28px] bg-[#383a3a] px-5 text-white/60">
                <Search className="h-5 w-5 shrink-0 text-white" />
                <span className="truncate text-sm">Search your media, audio, styles</span>
              </div>
              <div className="flex h-14 items-center gap-3 rounded-[28px] bg-[#383a3a] px-5">
                <span className={`h-3 w-3 rounded-full ${engineReady ? "bg-[#cfff45]" : "bg-amber-400"}`} />
                <span className="text-sm font-medium text-white/80">
                  {engineReady ? "Engine Ready" : "Engine Offline"}
                </span>
              </div>
              <button className="flex h-14 items-center gap-2 rounded-[28px] bg-[#516bef] px-6 text-sm font-semibold text-white shadow-lg shadow-blue-950/30">
                <Crown className="h-4 w-4" />
                Studio
              </button>
            </div>
          </header>

          <section className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(340px,0.8fr)]">
            <div className="space-y-6">
              <div className="rounded-[30px] bg-[#343535] p-5 ring-1 ring-white/5 md:p-6">
                <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <h2 className="text-2xl font-semibold">Create Montage</h2>
                    <p className="mt-1 text-sm text-white/60">Import, cut, sync, and export from one console.</p>
                  </div>
                  <button
                    onClick={handleClearSession}
                    className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-[#242525] px-4 py-2 text-sm text-white/70 transition hover:text-[#cfff45]"
                  >
                    <BadgePlus className="h-4 w-4" />
                    New Project
                  </button>
                </div>
                <Dropzone onIngest={handleIngest} />
                {ingestCount > 0 && (
                  <div className="mt-4 flex items-center justify-center gap-3 rounded-2xl border border-[#cfff45]/20 bg-[#cfff45]/10 px-4 py-3 text-sm font-medium text-[#d9ff6b]">
                    <div className="h-4 w-4 rounded-full border-2 border-[#cfff45] border-t-transparent animate-spin" />
                    Processing {ingestCount} clip{ingestCount !== 1 ? "s" : ""}.
                  </div>
                )}
              </div>

              <Storyboard pacing={pacing} referenceDuration={referenceStyle?.target_duration} />

              <div className="rounded-[30px] bg-[#343535] p-5 ring-1 ring-white/5 md:p-6">
                <div className="mb-5 flex items-center justify-between gap-4">
                  <div>
                    <h2 className="text-2xl font-semibold">Media Library</h2>
                    <p className="mt-1 text-sm text-white/60">All usable clips and photos from this session.</p>
                  </div>
                  <Film className="h-7 w-7 text-[#cfff45]" />
                </div>
                <MediaGallery />
              </div>
            </div>

            <aside className="space-y-6">
              <div className="rounded-[30px] bg-[#516bef] p-6 text-white shadow-xl shadow-blue-950/25">
                <div className="mb-7 flex items-center justify-between gap-4">
                  <div>
                    <h2 className="text-2xl font-semibold">Export Suite</h2>
                    <p className="mt-1 text-sm text-white/75">Current montage settings</p>
                  </div>
                  <Sparkles className="h-7 w-7" />
                </div>
                <button
                  onClick={handleExport}
                  disabled={isExporting}
                  className={`flex h-16 w-full items-center justify-center gap-3 rounded-[24px] text-base font-bold transition ${
                    isExporting
                      ? "bg-[#222525] text-white/50"
                      : "bg-[#1e1f1f] text-white shadow-lg shadow-blue-950/30 hover:bg-[#292b2b]"
                  }`}
                >
                  {isExporting ? (
                    <div className="h-5 w-5 rounded-full border-2 border-white/60 border-t-transparent animate-spin" />
                  ) : (
                    <Upload className="h-5 w-5" />
                  )}
                  {isExporting ? "Exporting..." : "Export Montage"}
                </button>
                <button
                  onClick={handlePreview}
                  disabled={isExporting}
                  className={`mt-3 flex h-12 w-full items-center justify-center gap-2 rounded-[20px] text-sm font-semibold transition ${
                    isExporting
                      ? "bg-[#222525] text-white/30"
                      : "bg-[#242525] text-white/80 hover:bg-[#2e3030] ring-1 ring-white/10"
                  }`}
                >
                  <Film className="h-4 w-4" />
                  Quick Preview
                </button>
              </div>

              <div className="rounded-[30px] bg-[#343535] p-6 ring-1 ring-white/5">
                <div className="mb-5 flex items-center justify-between">
                  <h2 className="text-xl font-semibold">Edit Controls</h2>
                  <SlidersHorizontal className="h-5 w-5 text-[#cfff45]" />
                </div>

                <div className="space-y-4">
                  <button
                    onClick={handleSelectAudio}
                    className="control-button"
                  >
                    <Music2 className="h-5 w-5 text-[#cfff45]" />
                    <span className="min-w-0 flex-1 truncate text-left">
                      {audioPath ? audioPath.split('/').pop() : "Select Background Music"}
                    </span>
                  </button>

                  <label className="control-field">
                    <span>Pacing</span>
                    <select value={pacing} onChange={(e) => setPacing(e.target.value)}>
                      <option value="cinematic">Cinematic (~3.0s cuts)</option>
                      <option value="dynamic">Dynamic (~2.0s cuts)</option>
                      <option value="fast">Hype (~1.0s cuts)</option>
                      <option value="reference" disabled={!referenceStyle}>
                        Match Reference{referenceStyle ? ` (~${referenceStyle.target_duration.toFixed(1)}s cuts)` : ""}
                      </option>
                    </select>
                  </label>

                  <button onClick={handleSelectReference} className="control-button">
                    <Wand2 className="h-5 w-5 text-[#cfff45]" />
                    <span className="min-w-0 flex-1 truncate text-left">
                      {referenceStyle ? `Needs ${referenceStyle.detected_cuts} clips | ${referenceStyle.energy}` : "Match Reference Video"}
                    </span>
                  </button>

                  <label className="control-field">
                    <span>Title Overlay</span>
                    <input
                      value={titleText}
                      onChange={(e) => setTitleText(e.target.value)}
                      placeholder="Title overlay"
                      maxLength={48}
                    />
                  </label>

                  <label className="control-field">
                    <span>Style</span>
                    <select value={editStyle} onChange={(e) => setEditStyle(e.target.value)}>
                      <option value="title">Title</option>
                      <option value="style1">Style 1 - lyric flash</option>
                    </select>
                  </label>
                </div>
              </div>

              {editStyle === "style1" && (
                <div className="rounded-[30px] bg-[#343535] p-6 ring-1 ring-white/5">
                  <div className="mb-5 flex items-center justify-between">
                    <h2 className="text-xl font-semibold">Lyric Flash</h2>
                    <Activity className="h-5 w-5 text-[#cfff45]" />
                  </div>
                  <div className="space-y-3">
                    <div className="flex gap-2">
                      <input
                        value={lyricsSearch}
                        onChange={(e) => setLyricsSearch(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleFindLyrics();
                        }}
                        placeholder="Song name"
                        className="min-w-0 flex-1 rounded-full bg-[#242525] px-4 py-3 text-sm text-white outline-none ring-1 ring-white/10 placeholder:text-white/35 focus:ring-[#cfff45]"
                      />
                      <button
                        onClick={handleFindLyrics}
                        disabled={isLyricsLoading}
                        className="rounded-full bg-[#cfff45] px-4 py-3 text-sm font-semibold text-[#1e1f1f] disabled:bg-white/15 disabled:text-white/40"
                      >
                        {isLyricsLoading ? "Finding" : "Find"}
                      </button>
                    </div>
                    <button onClick={handleImportLyrics} className="control-button">
                      <Upload className="h-5 w-5 text-[#cfff45]" />
                      <span className="min-w-0 flex-1 truncate text-left">
                        {lyricsFileName || "Import timed lyrics"}
                      </span>
                    </button>
                    <label className="flex items-center gap-2 rounded-2xl bg-[#242525] px-4 py-3 text-sm text-white/70">
                      <input
                        type="checkbox"
                        checked={autoLyrics}
                        onChange={(e) => setAutoLyrics(e.target.checked)}
                        className="accent-[#cfff45]"
                      />
                      Placeholder captions
                    </label>
                    <textarea
                      value={lyricsText}
                      onChange={(e) => {
                        setLyricsText(e.target.value);
                        setLyricsTimedLines([]);
                        if (e.target.value.trim()) setAutoLyrics(false);
                      }}
                      placeholder="Exact lyric/caption lines"
                      rows={4}
                      className="w-full resize-none rounded-[22px] bg-[#242525] px-4 py-3 text-sm text-white outline-none ring-1 ring-white/10 placeholder:text-white/35 focus:ring-[#cfff45]"
                    />
                  </div>
                </div>
              )}

              {referencePath && referenceTexts.length > 0 && (
                <TextSyncAnalysis 
                  referencePath={referencePath} 
                  referenceTexts={referenceTexts} 
                  setReferenceTexts={setReferenceTexts}
                  onReanalyze={(roi) => analyzeReference(referencePath, roi)}
                  isAnalyzing={isAnalyzingRef}
                />
              )}

              {exportMessage && (
                <div className={`rounded-[26px] px-5 py-4 text-sm font-medium ring-1 ${
                  exportMessage.includes("succeeded")
                    ? "bg-[#cfff45]/15 text-[#dfff75] ring-[#cfff45]/25"
                    : exportMessage.includes("failed")
                    ? "bg-red-500/15 text-red-200 ring-red-400/20"
                    : "bg-white/8 text-white/75 ring-white/10"
                }`}>
                  {exportMessage}
                </div>
              )}
            </aside>
          </section>
        </main>
      </div>

      {previewUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="relative w-full max-w-4xl rounded-[24px] bg-[#1e1f1f] overflow-hidden shadow-2xl ring-1 ring-white/20">
            <div className="flex items-center justify-between bg-[#2a2b2b] px-5 py-4 border-b border-white/5">
              <h3 className="text-base font-semibold text-white/90">Quick Preview</h3>
              <button 
                onClick={() => setPreviewUrl(null)} 
                className="rounded-full bg-[#383a3a] px-4 py-1.5 text-sm font-medium text-white/80 transition hover:bg-[#4a4d4d]"
              >
                Close
              </button>
            </div>
            <div className="aspect-video bg-black flex items-center justify-center p-2">
              <video 
                src={previewUrl} 
                controls 
                autoPlay 
                className="w-full h-full object-contain rounded-xl"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
