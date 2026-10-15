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
  confidence: number;
  source_page?: number | null;
  source_bbox?: number[] | null;
}

export interface BackendTagAuditItem {
  tag_name: string;
  type: string;
  source_bbox: number[];
  source_page?: number | null;
  excel_row: number;
  status: BackendTagStatus;
  confidence: number;
}

export interface BackendClarificationItem {
  id: string;
  location_label: string;
  question: string;
  crop_bbox: number[];
  default_recommendation: string;
  options: string[];
  status: string;
}

export interface ProcessPidResponse {
  kpis: BackendKpiSummary;
  nodes: BackendEquipmentNode[];
  edges: BackendProcessEdge[];
  tag_audit: BackendTagAuditItem[];
  clarification_queue: BackendClarificationItem[];
  pdf_page_count: number;
}

export interface ResolveAmbiguityResponse {
  kpis: BackendKpiSummary;
  edges: BackendProcessEdge[];
  resolved_item_id: string;
  selected_option: string;
  message: string;
}

export class UntangleApiError extends Error {
  status?: number;
  unreachable: boolean;

  constructor(message: string, opts?: { status?: number; unreachable?: boolean }) {
    super(message);
    this.name = 'UntangleApiError';
    this.status = opts?.status;
    this.unreachable = opts?.unreachable ?? false;
  }
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

export async function processPid(pdf: File, excel: File): Promise<ProcessPidResponse> {
  const form = new FormData();
  form.append('file_pdf', pdf);
  form.append('file_excel', excel);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/process-pid`, {
      method: 'POST',
      body: form,
    });
  } catch {
    throw new UntangleApiError(
      'Cannot reach UNTANGLE backend at http://localhost:8000. Start the FastAPI server and try again.',
      { unreachable: true },
    );
  }

  if (!response.ok) {
    throw new UntangleApiError(await parseError(response), { status: response.status });
  }

  return (await response.json()) as ProcessPidResponse;
}

export async function resolveAmbiguity(
  itemId: string,
  selectedOption: string,
): Promise<ResolveAmbiguityResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/resolve-ambiguity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId, selected_option: selectedOption }),
    });
  } catch {
    throw new UntangleApiError(
      'Cannot reach UNTANGLE backend at http://localhost:8000. Start the FastAPI server and try again.',
      { unreachable: true },
    );
  }

  if (!response.ok) {
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
