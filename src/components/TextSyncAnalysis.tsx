import React, { useState, useRef } from 'react';
import { Settings2, Edit2, SplitSquareHorizontal, Merge } from 'lucide-react';

interface TextSegment {
  start: number;
  end: number;
  text: string;
  confidence: number;
}

interface Props {
  referencePath: string | null;
  referenceTexts: TextSegment[];
  setReferenceTexts: (texts: TextSegment[]) => void;
  onReanalyze: (roi: { x: number; y: number; w: number; h: number }) => void;
  isAnalyzing: boolean;
}

export const TextSyncAnalysis: React.FC<Props> = ({
  referencePath,
  referenceTexts,
  setReferenceTexts,
  onReanalyze,
  isAnalyzing
}) => {
  const [showRoiModal, setShowRoiModal] = useState(false);
  const [roi, setRoi] = useState({ x: 0.2, y: 0.4, w: 0.6, h: 0.2 });
  
  const handleNudge = (index: number, field: 'start' | 'end', delta: number) => {
    const newTexts = [...referenceTexts];
    newTexts[index] = { ...newTexts[index], [field]: Math.max(0, newTexts[index][field] + delta) };
    setReferenceTexts(newTexts);
  };

  const handleEdit = (index: number) => {
    const newText = window.prompt("Edit text:", referenceTexts[index].text);
    if (newText !== null) {
      const newTexts = [...referenceTexts];
      newTexts[index] = { ...newTexts[index], text: newText };
      setReferenceTexts(newTexts);
    }
  };

  const handleSplit = (index: number) => {
    const seg = referenceTexts[index];
    const mid = seg.start + (seg.end - seg.start) / 2;
    const newTexts = [...referenceTexts];
    newTexts.splice(index, 1, 
      { ...seg, end: mid },
      { ...seg, start: mid }
    );
    setReferenceTexts(newTexts);
  };

  const handleMerge = (index: number) => {
    if (index >= referenceTexts.length - 1) return;
    const seg = referenceTexts[index];
    const nextSeg = referenceTexts[index + 1];
    const newTexts = [...referenceTexts];
    newTexts.splice(index, 2, {
      ...seg,
      end: nextSeg.end,
      text: seg.text + " " + nextSeg.text,
      confidence: Math.min(seg.confidence, nextSeg.confidence)
    });
    setReferenceTexts(newTexts);
  };

  if (!referencePath || referenceTexts.length === 0) return null;

  return (
    <div className="rounded-[30px] bg-[#343535] p-6 ring-1 ring-white/5 mt-6">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Text Sync Analysis</h2>
        <button 
          onClick={() => setShowRoiModal(true)}
          className="flex items-center gap-2 rounded-full bg-[#4a4d4d] px-4 py-2 text-sm font-medium hover:bg-[#5a5d5d]"
        >
          <Settings2 className="h-4 w-4" />
          Adjust ROI
        </button>
      </div>

      <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
        {referenceTexts.map((seg, i) => (
          <div key={i} className="rounded-xl bg-[#242525] p-4 flex flex-col gap-3 border border-white/5">
            <div className="flex items-center justify-between">
              <span className="font-medium text-[#cfff45] text-lg">"{seg.text}"</span>
              <span className={`text-xs px-2 py-1 rounded-md ${seg.confidence > 0.7 ? 'bg-green-500/20 text-green-300' : 'bg-yellow-500/20 text-yellow-300'}`}>
                {Math.round(seg.confidence * 100)}% Conf
              </span>
            </div>
            
            <div className="flex items-center gap-4 text-sm text-white/60">
              <div className="flex items-center gap-2">
                <span>Start: {seg.start.toFixed(2)}s</span>
                <button onClick={() => handleNudge(i, 'start', -0.05)} className="px-1 hover:text-white">-</button>
                <button onClick={() => handleNudge(i, 'start', 0.05)} className="px-1 hover:text-white">+</button>
              </div>
              <div className="flex items-center gap-2">
                <span>End: {seg.end.toFixed(2)}s</span>
                <button onClick={() => handleNudge(i, 'end', -0.05)} className="px-1 hover:text-white">-</button>
                <button onClick={() => handleNudge(i, 'end', 0.05)} className="px-1 hover:text-white">+</button>
              </div>
            </div>

            <div className="flex gap-2 mt-2">
              <button onClick={() => handleEdit(i)} className="p-2 rounded bg-white/5 hover:bg-white/10" title="Edit Text"><Edit2 className="h-4 w-4" /></button>
              <button onClick={() => handleSplit(i)} className="p-2 rounded bg-white/5 hover:bg-white/10" title="Split"><SplitSquareHorizontal className="h-4 w-4" /></button>
              {i < referenceTexts.length - 1 && (
                <button onClick={() => handleMerge(i)} className="p-2 rounded bg-white/5 hover:bg-white/10" title="Merge with next"><Merge className="h-4 w-4" /></button>
              )}
            </div>
          </div>
        ))}
      </div>

      {showRoiModal && (
        <RoiModal 
          videoPath={referencePath}
          initialRoi={roi}
          onClose={() => setShowRoiModal(false)}
          onAnalyze={(newRoi: { x: number, y: number, w: number, h: number }) => {
            setRoi(newRoi);
            setShowRoiModal(false);
            onReanalyze(newRoi);
          }}
          isAnalyzing={isAnalyzing}
        />
      )}
    </div>
  );
};

const RoiModal = ({ videoPath, initialRoi, onClose, onAnalyze, isAnalyzing }: any) => {
  const [roi, setRoi] = useState(initialRoi);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setDragStart({ x, y });
    setRoi({ x, y, w: 0, h: 0 });
    setIsDragging(true);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const currentX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const currentY = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    
    setRoi({
      x: Math.min(dragStart.x, currentX),
      y: Math.min(dragStart.y, currentY),
      w: Math.abs(currentX - dragStart.x),
      h: Math.abs(currentY - dragStart.y)
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  // We need to fetch the video through our streaming endpoint to bypass CORS
  const encodedPath = encodeURIComponent(videoPath);
  const videoUrl = `http://127.0.0.1:8000/api/media/stream?path=${encodedPath}`;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4">
      <div className="bg-[#1e1f1f] rounded-2xl max-w-4xl w-full p-6 ring-1 ring-white/10">
        <h3 className="text-xl font-bold mb-4">Adjust Text Detection Region (ROI)</h3>
        <p className="text-sm text-white/60 mb-4">Draw a box around where the lyrics/text appear to ignore background noise.</p>
        
        <div 
          className="relative w-full aspect-[9/16] max-h-[60vh] bg-black mx-auto overflow-hidden cursor-crosshair"
          ref={containerRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <video src={videoUrl} autoPlay loop muted className="w-full h-full object-contain pointer-events-none" />
          
          <div 
            className="absolute border-2 border-[#cfff45] bg-[#cfff45]/20"
            style={{
              left: `${roi.x * 100}%`,
              top: `${roi.y * 100}%`,
              width: `${roi.w * 100}%`,
              height: `${roi.h * 100}%`
            }}
          />
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button onClick={onClose} className="px-5 py-2 rounded-full hover:bg-white/10">Cancel</button>
          <button 
            onClick={() => onAnalyze(roi)} 
            disabled={isAnalyzing || roi.w === 0}
            className="bg-[#cfff45] text-black px-5 py-2 rounded-full font-bold disabled:opacity-50"
          >
            {isAnalyzing ? "Analyzing..." : "Save & Re-analyze"}
          </button>
        </div>
      </div>
    </div>
  );
};
