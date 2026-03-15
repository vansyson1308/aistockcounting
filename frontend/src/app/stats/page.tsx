'use client';

import { useEffect, useState } from 'react';

import LoadingSkeleton from '@/components/LoadingSkeleton';
import StatsChart from '@/components/StatsChart';
import { ApiClientError, downloadExportCsv, getStats } from '@/lib/api';
import { StatsData } from '@/types';

export default function StatsPage() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((e) =>
        setError(e instanceof ApiClientError ? e.message : 'Không tải được thống kê')
      );
  }, []);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!stats) return <LoadingSkeleton count={3} />;

  const chartData = [
    { label: 'Tổng', value: stats.total_records },
    { label: 'TB AI', value: Math.round(stats.avg_detected_count) },
    { label: 'TB Manual', value: Math.round(stats.avg_manual_count) },
  ];

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Thống kê</h1>
        <button
          onClick={() => downloadExportCsv()}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Xuất CSV
        </button>
      </div>

      <div className="space-y-2 rounded-xl bg-white p-4 shadow dark:bg-slate-800">
        <p>
          Tổng bản ghi: <strong>{stats.total_records}</strong>
        </p>
        <p>
          TB AI đếm: <strong>{stats.avg_detected_count.toFixed(2)}</strong>
        </p>
        <p>
          TB manual: <strong>{stats.avg_manual_count.toFixed(2)}</strong>
        </p>
        <p>
          Tỷ lệ AI đúng:{' '}
          <strong>{(stats.ai_correct_rate * 100).toFixed(1)}%</strong>
        </p>
      </div>

      <StatsChart data={chartData} title="Tổng quan" />

      <StatsChart
        data={[{ label: 'AI đúng', value: Math.round(stats.ai_correct_rate * 100) }]}
        title="Tỷ lệ AI đúng (%)"
        color="#10b981"
      />
    </section>
  );
}
