'use client';

import { forwardRef, useId } from 'react';

import EvidenceThumbnail from '@/components/EvidenceLightbox';

type Props = {
  /** The scan that asked for the re-shot; the next upload is linked to it. */
  scanId: string;
  /** The agent's specific retake instruction. */
  instruction: string;
  attempt?: number | null;
  /** Absolute or origin-relative evidence image URL, already resolved. */
  evidenceSrc?: string;
  onRetake: (parentScanId: string) => void;
};

const RecaptureCard = forwardRef<HTMLElement, Props>(function RecaptureCard(
  { scanId, instruction, attempt, evidenceSrc, onRetake },
  ref
) {
  const headingId = useId();

  return (
    <section
      ref={ref}
      tabIndex={-1}
      aria-labelledby={headingId}
      className="rounded-xl border-2 border-amber-400 bg-amber-50 p-4 shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:border-amber-600 dark:bg-amber-950/40"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-900 dark:text-amber-200">
        Retake needed{attempt ? ` · attempt ${attempt}` : ''}
      </p>
      <h2 id={headingId} className="mt-1 text-xl font-bold text-amber-950 dark:text-amber-50">
        Please take the photo again
      </h2>
      <div className="mt-3 flex gap-3">
        <p className="min-w-0 flex-1 text-base font-medium leading-relaxed text-slate-900 dark:text-amber-50">
          {instruction}
        </p>
        {evidenceSrc && (
          <EvidenceThumbnail
            src={evidenceSrc}
            alt={`Evidence for the retake request: ${instruction}`}
            title="Why a retake is needed"
            className="shrink-0 self-start"
          />
        )}
      </div>
      <button
        type="button"
        onClick={() => onRetake(scanId)}
        className="mt-4 w-full rounded-lg bg-amber-700 px-4 py-3 text-base font-semibold text-white transition hover:bg-amber-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-800 dark:bg-amber-500 dark:text-slate-950 dark:hover:bg-amber-400"
      >
        Retake photo
      </button>
    </section>
  );
});

export default RecaptureCard;
