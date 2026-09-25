'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import AgentTimeline from '@/components/AgentTimeline';
import BoundingBoxOverlay from '@/components/BoundingBoxOverlay';
import CameraCapture from '@/components/CameraCapture';
import EvidenceThumbnail from '@/components/EvidenceLightbox';
import ImageViewer from '@/components/ImageViewer';
import RecaptureCard from '@/components/RecaptureCard';
import { terminalStep } from '@/lib/agent-format';
import {
  ApiClientError,
  buildImageUrl,
  createAuditScan,
  evidenceSrc,
  getTrace,
  reviewAuditScan,
  runAgent,
} from '@/lib/api';
import { compressImage } from '@/lib/image-compress';
import { sanitizeText } from '@/lib/sanitize';
import { useReviewQueueStore } from '@/store/useReviewQueueStore';
import { useSessionStore } from '@/store/useSessionStore';
import { useToastStore } from '@/store/useToastStore';
import { ScanCreateData, TraceStep } from '@/types';

const POLL_INTERVAL_MS = 400;

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'VND' });

const inputClass =
  'mt-1 w-full rounded-md border border-slate-300 p-2.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-slate-600 dark:bg-slate-900';

const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600';

type Phase = 'capture' | 'uploading' | 'running' | 'done';

type Retake = { parentScanId: string; instruction: string };

function parseOptionalNumber(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiClientError ? error.message : fallback;
}

function CountSummary({
  count,
  expected,
  variance,
}: {
  count: number | null | undefined;
  expected: number | null | undefined;
  variance: number | null | undefined;
}) {
  return (
    <dl className="grid grid-cols-3 gap-3 text-center">
      <div>
        <dt className="text-xs text-slate-600 dark:text-slate-400">Agent count</dt>
        <dd className="text-2xl font-bold tabular-nums">{count ?? '—'}</dd>
      </div>
      <div>
        <dt className="text-xs text-slate-600 dark:text-slate-400">POS count</dt>
        <dd className="text-2xl font-bold tabular-nums">{expected ?? '—'}</dd>
      </div>
      <div>
        <dt className="text-xs text-slate-600 dark:text-slate-400">Variance</dt>
        <dd
          className={`text-2xl font-bold tabular-nums ${
            variance ? 'text-rose-700 dark:text-rose-300' : 'text-emerald-700 dark:text-emerald-300'
          }`}
        >
          {variance === null || variance === undefined
            ? '—'
            : `${variance > 0 ? '+' : ''}${variance}`}
        </dd>
      </div>
    </dl>
  );
}

