import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApprovalPanel from '@/components/ApprovalPanel';
import { ApiClientError, approveScan } from '@/lib/api';
import { useSessionStore } from '@/store/useSessionStore';
import { ScanSession } from '@/types';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, approveScan: vi.fn() };
});

const mockApprove = vi.mocked(approveScan);

function makeScan(overrides: Partial<ScanSession> = {}): ScanSession {
  return {
    id: 'scan-1',
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
    created_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  mockApprove.mockReset();
  useSessionStore.setState({ staffId: '' });
});

afterEach(() => cleanup());

describe('ApprovalPanel', () => {
  it('requires an approver ID before calling the API', async () => {
    const user = userEvent.setup();
    render(<ApprovalPanel scan={makeScan()} />);

    await user.click(screen.getByRole('button', { name: 'Approve agent count (23)' }));

    expect(mockApprove).not.toHaveBeenCalled();
    expect(screen.getByText('Enter your approver ID.')).toBeInTheDocument();
    const approver = screen.getByLabelText(/approver id/i);
    expect(approver).toHaveAttribute('aria-invalid', 'true');
    expect(approver).toHaveFocus();
  });

  it('prefills the approver ID from the session and approves the agent count', async () => {
    useSessionStore.setState({ staffId: 'MGR-7' });
    const result = {
      scan: makeScan({ status: 'discrepancy_open', approved_by: 'MGR-7' }),
      discrepancy: null,
    };
    mockApprove.mockResolvedValueOnce(result);
    const onDecided = vi.fn();
    const user = userEvent.setup();
    render(<ApprovalPanel scan={makeScan()} onDecided={onDecided} />);

    expect(screen.getByLabelText(/approver id/i)).toHaveValue('MGR-7');
    await user.click(screen.getByRole('button', { name: 'Approve agent count (23)' }));

    expect(mockApprove).toHaveBeenCalledWith('scan-1', {
      approver_id: 'MGR-7',
      decision: 'approve',
    });
    await waitFor(() => expect(onDecided).toHaveBeenCalledWith(result));
  });

  it('requires a corrected count for a correction and sends it with the note', async () => {
    mockApprove.mockResolvedValueOnce({
      scan: makeScan({ status: 'reviewed' }),
      discrepancy: null,
    });
    const user = userEvent.setup();
    render(<ApprovalPanel scan={makeScan()} />);

    await user.type(screen.getByLabelText(/approver id/i), 'MGR-1');
    await user.click(screen.getByRole('button', { name: 'Save correction' }));
    expect(mockApprove).not.toHaveBeenCalled();
    expect(screen.getByText(/enter the corrected count/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Corrected count')).toHaveFocus();

    await user.type(screen.getByLabelText('Corrected count'), '25');
    await user.type(screen.getByLabelText(/note/i), 'Two rings under the tray lip');
    await user.click(screen.getByRole('button', { name: 'Save correction' }));

    expect(mockApprove).toHaveBeenCalledWith('scan-1', {
      approver_id: 'MGR-1',
      decision: 'correct',
      corrected_count: 25,
      note: 'Two rings under the tray lip',
    });
  });

  it('sends a rejection with its note', async () => {
    mockApprove.mockResolvedValueOnce({
      scan: makeScan({ status: 'needs_recapture' }),
      discrepancy: null,
    });
    const user = userEvent.setup();
    render(<ApprovalPanel scan={makeScan()} />);

    await user.type(screen.getByLabelText(/approver id/i), 'MGR-1');
    await user.type(screen.getByLabelText(/note/i), 'Tray was not fully in frame');
    await user.click(screen.getByRole('button', { name: 'Reject and request a recount' }));

    expect(mockApprove).toHaveBeenCalledWith('scan-1', {
      approver_id: 'MGR-1',
      decision: 'reject',
      note: 'Tray was not fully in frame',
    });
  });

  it('disables every action while submitting and shows API errors', async () => {
    let rejectCall: (e: unknown) => void = () => {};
    mockApprove.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectCall = reject;
        })
    );
    const user = userEvent.setup();
    render(<ApprovalPanel scan={makeScan()} />);

    await user.type(screen.getByLabelText(/approver id/i), 'MGR-1');
    await user.click(screen.getByRole('button', { name: 'Approve agent count (23)' }));

    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save correction' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject and request a recount' })).toBeDisabled();

    rejectCall(new ApiClientError('NOT_AWAITING_APPROVAL', 'Scan is no longer awaiting approval.'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Scan is no longer awaiting approval.'
    );
    expect(screen.getByRole('button', { name: 'Approve agent count (23)' })).toBeEnabled();
  });

  it('shows the final decision and no actions when the scan is not awaiting approval', () => {
    render(
      <ApprovalPanel
        scan={makeScan({
          status: 'reviewed',
          final_count: 25,
          approved_by: 'MGR-9',
          approved_at: '2026-09-02T10:00:00Z',
        })}
      />
    );

    expect(screen.getByRole('heading', { name: 'Final decision' })).toBeInTheDocument();
    expect(screen.getByText('MGR-9')).toBeInTheDocument();
    expect(screen.getByText('Reviewed')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/approver id/i)).not.toBeInTheDocument();
  });
});
