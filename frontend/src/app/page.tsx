'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { getDiscrepancies, getKiotVietStatus, getStats } from '@/lib/api';
import { DiscrepancyListData, KiotVietStatus, StatsData } from '@/types';

export default function HomePage() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [discrepancies, setDiscrepancies] = useState<DiscrepancyListData | null>(null);
  const [kiotviet, setKiotviet] = useState<KiotVietStatus | null>(null);

  useEffect(() => {
    getStats().then(setStats).catch(() => setStats(null));
    getDiscrepancies(new URLSearchParams({ status: 'open' }))
      .then(setDiscrepancies)
      .catch(() => setDiscrepancies(null));
    getKiotVietStatus().then(setKiotviet).catch(() => setKiotviet(null));
  }, []);

  const openRisk = discrepancies?.items.reduce((sum, item) => sum + Math.abs(item.variance_value || 0), 0) ?? 0;

  return (
    <section className="space-y-6">
      <div className="border-b border-slate-200 pb-5 dark:border-slate-700">
        <p className="text-xs font-semibold uppercase text-indigo-600 dark:text-indigo-400">
          Jewelry Inventory Truth Layer
        </p>
        <h1 className="mt-2 text-3xl font-bold leading-tight">So cai ton kho co bang chung hinh anh</h1>
        <p className="mt-3 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
          Quet khay, doi soat voi POS, mo discrepancy khi co lech va giu lai anh lam bang chung cho ca cua hang.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <div className="border-l-4 border-indigo-600 pl-3">
          <p className="text-xs text-slate-500">Ban ghi cu</p>
          <p className="text-2xl font-bold">{stats?.total_records ?? '-'}</p>
        </div>
        <div className="border-l-4 border-rose-600 pl-3">
          <p className="text-xs text-slate-500">Lech dang mo</p>
          <p className="text-2xl font-bold">{discrepancies?.total ?? '-'}</p>
        </div>
        <div className="border-l-4 border-amber-500 pl-3">
          <p className="text-xs text-slate-500">Risk value</p>
          <p className="text-2xl font-bold">{openRisk ? `${Math.round(openRisk / 1_000_000)}tr` : '-'}</p>
        </div>
        <div className="border-l-4 border-emerald-600 pl-3">
          <p className="text-xs text-slate-500">KiotViet snapshots</p>
          <p className="text-2xl font-bold">{kiotviet?.snapshots ?? '-'}</p>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Link
          href="/scan"
          className="rounded-lg bg-indigo-600 p-4 font-semibold text-white transition hover:bg-indigo-700"
        >
          Tao audit scan
        </Link>
        <Link
          href="/discrepancies"
          className="rounded-lg bg-slate-900 p-4 font-semibold text-white transition hover:bg-slate-700 dark:bg-white dark:text-slate-900"
        >
          Xu ly lech ton
        </Link>
        <Link
          href="/stats"
          className="rounded-lg border border-slate-300 p-4 font-semibold transition hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Xem thong ke
        </Link>
      </div>

      <div className="border-t border-slate-200 pt-5 dark:border-slate-700">
        <h2 className="text-lg font-bold">Trang thai POS</h2>
        <div className="mt-3 grid gap-3 text-sm md:grid-cols-3">
          <p>
            Connector:{' '}
            <strong className={kiotviet?.configured ? 'text-emerald-600' : 'text-amber-600'}>
              {kiotviet?.configured ? 'Da cau hinh' : 'CSV fallback'}
            </strong>
          </p>
          <p>Lan sync cuoi: {kiotviet?.last_sync_at ? new Date(kiotviet.last_sync_at).toLocaleString('vi-VN') : '-'}</p>
          <p>
            Event cuoi:{' '}
            {kiotviet?.last_event_at ? new Date(kiotviet.last_event_at).toLocaleString('vi-VN') : '-'}
          </p>
        </div>
      </div>
    </section>
  );
}
