import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  API_BASE,
  ApiClientError,
  approveScan,
  buildImageUrl,
  createAuditScan,
  evidenceSrc,
  getDiscrepancies,
  getStats,
  getTrace,
  resolveEvidenceSrc,
  reviewAuditScan,
  runAgent,
  saveRecord,
} from '@/lib/api';

// Mock global fetch
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

beforeEach(() => {
  mockFetch.mockReset();
});

describe('parseResponse (via public API)', () => {
  it('returns data on successful response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          total_records: 5,
          avg_detected_count: 3.0,
          avg_manual_count: 3.0,
          ai_correct_rate: 0.8,
        },
      }),
    });

    const result = await getStats();
    expect(result.total_records).toBe(5);
  });

  it('throws ApiClientError on failure response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        success: false,
        error: { code: 'VALIDATION_ERROR', message: 'Invalid request.' },
      }),
    });

    await expect(getStats()).rejects.toThrow(ApiClientError);
    await mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        success: false,
        error: { code: 'TEST', message: 'Test error' },
      }),
    });
    try {
      await getStats();
    } catch (e) {
      expect(e).toBeInstanceOf(ApiClientError);
      expect((e as ApiClientError).code).toBe('TEST');
    }
  });

  it('throws ApiClientError when success is false even with ok status', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: false,
        error: { code: 'MODEL_ERROR', message: 'Model failed' },
      }),
    });

    await expect(getStats()).rejects.toThrow('Model failed');
  });
});

describe('saveRecord', () => {
  it('sends JSON POST and returns id', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        data: { id: 'abc-123', created_at: '2026-03-01T00:00:00' },
      }),
    });

    const result = await saveRecord({
      image_path: 'uploads/test.jpg',
      detected_count: 5,
      boxes_json: [],
    });
    expect(result.id).toBe('abc-123');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/save'),
      expect.objectContaining({ method: 'POST' })
    );
  });
});

describe('buildImageUrl', () => {
  it('returns empty string for null/undefined', () => {
    expect(buildImageUrl(null)).toBe('');
    expect(buildImageUrl(undefined)).toBe('');
    expect(buildImageUrl('')).toBe('');
  });

  it('returns http URLs as-is', () => {
    expect(buildImageUrl('http://example.com/img.jpg')).toBe('http://example.com/img.jpg');
    expect(buildImageUrl('https://example.com/img.jpg')).toBe('https://example.com/img.jpg');
  });

  it('returns relative paths as-is', () => {
    expect(buildImageUrl('uploads/test.jpg')).toContain('/images/object/uploads/test.jpg');
  });
});

describe('truth-layer APIs', () => {
  it('creates an audit scan as multipart form data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        data: { scan: { id: 'scan-1', status: 'pending_review' }, discrepancy: null },
      }),
    });

    const file = new File(['x'], 'tray.jpg', { type: 'image/jpeg' });
    const result = await createAuditScan(file, {
      branchCode: 'HN-01',
      trayCode: 'RING-A',
      expectedCount: 12,
    });

    expect(result.scan.id).toBe('scan-1');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/scans'),
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) })
    );
  });

  it('reviews a scan and fetches the discrepancy inbox', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          data: { scan: { id: 'scan-1', status: 'reviewed' }, discrepancy: null },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, data: { items: [], total: 0 } }),
      });

    await reviewAuditScan('scan-1', { manual_count: 12, expected_count: 12 });
    const inbox = await getDiscrepancies(new URLSearchParams({ status: 'open' }));

    expect(inbox.total).toBe(0);
    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/scans/scan-1/review'),
      expect.objectContaining({ method: 'PATCH' })
    );
  });
});

function ok(data: unknown) {
  return { ok: true, status: 200, json: async () => ({ success: true, data }) };
}

describe('API_BASE', () => {
  it('defaults to the same-origin API prefix', () => {
    expect(API_BASE).toBe(process.env.NEXT_PUBLIC_API_BASE || '/api/v1');
  });
});

describe('evidenceSrc', () => {
  const url = '/api/v1/images/object/evidence/run-1/final.jpg';

  it('returns an empty string for missing URLs', () => {
    expect(resolveEvidenceSrc(null, '/api/v1')).toBe('');
    expect(resolveEvidenceSrc(undefined, 'http://api.test/api/v1')).toBe('');
    expect(evidenceSrc('')).toBe('');
  });

  it('uses the origin-relative URL as is when the API base is relative', () => {
    expect(resolveEvidenceSrc(url, '/api/v1')).toBe(url);
    expect(resolveEvidenceSrc('api/v1/images/object/e.jpg', '/api/v1')).toBe(
      '/api/v1/images/object/e.jpg'
    );
  });

  it('prefixes the origin of an absolute API base without duplicating the API prefix', () => {
    expect(resolveEvidenceSrc(url, 'http://localhost:8000/api/v1')).toBe(
      `http://localhost:8000${url}`
    );
    expect(resolveEvidenceSrc(url, 'https://api.example.com/api/v1/')).toBe(
      `https://api.example.com${url}`
    );
  });

  it('keeps absolute URLs unchanged', () => {
    const absolute = 'https://cdn.example.com/evidence/x.jpg';
    expect(resolveEvidenceSrc(absolute, 'http://localhost:8000/api/v1')).toBe(absolute);
  });

  it('resolves against the configured API base', () => {
    expect(evidenceSrc(url)).toBe(resolveEvidenceSrc(url, API_BASE));
  });
});

