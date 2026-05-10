'use client';

import { useMemo, useState } from 'react';

import BoundingBoxOverlay from '@/components/BoundingBoxOverlay';
import CameraCapture from '@/components/CameraCapture';
import ImageViewer from '@/components/ImageViewer';
import { ApiClientError, buildImageUrl, createAuditScan, reviewAuditScan } from '@/lib/api';
import { compressImage } from '@/lib/image-compress';
import { sanitizeText } from '@/lib/sanitize';
import { useSessionStore } from '@/store/useSessionStore';
import { useToastStore } from '@/store/useToastStore';
import { ScanCreateData } from '@/types';

const currency = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' });

function parseOptionalNumber(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export default function ScanPage() {
  const { staffId, setStaffId } = useSessionStore();
  const showToast = useToastStore((s) => s.show);

  const [branchCode, setBranchCode] = useState('MAIN');
  const [trayCode, setTrayCode] = useState('');
  const [expectedCount, setExpectedCount] = useState('');
  const [unitValue, setUnitValue] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [compressionInfo, setCompressionInfo] = useState('');
  const [result, setResult] = useState<ScanCreateData | null>(null);
  const [manualCount, setManualCount] = useState('');
  const [isAICorrect, setIsAICorrect] = useState<boolean | null>(null);
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [imgNatural, setImgNatural] = useState({ w: 0, h: 0 });
  const [imgDisplay, setImgDisplay] = useState({ w: 0, h: 0 });

  const scan = result?.scan;
  const variance = scan?.variance_count ?? null;
  const qualityFlags = scan?.quality_flags ?? [];
  const displaySrc = preview || buildImageUrl(scan?.image_path);

  const reviewCount = useMemo(() => {
    if (manualCount.trim() !== '') return parseOptionalNumber(manualCount);
    return scan?.final_count ?? null;
  }, [manualCount, scan?.final_count]);

  const handleFile = async (selected: File, url?: string) => {
    const originalSize = selected.size;
    const compressed = await compressImage(selected);
    const savedUrl = url || URL.createObjectURL(compressed);
    if (compressed.size < originalSize) {
      const saved = ((1 - compressed.size / originalSize) * 100).toFixed(0);
      setCompressionInfo(
        `${(originalSize / 1024 / 1024).toFixed(1)}MB -> ${(compressed.size / 1024 / 1024).toFixed(1)}MB (-${saved}%)`,
      );
    } else {
      setCompressionInfo('');
    }
    setFile(compressed);
    setPreview(savedUrl);
    setResult(null);
    setStatus('');
  };

  const runAudit = async () => {
    if (!file) return setStatus('Chon hoac chup anh khay truoc.');
    if (!trayCode.trim()) return setStatus('Nhap ma khay de doi soat.');

    try {
      setLoading(true);
      setStatus('Dang tao audit scan...');
      const data = await createAuditScan(file, {
        branchCode: sanitizeText(branchCode, 80) || 'MAIN',
        trayCode: sanitizeText(trayCode, 80),
        staffId: sanitizeText(staffId, 50),
        expectedCount: parseOptionalNumber(expectedCount),
        unitValue: parseOptionalNumber(unitValue),
      });
      setResult(data);
      setManualCount(String(data.scan.final_count));
      setStatus(data.discrepancy ? 'Phat hien lech ton kho.' : 'Scan da san sang review.');
    } catch (error) {
      setStatus(error instanceof ApiClientError ? error.message : 'Khong the tao audit scan.');
    } finally {
      setLoading(false);
    }
  };

  const submitReview = async () => {
    if (!scan) return;
    try {
      setReviewing(true);
      const data = await reviewAuditScan(scan.id, {
        manual_count: reviewCount,
        expected_count: parseOptionalNumber(expectedCount) ?? scan.expected_count ?? null,
        unit_value: parseOptionalNumber(unitValue),
        is_ai_correct: isAICorrect,
        notes: sanitizeText(notes, 500) || null,
      });
      setResult(data);
      showToast(data.discrepancy ? 'Da cap nhat lech ton kho' : 'Da review scan');
      setStatus(data.discrepancy ? 'Discrepancy van mo.' : 'Scan da khop voi ton ky vong.');
    } catch (error) {
      setStatus(error instanceof ApiClientError ? error.message : 'Review that bai.');
    } finally {
      setReviewing(false);
    }
  };

  const resetFlow = () => {
    setFile(null);
    setPreview('');
    setResult(null);
    setManualCount('');
    setNotes('');
    setIsAICorrect(null);
    setTrayCode('');
    setExpectedCount('');
    setUnitValue('');
    setCompressionInfo('');
    setStatus('');
  };

  return (
    <section className="space-y-5">
      <div className="border-b border-slate-200 pb-4 dark:border-slate-700">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">
          Audit scan
        </p>
        <h1 className="mt-1 text-2xl font-bold">Doi soat khay bang hinh anh</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          Chup khay, luu bang chung, so voi ton POS hoac so ky vong, roi xu ly lech ngay trong inbox.
        </p>
      </div>

      <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800 md:grid-cols-2">
        <label className="text-sm font-medium">
          Chi nhanh
          <input
            value={branchCode}
            onChange={(e) => setBranchCode(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
          />
        </label>
        <label className="text-sm font-medium">
          Ma khay
          <input
            value={trayCode}
            onChange={(e) => setTrayCode(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
          />
        </label>
        <label className="text-sm font-medium">
          Ma nhan vien
          <input
            value={staffId}
            onChange={(e) => setStaffId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
          />
        </label>
        <label className="text-sm font-medium">
          Ton ky vong
          <input
            type="number"
            min={0}
            value={expectedCount}
            onChange={(e) => setExpectedCount(e.target.value)}
            placeholder="Lay tu KiotViet neu de trong"
            className="mt-1 w-full rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
          />
        </label>
        <label className="text-sm font-medium md:col-span-2">
          Gia tri uoc tinh moi mon
          <input
            type="number"
            min={0}
            value={unitValue}
            onChange={(e) => setUnitValue(e.target.value)}
            placeholder="Dung de tinh risk value cho discrepancy"
            className="mt-1 w-full rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
          />
        </label>
      </div>

      <div className="space-y-3">
        <CameraCapture onCapture={handleFile} />
        <div className="rounded-lg border border-dashed border-slate-300 p-4 dark:border-slate-700">
          <label className="block text-sm font-medium">Hoac tai anh len</label>
          <input
            type="file"
            accept="image/jpeg,image/png"
            capture="environment"
            onChange={(e) => {
              const selected = e.target.files?.[0];
              if (selected) handleFile(selected);
            }}
            className="mt-2 w-full text-sm"
          />
          {compressionInfo && <p className="mt-2 text-xs text-emerald-600">{compressionInfo}</p>}
        </div>
      </div>

      <button
        onClick={runAudit}
        disabled={loading}
        className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-60"
      >
        {loading ? 'Dang doi soat...' : 'Tao audit scan'}
      </button>

      {displaySrc && (
        <ImageViewer
          src={displaySrc}
          alt="Anh khay audit"
          onLoad={(event) => {
            const el = event.currentTarget as HTMLImageElement;
            setImgNatural({ w: el.naturalWidth, h: el.naturalHeight });
            setImgDisplay({ w: el.clientWidth, h: el.clientHeight });
          }}
        >
          {scan?.boxes_json && (
            <BoundingBoxOverlay
              boxes={scan.boxes_json}
              naturalWidth={imgNatural.w}
              naturalHeight={imgNatural.h}
              displayWidth={imgDisplay.w}
              displayHeight={imgDisplay.h}
            />
          )}
        </ImageViewer>
      )}

      {scan && (
        <div className="space-y-4 border-t border-slate-200 pt-4 dark:border-slate-700">
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <p className="text-xs text-slate-500">AI dem</p>
              <p className="text-2xl font-bold">{scan.detected_count}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Ton ky vong</p>
              <p className="text-2xl font-bold">{scan.expected_count ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Lech</p>
              <p className={`text-2xl font-bold ${variance ? 'text-rose-600' : 'text-emerald-600'}`}>
                {variance ?? '-'}
              </p>
            </div>
          </div>

          {scan.variance_value !== null && scan.variance_value !== undefined && (
            <div className="rounded-md bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
              Gia tri rui ro uoc tinh: <strong>{currency.format(scan.variance_value)}</strong>
            </div>
          )}

          {qualityFlags.length > 0 && (
            <div className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
              Can chup lai neu co the: {qualityFlags.join(', ')}
            </div>
          )}

          <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <label className="text-sm font-medium">
              So sau khi dem lai
              <input
                type="number"
                min={0}
                value={manualCount}
                onChange={(e) => setManualCount(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 p-2.5 dark:border-slate-600 dark:bg-slate-900"
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setIsAICorrect(true)}
                className={`rounded-md border p-2.5 text-sm font-semibold ${
                  isAICorrect === true ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-slate-300'
                }`}
              >
                AI dung
              </button>
              <button
                type="button"
                onClick={() => setIsAICorrect(false)}
                className={`rounded-md border p-2.5 text-sm font-semibold ${
                  isAICorrect === false ? 'border-rose-600 bg-rose-600 text-white' : 'border-slate-300'
                }`}
              >
                AI can sua
              </button>
            </div>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Ly do lech, mat hang bi che, POS chua dong bo..."
              className="min-h-24 rounded-md border border-slate-300 p-2.5 text-sm dark:border-slate-600 dark:bg-slate-900"
            />
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={submitReview}
                disabled={reviewing}
                className="rounded-lg bg-slate-900 px-4 py-3 font-semibold text-white transition hover:bg-slate-700 disabled:opacity-60 dark:bg-white dark:text-slate-900"
              >
                {reviewing ? 'Dang luu...' : 'Review & cap nhat'}
              </button>
              <button
                onClick={resetFlow}
                className="rounded-lg border border-slate-300 px-4 py-3 font-semibold transition hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800"
              >
                Khay tiep
              </button>
            </div>
          </div>
        </div>
      )}

      {status && <p className="text-sm text-slate-700 dark:text-slate-300">{status}</p>}
    </section>
  );
}