export default function ScanPage() {
  const { staffId, setStaffId } = useSessionStore();
  const showToast = useToastStore((s) => s.show);
  const addToQueue = useReviewQueueStore((s) => s.add);

  const [branchCode, setBranchCode] = useState('MAIN');
  const [trayCode, setTrayCode] = useState('');
  const [expectedCount, setExpectedCount] = useState('');
  const [unitValue, setUnitValue] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [compressionInfo, setCompressionInfo] = useState('');
  const [phase, setPhase] = useState<Phase>('capture');
  const [result, setResult] = useState<ScanCreateData | null>(null);
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [retake, setRetake] = useState<Retake | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  const [imgDisplay, setImgDisplay] = useState({ w: 0, h: 0 });

  // Manual review, only for scans the agent did not decide (e.g. the agent run failed).
  const [manualCount, setManualCount] = useState('');
  const [isAICorrect, setIsAICorrect] = useState<boolean | null>(null);
  const [notes, setNotes] = useState('');
  const [reviewing, setReviewing] = useState(false);

  const pollRef = useRef<{ cancelled: boolean; timer: ReturnType<typeof setTimeout> | null }>({
    cancelled: true,
    timer: null,
  });
  const captureRef = useRef<HTMLDivElement>(null);
  const outcomeRef = useRef<HTMLElement>(null);

  const scan = result?.scan;
  const agent = result?.agent ?? null;
  const decision = agent?.decision ?? scan?.agent_decision ?? null;
  const terminal = useMemo(() => terminalStep(steps), [steps]);
  const reason =
    agent?.instruction || agent?.reason || terminal?.reason || scan?.agent_reason || '';
  const agentCount = agent?.count ?? scan?.agent_count ?? scan?.final_count ?? null;
  const busy = phase === 'uploading' || phase === 'running';
  const displaySrc = preview || buildImageUrl(scan?.image_path);
  const showManualReview =
    phase === 'done' && !!scan && decision === null && scan.status !== 'awaiting_approval';

  const stopPolling = useCallback(() => {
    pollRef.current.cancelled = true;
    if (pollRef.current.timer) clearTimeout(pollRef.current.timer);
    pollRef.current.timer = null;
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  useEffect(() => {
    if (phase === 'done' && decision) outcomeRef.current?.focus();
  }, [phase, decision]);

  const startPolling = (scanId: string) => {
    stopPolling();
    const state = { cancelled: false, timer: null as ReturnType<typeof setTimeout> | null };
    pollRef.current = state;
    const tick = async () => {
      if (state.cancelled) return;
      try {
        const trace = await getTrace(scanId);
        if (!state.cancelled && trace.live) setSteps(trace.live.steps);
      } catch {
        // A missed poll is harmless: the final trace arrives with the agent-run response.
      }
      if (!state.cancelled) state.timer = setTimeout(tick, POLL_INTERVAL_MS);
    };
    state.timer = setTimeout(tick, 0);
  };

  const handleFile = async (selected: File, url?: string) => {
    const originalSize = selected.size;
    const compressed = await compressImage(selected);
    const savedUrl = url || URL.createObjectURL(compressed);
    if (compressed.size < originalSize) {
      const saved = ((1 - compressed.size / originalSize) * 100).toFixed(0);
      setCompressionInfo(
        `Compressed ${(originalSize / 1024 / 1024).toFixed(1)} MB → ${(compressed.size / 1024 / 1024).toFixed(1)} MB (−${saved}%)`
      );
    } else {
      setCompressionInfo('');
    }
    setFile(compressed);
    setPreview(savedUrl);
    setResult(null);
    setSteps([]);
    setPhase('capture');
    setStatus('');
    setError('');
  };

  const announceOutcome = (data: ScanCreateData) => {
    const next = data.agent?.decision ?? data.scan.agent_decision;
    if (next === 'auto_accept') setStatus('Count verified by the agent.');
    else if (next === 'request_recapture') setStatus('The agent asked for a new photo.');
    else if (next === 'escalate') {
      setStatus('The agent escalated this count for approval.');
      addToQueue({
        id: data.scan.id,
        branchCode: data.scan.branch_code,
        trayCode: data.scan.tray_code,
        agentCount: data.agent?.count ?? data.scan.agent_count ?? null,
        expectedCount: data.scan.expected_count ?? null,
        createdAt: data.scan.created_at,
      });
    } else setStatus('');
  };

  /** If the agent-run request failed in transit, the run may still have finished server-side. */
  const recoverFromTrace = async (scanId: string): Promise<ScanCreateData | null> => {
    try {
      const trace = await getTrace(scanId);
      if (!trace.scan.agent_decision) return null;
      const finalSteps = trace.steps.length > 0 ? trace.steps : (trace.live?.steps ?? []);
      const recovered: ScanCreateData = { scan: trace.scan, discrepancy: null, agent: null };
      setSteps(finalSteps);
      setResult(recovered);
      return recovered;
    } catch {
      return null;
    }
  };

  const runAudit = async () => {
    setError('');
    if (!file) return setError('Take or choose a photo of the tray first.');
    if (!trayCode.trim()) return setError('Enter the tray code.');

    let scanId: string | null = null;
    try {
      setPhase('uploading');
      setSteps([]);
      setResult(null);
      setStatus('Uploading photo…');
      const created = await createAuditScan(file, {
        branchCode: sanitizeText(branchCode, 80) || 'MAIN',
        trayCode: sanitizeText(trayCode, 80),
        staffId: sanitizeText(staffId, 50),
        expectedCount: parseOptionalNumber(expectedCount),
        unitValue: parseOptionalNumber(unitValue),
        parentScanId: retake?.parentScanId,
        runAgent: false,
      });
      scanId = created.scan.id;
      setResult(created);
      setManualCount(String(created.scan.final_count));
      setPhase('running');
      setStatus('TrayAgent is checking the photo…');

      startPolling(scanId);
      const data = await runAgent(scanId);
      stopPolling();
      if (data.agent?.trace?.length) setSteps(data.agent.trace);
      setResult(data);
      setManualCount(String(data.scan.final_count));
      setRetake(null);
      setPhase('done');

      announceOutcome(data);
    } catch (err) {
      stopPolling();
      const recovered = scanId ? await recoverFromTrace(scanId) : null;
      if (recovered) {
        setRetake(null);
        setPhase('done');
        announceOutcome(recovered);
        return;
      }
      setPhase(scanId ? 'done' : 'capture');
      setStatus('');
      setError(
        scanId
          ? `${errorMessage(err, 'The agent could not finish.')} The photo was saved; review the count manually below.`
          : errorMessage(err, 'Could not upload the scan. Check your connection and try again.')
      );
    }
  };

  const submitReview = async () => {
    if (!scan) return;
    try {
      setReviewing(true);
      setError('');
      const data = await reviewAuditScan(scan.id, {
        manual_count:
          manualCount.trim() !== '' ? parseOptionalNumber(manualCount) : scan.final_count,
        expected_count: parseOptionalNumber(expectedCount) ?? scan.expected_count ?? null,
        unit_value: parseOptionalNumber(unitValue),
        is_ai_correct: isAICorrect,
        notes: sanitizeText(notes, 500) || null,
      });
      setResult((prev) => ({ ...data, agent: prev?.agent ?? null }));
      showToast(data.discrepancy ? 'Discrepancy updated' : 'Scan reviewed');
      setStatus(
        data.discrepancy ? 'The discrepancy is still open.' : 'The scan matches the expected count.'
      );
    } catch (err) {
      setError(errorMessage(err, 'Could not save the review.'));
    } finally {
      setReviewing(false);
    }
  };

  const clearPhoto = () => {
    setFile(null);
    setPreview('');
    setResult(null);
    setSteps([]);
    setCompressionInfo('');
    setManualCount('');
    setNotes('');
    setIsAICorrect(null);
    setStatus('');
    setError('');
    setPhase('capture');
  };

  const startRetake = (parentScanId: string) => {
    setRetake({ parentScanId, instruction: reason });
    clearPhoto();
    requestAnimationFrame(() => {
      captureRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      captureRef.current?.focus({ preventScroll: true });
    });
  };

  const nextTray = () => {
    stopPolling();
    clearPhoto();
    setRetake(null);
    setTrayCode('');
    setExpectedCount('');
    setUnitValue('');
  };

  const finalEvidence = evidenceSrc(terminal?.evidence_url);

  return (
    <section className="space-y-5">
      <div className="border-b border-slate-200 pb-4 dark:border-slate-700">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-400">
          TrayAgent scan
        </p>
        <h1 className="mt-1 text-2xl font-bold">Count a tray from a photo</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          Take a photo of the tray. TrayAgent checks the photo, counts every item, rechecks anything
          uncertain and compares the result with the POS count.
        </p>
      </div>

      <fieldset
        disabled={busy}
        className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800 md:grid-cols-2"
      >
        <legend className="sr-only">Tray details</legend>
        <label className="text-sm font-medium">
          Branch
          <input
            value={branchCode}
            onChange={(e) => setBranchCode(e.target.value)}
            autoComplete="off"
            className={inputClass}
          />
        </label>
        <label className="text-sm font-medium">
          Tray code <span aria-hidden="true">*</span>
          <input
            value={trayCode}
            onChange={(e) => setTrayCode(e.target.value)}
            required
            aria-required="true"
            autoComplete="off"
            className={inputClass}
          />
        </label>
        <label className="text-sm font-medium">
          Staff ID
          <input
            value={staffId}
            onChange={(e) => setStaffId(e.target.value)}
            autoComplete="username"
            className={inputClass}
          />
        </label>
        <label className="text-sm font-medium">
          POS count
          <input
            type="number"
            inputMode="numeric"
            min={0}
            value={expectedCount}
            onChange={(e) => setExpectedCount(e.target.value)}
            placeholder="Leave empty to use KiotViet stock"
            className={inputClass}
          />
        </label>
        <label className="text-sm font-medium md:col-span-2">
          Estimated value per item (VND)
          <input
            type="number"
            inputMode="decimal"
            min={0}
            value={unitValue}
            onChange={(e) => setUnitValue(e.target.value)}
            placeholder="Used to estimate the value at risk of a discrepancy"
            className={inputClass}
          />
        </label>
      </fieldset>

      <div ref={captureRef} tabIndex={-1} className="space-y-3 focus:outline-none">
        {retake && (
          <div
            role="note"
            className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
          >
            <p className="font-semibold">Retaking the photo</p>
            {retake.instruction && <p className="mt-1">{retake.instruction}</p>}
            <p className="mt-1 text-xs">The new photo will be linked to the previous scan.</p>
          </div>
        )}
        {phase === 'capture' && (
          <>
            <CameraCapture onCapture={handleFile} />
            <div className="rounded-lg border border-dashed border-slate-300 p-4 dark:border-slate-700">
              <label className="block text-sm font-medium">
                Or upload a photo
                <input
                  type="file"
                  accept="image/jpeg,image/png"
                  capture="environment"
                  onChange={(e) => {
                    const selected = e.target.files?.[0];
                    if (selected) handleFile(selected);
                    e.target.value = '';
                  }}
                  className={`mt-2 w-full text-sm ${focusRing}`}
                />
              </label>
              {compressionInfo && (
                <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-300">
                  {compressionInfo}
                </p>
              )}
            </div>
          </>
        )}
      </div>

      {phase !== 'done' && (
        <button
          type="button"
          onClick={runAudit}
          disabled={busy}
          className={`w-full rounded-lg bg-indigo-600 px-4 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 ${focusRing}`}
        >
          {phase === 'uploading'
            ? 'Uploading…'
            : phase === 'running'
              ? 'Agent is working…'
              : retake
                ? 'Count retaken photo'
                : 'Count this tray'}
        </button>
      )}

      <p role="status" className="text-sm text-slate-700 dark:text-slate-300">
        {status}
      </p>
      {error && (
        <p
          role="alert"
          className="rounded-md bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-200"
        >
          {error}
        </p>
      )}

      {phase === 'done' && decision === 'auto_accept' && scan && (
        <section
          ref={outcomeRef}
          tabIndex={-1}
          aria-labelledby="outcome-heading"
          className="space-y-3 rounded-xl border-2 border-emerald-400 bg-emerald-50 p-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 dark:border-emerald-700 dark:bg-emerald-950/40"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800 dark:text-emerald-200">
            Auto-accepted
          </p>
          <h2 id="outcome-heading" className="text-xl font-bold">
            {scan.expected_count === null || scan.expected_count === undefined
              ? `Counted ${agentCount ?? scan.final_count} items`
              : 'Count matches POS'}
          </h2>
          <CountSummary
            count={agentCount}
            expected={scan.expected_count}
            variance={scan.variance_count}
          />
          {reason && <p className="text-sm text-slate-800 dark:text-slate-200">{reason}</p>}
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={nextTray}
              className={`flex-1 rounded-lg bg-emerald-700 px-4 py-3 font-semibold text-white transition hover:bg-emerald-800 ${focusRing}`}
            >
              Scan next tray
            </button>
            <Link
              href={`/review/${scan.id}`}
              className={`flex-1 rounded-lg border border-emerald-700 px-4 py-3 text-center font-semibold text-emerald-800 transition hover:bg-emerald-100 dark:text-emerald-200 dark:hover:bg-emerald-900/40 ${focusRing}`}
            >
              View evidence
            </Link>
          </div>
        </section>
      )}

      {phase === 'done' && decision === 'request_recapture' && scan && (
        <RecaptureCard
          ref={outcomeRef}
          scanId={scan.id}
          instruction={reason || 'Retake the photo of the whole tray from directly above.'}
          attempt={scan.attempt}
          evidenceSrc={finalEvidence}
          onRetake={startRetake}
        />
      )}

      {phase === 'done' && decision === 'escalate' && scan && (
        <section
          ref={outcomeRef}
          tabIndex={-1}
          aria-labelledby="outcome-heading"
          className="space-y-3 rounded-xl border-2 border-rose-400 bg-rose-50 p-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-600 dark:border-rose-700 dark:bg-rose-950/40"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-rose-800 dark:text-rose-200">
            Escalated to a human
          </p>
          <h2 id="outcome-heading" className="text-xl font-bold">
            A manager needs to approve this count
          </h2>
          <CountSummary
            count={agentCount}
            expected={scan.expected_count}
            variance={scan.variance_count}
          />
          {scan.variance_value !== null && scan.variance_value !== undefined && (
            <p className="text-sm">
              Estimated value at risk: <strong>{currency.format(scan.variance_value)}</strong>
            </p>
          )}
          {reason && <p className="text-sm text-slate-800 dark:text-slate-200">{reason}</p>}
          <div className="flex flex-col gap-2 sm:flex-row">
            <Link
              href={`/review/${scan.id}`}
              className={`flex-1 rounded-lg bg-rose-700 px-4 py-3 text-center font-semibold text-white transition hover:bg-rose-800 ${focusRing}`}
            >
              Open review
            </Link>
            <button
              type="button"
              onClick={nextTray}
              className={`flex-1 rounded-lg border border-slate-400 px-4 py-3 font-semibold transition hover:bg-white dark:border-slate-500 dark:hover:bg-slate-800 ${focusRing}`}
            >
              Scan next tray
            </button>
          </div>
        </section>
      )}

      {(phase === 'running' || steps.length > 0) && (
        <AgentTimeline steps={steps} running={phase === 'running'} />
      )}

      {displaySrc && (
        <div className="space-y-2">
          <h2 className="text-lg font-semibold">Photo</h2>
          <ImageViewer
            src={displaySrc}
            alt={
              scan
                ? `Tray ${scan.tray_code} photo${scan.boxes_json?.length ? ` with ${scan.boxes_json.length} detected items outlined` : ''}`
                : 'Selected tray photo'
            }
            onLoad={(event) => {
              const el = event.currentTarget as HTMLImageElement;
              setImgNatural({ w: el.naturalWidth, h: el.naturalHeight });
              setImgDisplay({ w: el.clientWidth, h: el.clientHeight });
            }}
          >
            {phase === 'done' && scan?.boxes_json && (
              <BoundingBoxOverlay
                boxes={scan.boxes_json}
                naturalWidth={imgNatural.w}
                naturalHeight={imgNatural.h}
                displayWidth={imgDisplay.w}
                displayHeight={imgDisplay.h}
              />
            )}
          </ImageViewer>
          {finalEvidence && decision !== 'request_recapture' && (
            <div className="flex items-center gap-3 text-sm">
              <EvidenceThumbnail
                src={finalEvidence}
                alt="Agent evidence sheet with counted items and any uncertain regions marked"
                title="Agent evidence sheet"
              />
              <span className="text-slate-700 dark:text-slate-300">Agent evidence sheet</span>
            </div>
          )}
        </div>
      )}

      {showManualReview && scan && (
        <section
          aria-labelledby="manual-review-heading"
          className="space-y-4 border-t border-slate-200 pt-4 dark:border-slate-700"
        >
          <h2 id="manual-review-heading" className="text-lg font-semibold">
            Manual review
          </h2>
          <CountSummary
            count={scan.detected_count}
            expected={scan.expected_count}
            variance={scan.variance_count}
          />

          {scan.variance_value !== null && scan.variance_value !== undefined && (
            <div className="rounded-md bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
              Estimated value at risk: <strong>{currency.format(scan.variance_value)}</strong>
            </div>
          )}

          {(scan.quality_flags?.length ?? 0) > 0 && (
            <div className="rounded-md bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              Consider retaking the photo: {scan.quality_flags?.join(', ')}
            </div>
          )}

          <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <label className="text-sm font-medium">
              Recounted quantity
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={manualCount}
                onChange={(e) => setManualCount(e.target.value)}
                className={inputClass}
              />
            </label>
            <div
              role="group"
              aria-label="Was the AI count correct?"
              className="grid grid-cols-2 gap-2"
            >
              <button
                type="button"
                aria-pressed={isAICorrect === true}
                onClick={() => setIsAICorrect(true)}
                className={`rounded-md border p-2.5 text-sm font-semibold ${focusRing} ${
                  isAICorrect === true
                    ? 'border-emerald-700 bg-emerald-700 text-white'
                    : 'border-slate-300'
                }`}
              >
                AI was right
              </button>
              <button
                type="button"
                aria-pressed={isAICorrect === false}
                onClick={() => setIsAICorrect(false)}
                className={`rounded-md border p-2.5 text-sm font-semibold ${focusRing} ${
                  isAICorrect === false
                    ? 'border-rose-700 bg-rose-700 text-white'
                    : 'border-slate-300'
                }`}
              >
                AI needs correction
              </button>
            </div>
            <label className="text-sm font-medium">
              Notes
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Reason for the variance, hidden items, POS not synced…"
                className={`${inputClass} min-h-24 text-sm`}
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={submitReview}
                disabled={reviewing}
                className={`rounded-lg bg-slate-900 px-4 py-3 font-semibold text-white transition hover:bg-slate-700 disabled:opacity-60 dark:bg-white dark:text-slate-900 ${focusRing}`}
              >
                {reviewing ? 'Saving…' : 'Save review'}
              </button>
              <button
                type="button"
                onClick={nextTray}
                className={`rounded-lg border border-slate-300 px-4 py-3 font-semibold transition hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800 ${focusRing}`}
              >
                Next tray
              </button>
            </div>
          </div>
        </section>
      )}
    </section>
  );
}
