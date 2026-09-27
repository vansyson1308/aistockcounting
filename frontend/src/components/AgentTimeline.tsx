'use client';

import { useId } from 'react';

import EvidenceThumbnail from '@/components/EvidenceLightbox';
import {
  decisionBadgeClass,
  decisionLabel,
  formatLatency,
  qualityFlags,
  stepMetrics,
  toolLabel,
} from '@/lib/agent-format';
import { evidenceSrc } from '@/lib/api';
import { TraceStep } from '@/types';

type Props = {
  steps: TraceStep[];
  /** True while the agent is still working: shows a pending item at the end. */
  running?: boolean;
  title?: string;
  /** Shown when there are no steps and nothing is running. */
  emptyText?: string;
  className?: string;
};

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent motion-reduce:animate-none dark:border-indigo-400 dark:border-t-transparent"
    />
  );
}

function dotClass(step: TraceStep): string {
  if (step.tool === 'planner') return 'bg-amber-500 ring-amber-100 dark:ring-amber-900/60';
  if (step.tool === 'render_evidence') {
    if (step.decision === 'auto_accept')
      return 'bg-emerald-600 ring-emerald-100 dark:ring-emerald-900/60';
    if (step.decision === 'request_recapture')
      return 'bg-amber-500 ring-amber-100 dark:ring-amber-900/60';
    return 'bg-rose-600 ring-rose-100 dark:ring-rose-900/60';
  }
  return 'bg-indigo-600 ring-indigo-100 dark:ring-indigo-900/60';
}

function TimelineItem({ step, index }: { step: TraceStep; index: number }) {
  const label = toolLabel(step.tool);
  const metrics = stepMetrics(step);
  const flags = step.tool === 'assess_quality' ? qualityFlags(step) : [];
  const isTerminal = step.tool === 'render_evidence';
  const isFallback = step.tool === 'planner';
  const src = evidenceSrc(step.evidence_url);
  const latency = formatLatency(step.latency_ms);
  const plannerError =
    isFallback && typeof step.outputs?.error === 'string' ? step.outputs.error : null;

  return (
    <li className="relative pb-5 pl-8 last:pb-0">
      <span
        aria-hidden="true"
        className="absolute bottom-0 left-[7px] top-5 w-px bg-slate-200 dark:bg-slate-700"
      />
      <span
        aria-hidden="true"
        className={`absolute left-0 top-1 h-4 w-4 rounded-full ring-4 ${dotClass(step)}`}
      />
      <article
        aria-label={`${index + 1}. ${label}`}
        className={`rounded-lg border bg-white p-3 dark:bg-slate-800 ${
          isFallback
            ? 'border-amber-300 dark:border-amber-700'
            : 'border-slate-200 dark:border-slate-700'
        }`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">{label}</h3>
          {step.step_no > 0 && (
            <span className="text-xs text-slate-600 dark:text-slate-400">Step {step.step_no}</span>
          )}
          {isFallback && (
            <span className="rounded-full border border-amber-400 bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900 dark:border-amber-600 dark:bg-amber-900/50 dark:text-amber-100">
              Fallback
            </span>
          )}
          {step.planner === 'bedrock' && (
            <span className="rounded-full border border-violet-300 bg-violet-50 px-2 py-0.5 text-xs font-semibold text-violet-800 dark:border-violet-700 dark:bg-violet-950/40 dark:text-violet-200">
              Bedrock planner
            </span>
          )}
          {isTerminal && (
            <span
              className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${decisionBadgeClass(step.decision)}`}
            >
              {decisionLabel(step.decision)}
            </span>
          )}
          {latency && (
            <span className="ml-auto text-xs tabular-nums text-slate-600 dark:text-slate-400">
              <span className="sr-only">Took </span>
              {latency}
            </span>
          )}
        </div>

        <div className="mt-2 flex gap-3">
          <div className="min-w-0 flex-1 space-y-2">
            {metrics.length > 0 && (
              <dl className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                {metrics.map((m) => (
                  <div key={m.label} className="flex gap-1">
                    <dt className="text-slate-600 dark:text-slate-400">{m.label}</dt>
                    <dd className="font-semibold tabular-nums">{m.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {flags.length > 0 && (
              <ul aria-label="Quality flags" className="flex flex-wrap gap-1">
                {flags.map((flag) => (
                  <li
                    key={flag}
                    className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/50 dark:text-amber-100"
                  >
                    {flag.replace(/_/g, ' ')}
                  </li>
                ))}
              </ul>
            )}
            {step.reason && (
              <p className="border-l-4 border-indigo-300 pl-2 text-sm text-slate-800 dark:border-indigo-500 dark:text-slate-200">
                <span className="sr-only">Why: </span>
                {step.reason}
              </p>
            )}
            {plannerError && (
              <p className="break-words text-xs text-slate-600 dark:text-slate-400">
                Planner error: {plannerError}
              </p>
            )}
          </div>
          {src && (
            <EvidenceThumbnail
              src={src}
              alt={`Evidence image from “${label}”${step.reason ? `: ${step.reason}` : ''}`}
              title={`${label} evidence`}
              className="shrink-0 self-start"
              imgClassName="h-16 w-20 object-cover sm:h-20 sm:w-28"
            />
          )}
        </div>
      </article>
    </li>
  );
}

/** Vertical, live timeline of the agent's tool calls and the reasons for each next action. */
export default function AgentTimeline({
  steps,
  running = false,
  title = 'Agent timeline',
  emptyText = 'No agent steps recorded for this scan yet.',
  className = '',
}: Props) {
  const headingId = useId();

  return (
    <section aria-labelledby={headingId} className={className}>
      <div className="mb-3 flex items-center gap-2">
        <h2 id={headingId} className="text-lg font-semibold">
          {title}
        </h2>
        {running && (
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-200">
            Live
          </span>
        )}
      </div>
      <div aria-live="polite" aria-relevant="additions text">
        {steps.length === 0 && !running ? (
          <p className="text-sm text-slate-600 dark:text-slate-400">{emptyText}</p>
        ) : (
          <ol role="list" aria-label="Agent steps" className="list-none">
            {steps.map((step, index) => (
              <TimelineItem key={`${step.seq}-${step.tool}`} step={step} index={index} />
            ))}
            {running && (
              <li className="relative pl-8" data-testid="timeline-pending">
                <span className="absolute left-0 top-1 flex h-4 w-4 items-center justify-center">
                  <Spinner />
                </span>
                <p className="rounded-lg border border-dashed border-indigo-300 bg-indigo-50/60 p-3 text-sm font-medium text-indigo-900 dark:border-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-100">
                  {steps.length === 0 ? 'Starting the agent…' : 'Agent is choosing the next step…'}
                </p>
              </li>
            )}
          </ol>
        )}
      </div>
    </section>
  );
}