describe('TrayAgent APIs', () => {
  it('sends parent_scan_id and run_agent when creating a re-shot scan', async () => {
    mockFetch.mockResolvedValueOnce(ok({ scan: { id: 'scan-2' }, discrepancy: null, agent: null }));

    const file = new File(['x'], 'tray.jpg', { type: 'image/jpeg' });
    await createAuditScan(file, {
      branchCode: 'HN-01',
      trayCode: 'RING-A',
      staffId: 'S-1',
      expectedCount: 12,
      unitValue: 1500000,
      parentScanId: '7d3c1a52-0000-4000-8000-000000000001',
      runAgent: false,
    });

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe(`${API_BASE}/scans`);
    const body = init.body as FormData;
    expect(body.get('image')).toBeInstanceOf(File);
    expect(body.get('branch_code')).toBe('HN-01');
    expect(body.get('tray_code')).toBe('RING-A');
    expect(body.get('staff_id')).toBe('S-1');
    expect(body.get('expected_count')).toBe('12');
    expect(body.get('unit_value')).toBe('1500000');
    expect(body.get('parent_scan_id')).toBe('7d3c1a52-0000-4000-8000-000000000001');
    expect(body.get('run_agent')).toBe('false');
  });

  it('omits parent_scan_id and run_agent when not given', async () => {
    mockFetch.mockResolvedValueOnce(ok({ scan: { id: 'scan-3' }, discrepancy: null, agent: null }));

    const file = new File(['x'], 'tray.jpg', { type: 'image/jpeg' });
    await createAuditScan(file, { branchCode: 'HN-01', trayCode: 'RING-A' });

    const body = mockFetch.mock.calls[0][1].body as FormData;
    expect(body.has('parent_scan_id')).toBe(false);
    expect(body.has('run_agent')).toBe(false);
    expect(body.has('expected_count')).toBe(false);
  });

  it('runs the agent and reads the trace', async () => {
    mockFetch
      .mockResolvedValueOnce(
        ok({ scan: { id: 'scan-1' }, discrepancy: null, agent: { decision: 'auto_accept' } })
      )
      .mockResolvedValueOnce(
        ok({ scan: { id: 'scan-1' }, latest_run_id: 'r1', steps: [], runs: [], live: null })
      );

    const run = await runAgent('scan-1');
    const trace = await getTrace('scan-1');

    expect(run.agent?.decision).toBe('auto_accept');
    expect(trace.latest_run_id).toBe('r1');
    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      `${API_BASE}/scans/scan-1/agent-run`,
      expect.objectContaining({ method: 'POST' })
    );
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      `${API_BASE}/scans/scan-1/trace`,
      expect.objectContaining({ cache: 'no-store' })
    );
  });

  it('posts the approval payload as JSON', async () => {
    mockFetch.mockResolvedValueOnce(
      ok({ scan: { id: 'scan-1', status: 'reviewed' }, discrepancy: null })
    );

    const result = await approveScan('scan-1', {
      approver_id: 'MGR-1',
      decision: 'correct',
      corrected_count: 25,
      note: 'Recounted by hand',
    });

    expect(result.scan.status).toBe('reviewed');
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe(`${API_BASE}/scans/scan-1/approve`);
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body)).toEqual({
      approver_id: 'MGR-1',
      decision: 'correct',
      corrected_count: 25,
      note: 'Recounted by hand',
    });
  });

  it('surfaces the approval gate error code', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({
        success: false,
        error: { code: 'NOT_AWAITING_APPROVAL', message: 'Only escalated scans can be approved.' },
      }),
    });

    await expect(
      approveScan('scan-1', { approver_id: 'MGR-1', decision: 'approve' })
    ).rejects.toMatchObject({ code: 'NOT_AWAITING_APPROVAL' });
  });

  it('reports FastAPI validation details and non-JSON responses as ApiClientError', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => ({ detail: [{ msg: 'Field required' }] }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: async () => {
          throw new SyntaxError('Unexpected token <');
        },
      });

    await expect(
      approveScan('scan-1', { approver_id: '', decision: 'approve' })
    ).rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'Field required' });
    await expect(runAgent('scan-1')).rejects.toMatchObject({ code: 'HTTP_502' });
  });
});
