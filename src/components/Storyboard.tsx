import { useState, useEffect } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  horizontalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Trash2, GripHorizontal, Film } from 'lucide-react';

interface StoryboardItem {
  storyboard_id: string;
  order_index: number;
  segment_id: string;
  start_time: number;
  end_time: number;
  score: number;
  media_id: string;
  file_path: string;
  thumbnail_path: string | null;
  type: string;
}

function SortableItem({ item, onDelete, outputDuration }: { item: StoryboardItem, onDelete: (id: string) => void, outputDuration: number }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.storyboard_id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`relative h-32 w-56 flex-shrink-0 overflow-hidden rounded-[22px] border-2 bg-[#242525] ${
        isDragging ? 'z-50 border-[#cfff45] opacity-80 shadow-2xl' : 'border-white/10 hover:border-[#cfff45]/50'
      } group`}
    >
      {/* Drag Handle */}
      <div 
        {...attributes} 
        {...listeners}
        className="absolute left-0 top-0 z-10 flex h-9 w-full cursor-grab items-start justify-center bg-gradient-to-b from-black/75 to-transparent pt-1 opacity-0 transition-opacity active:cursor-grabbing group-hover:opacity-100"
      >
        <GripHorizontal className="w-5 h-5 text-white/70" />
      </div>

      {/* Thumbnail */}
      {item.thumbnail_path ? (
        <img 
          src={`http://127.0.0.1:8000/projects/${item.thumbnail_path.split('.clipforge/projects/')[1]}`} 
          alt="thumbnail"
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-[#1e1f1f] text-white/25">
          <Film className="h-8 w-8 opacity-50" />
        </div>
      )}

      {/* Segment Info */}
      <div className="absolute bottom-0 left-0 z-10 flex w-full items-center justify-between bg-black/72 px-2 py-1.5">
        <span className="font-mono text-[11px] text-white/80">
          {item.start_time.toFixed(1)}s - {(item.start_time + outputDuration).toFixed(1)}s
        </span>
        <button 
          onClick={(e) => { e.stopPropagation(); onDelete(item.storyboard_id); }}
          className="rounded-full p-1 text-white/50 hover:bg-white/10 hover:text-red-300"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      
      {/* AI Score Badge */}
      <div className="absolute left-2 top-2 z-10 rounded-full bg-[#cfff45] px-2 py-1 text-[10px] font-bold text-[#1e1f1f] shadow-sm">
        AI: {item.score.toFixed(1)}
      </div>
    </div>
  );
}

const pacingDuration: Record<string, number> = {
  fast: 1.0,
  dynamic: 2.0,
  cinematic: 3.0,
};

export function Storyboard({ pacing, referenceDuration }: { pacing: string, referenceDuration?: number }) {
  const [items, setItems] = useState<StoryboardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const outputDuration = pacing === "reference" && referenceDuration ? referenceDuration : pacingDuration[pacing] ?? 2.0;

  const fetchStoryboard = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/storyboard");
      if (res.ok) {
        const data = await res.json();
        // Don't override if user is dragging, but for simplicity we'll just set it
        // In a real app we'd pause polling during drag
        setItems(data);
      }
    } catch (e) {
      console.error("Failed to fetch storyboard", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStoryboard();
    const interval = setInterval(fetchStoryboard, 3000); // Poll for new segments
    return () => clearInterval(interval);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = async (event: any) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      let newOrderIds: string[] = [];
      setItems((items) => {
        const oldIndex = items.findIndex((i) => i.storyboard_id === active.id);
        const newIndex = items.findIndex((i) => i.storyboard_id === over.id);
        const newArray = arrayMove(items, oldIndex, newIndex);
        newOrderIds = newArray.map(i => i.storyboard_id);
        return newArray;
      });

      // Save to backend
      try {
        await fetch("http://127.0.0.1:8000/api/storyboard/reorder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ storyboard_ids: newOrderIds }),
        });
      } catch (e) {
        console.error("Failed to reorder", e);
      }
    }
  };

  const handleDelete = async (id: string) => {
    // Optimistic update
    setItems(items.filter(i => i.storyboard_id !== id));
    try {
      await fetch(`http://127.0.0.1:8000/api/storyboard/${id}`, { method: "DELETE" });
    } catch (e) {
      console.error("Failed to delete", e);
      fetchStoryboard(); // revert on fail
    }
  };

  if (loading && items.length === 0) return <div className="py-8 text-white/45">Loading timeline...</div>;

  return (
    <div className="w-full rounded-[30px] bg-[#343535] p-5 ring-1 ring-white/5 md:p-6">
      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="flex items-center gap-2 text-2xl font-semibold text-white">
          <Film className="h-6 w-6 text-[#cfff45]" />
          Timeline ({items.length} clips)
        </h2>
        <span className="text-sm text-white/45">Drag to reorder. Output runs left to right.</span>
      </div>

      <div className="w-full overflow-x-auto pb-4 custom-scrollbar">
        <div className="flex min-h-[148px] gap-4 px-1 py-2">
          {items.length === 0 ? (
            <div className="flex w-full items-center justify-center rounded-[24px] border border-dashed border-white/10 bg-[#242525] text-sm italic text-white/40">
              Upload videos to see AI-extracted hero moments.
            </div>
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={items.map(i => i.storyboard_id)}
                strategy={horizontalListSortingStrategy}
              >
                {items.map((item) => (
                  <SortableItem key={item.storyboard_id} item={item} onDelete={handleDelete} outputDuration={outputDuration} />
                ))}
              </SortableContext>
            </DndContext>
          )}
        </div>
      </div>
    </div>
  );
}
