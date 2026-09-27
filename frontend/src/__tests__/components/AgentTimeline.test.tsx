import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import AgentTimeline from '@/components/AgentTimeline';
import { TraceStep } from '@/types';

afterEach(() => cleanup());

function step(overrides: Partial<TraceStep>): TraceStep {
  return {
    seq: 1,
    step_no: 1,
    tool: 'assess_quality',
    inputs: {},
    outputs: {},
    evidence_key: null,
    evidence_url: null,
    decision: 'assess_quality',
    reason: '',
    latency_ms: 12,
    planner: 'deterministic',
    ...overrides,
  };
}

const steps: TraceStep[] = [
  step({
    seq: 1,
    step_no: 1,
    tool: 'assess_quality',
    outputs: {
      score: 0.82,
      flags: ['glare'],
      blur_var: 412.3,
      glare_ratio: 0.03,
      tray_coverage: 0.7,
    },
    reason: 'Glare ratio 0.03 > 0.01: inpaint highlights before counting',
    latency_ms: 35,
  }),
  step({
    seq: 2,
    step_no: 2,
    tool: 'detect',
    outputs: { count: 24, mean_conf: 0.91, uncertain: 2 },
    reason: '2 low-confidence detections: tile and recount',
    evidence_key: 'evidence/run/detect.jpg',
    evidence_url: '/api/v1/images/object/evidence/run/detect.jpg',
    latency_ms: 1520,
    planner: 'bedrock',
  }),
  step({
    seq: 3,
    step_no: 0,
    tool: 'render_evidence',
    decision: 'escalate',
    outputs: { boxes: 24, uncertain_regions: 1, changed_regions: 0 },
    reason: 'Count 24 differs from POS 25 after recount',
  }),
];

describe('AgentTimeline', () => {
  it('renders every step with its label, numbers, reason and latency in a live list', () => {
    render(<AgentTimeline steps={steps} />);

    const list = screen.getByRole('list', { name: 'Agent steps' });
    expect(list.closest('[aria-live="polite"]')).not.toBeNull();
    const items = within(list)
      .getAllByRole('listitem')
      .filter((li) => li.parentElement === list);
    expect(items).toHaveLength(3);

    expect(screen.getByRole('heading', { name: 'Check photo quality' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Count items' })).toBeInTheDocument();
    expect(
      screen.getByText('Glare ratio 0.03 > 0.01: inpaint highlights before counting')
    ).toBeInTheDocument();
    expect(screen.getByText('glare')).toBeInTheDocument();
    const detect = screen.getByRole('article', { name: '2. Count items' });
    expect(within(detect).getByText('Count').nextSibling).toHaveTextContent('24');
    expect(within(detect).getByText('Mean confidence').nextSibling).toHaveTextContent('91%');
    expect(screen.getByText('1.5 s')).toBeInTheDocument();
    expect(screen.getByText('35 ms')).toBeInTheDocument();
    expect(screen.getByText('Escalated to a human')).toBeInTheDocument();
    expect(screen.getByText('Bedrock planner')).toBeInTheDocument();
    expect(screen.queryByTestId('timeline-pending')).not.toBeInTheDocument();
  });

  it('opens evidence full size in a dialog and closes it with Escape', async () => {
    const user = userEvent.setup();
    render(<AgentTimeline steps={steps} />);

    const thumb = screen.getByRole('button', { name: /view full size: count items evidence/i });
    const img = within(thumb).getByRole('img');
    expect(img).toHaveAttribute('src', '/api/v1/images/object/evidence/run/detect.jpg');
    expect(img.getAttribute('alt')).toMatch(/count items/i);

    await user.click(thumb);
    const dialog = screen.getByRole('dialog', { name: 'Count items evidence' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(within(dialog).getByRole('button', { name: 'Close' })).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows a pending item with a spinner while the agent runs', () => {
    render(<AgentTimeline steps={steps.slice(0, 1)} running />);
    const pending = screen.getByTestId('timeline-pending');
    expect(pending).toHaveTextContent('Agent is choosing the next step…');
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('shows a starting item when running with no steps yet, and an empty state otherwise', () => {
    const { rerender } = render(<AgentTimeline steps={[]} running />);
    expect(screen.getByTestId('timeline-pending')).toHaveTextContent('Starting the agent…');

    rerender(<AgentTimeline steps={[]} />);
    expect(screen.queryByRole('list', { name: 'Agent steps' })).not.toBeInTheDocument();
    expect(screen.getByText('No agent steps recorded for this scan yet.')).toBeInTheDocument();
  });

  it('marks planner fallback steps visibly', () => {
    render(
      <AgentTimeline
        steps={[
          step({
            seq: 4,
            step_no: 0,
            tool: 'planner',
            decision: 'planner_fallback',
            outputs: { error: 'timeout' },
            reason: 'bedrock planner failed; deterministic controller takes over.',
            planner: 'bedrock',
          }),
        ]}
      />
    );
    expect(screen.getByRole('heading', { name: 'Planner fallback' })).toBeInTheDocument();
    expect(screen.getByText('Fallback')).toBeInTheDocument();
    expect(screen.getByText('Planner error: timeout')).toBeInTheDocument();
  });
});
