'use client';

import { useCallback, useEffect, useState } from 'react';

import LoadingSkeleton from '@/components/LoadingSkeleton';
import { ApiClientError, getDiscrepancies, resolveDiscrepancy } from '@/lib/api';
import { Discrepancy } from '@/types';

const currency = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' });

function severityClass(severity: string) {
  if (severity === 'high') return 'text-rose-700 bg-rose-50 border-rose-200';
  if (severity === 'medium') return 'text-amber-700 bg-amber-50 border-amber-200';
  return 'text-slate-700 bg-slate-50 border-slate-200';
}

export default function DiscrepanciesPage() {
  const [items, setItems] = useState<Discrepancy[]>([]);
  const [status, setStatus] = useState('open');
  const [branchCode, setBranchCode] = useState('');
  const [resolutionBy, setResolutionBy] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const params = new URLSearchParams({ status });
      if (branchCode) params.set('branch_code', branchCode);
      const data = await getDiscrepancies(params);
      setItems(data.items);
    } catch (e) {
      setError(e instanceof ApiClientError ? e.message : 'Khong tai duoc danh sach lech.');
    } finally {
      setLoading(false);
    }
  }, [branchCode, status]);

  useEffect(() => {
    load();
  }, [load]);

  const resolve = async (item: Discrepancy, nextStatus: 'resolved' | 'ignored') => {
    try {
      await resolveDiscrepancy(item.id, {
        status: nextStatus,
        resolution_note:
          nextStatus === 'resolved' ? 'Da doi soat va xac nhan xu ly.' : 'Bo qua sau khi review.',
        resolved_by: resolutionBy || null,
      });
      await load();
    } catch (e) {
      setError(e instanceof ApiClientError ? e.message : 'Khong the cap nhat discrepancy.');
    }
  };

  return (
    <section className="space-y-5">
      <div className="border-b border-slate-200 pb-4 dark:border-slate-700">
        <p className="text-xs font-semibold uppercase text-indigo-600 dark:text-indigo-400">
          Discrepancy inbox
        </p>
        <h1 className="mt-1 text-2xl font-bold">Lech ton can xu ly</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          Noi quan ly chenh lech giua anh scan, so dem lai va ton ky vong tu POS.
        </p>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
        >
          <option value="open">Dang mo</option>
          <option value="resolved">Da xu ly</option>
          <option value="ignored">Da bo qua</option>
        </select>
        <input
          value={branchCode}
          onChange={(e) => setBranchCode(e.target.value)}
          placeholder="Chi nhanh"
          className="rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
        />
        <input
          value={resolutionBy}
          onChange={(e) => setResolutionBy(e.target.value)}
          placeholder="Nguoi xu ly"
          className="rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
        />
        <button onClick={load} className="rounded-md bg-indigo-600 p-2.5 font-semibold text-white">
          Loc
        </button>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {loading ? (
        <LoadingSkeleton count={4} />
      ) : (
        <div className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white dark:divide-slate-700 dark:border-slate-700 dark:bg-slate-800">
          {items.length === 0 && <p className="p-4 text-sm text-slate-500">Khong co discrepancy nao.</p>}
          {items.map((item) => (
            <article key={item.id} className="grid gap-3 p-4 md:grid-cols-[1fr_auto]">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-semibold">
                    {item.branch_code} / {item.tray_code}
                  </h2>
                  <span className={`rounded-full border px-2 py-0.5 text-xs ${severityClass(item.severity)}`}>
                    {item.severity}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                  Ky vong {item.expected_count}, thuc te {item.actual_count}, lech {item.variance_count}
                </p>
                <p className="mt-1 text-sm">
                  Risk value:{' '}
                  <strong>{item.variance_value ? currency.format(item.variance_value) : 'Chua co gia tri'}</strong>
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Tao luc {new Date(item.created_at).toLocaleString('vi-VN')}
                </p>
              </div>
              {item.status === 'open' && (
                <div className="grid grid-cols-2 gap-2 md:w-52">
                  <button
                    onClick={() => resolve(item, 'resolved')}
                    className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white"
                  >
                    Xu ly
                  </button>
                  <button
                    onClick={() => resolve(item, 'ignored')}
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold dark:border-slate-600"
                  >
                    Bo qua
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
