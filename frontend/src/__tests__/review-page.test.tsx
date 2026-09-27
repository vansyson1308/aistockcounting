import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ReviewPage from '@/app/review/[id]/page';
import { getTrace } from '@/lib/api';
import { ScanSession, TraceStep } from '@/types';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, getTrace: vi.fn() };
});

const mockTrace = vi.mocked(getTrace);

function step(overrides: Partial<TraceStep>): TraceStep {
  return {
    seq: 1,
    step_no: 1,
    tool: 'detect',
    inputs: {},
    outputs: {},
    evidence_key: null,
    evidence_url: null,
    decision: 'detect',
    reason: '',
    latency_ms: 10,
    planner: 'deterministic',
    ...overrides,
  };
}

const scan: ScanSession = {
  id: 'scan-9',
  tenant_key: 'default',
  branch_code: 'HN-01',
  tray_code: 'RING-A',
  image_path: 'uploads/a.jpg',
  detected_count: 23,
  final_count: 23,
  expected_count: 25,
  variance_count: -2,
  status: 'awaiting_approval',
  agent_decision: 'escalate',
  agent_count: 23,
  agent_reason: 'Count 23 differs from POS 25 after recount',
  created_at: '2026-09-01T00:00:00Z',
};

beforeEach(() => mockTrace.mockReset());
afterEach(() => cleanup());

describe('ReviewPage', () => {
  it('shows counts, before/after evidence, uncertain regions, the diff and the approval panel', async () => {
    mockTrace.mockResolvedValueOnce({
      scan,
      latest_run_id: 'r1',
      runs: [{ run_id: 'r1', steps: [] }],
      live: null,
      steps: [
        step({
          seq: 1,
          tool: 'zoom_recount',
          outputs: {
            count: 23,
            count_before: 22,
            regions: [
              { rect: [10, 20, 30, 40], before: 1, after: 2, resolved: true },
              { rect: [50, 60, 30, 40], before: 0, after: 1, resolved: false },
            ],
          },
          evidence_url: '/api/v1/images/object/evidence/r1/zoom.jpg',
          reason: '2 uncertain regions: zoom in and recount',
        }),
        step({
          seq: 2,
          tool: 'compare_previous',
          outputs: {
            aligned: true,
            inliers: 120,
            changed_ratio: 0.04,
            changed_regions: [[1, 2, 3, 4]],
          },
          evidence_url: '/api/v1/images/object/evidence/r1/diff.jpg',
          reason: '1 changed region vs the last approved photo',
        }),
        step({
          seq: 3,
          step_no: 0,
          tool: 'render_evidence',
          decision: 'escalate',
          evidence_url: '/api/v1/images/object/evidence/r1/final.jpg',
          reason: 'Count 23 differs from POS 25 after recount',
        }),
      ],
    });

    render(<ReviewPage params={{ id: 'scan-9' }} />);

    expect(await screen.findByRole('heading', { name: 'HN-01 / RING-A' })).toBeInTheDocument();
    expect(mockTrace).toHaveBeenCalledWith('scan-9');
    expect(screen.getByText('-2')).toBeInTheDocument();

    const beforeAfter = screen.getByRole('region', { name: 'Before / after' });
    expect(within(beforeAfter).getByAltText('Original photo of tray RING-A')).toHaveAttribute(
      'src',
      expect.stringContaining('/images/object/uploads/a.jpg')
    );
    expect(within(beforeAfter).getByAltText(/agent evidence sheet/i)).toHaveAttribute(
      'src',
      expect.stringContaining('/api/v1/images/object/evidence/r1/final.jpg')
    );

    const uncertain = screen.getByRole('region', { name: 'Uncertain regions' });
    expect(within(uncertain).getByText('Resolved')).toBeInTheDocument();
    expect(within(uncertain).getByText('Unresolved')).toBeInTheDocument();

    const diff = screen.getByRole('region', { name: 'Diff vs last approved photo' });
    expect(within(diff).getByAltText(/change heatmap/i)).toBeInTheDocument();

    expect(screen.getByRole('list', { name: 'Agent steps' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve agent count (23)' })).toBeEnabled();
  });

  it('shows an error when the scan cannot be loaded', async () => {
    const { ApiClientError } = await import('@/lib/api');
    mockTrace.mockRejectedValueOnce(new ApiClientError('SCAN_NOT_FOUND', 'Scan not found'));

    render(<ReviewPage params={{ id: 'missing' }} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Scan not found');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
