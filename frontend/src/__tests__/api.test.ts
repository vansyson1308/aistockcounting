import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ApiClientError, buildImageUrl, getStats, saveRecord } from '@/lib/api';

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
        data: { total_records: 5, avg_detected_count: 3.0, avg_manual_count: 3.0, ai_correct_rate: 0.8 },
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
      expect.objectContaining({ method: 'POST' }),
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
    expect(buildImageUrl('uploads/test.jpg')).toBe('uploads/test.jpg');
  });
});
