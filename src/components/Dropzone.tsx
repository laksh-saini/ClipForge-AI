import { useState, useEffect } from 'react';
import { UploadCloud } from 'lucide-react';
import { open } from '@tauri-apps/plugin-dialog';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

interface DropzoneProps {
  onIngest: (paths: string[]) => void;
}

export function Dropzone({ onIngest }: DropzoneProps) {
  const [isHovering, setIsHovering] = useState(false);

  useEffect(() => {
    let unlistenDrop: (() => void) | undefined;
    let unlistenEnter: (() => void) | undefined;
    let unlistenLeave: (() => void) | undefined;
    let isMounted = true;

    const setupListeners = async () => {
      const drop = await listen('tauri://drag-drop', async (event) => {
        setIsHovering(false);
        const paths = (event.payload as any).paths as string[];
        if (paths && paths.length > 0) {
          try {
            const staged = await invoke<string[]>('stage_media_files', { paths });
            onIngest(staged);
          } catch (stageError) {
            console.error("Error staging files:", stageError);
            onIngest(paths);
          }
        }
      });
      if (isMounted) unlistenDrop = drop; else drop();

      const enter = await listen('tauri://drag-enter', () => {
        setIsHovering(true);
      });
      if (isMounted) unlistenEnter = enter; else enter();

      const leave = await listen('tauri://drag-leave', () => {
        setIsHovering(false);
      });
      if (isMounted) unlistenLeave = leave; else leave();
    };

    setupListeners();

    return () => {
      isMounted = false;
      if (unlistenDrop) unlistenDrop();
      if (unlistenEnter) unlistenEnter();
      if (unlistenLeave) unlistenLeave();
    };
  }, [onIngest]);

  const handleManualSelect = async () => {
    try {
      const selected = await open({
        multiple: true,
        directory: false,
        filters: [{
          name: 'Media',
          extensions: ['mp4', 'mov', 'avi', 'mkv', 'jpg', 'jpeg', 'png', 'heic']
        }]
      });
      
      const paths = Array.isArray(selected) ? selected : selected ? [selected] : [];
      if (paths.length > 0) {
        try {
          const staged = await invoke<string[]>('stage_media_files', { paths });
          onIngest(staged);
        } catch (stageError) {
          console.error("Error staging files:", stageError);
          onIngest(paths);
        }
      }
    } catch (e) {
      console.error("Error selecting files:", e);
    }
  };

  return (
    <div 
      className={`flex min-h-[180px] w-full cursor-pointer flex-col items-start justify-center rounded-[28px] border-2 border-dashed p-7 text-left transition-all duration-200 ${
        isHovering ? 'border-[#cfff45] bg-[#cfff45]/12' : 'border-white/12 bg-[#242525] hover:border-[#cfff45]/55 hover:bg-[#292b2b]'
      }`}
      onDragOver={(e) => { e.preventDefault(); setIsHovering(true); }}
      onDragLeave={() => setIsHovering(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsHovering(false);
        // We handle file drops via the Tauri event listener in useEffect
      }}
      onClick={handleManualSelect}
    >
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[#cfff45] text-[#1e1f1f] shadow-lg shadow-lime-950/20">
        <UploadCloud className="h-8 w-8" />
      </div>
      <h3 className="mb-2 text-xl font-semibold text-white">
        Drop media into the studio
      </h3>
      <p className="max-w-md text-sm text-white/55">
        MP4, MOV, AVI, JPG, PNG, and HEIC are ready for AI clipping.
      </p>
    </div>
  );
}
