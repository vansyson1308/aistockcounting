import { AgentDecision, TraceStep } from '@/types';

export const TOOL_LABELS: Record<string, string> = {
  assess_quality: 'Check photo quality',
  reduce_glare: 'Reduce glare',
  rectify_tray: 'Straighten tray',
  detect: 'Count items',
  tile_detect: 'Recount in tiles',
  zoom_recount: 'Zoom into uncertain areas',
  compare_previous: 'Compare with last approved photo',
  render_evidence: 'Decision and evidence',
  planner: 'Planner fallback',
};

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool.replace(/_/g, ' ');
}

export const DECISION_LABELS: Record<AgentDecision, string> = {
  auto_accept: 'Auto-accepted',
  request_recapture: 'Retake requested',
  escalate: 'Escalated to a human',
};

export function decisionLabel(decision: string | null | undefined): string {
  if (!decision) return 'No decision';
  return DECISION_LABELS[decision as AgentDecision] ?? decision.replace(/_/g, ' ');
}

/** Tailwind classes for a decision badge; all pairs meet WCAG AA contrast. */
export function decisionBadgeClass(decision: string | null | undefined): string {
  switch (decision) {
    case 'auto_accept':
      return 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200';
    case 'request_recapture':
      return 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200';
    case 'escalate':
      return 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-700 dark:bg-rose-950/40 dark:text-rose-200';
    default:
      return 'border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200';
  }
}

export const STATUS_LABELS: Record<string, string> = {
  pending_review: 'Pending review',
  reviewed: 'Reviewed',
  discrepancy_open: 'Discrepancy open',
  needs_recapture: 'Needs retake',
  awaiting_approval: 'Awaiting approval',
  superseded: 'Superseded by a retake',
  agent_running: 'Agent running',
  ignored: 'Ignored',
};

export function statusLabel(status: string | null | undefined): string {
  if (!status) return 'Unknown';
  return STATUS_LABELS[status] ?? status.replace(/_/g, ' ');
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Tool outputs report regions either as a list of rects or as a plain count. */
export function countOf(value: unknown): number | null {
  if (Array.isArray(value)) return value.length;
  return num(value);
}

function fixed(value: unknown, digits: number): string | null {
  const n = num(value);
  return n === null ? null : n.toFixed(digits);
}

function percent(value: unknown): string | null {
  const n = num(value);
  if (n === null) return null;
  const pct = n * 100;
  return `${pct < 10 && pct > 0 ? pct.toFixed(1) : Math.round(pct)}%`;
}

export type StepMetric = { label: string; value: string };

/** The few numbers per tool that explain what the agent observed. */
export function stepMetrics(step: TraceStep): StepMetric[] {
  const o = step.outputs ?? {};
  const out: StepMetric[] = [];
  const push = (label: string, value: string | number | null | undefined) => {
    if (value === null || value === undefined || value === '') return;
    out.push({ label, value: String(value) });
  };

  switch (step.tool) {
    case 'assess_quality':
      push('Quality', fixed(o.score, 2));
      push('Sharpness', fixed(o.blur_var, 0));
      push('Glare', percent(o.glare_ratio));
      push('Tray coverage', percent(o.tray_coverage));
      break;
    case 'reduce_glare':
      push('Glare before', percent(o.glare_before));
      push('Glare after', percent(o.glare_after));
      push('Inpainted', percent(o.inpainted_frac));
      break;
    case 'rectify_tray':
      if (typeof o.found === 'boolean') push('Tray found', o.found ? 'yes' : 'no');
      push('Method', typeof o.method === 'string' ? o.method : null);
      break;
    case 'detect':
      push('Count', num(o.count));
      push('Mean confidence', percent(o.mean_conf));
      push('Uncertain', countOf(o.uncertain));
      break;
    case 'tile_detect': {
      push('Count', num(o.count));
      const grid = Array.isArray(o.grid) ? o.grid.filter((g) => typeof g === 'number') : [];
      push('Grid', grid.length === 2 ? `${grid[0]}×${grid[1]}` : null);
      push('Disagreeing cells', countOf(o.disagreement_cells));
      break;
    }
    case 'zoom_recount': {
      const before = num(o.count_before);
      const after = num(o.count);
      push('Count', before !== null && after !== null ? `${before} → ${after}` : after);
      const regions = zoomRegions(step);
      if (regions.length > 0) {
        push('Resolved', `${regions.filter((r) => r.resolved).length}/${regions.length}`);
      }
      break;
    }
    case 'compare_previous':
      if (typeof o.aligned === 'boolean') push('Aligned', o.aligned ? 'yes' : 'no');
      push('Inliers', num(o.inliers));
      push('Changed area', percent(o.changed_ratio));
      push('Changed regions', countOf(o.changed_regions));
      break;
    case 'render_evidence':
      push('Items boxed', countOf(o.boxes));
      push('Uncertain regions', countOf(o.uncertain_regions));
      push('Changed regions', countOf(o.changed_regions));
      break;
    default:
      break;
  }
  return out;
}

/** Quality flags reported by `assess_quality`, e.g. `blur`, `glare`. */
export function qualityFlags(step: TraceStep): string[] {
  const flags = step.outputs?.flags;
  return Array.isArray(flags) ? flags.filter((f): f is string => typeof f === 'string') : [];
}

export type ZoomRegion = {
  rect: number[];
  before: number | null;
  after: number | null;
  resolved: boolean;
};

export function zoomRegions(step: TraceStep | null | undefined): ZoomRegion[] {
  const regions = step?.outputs?.regions;
  if (!Array.isArray(regions)) return [];
  return regions
    .filter((r): r is Record<string, unknown> => typeof r === 'object' && r !== null)
    .map((r) => ({
      rect: Array.isArray(r.rect) ? r.rect.filter((v): v is number => typeof v === 'number') : [],
      before: num(r.before),
      after: num(r.after),
      resolved: r.resolved === true,
    }));
}

/** The last step of a run with this tool (a run may call a tool more than once). */
export function lastStep(steps: TraceStep[], tool: string): TraceStep | null {
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    if (steps[i].tool === tool) return steps[i];
  }
  return null;
}

/** The terminal `render_evidence` step: its decision is the action, its reason the explanation. */
export function terminalStep(steps: TraceStep[]): TraceStep | null {
  return lastStep(steps, 'render_evidence');
}
