/** FastAPI client for Project UNTANGLE backend. */

export const API_BASE = 'http://localhost:8000';

export type BackendTagStatus =
  | 'Matched'
  | 'Missing in P&ID'
  | 'Pending Review'
  | 'Ambiguous';

export interface BackendKpiSummary {
  total_tags: number;
  matched_tags: number;
  retained_equipment: number;
  graph_integrity: string;
  processing_time_seconds: number;
  inventory_rows?: number;
  usable_inventory_rows?: number;
  unique_inventory_tags?: number;
  duplicate_inventory_tags?: number;
  duplicate_inventory_rows?: number;
  detected_source_tags?: number;
  missing_tags?: number;
  ambiguous_tags?: number;
  pdf_only_tags?: number;
  pending_review_tags?: number;
  audit_rows?: number;
  clarification_items?: number;
}

export interface BackendEquipmentNode {
  id: string;
  tag: string;
  type: 'tank' | 'pump' | 'mixer' | 'exchanger' | 'vessel' | 'valve' | 'filter' | 'junction';
  label: string;
  source_bbox: number[];
  source_page: number;
  source_symbol_bbox?: number[] | null;
  collapsed_tags: string[];
  duty_standby: boolean;
}

export interface BackendProcessEdge {
  id: string;
  source: string;
  target: string;
  flow_direction: string;
  relation: string;
  confidence?: number | null;
  evidence_status?: string;
  source_segment_ids?: string[];
  source_page?: number | null;
  source_bbox?: number[] | null;
}

export interface BackendTagAuditItem {
  tag_name: string;
  type: string;
  source_bbox: number[];
  source_page?: number | null;
  excel_row: number;
  excel_rows?: number[];
  excel_sheet?: string | null;
  excel_sheets?: (string | null)[];
  status: BackendTagStatus;
  confidence: number;
  reason?: string | null;
}

export interface BackendClarificationItem {
  id: string;
  location_label: string;
  question: string;
  crop_bbox: number[];
  source_page?: number;
  evidence_crop_data_uri?: string | null;
  default_recommendation: string;
  options: string[];
  status: string;
  confidence?: number | null;
  selected_option?: string | null;
}

export interface BackendClarificationDecision {
  item_id: string;
  selected_option: string;
  status: string;
  updated_at: string;
}

export interface ProcessPidResponse {
  run_id: string;
  created_at: string;
  pdf_filename: string;
  excel_filename: string;
  kpis: BackendKpiSummary;
  nodes: BackendEquipmentNode[];
  edges: BackendProcessEdge[];
  tag_audit: BackendTagAuditItem[];
  clarification_queue: BackendClarificationItem[];
  clarification_decisions: BackendClarificationDecision[];
  pdf_page_count: number;
}

export interface SavedRunSummary {
  run_id: string;
  created_at: string;
  pdf_filename: string;
  excel_filename: string;
  kpis: BackendKpiSummary;
}

export interface SavedRunListResponse {
  runs: SavedRunSummary[];
}

export interface ResolveAmbiguityResponse {
  run_id: string;
  kpis: BackendKpiSummary;
  nodes: BackendEquipmentNode[];
  edges: BackendProcessEdge[];
  resolved_item_id: string;
  selected_option: string;
  message: string;
  topology_changed: boolean;
}

export class UntangleApiError extends Error {
  status?: number;
  unreachable: boolean;

  constructor(message: string, opts?: { status?: number; unreachable?: boolean }) {
    super(message);
    this.name = 'UntangleApiError';
    if (opts?.status !== undefined) this.status = opts.status;
    this.unreachable = opts?.unreachable ?? false;
  }
}

export interface AuthUser {
  user_id: string;
  full_name: string;
  email: string;
  role: string;
}

export interface AuthSession {
  access_token: string;
  token_type: string;
  expires_at: number;
  user: AuthUser;
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

function reportUnauthorized(response: Response): void {
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("untangle:auth-expired"));
  }
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw new UntangleApiError(await parseError(response), { status: response.status });
  return response.json() as Promise<AuthSession>;
}

export async function getCurrentUser(token: string): Promise<AuthUser> {
  const response = await fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders(token) });
  if (!response.ok) {
    reportUnauthorized(response);
    throw new UntangleApiError(await parseError(response), { status: response.status });
  }
  return response.json() as Promise<AuthUser>;
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string | { msg?: string }[] };
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map(d => d.msg ?? JSON.stringify(d)).join('; ');
    }
  } catch {
    /* ignore */
  }
  return `Request failed (${response.status})`;
}

export async function processPid(pdf: File, excel: File, token: string): Promise<ProcessPidResponse> {
  const form = new FormData();
  form.append('file_pdf', pdf);
  form.append('file_excel', excel);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/process-pid`, {
      method: 'POST',
      headers: authHeaders(token),
      body: form,
    });
  } catch {
    throw new UntangleApiError(
      'Cannot reach UNTANGLE backend at http://localhost:8000. Start the FastAPI server and try again.',
      { unreachable: true },
    );
  }

  if (!response.ok) {
    reportUnauthorized(response);
    throw new UntangleApiError(await parseError(response), { status: response.status });
  }

  return (await response.json()) as ProcessPidResponse;
}

export async function listSavedRuns(token: string, limit = 20): Promise<SavedRunListResponse> {
  const response = await fetch(`${API_BASE}/api/runs?limit=${encodeURIComponent(limit)}`, { headers: authHeaders(token) });
  if (!response.ok) {
    reportUnauthorized(response);
    throw new UntangleApiError(await parseError(response), { status: response.status });
  }
  return (await response.json()) as SavedRunListResponse;
}

export async function getSavedRun(runId: string, token: string): Promise<ProcessPidResponse> {
  const response = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`, { headers: authHeaders(token) });
  if (!response.ok) {
    reportUnauthorized(response);
    throw new UntangleApiError(await parseError(response), { status: response.status });
  }
  return (await response.json()) as ProcessPidResponse;
}

export async function getSavedRunFile(runId: string, kind: "pdf" | "excel", token: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}/files/${kind}`, { headers: authHeaders(token) });
  if (!response.ok) {
    reportUnauthorized(response);
    throw new UntangleApiError(await parseError(response), { status: response.status });
  }
  return response.blob();
}

export async function resolveAmbiguity(
  runId: string,
  itemId: string,
  selectedOption: string,
  token: string,
): Promise<ResolveAmbiguityResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/resolve-ambiguity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({ run_id: runId, item_id: itemId, selected_option: selectedOption }),
    });
  } catch {
    throw new UntangleApiError(
      'Cannot reach UNTANGLE backend at http://localhost:8000. Start the FastAPI server and try again.',
      { unreachable: true },
    );
  }

  if (!response.ok) {
    reportUnauthorized(response);
    throw new UntangleApiError(await parseError(response), { status: response.status });
  }

  return (await response.json()) as ResolveAmbiguityResponse;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/health`);
    return response.ok;
  } catch {
    return false;
  }
}
