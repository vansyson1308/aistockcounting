'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ApiClientError, getHistory } from '@/lib/api';
import { HistoryItem } from '@/types';

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [total, setTotal] = useState(0);
  const [staffId, setStaffId] = useState('');
  const [trayId, setTrayId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [aiCorrect, setAiCorrect] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      setError('');
      const params = new URLSearchParams({ page: String(page), limit: String(limit) });
      if (staffId) params.set('staff_id', staffId);
      if (trayId) params.set('tray_id', trayId);
      if (dateFrom) params.set('date_from', `${dateFrom}T00:00:00`);
      if (dateTo) params.set('date_to', `${dateTo}T23:59:59`);
      if (aiCorrect) params.set('ai_correct', aiCorrect);

      const data = await getHistory(params);
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof ApiClientError ? e.message : 'Không tải được lịch sử.');
    }
  };

  useEffect(() => {
    load();
  }, [page]);

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-bold">Lịch sử kiểm kê</h1>

      <div className="grid grid-cols-2 gap-2 rounded-xl bg-white p-3 shadow">
        <input placeholder="Mã NV" value={staffId} onChange={(e) => setStaffId(e.target.value)} className="rounded border p-2" />
        <input placeholder="Mã khay" value={trayId} onChange={(e) => setTrayId(e.target.value)} className="rounded border p-2" />
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="rounded border p-2" />
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="rounded border p-2" />
        <select value={aiCorrect} onChange={(e) => setAiCorrect(e.target.value)} className="col-span-2 rounded border p-2">
          <option value="">AI đúng/sai: tất cả</option>
          <option value="true">AI đúng</option>
          <option value="false">AI sai</option>
        </select>
        <button onClick={() => { setPage(1); load(); }} className="col-span-2 rounded bg-indigo-600 p-2 font-semibold text-white">Lọc</button>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id} className="rounded-xl bg-white p-3 shadow">
            <Link href={`/history/${item.id}`} className="block">
              <p className="font-semibold">Khay: {item.tray_id || 'N/A'} • NV: {item.staff_id || 'N/A'}</p>
              <p className="text-sm text-slate-600">
                AI: {item.detected_count} • Manual: {item.manual_count ?? '-'} • {new Date(item.created_at).toLocaleString('vi-VN')}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      <div className="flex items-center justify-between rounded-xl bg-white p-3 shadow">
        <button disabled={page <= 1} onClick={() => setPage((v) => Math.max(1, v - 1))} className="rounded border px-3 py-2 disabled:opacity-50">Trước</button>
        <span className="text-sm">Trang {page} • Tổng {total}</span>
        <button disabled={page * limit >= total} onClick={() => setPage((v) => v + 1)} className="rounded border px-3 py-2 disabled:opacity-50">Sau</button>
      </div>
    </section>
  );
}
