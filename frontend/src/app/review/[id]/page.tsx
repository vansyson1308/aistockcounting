'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import AgentTimeline from '@/components/AgentTimeline';
import ApprovalPanel from '@/components/ApprovalPanel';
import EvidenceThumbnail from '@/components/EvidenceLightbox';
import LoadingSkeleton from '@/components/LoadingSkeleton';
import {
  decisionBadgeClass,
  decisionLabel,
  lastStep,
  statusLabel,
  stepMetrics,
  terminalStep,
  zoomRegions,
} from '@/lib/agent-format';
import { ApiClientError, buildImageUrl, evidenceSrc, getTrace } from '@/lib/api';
import { useReviewQueueStore } from '@/store/useReviewQueueStore';
import { useToastStore } from '@/store/useToastStore';
import { ApproveResult, TraceData } from '@/types';

const LIVE_REFRESH_MS = 1000;

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'VND' });

const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600';

function signed(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value > 0 ? '+' : ''}${value}`;
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-center dark:border-slate-700 dark:bg-slate-800">
      <dt className="text-xs text-slate-600 dark:text-slate-400">{label}</dt>
      <dd className={`text-2xl font-bold tabular-nums ${tone ?? ''}`}>{value}</dd>
    </div>
  );
}

export default function ReviewPage({ params }: { params: { id: string } }) {
  const scanId = params.id;
  const showToast = useToastStore((s) => s.show);
  const removeFromQueue = useReviewQueueStore((s) => s.remove);

  const [trace, setTrace] = useState<TraceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [view, setView] = useState<'before' | 'after'>('after');

  const load = useCallback(
    async (quiet = false) => {
      try {
        if (!quiet) setLoading(true);
        const data = await getTrace(scanId);
        setTrace(data);
        setError('');
      } catch (e) {
        setError(e instanceof ApiClientError ? e.message : 'Could not load this scan.');
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [scanId]
  );

  useEffect(() => {
    load();
  }, [load]);

  const liveRunning = trace?.live?.running === true;

  // If the agent is still running on this scan, keep the timeline live until it finishes.
  useEffect(() => {
    if (!liveRunning) return;
    const timer = setTimeout(() => load(true), LIVE_REFRESH_MS);
    return () => clearTimeout(timer);
  }, [liveRunning, trace, load]);

  const steps = useMemo(() => {
    if (!trace) return [];
    if (trace.live?.running || trace.steps.length === 0) return trace.live?.steps ?? trace.steps;
    return trace.steps;
  }, [trace]);

  const scan = trace?.scan;
  const terminal = terminalStep(steps);
  const zoom = lastStep(steps, 'zoom_recount');
  const compare = lastStep(steps, 'compare_previous');
  const regions = zoomRegions(zoom);
  const decision = scan?.agent_decision ?? terminal?.decision ?? null;
  const reason = terminal?.reason || scan?.agent_reason || '';
  const agentCount = scan?.agent_count ?? scan?.final_count ?? null;
  const originalSrc = buildImageUrl(scan?.image_path);
  const finalSrc = evidenceSrc(terminal?.evidence_url);
  const zoomSrc = evidenceSrc(zoom?.evidence_url);
  const compareSrc = evidenceSrc(compare?.evidence_url);

  const onDecided = (result: ApproveResult) => {
    setTrace((prev) => (prev ? { ...prev, scan: result.scan } : prev));
    removeFromQueue(result.scan.id);
    showToast(
      result.scan.status === 'needs_recapture'
        ? 'Count rejected: a recount was requested'
        : `Decision saved: final count ${result.scan.final_count}`
    );
  };

  if (loading && !trace) {
    return (
      <section className="space-y-4" aria-busy="true">
        <h1 className="text-2xl font-bold">Review scan</h1>
        <LoadingSkeleton count={3} />
      </section>
    );
  }

  if (!scan) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-bold">Review scan</h1>
        <p
          role="alert"
          className="rounded-md bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-200"
        >
          {error || 'Scan not found.'}
        </p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => load()}
            className={`rounded-lg bg-indigo-600 px-4 py-2.5 font-semibold text-white hover:bg-indigo-700 ${focusRing}`}
          >
            Try again
          </button>
          <Link
            href="/review"
            className={`rounded-lg border border-slate-300 px-4 py-2.5 font-semibold hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800 ${focusRing}`}
          >
            Review queue
          </Link>
        </div>
      </section>
    );
  }

  const variance = scan.variance_count;

  return (
    <section className="space-y-6">
      <header className="space-y-3 border-b border-slate-200 pb-4 dark:border-slate-700">
        <nav aria-label="Breadcrumb" className="text-sm">
          <Link
            href="/review"
            className={`rounded text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300 ${focusRing}`}
          >
            Review queue
          </Link>
        </nav>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold">
            {scan.branch_code} / {scan.tray_code}
          </h1>
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${decisionBadgeClass(decision)}`}
          >
            {decisionLabel(decision)}
          </span>
          <span className="rounded-full border border-slate-300 px-2 py-0.5 text-xs font-semibold text-slate-700 dark:border-slate-600 dark:text-slate-200">
            {statusLabel(scan.status)}
          </span>
        </div>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Scanned {new Date(scan.created_at).toLocaleString('en-GB')}
          {scan.staff_id ? ` by ${scan.staff_id}` : ''}
          {scan.attempt ? ` · attempt ${scan.attempt}` : ''}
          {scan.parent_scan_id && (
            <>
              {' · retake of '}
              <Link
                href={`/review/${scan.parent_scan_id}`}
                className={`rounded text-indigo-700 underline underline-offset-2 dark:text-indigo-300 ${focusRing}`}
              >
                the previous scan
              </Link>
            </>
          )}
        </p>
        <dl className="grid grid-cols-3 gap-2 sm:gap-3">
          <Stat label="Agent count" value={agentCount ?? '—'} />
          <Stat label="POS count" value={scan.expected_count ?? '—'} />
          <Stat
            label="Variance"
            value={signed(variance)}
            tone={
              variance
                ? 'text-rose-700 dark:text-rose-300'
                : variance === 0
                  ? 'text-emerald-700 dark:text-emerald-300'
                  : undefined
            }
          />
        </dl>
        {scan.final_count !== agentCount && (
          <p className="text-sm">
            Final approved count: <strong className="tabular-nums">{scan.final_count}</strong>
          </p>
        )}
        {scan.variance_value !== null && scan.variance_value !== undefined && (
          <p className="text-sm">
            Estimated value at risk: <strong>{currency.format(scan.variance_value)}</strong>
          </p>
        )}
        {reason && (
          <p className="rounded-md border-l-4 border-indigo-400 bg-indigo-50 p-3 text-sm text-slate-900 dark:bg-indigo-950/30 dark:text-slate-100">
            <span className="font-semibold">Agent: </span>
            {reason}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-rose-700 dark:text-rose-300">
            {error}
          </p>
        )}
        {scan.status === 'awaiting_approval' && (
          <a
            href="#decision"
            className={`block rounded-lg bg-indigo-600 px-4 py-2.5 text-center font-semibold text-white hover:bg-indigo-700 lg:hidden ${focusRing}`}
          >
            Go to approval
          </a>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
        <div className="min-w-0 space-y-6">
          <section aria-labelledby="before-after-heading" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="before-after-heading" className="text-lg font-semibold">
                Before / after
              </h2>
              <div
                role="group"
                aria-label="Choose image"
                className="inline-flex rounded-lg border border-slate-300 p-0.5 md:hidden dark:border-slate-600"
              >
                {(['before', 'after'] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    aria-pressed={view === v}
                    onClick={() => setView(v)}
                    className={`rounded-md px-3 py-1.5 text-sm font-semibold ${focusRing} ${
                      view === v
                        ? 'bg-indigo-600 text-white'
                        : 'text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800'
                    }`}
                  >
                    {v === 'before' ? 'Original' : 'Evidence'}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <figure className={`${view === 'before' ? 'block' : 'hidden'} space-y-1 md:block`}>
                {originalSrc ? (
                  <EvidenceThumbnail
                    src={originalSrc}
                    alt={`Original photo of tray ${scan.tray_code}`}
                    title="Original photo"
                    className="w-full"
                    imgClassName="h-auto w-full"
                  />
                ) : (
                  <p className="text-sm text-slate-600 dark:text-slate-400">No photo stored.</p>
                )}
                <figcaption className="text-xs text-slate-600 dark:text-slate-400">
                  Original photo as uploaded
                </figcaption>
              </figure>
              <figure className={`${view === 'after' ? 'block' : 'hidden'} space-y-1 md:block`}>
                {finalSrc ? (
                  <EvidenceThumbnail
                    src={finalSrc}
                    alt={`Agent evidence sheet for tray ${scan.tray_code}: ${reason || decisionLabel(decision)}`}
                    title="Final evidence sheet"
                    className="w-full"
                    imgClassName="h-auto w-full"
                  />
                ) : (
                  <p className="text-sm text-slate-600 dark:text-slate-400">
                    No evidence sheet for this scan.
                  </p>
                )}
                <figcaption className="text-xs text-slate-600 dark:text-slate-400">
                  Evidence sheet: counted items boxed, uncertain and changed regions marked
                </figcaption>
              </figure>
            </div>
          </section>

          <section aria-labelledby="uncertain-heading" className="space-y-3">
            <h2 id="uncertain-heading" className="text-lg font-semibold">
              Uncertain regions
            </h2>
            {zoom ? (
              <div className="flex flex-col gap-3 sm:flex-row">
                {zoomSrc && (
                  <EvidenceThumbnail
                    src={zoomSrc}
                    alt={`Zoomed recount of uncertain regions: ${zoom.reason}`}
                    title="Zoomed recount"
                    className="shrink-0 self-start"
                    imgClassName="h-32 w-44 object-cover"
                  />
                )}
                <div className="min-w-0 flex-1 space-y-2">
                  <p className="text-sm text-slate-800 dark:text-slate-200">{zoom.reason}</p>
                  {regions.length > 0 ? (
                    <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white text-sm dark:divide-slate-700 dark:border-slate-700 dark:bg-slate-800">
                      {regions.map((region, i) => (
                        <li key={i} className="flex flex-wrap items-center gap-2 p-2.5">
                          <span className="font-medium">Region {i + 1}</span>
                          {region.rect.length === 4 && (
                            <span className="text-xs text-slate-600 dark:text-slate-400">
                              at ({region.rect[0]}, {region.rect[1]}), {region.rect[2]}×
                              {region.rect[3]} px
                            </span>
                          )}
                          <span className="tabular-nums">
                            {region.before ?? '?'} → {region.after ?? '?'}
                          </span>
                          <span
                            className={`ml-auto rounded-full px-2 py-0.5 text-xs font-semibold ${
                              region.resolved
                                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-100'
                                : 'bg-rose-100 text-rose-800 dark:bg-rose-900/50 dark:text-rose-100'
                            }`}
                          >
                            {region.resolved ? 'Resolved' : 'Unresolved'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      No regions were recounted.
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-600 dark:text-slate-400">
                The agent did not need a zoomed recount for this scan.
              </p>
            )}
          </section>

          <section aria-labelledby="diff-heading" className="space-y-3">
            <h2 id="diff-heading" className="text-lg font-semibold">
              Diff vs last approved photo
            </h2>
            {compare ? (
              <div className="flex flex-col gap-3 sm:flex-row">
                {compareSrc && (
                  <EvidenceThumbnail
                    src={compareSrc}
                    alt={`Change heatmap against the last approved photo of this tray: ${compare.reason}`}
                    title="Change heatmap"
                    className="shrink-0 self-start"
                    imgClassName="h-32 w-44 object-cover"
                  />
                )}
                <div className="min-w-0 flex-1 space-y-2">
                  <dl className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                    {stepMetrics(compare).map((m) => (
                      <div key={m.label} className="flex gap-1">
                        <dt className="text-slate-600 dark:text-slate-400">{m.label}</dt>
                        <dd className="font-semibold tabular-nums">{m.value}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="text-sm text-slate-800 dark:text-slate-200">{compare.reason}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-600 dark:text-slate-400">
                No earlier approved photo of this tray to compare with.
              </p>
            )}
          </section>

          <div className="space-y-2">
            <AgentTimeline
              steps={steps}
              running={liveRunning}
              title={liveRunning ? 'Agent timeline' : 'Agent timeline (latest run)'}
            />
            {trace && trace.runs.length > 1 && (
              <p className="text-xs text-slate-600 dark:text-slate-400">
                This scan has {trace.runs.length} agent runs; the latest is shown.
              </p>
            )}
          </div>
        </div>

        <div id="decision" className="scroll-mt-20 lg:sticky lg:top-20">
          <ApprovalPanel scan={scan} onDecided={onDecided} />
        </div>
      </div>
    </section>
  );
}
