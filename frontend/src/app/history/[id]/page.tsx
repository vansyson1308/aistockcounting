'use client';

import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import BoundingBoxOverlay from '@/components/BoundingBoxOverlay';
import { ApiClientError, buildImageUrl, getHistoryById } from '@/lib/api';
import { HistoryItem } from '@/types';

export default function HistoryDetailPage() {
  const params = useParams<{ id: string }>();
  const [record, setRecord] = useState<HistoryItem | null>(null);
  const [error, setError] = useState('');
  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  const [imgDisplay, setImgDisplay] = useState({ w: 0, h: 0 });

  useEffect(() => {
    if (!params?.id) return;
    getHistoryById(params.id)
      .then(setRecord)
      .catch((e) => setError(e instanceof ApiClientError ? e.message : 'Không tải được chi tiết'));
  }, [params?.id]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!record) return <p>Đang tải...</p>;

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-bold">Chi tiết kiểm kê</h1>
      <div className="rounded-xl bg-white p-4 shadow">
        <p>Mã bản ghi: {record.id}</p>
        <p>Mã khay: {record.tray_id || 'N/A'}</p>
        <p>Nhân viên: {record.staff_id || 'N/A'}</p>
        <p>AI: {record.detected_count} • Manual: {record.manual_count ?? '-'}</p>
        <p>AI đúng: {record.is_ai_correct === null ? 'N/A' : record.is_ai_correct ? 'Đúng' : 'Sai'}</p>
        <p>Ghi chú: {record.notes || 'Không có'}</p>
      </div>

      <div className="relative overflow-hidden rounded-xl bg-black">
        <img
          src={buildImageUrl(record.image_path)}
          alt="Ảnh khay"
          className="w-full"
          onLoad={(event) => {
            setImgNatural({ w: event.currentTarget.naturalWidth, h: event.currentTarget.naturalHeight });
            setImgDisplay({ w: event.currentTarget.clientWidth, h: event.currentTarget.clientHeight });
          }}
        />
        <BoundingBoxOverlay
          boxes={record.boxes_json || []}
          naturalWidth={imgNatural.w}
          naturalHeight={imgNatural.h}
          displayWidth={imgDisplay.w}
          displayHeight={imgDisplay.h}
        />
      </div>
    </section>
  );
}
