'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { useReviewQueueStore } from '@/store/useReviewQueueStore';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600';

export default function ReviewQueuePage() {
  const router = useRouter();
  const items = useReviewQueueStore((s) => s.items);
  const remove = useReviewQueueStore((s) => s.remove);
  // The queue lives in localStorage; render it only after mount to avoid a hydration mismatch.
  const [mounted, setMounted] = useState(false);
  const [scanId, setScanId] = useState('');
  const [error, setError] = useState('');

  useEffect(() => setMounted(true), []);

  const open = (event: React.FormEvent) => {
    event.preventDefault();
    const id = scanId.trim();
    if (!UUID_RE.test(id)) {
      setError('Enter a valid scan ID (a UUID such as 3f2b…-…).');
      return;
    }
    setError('');
    router.push(`/review/${id}`);
  };

  return (
    <section className="space-y-5">
      <div className="border-b border-slate-200 pb-4 dark:border-slate-700">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-400">
          Review queue
        </p>
        <h1 className="mt-1 text-2xl font-bold">Escalated scans</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          When TrayAgent is not confident, it escalates the count to a human. Open a scan to see its
          evidence and approve, correct or reject the count.
        </p>
      </div>

      <form
        onSubmit={open}
        noValidate
        className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800 sm:flex-row sm:items-end"
      >
        <div className="flex-1">
          <label htmlFor="scan-id" className="text-sm font-medium">
            Open a scan by ID
          </label>
          <input
            id="scan-id"
            value={scanId}
            onChange={(e) => setScanId(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? 'scan-id-error' : undefined}
            className="mt-1 w-full rounded-md border border-slate-300 p-2.5 font-mono text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-slate-600 dark:bg-slate-900"
          />
        </div>
        <button
          type="submit"
          className={`rounded-lg bg-indigo-600 px-4 py-2.5 font-semibold text-white hover:bg-indigo-700 ${focusRing}`}
        >
          Open
        </button>
      </form>
      {error && (
        <p id="scan-id-error" role="alert" className="text-sm text-rose-700 dark:text-rose-300">
          {error}
        </p>
      )}

      <section aria-labelledby="queue-heading" className="space-y-2">
        <h2 id="queue-heading" className="text-lg font-semibold">
          Escalated on this device
        </h2>
        {!mounted ? null : items.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            No escalated scans on this device. Escalations from the{' '}
            <Link
              href="/scan"
              className={`rounded text-indigo-700 underline underline-offset-2 dark:text-indigo-300 ${focusRing}`}
            >
              scan page
            </Link>{' '}
            appear here.
          </p>
        ) : (
          <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white dark:divide-slate-700 dark:border-slate-700 dark:bg-slate-800">
            {items.map((item) => (
              <li key={item.id} className="flex items-center gap-3 p-3">
                <Link href={`/review/${item.id}`} className={`min-w-0 flex-1 rounded ${focusRing}`}>
                  <span className="block font-semibold">
                    {item.branchCode} / {item.trayCode}
                  </span>
                  <span className="block text-sm text-slate-600 dark:text-slate-400">
                    Agent {item.agentCount ?? '—'} vs POS {item.expectedCount ?? '—'} ·{' '}
                    {new Date(item.createdAt).toLocaleString('en-GB')}
                  </span>
                </Link>
                <button
                  type="button"
                  onClick={() => remove(item.id)}
                  aria-label={`Remove ${item.branchCode} / ${item.trayCode} from this list`}
                  className={`rounded-md border border-slate-300 px-2.5 py-1 text-sm hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700 ${focusRing}`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
