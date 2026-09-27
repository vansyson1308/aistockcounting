'use client';

import { useEffect, useId, useRef, useState } from 'react';

import { statusLabel } from '@/lib/agent-format';
import { ApiClientError, approveScan } from '@/lib/api';
import { sanitizeText } from '@/lib/sanitize';
import { useSessionStore } from '@/store/useSessionStore';
import { ApproveDecision, ApprovePayload, ApproveResult, ScanSession } from '@/types';

type Props = {
  scan: ScanSession;
  onDecided?: (result: ApproveResult) => void;
};

const inputClass =
  'mt-1 w-full rounded-md border border-slate-300 p-2.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 aria-[invalid=true]:border-rose-600 dark:border-slate-600 dark:bg-slate-900';

const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600';

function formatDate(value: string | null | undefined): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-GB');
}

function FinalDecision({ scan }: { scan: ScanSession }) {
  return (
    <dl className="grid grid-cols-2 gap-3 text-sm">
      <div>
        <dt className="text-slate-600 dark:text-slate-400">Status</dt>
        <dd className="font-semibold">{statusLabel(scan.status)}</dd>
      </div>
      <div>
        <dt className="text-slate-600 dark:text-slate-400">Final count</dt>
        <dd className="font-semibold tabular-nums">{scan.final_count}</dd>
      </div>
      <div>
        <dt className="text-slate-600 dark:text-slate-400">Decided by</dt>
        <dd className="font-semibold">{scan.approved_by || 'Agent (no human approval)'}</dd>
      </div>
      <div>
        <dt className="text-slate-600 dark:text-slate-400">Decided at</dt>
        <dd className="font-semibold">{formatDate(scan.approved_at) || '—'}</dd>
      </div>
      {scan.notes && (
        <div className="col-span-2">
          <dt className="text-slate-600 dark:text-slate-400">Note</dt>
          <dd>{scan.notes}</dd>
        </div>
      )}
    </dl>
  );
}

/** Human approval gate for a scan the agent escalated. */
export default function ApprovalPanel({ scan, onDecided }: Props) {
  const staffId = useSessionStore((s) => s.staffId);
  const [approverId, setApproverId] = useState('');
  const [correctedCount, setCorrectedCount] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState<ApproveDecision | null>(null);
  const [approverError, setApproverError] = useState('');
  const [countError, setCountError] = useState('');
  const [apiError, setApiError] = useState('');
  const approverRef = useRef<HTMLInputElement>(null);
  const countRef = useRef<HTMLInputElement>(null);
  const ids = {
    heading: useId(),
    approver: useId(),
    approverError: useId(),
    count: useId(),
    countError: useId(),
    note: useId(),
  };

  // The session store is persisted in localStorage; prefill once it is available.
  useEffect(() => {
    setApproverId((current) => current || staffId);
  }, [staffId]);

  const awaiting = scan.status === 'awaiting_approval';
  const agentCount = scan.agent_count ?? scan.final_count;

  const submit = async (decision: ApproveDecision) => {
    setApiError('');
    const approver = sanitizeText(approverId, 80);
    let valid = true;
    if (!approver) {
      setApproverError('Enter your approver ID.');
      valid = false;
    } else {
      setApproverError('');
    }

    let count: number | undefined;
    if (decision === 'correct') {
      const parsed = Number(correctedCount);
      if (correctedCount.trim() === '' || !Number.isInteger(parsed) || parsed < 0) {
        setCountError('Enter the corrected count as a whole number (0 or more).');
        valid = false;
      } else {
        setCountError('');
        count = parsed;
      }
    } else {
      setCountError('');
    }

    if (!valid) {
      if (!approver) approverRef.current?.focus();
      else countRef.current?.focus();
      return;
    }

    const payload: ApprovePayload = { approver_id: approver, decision };
    if (count !== undefined) payload.corrected_count = count;
    const cleanNote = sanitizeText(note, 500);
    if (cleanNote) payload.note = cleanNote;

    try {
      setSubmitting(decision);
      const result = await approveScan(scan.id, payload);
      onDecided?.(result);
    } catch (error) {
      setApiError(
        error instanceof ApiClientError
          ? error.message
          : 'Could not save the decision. Check your connection and try again.'
      );
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <section
      aria-labelledby={ids.heading}
      className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800"
    >
      <h2 id={ids.heading} className="text-lg font-semibold">
        {awaiting ? 'Your decision' : 'Final decision'}
      </h2>

      {!awaiting ? (
        <div className="mt-3">
          <FinalDecision scan={scan} />
        </div>
      ) : (
        <div className="mt-3 space-y-4">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            The agent escalated this count to a human. Approve it, correct it, or reject it to
            request a recount.
          </p>

          <div>
            <label htmlFor={ids.approver} className="text-sm font-medium">
              Approver ID <span aria-hidden="true">*</span>
            </label>
            <input
              ref={approverRef}
              id={ids.approver}
              value={approverId}
              onChange={(e) => setApproverId(e.target.value)}
              required
              aria-required="true"
              aria-invalid={approverError ? true : undefined}
              aria-describedby={approverError ? ids.approverError : undefined}
              autoComplete="username"
              className={inputClass}
            />
            {approverError && (
              <p id={ids.approverError} className="mt-1 text-sm text-rose-700 dark:text-rose-300">
                {approverError}
              </p>
            )}
          </div>

          <div>
            <label htmlFor={ids.note} className="text-sm font-medium">
              Note{' '}
              <span className="font-normal text-slate-600 dark:text-slate-400">(optional)</span>
            </label>
            <textarea
              id={ids.note}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              placeholder="For example: two rings hidden under the tray lip"
              className={`${inputClass} min-h-20 text-sm`}
            />
          </div>

          <button
            type="button"
            onClick={() => submit('approve')}
            disabled={submitting !== null}
            className={`w-full rounded-lg bg-emerald-700 px-4 py-3 font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60 ${focusRing}`}
          >
            {submitting === 'approve' ? 'Saving…' : `Approve agent count (${agentCount})`}
          </button>

          <fieldset className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
            <legend className="px-1 text-sm font-medium">Correct the count</legend>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="flex-1">
                <label htmlFor={ids.count} className="text-sm">
                  Corrected count
                </label>
                <input
                  ref={countRef}
                  id={ids.count}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  step={1}
                  value={correctedCount}
                  onChange={(e) => setCorrectedCount(e.target.value)}
                  aria-invalid={countError ? true : undefined}
                  aria-describedby={countError ? ids.countError : undefined}
                  className={inputClass}
                />
              </div>
              <button
                type="button"
                onClick={() => submit('correct')}
                disabled={submitting !== null}
                className={`rounded-lg bg-indigo-600 px-4 py-2.5 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 ${focusRing}`}
              >
                {submitting === 'correct' ? 'Saving…' : 'Save correction'}
              </button>
            </div>
            {countError && (
              <p id={ids.countError} className="mt-1 text-sm text-rose-700 dark:text-rose-300">
                {countError}
              </p>
            )}
          </fieldset>

          <button
            type="button"
            onClick={() => submit('reject')}
            disabled={submitting !== null}
            className={`w-full rounded-lg border border-rose-300 px-4 py-3 font-semibold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-rose-700 dark:text-rose-300 dark:hover:bg-rose-950/40 ${focusRing}`}
          >
            {submitting === 'reject' ? 'Saving…' : 'Reject and request a recount'}
          </button>

          {apiError && (
            <p
              role="alert"
              className="rounded-md bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-200"
            >
              {apiError}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
