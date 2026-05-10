import {
  CountResult,
  DiscrepancyListData,
  HistoryItem,
  HistoryResponseData,
  KiotVietStatus,
  ReviewScanPayload,
  SavePayload,
  ScanCreateData,
  StatsData,
} from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api/v1';

export class ApiClientError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function parseResponse<T>(res: Response): Promise<T> {
  const payload = await res.json();
  if (!res.ok || payload.success === false) {
    throw new ApiClientError(payload?.error?.code || 'API_ERROR', payload?.error?.message || 'Lỗi hệ thống');
  }
  return payload.data as T;
}

export async function countItems(file: File, trayId?: string, staffId?: string): Promise<CountResult> {
  const formData = new FormData();
  formData.append('image', file);
  if (trayId) formData.append('tray_id', trayId);
  if (staffId) formData.append('staff_id', staffId);

  const res = await fetch(`${API_BASE}/count-items`, { method: 'POST', body: formData });
  return parseResponse<CountResult>(res);
}

export async function saveRecord(payload: SavePayload): Promise<{ id: string; created_at: string }> {
  const res = await fetch(`${API_BASE}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse<{ id: string; created_at: string }>(res);
}

export async function createAuditScan(
  file: File,
  payload: {
    branchCode: string;
    trayCode: string;
    staffId?: string;
    expectedCount?: number | null;
    unitValue?: number | null;
  },
): Promise<ScanCreateData> {
  const formData = new FormData();
  formData.append('image', file);
  formData.append('branch_code', payload.branchCode);
  formData.append('tray_code', payload.trayCode);
  if (payload.staffId) formData.append('staff_id', payload.staffId);
  if (payload.expectedCount !== null && payload.expectedCount !== undefined) {
    formData.append('expected_count', String(payload.expectedCount));
  }
  if (payload.unitValue !== null && payload.unitValue !== undefined) {
    formData.append('unit_value', String(payload.unitValue));
  }

  const res = await fetch(`${API_BASE}/scans`, { method: 'POST', body: formData });
  return parseResponse<ScanCreateData>(res);
}

export async function reviewAuditScan(id: string, payload: ReviewScanPayload): Promise<ScanCreateData> {
  const res = await fetch(`${API_BASE}/scans/${id}/review`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse<ScanCreateData>(res);
}

export async function getDiscrepancies(params?: URLSearchParams): Promise<DiscrepancyListData> {
  const query = params?.toString();
  const res = await fetch(`${API_BASE}/discrepancies${query ? `?${query}` : ''}`, { cache: 'no-store' });
  return parseResponse<DiscrepancyListData>(res);
}

export async function resolveDiscrepancy(
  id: string,
  payload: { status: 'resolved' | 'ignored'; resolution_note: string; resolved_by?: string | null },
) {
  const res = await fetch(`${API_BASE}/discrepancies/${id}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(res);
}

export async function getKiotVietStatus(): Promise<KiotVietStatus> {
  const res = await fetch(`${API_BASE}/integrations/kiotviet/status`, { cache: 'no-store' });
  return parseResponse<KiotVietStatus>(res);
}

export async function getHistory(params: URLSearchParams): Promise<HistoryResponseData> {
  const res = await fetch(`${API_BASE}/history?${params.toString()}`, { cache: 'no-store' });
  return parseResponse<HistoryResponseData>(res);
}

export async function getHistoryById(id: string): Promise<HistoryItem> {
  const res = await fetch(`${API_BASE}/history/${id}`, { cache: 'no-store' });
  return parseResponse<HistoryItem>(res);
}

export async function getStats(): Promise<StatsData> {
  const res = await fetch(`${API_BASE}/stats`, { cache: 'no-store' });
  return parseResponse<StatsData>(res);
}

export function downloadExportCsv(filters?: Record<string, string>): void {
  const params = new URLSearchParams(filters);
  window.open(`${API_BASE}/export/csv?${params.toString()}`, '_blank');
}

export function buildImageUrl(path?: string | null): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${API_BASE}/images/object/${path}`;
}
