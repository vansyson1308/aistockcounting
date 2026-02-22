import { CountResult, HistoryItem, HistoryResponseData, SavePayload, StatsData } from '@/types';

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

export function buildImageUrl(path?: string | null): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return path;
}
