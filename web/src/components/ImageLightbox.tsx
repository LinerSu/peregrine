import { useCallback, useEffect, useRef, useState } from "react";

// Screenshots in the manual are wide (a whole app window), so at column width the details
// they're pointing at are unreadable. Clicking one opens it here instead of a new tab:
// a new tab loses the page you were reading and drops you on a bare image with no way back.
//
// Zoom is fit <-> 100% plus steps, and panning is drag-to-scroll, because a 1799px-wide
// screenshot at natural size doesn't fit any laptop viewport.

const MIN = 0.25;
const MAX = 4;
const STEP = 0.25;

export function Lightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  const [scale, setScale] = useState(0); // 0 = "fit to the viewport"
  const closeRef = useRef<HTMLButtonElement>(null);
  const panRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  const clamp = (s: number) => Math.min(MAX, Math.max(MIN, s));
  const zoom = useCallback((delta: number) => setScale((s) => clamp((s || 1) + delta)), []);

  useEffect(() => {
    // Esc closes, +/- zoom, 0 resets — the keys people already try in an image viewer.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "+" || e.key === "=") zoom(STEP);
      else if (e.key === "-") zoom(-STEP);
      else if (e.key === "0") setScale(0);
    };
    document.addEventListener("keydown", onKey);
    // The page behind must not scroll while the overlay owns the screen.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose, zoom]);

  const startDrag = (e: React.MouseEvent) => {
    const el = panRef.current;
    if (!el || !scale) return; // nothing to pan while fitted
    drag.current = { x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop };
  };
  const onDrag = (e: React.MouseEvent) => {
    const el = panRef.current;
    if (!el || !drag.current) return;
    el.scrollLeft = drag.current.left - (e.clientX - drag.current.x);
    el.scrollTop = drag.current.top - (e.clientY - drag.current.y);
  };
  const endDrag = () => { drag.current = null; };

  const btn = "px-2.5 py-1 text-sm font-medium text-white/90 rounded hover:bg-white/20 disabled:opacity-40";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={alt || "Image"}
      className="fixed inset-0 z-50 flex flex-col bg-black/80 backdrop-blur-sm"
      onClick={onClose}   // clicking the backdrop closes; the image stops propagation
    >
      <div
        className="flex items-center gap-1 px-3 py-2 text-white/90"
        onClick={(e) => e.stopPropagation()}
      >
        <button className={btn} onClick={() => zoom(-STEP)} disabled={!!scale && scale <= MIN} title="Zoom out (-)">−</button>
        <span className="w-16 text-center text-xs tabular-nums">{scale ? `${Math.round(scale * 100)}%` : "fit"}</span>
        <button className={btn} onClick={() => zoom(STEP)} disabled={scale >= MAX} title="Zoom in (+)">+</button>
        <button className={btn} onClick={() => setScale((s) => (s ? 0 : 1))} title="Fit / actual size (0)">
          {scale ? "Fit" : "100%"}
        </button>
        <span className="ml-auto mr-2 hidden sm:inline text-xs text-white/60">
          drag to pan · Esc to close
        </span>
        <button ref={closeRef} className={btn} onClick={onClose} title="Close (Esc)" aria-label="Close">✕</button>
      </div>

      <div
        ref={panRef}
        className={`flex-1 overflow-auto p-4 ${scale ? "cursor-grab active:cursor-grabbing" : ""}`}
        onClick={(e) => e.stopPropagation()}
        onMouseDown={startDrag}
        onMouseMove={onDrag}
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
      >
        <img
          src={src}
          alt={alt}
          draggable={false}
          onClick={() => setScale((s) => (s ? 0 : 1))}   // click the image itself to toggle
          className={scale ? "max-w-none select-none" : "mx-auto max-h-full max-w-full select-none"}
          style={scale ? { width: `${scale * 100}%` } : undefined}
        />
      </div>
    </div>
  );
}

// The markdown <img> replacement: same picture, but it announces that it can be opened.
export function ZoomableImage({ src, alt }: { src?: string; alt?: string }) {
  const [open, setOpen] = useState(false);
  if (!src) return null;
  return (
    <>
      <img
        src={src}
        alt={alt || ""}
        onClick={() => setOpen(true)}
        title="Click to enlarge"
        className="my-4 w-full rounded-lg border border-gray-200 shadow-sm cursor-zoom-in hover:border-indigo-300"
      />
      {open && <Lightbox src={src} alt={alt || ""} onClose={() => setOpen(false)} />}
    </>
  );
}
