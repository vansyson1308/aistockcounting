import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ScanPage from '@/app/scan/page';
import { createAuditScan, getTrace, runAgent } from '@/lib/api';
import { ScanCreateData, ScanSession, TraceStep } from '@/types';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    createAuditScan: vi.fn(),
    runAgent: vi.fn(),
    getTrace: vi.fn(),
  };
});
vi.mock('@/lib/image-compress', () => ({ compressImage: async (f: File) => f }));

const mockCreate = vi.mocked(createAuditScan);
const mockRun = vi.mocked(runAgent);
const mockTrace = vi.mocked(getTrace);

function makeScan(overrides: Partial<ScanSession> = {}): ScanSession {
  return {
    id: 'scan-1',
    tenant_key: 'default',
    branch_code: 'MAIN',
    tray_code: 'RING-A',
    image_path: 'uploads/a.jpg',
    detected_count: 0,
    final_count: 0,
    status: 'pending_review',
    agent_decision: null,
    attempt: 0,
    created_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

const qualityStep: TraceStep = {
  seq: 1,
  step_no: 1,
  tool: 'assess_quality',
  inputs: {},
  outputs: { score: 0.2, flags: ['blur'] },
  evidence_key: null,
  evidence_url: null,
  decision: 'request_recapture',
  reason: 'Blur variance 40 < 80: the photo is too blurry to count',
  latency_ms: 20,
  planner: 'deterministic',
};

const terminalStep: TraceStep = {
  ...qualityStep,
  seq: 2,
  step_no: 0,
  tool: 'render_evidence',
  outputs: { boxes: 0 },
  evidence_url: '/api/v1/images/object/evidence/r1/final.jpg',
  reason: 'Hold the phone steady and retake the photo from directly above the tray.',
};

beforeEach(() => {
  // jsdom implements neither of these.
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:preview' }));
  mockCreate.mockReset();
  mockRun.mockReset();
  mockTrace.mockReset();
});

afterEach(() => cleanup());

async function selectPhotoAndStart() {
  fireEvent.change(screen.getByLabelText(/tray code/i), { target: { value: 'RING-A' } });
  const file = new File(['x'], 'tray.jpg', { type: 'image/jpeg' });
  await act(async () => {
    fireEvent.change(screen.getByLabelText(/or upload a photo/i), { target: { files: [file] } });
  });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /count this tray|count retaken photo/i }));
  });
}

describe('ScanPage agent flow', () => {
  it('uploads without the agent, shows live steps, then a retake card linked to the scan', async () => {
    mockCreate.mockResolvedValue({ scan: makeScan(), discrepancy: null, agent: null });
    let finishRun: (data: ScanCreateData) => void = () => {};
    mockRun.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishRun = resolve;
        })
    );
    mockTrace.mockResolvedValue({
      scan: makeScan({ status: 'agent_running' }),
      latest_run_id: null,
      steps: [],
      runs: [],
      live: { run_id: 'r1', running: true, steps: [qualityStep], t: 0 },
    });

    render(<ScanPage />);
    await selectPhotoAndStart();

    expect(mockCreate).toHaveBeenCalledWith(
      expect.any(File),
      expect.objectContaining({ trayCode: 'RING-A', runAgent: false, parentScanId: undefined })
    );
    expect(mockRun).toHaveBeenCalledWith('scan-1');
    expect(await screen.findByText(qualityStep.reason)).toBeInTheDocument();
    expect(screen.getByTestId('timeline-pending')).toBeInTheDocument();

    await act(async () => {
      finishRun({
        scan: makeScan({
          status: 'needs_recapture',
          agent_decision: 'request_recapture',
          attempt: 1,
        }),
        discrepancy: null,
        agent: {
          run_id: 'r1',
          decision: 'request_recapture',
          code: 'blur',
          reason: terminalStep.reason,
          instruction: terminalStep.reason,
          count: null,
          single_shot_count: null,
          steps_used: 1,
          elapsed_ms: 40,
          planner: 'deterministic',
          planner_fallbacks: 0,
          evidence_key: 'evidence/r1/final.jpg',
          uncertain_regions: [],
          changed_regions: [],
          status: 'needs_recapture',
          trace: [qualityStep, terminalStep],
        },
      });
    });

    const card = screen.getByRole('region', { name: 'Please take the photo again' });
    expect(card).toHaveTextContent(terminalStep.reason);
    expect(screen.queryByTestId('timeline-pending')).not.toBeInTheDocument();
    const polls = mockTrace.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'Retake photo' }));
    expect(screen.getByRole('note')).toHaveTextContent('Retaking the photo');

    mockCreate.mockResolvedValueOnce({
      scan: makeScan({ id: 'scan-2', parent_scan_id: 'scan-1', attempt: 2 }),
      discrepancy: null,
      agent: null,
    });
    mockRun.mockResolvedValueOnce({
      scan: makeScan({
        id: 'scan-2',
        status: 'reviewed',
        agent_decision: 'auto_accept',
        agent_count: 12,
        final_count: 12,
        expected_count: 12,
        variance_count: 0,
      }),
      discrepancy: null,
      agent: null,
    });
    await selectPhotoAndStart();

    expect(mockCreate).toHaveBeenLastCalledWith(
      expect.any(File),
      expect.objectContaining({ parentScanId: 'scan-1', runAgent: false })
    );
    expect(await screen.findByRole('heading', { name: 'Count matches POS' })).toBeInTheDocument();
    // Polling stopped after the first run resolved (the second resolved immediately).
    await waitFor(() => expect(mockTrace.mock.calls.length).toBeLessThanOrEqual(polls + 1));
  });

  it('links escalated scans to the review page', async () => {
    mockCreate.mockResolvedValue({ scan: makeScan(), discrepancy: null, agent: null });
    mockTrace.mockResolvedValue({
      scan: makeScan(),
      latest_run_id: null,
      steps: [],
      runs: [],
      live: null,
    });
    mockRun.mockResolvedValueOnce({
      scan: makeScan({
        status: 'awaiting_approval',
        agent_decision: 'escalate',
        agent_count: 23,
        expected_count: 25,
        variance_count: -2,
        agent_reason: 'Count 23 differs from POS 25 after recount',
      }),
      discrepancy: null,
      agent: null,
    });

    render(<ScanPage />);
    await selectPhotoAndStart();

    expect(
      await screen.findByRole('heading', { name: 'A manager needs to approve this count' })
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open review' })).toHaveAttribute(
      'href',
      '/review/scan-1'
    );
    expect(screen.getByText('Count 23 differs from POS 25 after recount')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Manual review' })).not.toBeInTheDocument();
  });
});
