import {
  ApprovePayload,
  ApproveResult,
  CountResult,
  DiscrepancyListData,
  HistoryItem,
  HistoryResponseData,
  KiotVietStatus,
  ReviewScanPayload,
  SavePayload,
  ScanCreateData,
  StatsData,
  TraceData,
} from '@/types';

/**
 * Base URL of the backend API. Production serves the frontend and the API on one origin
 * (nginx / CloudFront), so the default is origin-relative.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1';

export class ApiClientError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

/** FastAPI's default validation errors use `{detail: string | [{msg}]}` instead of the envelope. */
function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown } | null;
    if (first && typeof first.msg === 'string') return first.msg;
  }
  return null;
}

async function parseResponse<T>(res: Response): Promise<T> {
  let payload;
  try {
    payload = await res.json();
  } catch {
    throw new ApiClientError(
      `HTTP_${res.status ?? 0}`,
      `Unexpected response from the server (HTTP ${res.status ?? 'error'}).`
    );
  }
  if (!res.ok || payload.success === false) {
    throw new ApiClientError(
      payload?.error?.code || (res.status === 422 ? 'VALIDATION_ERROR' : 'API_ERROR'),
      payload?.error?.message || detailMessage(payload?.detail) || 'Unexpected server error.'
    );
  }
  return payload.data as T;
}

export async function countItems(
  file: File,
  trayId?: string,
  staffId?: string
): Promise<CountResult> {
  const formData = new FormData();
  formData.append('image', file);
  if (trayId) formData.append('tray_id', trayId);
  if (staffId) formData.append('staff_id', staffId);

  const res = await fetch(`${API_BASE}/count-items`, { method: 'POST', body: formData });
  return parseResponse<CountResult>(res);
}

export async function saveRecord(
  payload: SavePayload
): Promise<{ id: string; created_at: string }> {
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
    /** Id of the scan whose agent asked for this re-shot. */
    parentScanId?: string | null;
    /** Run TrayAgent inside the upload request (server default: true). */
    runAgent?: boolean;
  }
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
  if (payload.parentScanId) formData.append('parent_scan_id', payload.parentScanId);
  if (payload.runAgent !== undefined) formData.append('run_agent', String(payload.runAgent));

  const res = await fetch(`${API_BASE}/scans`, { method: 'POST', body: formData });
  return parseResponse<ScanCreateData>(res);
}

export async function reviewAuditScan(
  id: string,
  payload: ReviewScanPayload
): Promise<ScanCreateData> {
  const res = await fetch(`${API_BASE}/scans/${id}/review`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse<ScanCreateData>(res);
}

/** Runs TrayAgent synchronously on a stored scan (can take up to ~20 s). */
export async function runAgent(id: string): Promise<ScanCreateData> {
  const res = await fetch(`${API_BASE}/scans/${encodeURIComponent(id)}/agent-run`, {
    method: 'POST',
  });
  return parseResponse<ScanCreateData>(res);
}

/** Persisted agent trace plus the in-process live progress of a running agent. */
export async function getTrace(id: string): Promise<TraceData> {
  const res = await fetch(`${API_BASE}/scans/${encodeURIComponent(id)}/trace`, {
    cache: 'no-store',
  });
  return parseResponse<TraceData>(res);
}

/** Human approval gate for scans the agent escalated (`awaiting_approval`). */
export async function approveScan(id: string, payload: ApprovePayload): Promise<ApproveResult> {
  const res = await fetch(`${API_BASE}/scans/${encodeURIComponent(id)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse<ApproveResult>(res);
}

export async function getDiscrepancies(params?: URLSearchParams): Promise<DiscrepancyListData> {
  const query = params?.toString();
  const res = await fetch(`${API_BASE}/discrepancies${query ? `?${query}` : ''}`, {
    cache: 'no-store',
  });
  return parseResponse<DiscrepancyListData>(res);
}

export async function resolveDiscrepancy(
  id: string,
  payload: { status: 'resolved' | 'ignored'; resolution_note: string; resolved_by?: string | null }
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

/**
 * Resolves an origin-relative evidence URL (it already contains the API prefix, e.g.
 * `/api/v1/images/object/evidence/x.jpg`) against the origin of `apiBase`. A relative
 * `apiBase` means the API shares the site origin, so the URL is used as is.
 */
export function resolveEvidenceSrc(url: string | null | undefined, apiBase: string): string {
  if (!url) return '';
  if (/^(https?:)?\/\//i.test(url) || url.startsWith('data:') || url.startsWith('blob:')) {
    return url;
  }
  const path = url.startsWith('/') ? url : `/${url}`;
  if (/^https?:\/\//i.test(apiBase)) {
    try {
      return `${new URL(apiBase).origin}${path}`;
    } catch {
      return path;
    }
  }
  return path;
}

export function evidenceSrc(url: string | null | undefined): string {
  return resolveEvidenceSrc(url, API_BASE);
}
