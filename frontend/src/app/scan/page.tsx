'use client';

import { useMemo, useState } from 'react';

import BoundingBoxOverlay from '@/components/BoundingBoxOverlay';
import CameraCapture from '@/components/CameraCapture';
import ImageViewer from '@/components/ImageViewer';
import ManualOverride from '@/components/ManualOverride';
import { ApiClientError, countItems, saveRecord } from '@/lib/api';
import { compressImage } from '@/lib/image-compress';
import { sanitizeText } from '@/lib/sanitize';
import { useScanStore } from '@/store/useScanStore';
import { useSessionStore } from '@/store/useSessionStore';
import { useToastStore } from '@/store/useToastStore';

export default function ScanPage() {
  const {
    file, preview, result, manualCount, isAICorrect, notes, loading, status,
    setFile, setResult, setManualCount, setIsAICorrect, setNotes, setLoading, setStatus, reset,
  } = useScanStore();

  const { staffId, setStaffId } = useSessionStore();
  const showToast = useToastStore((s) => s.show);

  const [trayId, setTrayId] = useState('');
  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  const [imgDisplay, setImgDisplay] = useState({ w: 0, h: 0 });
  const [compressionInfo, setCompressionInfo] = useState('');

  const detected = useMemo(() => result?.detected_count ?? 0, [result]);

  const handleFile = async (selected: File, url?: string) => {
    const originalSize = selected.size;
    const compressed = await compressImage(selected);
    const newSize = compressed.size;
    if (newSize < originalSize) {
      const saved = ((1 - newSize / originalSize) * 100).toFixed(0);
      setCompressionInfo(
        `${(originalSize / 1024 / 1024).toFixed(1)}MB → ${(newSize / 1024 / 1024).toFixed(1)}MB (-${saved}%)`
      );
    } else {
      setCompressionInfo('');
    }
    setFile(compressed, url);
  };

  const onUpload = async () => {
    if (!file) return setStatus('Vui lòng chụp hoặc chọn ảnh.');
    try {
      setLoading(true);
      setStatus('Đang xử lý ảnh...');
      const data = await countItems(file, sanitizeText(trayId, 50), sanitizeText(staffId, 50));
      setResult(data);
    } catch (error) {
      setStatus(error instanceof ApiClientError ? error.message : 'Không thể xử lý ảnh.');
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
      showToast('Đã lưu bản ghi');
      setStatus('Đã lưu thành công.');
    } catch (error) {
      setStatus(error instanceof ApiClientError ? error.message : 'Lưu thất bại.');
    }
  };

  const resetForNext = () => {
    reset();
    setTrayId('');
    setCompressionInfo('');
  };

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-bold">Kiểm kê khay mới</h1>

      <div className="rounded-xl bg-white p-4 shadow dark:bg-slate-800">
        <label className="mb-1 block text-sm font-medium">Mã khay (tuỳ chọn)</label>
        <input
          value={trayId}
          onChange={(e) => setTrayId(e.target.value)}
          className="mb-3 w-full rounded-lg border border-slate-300 p-3 dark:border-slate-600 dark:bg-slate-700"
        />
        <label className="mb-1 block text-sm font-medium">Mã nhân viên (tuỳ chọn)</label>
        <input
          value={staffId}
          onChange={(e) => setStaffId(e.target.value)}
          className="w-full rounded-lg border border-slate-300 p-3 dark:border-slate-600 dark:bg-slate-700"
        />
      </div>

      <CameraCapture onCapture={handleFile} />

      <div className="rounded-xl bg-white p-4 shadow dark:bg-slate-800">
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
        {compressionInfo && (
          <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-400">{compressionInfo}</p>
        )}
      </div>

      <button
        onClick={onUpload}
        disabled={loading}
        className="w-full rounded-xl bg-indigo-600 p-3 font-semibold text-white disabled:opacity-60 hover:bg-indigo-700"
      >
        {loading ? 'Đang xử lý...' : 'Đếm bằng AI'}
      </button>

      {preview && (
        <ImageViewer
          src={preview}
          alt="Ảnh kiểm kê"
          onLoad={(event) => {
            const el = event.currentTarget as HTMLImageElement;
            setImgNatural({ w: el.naturalWidth, h: el.naturalHeight });
            setImgDisplay({ w: el.clientWidth, h: el.clientHeight });
          }}
        >
          {result && (
            <BoundingBoxOverlay
              boxes={result.boxes}
              naturalWidth={imgNatural.w}
              naturalHeight={imgNatural.h}
              displayWidth={imgDisplay.w}
              displayHeight={imgDisplay.h}
            />
          )}
        </ImageViewer>
      )}

      {result?.mock_mode && (
        <div className="rounded-xl border border-amber-400 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-600 dark:bg-amber-900/30 dark:text-amber-300">
          AI model chưa sẵn sàng — kết quả là mô phỏng
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div className="rounded-xl bg-white p-4 shadow dark:bg-slate-800">
            <p className="text-sm text-slate-600 dark:text-slate-400">Kết quả AI</p>
            <p className="text-2xl font-bold">{detected} món</p>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Độ tin cậy TB: {(result.confidence_avg * 100).toFixed(1)}%
            </p>
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
            <button onClick={onSave} className="rounded-xl bg-emerald-600 p-3 font-semibold text-white hover:bg-emerald-700">
              Lưu
            </button>
            <button onClick={resetForNext} className="rounded-xl bg-slate-700 p-3 font-semibold text-white hover:bg-slate-600">
              Quét khay tiếp
            </button>
          </div>
        </div>
      )}

      {status && <p className="text-sm text-slate-700 dark:text-slate-300">{status}</p>}
    </section>
  );
}
