'use client';

import { useEffect, useState } from 'react';

import { ApiClientError, getStats } from '@/lib/api';
import { StatsData } from '@/types';

export default function StatsPage() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getStats().then(setStats).catch((e) => setError(e instanceof ApiClientError ? e.message : 'Không tải được thống kê'));
  }, []);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!stats) return <p>Đang tải...</p>;

  return (
    <section className="space-y-3">
      <h1 className="text-xl font-bold">Thống kê</h1>
      <div className="space-y-2 rounded-xl bg-white p-4 shadow">
        <p>Tổng bản ghi: <strong>{stats.total_records}</strong></p>
        <p>TB AI đếm: <strong>{stats.avg_detected_count.toFixed(2)}</strong></p>
        <p>TB manual: <strong>{stats.avg_manual_count.toFixed(2)}</strong></p>
        <p>Tỷ lệ AI đúng: <strong>{(stats.ai_correct_rate * 100).toFixed(1)}%</strong></p>
      </div>
    </section>
  );
}
