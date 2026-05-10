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
  created_at: string;
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
