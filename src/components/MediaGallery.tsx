import { useEffect, useState } from 'react';
import { Film, Image as ImageIcon } from 'lucide-react';

export interface MediaFile {
  id: string;
  file_path: string;
  type: string;
  status: string;
  thumbnail_path: string | null;
  is_rejected: number;
  reject_reason: string;
}

export function MediaGallery() {
  const [media, setMedia] = useState<MediaFile[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchMedia = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/media");
      if (res.ok) {
        const data = await res.json();
        setMedia(data);
      }
    } catch (e) {
      console.error("Failed to fetch media");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMedia();
    const interval = setInterval(fetchMedia, 3000); // Poll every 3 seconds for thumbnail updates
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="text-white/45">Loading media...</div>;

  if (media.length === 0) return null;
  const usableMedia = media.filter((file) => file.is_rejected !== 1);
  const failedCount = media.length - usableMedia.length;

  return (
    <div className="w-full">
      {failedCount > 0 && (
        <div className="mb-4 rounded-2xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">
          {failedCount} failed import{failedCount === 1 ? "" : "s"} hidden. Re-select those files after restarting the app.
        </div>
      )}
      
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
        {usableMedia.map((file) => (
          <div key={file.id} className={`group relative aspect-video overflow-hidden rounded-[20px] border bg-[#242525] transition-all ${file.is_rejected ? 'border-red-900/50 opacity-50' : 'border-white/10 hover:border-[#cfff45]/55'}`}>
            {file.type === 'video' ? (
              <video 
                src={`http://127.0.0.1:8000/api/media/stream?path=${encodeURIComponent(file.file_path)}`}
                poster={file.thumbnail_path ? `http://127.0.0.1:8000/projects/${file.thumbnail_path.split('.clipforge/projects/')[1]}` : undefined}
                className={`h-full w-full object-cover ${file.is_rejected ? 'grayscale' : ''}`}
                muted
                loop
                playsInline
                preload="none"
                onMouseEnter={(e) => { e.currentTarget.play().catch(() => {}); }}
                onMouseLeave={(e) => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}
              />
            ) : file.thumbnail_path ? (
              <img 
                src={`http://127.0.0.1:8000/projects/${file.thumbnail_path.split('.clipforge/projects/')[1]}`} 
                alt="thumbnail"
                className={`h-full w-full object-cover ${file.is_rejected ? 'grayscale' : ''}`}
              />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center bg-[#1e1f1f] text-white/35">
                {file.type === 'video' ? <Film className="mb-2 h-8 w-8 opacity-50" /> : <ImageIcon className="mb-2 h-8 w-8 opacity-50" />}
                <span className="text-xs font-medium uppercase">{file.status}</span>
              </div>
            )}
            
            {/* Rejected Badge */}
            {file.is_rejected === 1 && (
              <div className="absolute right-2 top-2 rounded-full bg-red-600/90 px-2 py-1 text-[10px] font-bold text-white shadow-sm">
                REJECTED: {file.reject_reason}
              </div>
            )}
            
            {/* Overlay */}
            <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/82 via-transparent to-transparent p-3 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
              <span className="w-full truncate text-[11px] text-white/80" title={file.file_path}>
                {file.file_path.split('/').pop() || file.file_path.split('\\').pop()}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
