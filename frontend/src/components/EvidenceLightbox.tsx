'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

type LightboxProps = {
  src: string;
  alt: string;
  title: string;
  onClose: () => void;
};

/** Accessible full-size image dialog: focus moves in, Tab is trapped, Escape closes. */
export function EvidenceLightbox({ src, alt, title, onClose }: LightboxProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
      previous?.focus?.();
    };
  }, []);

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== 'Tab' || !dialogRef.current) return;
    const focusables = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 sm:p-6"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
        onClick={(event) => event.stopPropagation()}
        className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl dark:bg-slate-900"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
          <h2 id={titleId} className="truncate text-sm font-semibold">
            {title}
          </h2>
          <div className="flex shrink-0 items-center gap-2">
            <a
              href={src}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md px-2 py-1 text-sm font-medium text-indigo-700 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 dark:text-indigo-300"
            >
              Open original
            </a>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-300 px-3 py-1 text-sm font-semibold hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-slate-600 dark:hover:bg-slate-800"
            >
              Close
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-slate-950">
          {/* eslint-disable-next-line @next/next/no-img-element -- API-served evidence, not a static asset */}
          <img src={src} alt={alt} className="mx-auto h-auto max-w-full" />
        </div>
      </div>
    </div>,
    document.body
  );
}

type ThumbnailProps = {
  src: string;
  alt: string;
  /** Dialog heading and accessible button name suffix. */
  title: string;
  className?: string;
  imgClassName?: string;
};

/** A thumbnail button that opens the image full size in an accessible dialog. */
export default function EvidenceThumbnail({
  src,
  alt,
  title,
  className = '',
  imgClassName = 'h-20 w-28 object-cover',
}: ThumbnailProps) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  if (!src) return null;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`View full size: ${title}`}
        className={`group relative block overflow-hidden rounded-md border border-slate-300 bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:border-slate-600 dark:bg-slate-800 ${className}`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- API-served evidence, not a static asset */}
        <img src={src} alt={alt} loading="lazy" className={imgClassName} />
        <span
          aria-hidden="true"
          className="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-semibold text-white group-hover:bg-black/85"
        >
          Enlarge
        </span>
      </button>
      {open && <EvidenceLightbox src={src} alt={alt} title={title} onClose={close} />}
    </>
  );
}
