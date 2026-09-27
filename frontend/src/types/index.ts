export type Box = { x: number; y: number; w: number; h: number; conf: number };

export type ApiError = { code: string; message: string };

export type ApiEnvelope<T> = {
  success: boolean;
  data: T;
};

export type CountResult = {
  image_path: string;
  image_thumbnail?: string | null;
  detected_count: number;
  confidence_avg: number;
  processing_time_ms: number;
  boxes: Box[];
  tray_id?: string | null;
  staff_id?: string | null;
  mock_mode?: boolean;
  model_version?: string;
};

export type SavePayload = {
  image_path: string;
  image_thumbnail?: string | null;
  detected_count: number;
  manual_count?: number | null;
  confidence_avg?: number | null;
  boxes_json: Box[];
  staff_id?: string | null;
  tray_id?: string | null;
  is_ai_correct?: boolean | null;
  notes?: string | null;
};

export type ScanSession = {
  id: string;
  tenant_key: string;
  branch_code: string;
  tray_code: string;
  staff_id?: string | null;
  image_path: string;
  image_thumbnail?: string | null;
  detected_count: number;
  manual_count?: number | null;
  final_count: number;
  expected_count?: number | null;
  variance_count?: number | null;
  variance_value?: number | null;
  confidence_avg?: number | null;
  boxes_json?: Box[] | null;
  quality_score?: number | null;
  quality_flags?: string[] | null;
  is_ai_correct?: boolean | null;
  notes?: string | null;
  status: string;
  model_version?: string | null;
  processing_time_ms?: number | null;
  parent_scan_id?: string | null;
  attempt?: number | null;
  agent_run_id?: string | null;
  agent_decision?: AgentDecision | null;
  agent_count?: number | null;
  agent_reason?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  created_at: string;
};

export type ScanStatus =
  | 'pending_review'
  | 'reviewed'
  | 'discrepancy_open'
  | 'needs_recapture'
  | 'awaiting_approval'
  | 'superseded'
  | 'agent_running'
  | 'ignored';

export type AgentDecision = 'auto_accept' | 'request_recapture' | 'escalate';

export type AgentTool =
  | 'assess_quality'
  | 'reduce_glare'
  | 'rectify_tray'
  | 'detect'
  | 'tile_detect'
  | 'zoom_recount'
  | 'compare_previous'
  | 'render_evidence'
  | 'planner';

export type PlannerName = 'deterministic' | 'bedrock';

/** One tool call (or planner event) recorded by the agent. `outputs` depends on `tool`. */
export type TraceStep = {
  seq: number;
  step_no: number;
  tool: AgentTool | string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  evidence_key: string | null;
  /** Origin-relative URL, e.g. `/api/v1/images/object/evidence/...jpg`. */
  evidence_url: string | null;
  decision: string;
  reason: string;
  latency_ms: number;
  planner: PlannerName | string;
};

export type TraceRun = {
  run_id: string;
  steps: TraceStep[];
};

export type LiveTrace = {
  run_id: string;
  running: boolean;
  steps: TraceStep[];
  t: number;
};

export type TraceData = {
  scan: ScanSession;
  latest_run_id: string | null;
  steps: TraceStep[];
  runs: TraceRun[];
  live: LiveTrace | null;
};

/** [x, y, w, h] in the rectified tray image. */
export type Rect = [number, number, number, number];

export type AgentRun = {
  run_id: string;
  decision: AgentDecision;
  code: string;
  reason: string;
  instruction: string | null;
  count: number | null;
  single_shot_count: number | null;
  steps_used: number;
  elapsed_ms: number;
  planner: PlannerName | string;
  planner_fallbacks: number;
  evidence_key: string | null;
  uncertain_regions: Rect[];
  changed_regions: Rect[];
  status: ScanStatus | string;
  trace: TraceStep[];
};

export type ApproveDecision = 'approve' | 'correct' | 'reject';

export type ApprovePayload = {
  approver_id: string;
  decision: ApproveDecision;
  corrected_count?: number;
  note?: string;
  unit_value?: number;
};

export type Discrepancy = {
  id: string;
  scan_id: string;
  tenant_key: string;
  branch_code: string;
  tray_code: string;
  expected_count: number;
  actual_count: number;
  variance_count: number;
  variance_value?: number | null;
  severity: 'low' | 'medium' | 'high' | string;
  status: 'open' | 'resolved' | 'ignored' | string;
  resolution_note?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  created_at: string;
};

export type ScanCreateData = {
  scan: ScanSession;
  discrepancy?: Discrepancy | null;
  agent?: AgentRun | null;
};

export type ApproveResult = {
  scan: ScanSession;
  discrepancy: Discrepancy | null;
};

export type ReviewScanPayload = {
  manual_count?: number | null;
  expected_count?: number | null;
  unit_value?: number | null;
  is_ai_correct?: boolean | null;
  notes?: string | null;
};

export type DiscrepancyListData = {
  items: Discrepancy[];
  total: number;
};

export type KiotVietStatus = {
  provider: string;
  configured: boolean;
  snapshots: number;
  last_sync_at?: string | null;
  last_event_at?: string | null;
};

export type HistoryItem = {
  id: string;
  image_path: string;
  image_thumbnail?: string | null;
  detected_count: number;
  manual_count?: number | null;
  confidence_avg?: number | null;
  staff_id?: string | null;
  tray_id?: string | null;
  is_ai_correct?: boolean | null;
  notes?: string | null;
  boxes_json?: Box[] | null;
  created_at: string;
};

export type HistoryResponseData = {
  items: HistoryItem[];
  page: number;
  limit: number;
  total: number;
};

export type StatsData = {
  total_records: number;
  avg_detected_count: number;
  avg_manual_count: number;
  ai_correct_rate: number;
};
