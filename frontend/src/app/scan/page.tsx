'use client';

import { useMemo, useState } from 'react';

import BoundingBoxOverlay from '@/components/BoundingBoxOverlay';
import CameraCapture from '@/components/CameraCapture';
import ManualOverride from '@/components/ManualOverride';
import Toast from '@/components/Toast';
import { ApiClientError, countItems, saveRecord } from '@/lib/api';
import { sanitizeText } from '@/lib/sanitize';
import { CountResult } from '@/types';

export default function ScanPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [trayId, setTrayId] = useState('');
  const [staffId, setStaffId] = useState('');
  const [result, setResult] = useState<CountResult | null>(null);
  const [manualCount, setManualCount] = useState<number | ''>('');
  const [isAICorrect, setIsAICorrect] = useState<boolean | null>(null);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [toast, setToast] = useState(false);
  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  const [imgDisplay, setImgDisplay] = useState({ w: 0, h: 0 });

  const detected = useMemo(() => result?.detected_count ?? 0, [result]);

  const handleFile = (selected: File, url?: string) => {
    setFile(selected);
    setPreview(url || URL.createObjectURL(selected));
    setResult(null);
    setStatus('');
  };

  const onUpload = async () => {
    if (!file) return setStatus('Vui lòng chụp hoặc chọn ảnh.');
    try {
      setLoading(true);
      setStatus('Đang xử lý ảnh...');
      const safeTrayId = sanitizeText(trayId, 50);
      const safeStaffId = sanitizeText(staffId, 50);
      const data = await countItems(file, safeTrayId, safeStaffId);
      setResult(data);
      setManualCount(data.detected_count);
      setStatus(`AI đếm ${data.detected_count} món (${data.processing_time_ms}ms).`);
    } catch (error) {
      const message = error instanceof ApiClientError ? error.message : 'Không thể xử lý ảnh.';
      setStatus(message);
    } finally {
      setLoading(false);
    }
  };

  const onSave = async () => {
    if (!result) return;
    try {
      await saveRecord({
        image_path: result.image_path,
        image_thumbnail: result.image_thumbnail,
        detected_count: result.detected_count,
        manual_count: manualCount === '' ? null : manualCount,
        confidence_avg: result.confidence_avg,
        boxes_json: result.boxes,
        staff_id: sanitizeText(staffId, 50) || null,
        tray_id: sanitizeText(trayId, 50) || null,
        is_ai_correct: isAICorrect,
        notes: sanitizeText(notes, 500) || null,
      });
      setToast(true);
      setStatus('Đã lưu thành công.');
      setTimeout(() => setToast(false), 1600);
    } catch (error) {
      const message = error instanceof ApiClientError ? error.message : 'Lưu thất bại.';
      setStatus(message);
    }
  };

  const resetForNext = () => {
    setFile(null);
    setPreview('');
    setResult(null);
    setManualCount('');
    setIsAICorrect(null);
    setNotes('');
    setStatus('Sẵn sàng kiểm kê khay tiếp theo.');
  };

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-bold">Kiểm kê khay mới</h1>

      <div className="rounded-xl bg-white p-4 shadow">
        <label className="mb-1 block text-sm font-medium">Mã khay (tuỳ chọn)</label>
        <input value={trayId} onChange={(e) => setTrayId(e.target.value)} className="mb-3 w-full rounded-lg border p-3" />
        <label className="mb-1 block text-sm font-medium">Mã nhân viên (tuỳ chọn)</label>
        <input value={staffId} onChange={(e) => setStaffId(e.target.value)} className="w-full rounded-lg border p-3" />
      </div>

      <CameraCapture onCapture={handleFile} />

      <div className="rounded-xl bg-white p-4 shadow">
        <label className="mb-2 block text-sm font-medium">Hoặc tải ảnh lên</label>
        <input
          type="file"
          accept="image/jpeg,image/png"
          capture="environment"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
          className="w-full text-sm"
        />
      </div>

      <button onClick={onUpload} disabled={loading} className="w-full rounded-xl bg-indigo-600 p-3 font-semibold text-white disabled:opacity-60">
        {loading ? 'Đang xử lý...' : 'Đếm bằng AI'}
      </button>

      {preview && (
        <div className="relative overflow-hidden rounded-xl bg-black">
          <img
            src={preview}
            alt="Ảnh kiểm kê"
            className="h-auto w-full"
            onLoad={(event) => {
              setImgNatural({ w: event.currentTarget.naturalWidth, h: event.currentTarget.naturalHeight });
              setImgDisplay({ w: event.currentTarget.clientWidth, h: event.currentTarget.clientHeight });
            }}
          />
          {result && (
            <BoundingBoxOverlay
              boxes={result.boxes}
              naturalWidth={imgNatural.w}
              naturalHeight={imgNatural.h}
              displayWidth={imgDisplay.w}
              displayHeight={imgDisplay.h}
            />
          )}
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div className="rounded-xl bg-white p-4 shadow">
            <p className="text-sm text-slate-600">Kết quả AI</p>
            <p className="text-2xl font-bold">{detected} món</p>
            <p className="text-sm text-slate-500">Độ tin cậy TB: {(result.confidence_avg * 100).toFixed(1)}%</p>
          </div>

          <ManualOverride
            manualCount={manualCount}
            setManualCount={setManualCount}
            isAICorrect={isAICorrect}
            setIsAICorrect={setIsAICorrect}
            notes={notes}
            setNotes={setNotes}
          />

          <div className="grid grid-cols-2 gap-2">
            <button onClick={onSave} className="rounded-xl bg-emerald-600 p-3 font-semibold text-white">Lưu</button>
            <button onClick={resetForNext} className="rounded-xl bg-slate-700 p-3 font-semibold text-white">Quét khay tiếp</button>
          </div>
        </div>
      )}

      {status && <p className="text-sm text-slate-700">{status}</p>}
      <Toast message="Đã lưu bản ghi" show={toast} />
    </section>
  );
}
