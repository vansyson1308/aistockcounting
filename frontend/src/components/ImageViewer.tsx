'use client';

import { useCallback, useRef, useState } from 'react';

interface ImageViewerProps {
  src: string;
  alt: string;
  children?: React.ReactNode;
  onLoad?: (e: React.SyntheticEvent<HTMLImageElement>) => void;
}

export default function ImageViewer({ src, alt, children, onLoad }: ImageViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const lastPos = useRef({ x: 0, y: 0 });
  const lastDist = useRef(0);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setScale((s) => Math.max(1, Math.min(5, s - e.deltaY * 0.002)));
  }, []);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (scale <= 1) return;
    setDragging(true);
    lastPos.current = { x: e.clientX, y: e.clientY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [scale]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging) return;
    const dx = e.clientX - lastPos.current.x;
    const dy = e.clientY - lastPos.current.y;
    lastPos.current = { x: e.clientX, y: e.clientY };
    setTranslate((t) => ({ x: t.x + dx, y: t.y + dy }));
  }, [dragging]);

  const handlePointerUp = useCallback(() => {
    setDragging(false);
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const dist = Math.hypot(dx, dy);
      if (lastDist.current > 0) {
        const delta = dist / lastDist.current;
        setScale((s) => Math.max(1, Math.min(5, s * delta)));
      }
      lastDist.current = dist;
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    lastDist.current = 0;
  }, []);

  const resetZoom = useCallback(() => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative overflow-hidden rounded-xl bg-black"
      onWheel={handleWheel}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{ touchAction: scale > 1 ? 'none' : 'auto' }}
    >
      <div
        style={{
          transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
          transformOrigin: 'center',
          transition: dragging ? 'none' : 'transform 0.15s ease-out',
        }}
      >
        <img src={src} alt={alt} className="h-auto w-full" onLoad={onLoad} />
        {children}
      </div>
      {scale > 1 && (
        <button
          onClick={resetZoom}
          className="absolute right-2 top-2 rounded-full bg-black/60 px-2 py-1 text-xs text-white"
        >
          Reset
        </button>
      )}
    </div>
  );
}
