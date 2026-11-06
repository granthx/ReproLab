export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

export type ApiValidationError = {
  loc: (string | number)[];
  msg: string;
  type?: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

export class ApiError extends Error {
  readonly status: number;
  readonly validationErrors: ApiValidationError[];

  constructor(status: number, message: string, validationErrors: ApiValidationError[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.validationErrors = validationErrors;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isAbortError(error: unknown): boolean {
  return typeof error === "object" && error !== null && "name" in error && error.name === "AbortError";
}

function checkAborted(signal?: AbortSignal | null): void {
  if (signal?.aborted) {
    if (isAbortError(signal.reason)) throw signal.reason;
    throw new DOMException("The request was aborted.", "AbortError");
  }
}

function normalizeFailure(error: unknown, signal?: AbortSignal | null, message = "Could not reach the API. Check your connection and try again."): never {
  if (isAbortError(error)) throw error;
  checkAborted(signal);
  if (error instanceof ApiError) throw error;
  throw new ApiError(0, message);
}

function validationErrors(detail: unknown[]): ApiValidationError[] {
  return detail.flatMap((entry): ApiValidationError[] => {
    if (typeof entry === "string") return [{ loc: [], msg: entry }];
    if (!isObject(entry) || typeof entry.msg !== "string") return [];
    return [{
      loc: Array.isArray(entry.loc) ? entry.loc.filter((part): part is string | number => typeof part === "string" || typeof part === "number") : [],
      msg: entry.msg,
      ...(typeof entry.type === "string" ? { type: entry.type } : {}),
      ...("input" in entry ? { input: entry.input } : {}),
      ...(isObject(entry.ctx) ? { ctx: entry.ctx } : {}),
    }];
  });
}

async function responseError(response: Response): Promise<ApiError> {
  const text = await response.text();
  let payload: unknown = text;
  try { payload = JSON.parse(text); } catch { /* Non-JSON error responses can contain a useful message. */ }
  const detail = isObject(payload) ? payload.detail ?? payload.message : payload;
  const errors = Array.isArray(detail) ? validationErrors(detail) : [];
  const message = errors.length
    ? errors.map((error) => `${error.loc.length ? `${error.loc.join(".")}: ` : ""}${error.msg}`).join("; ")
    : typeof detail === "string" && detail.trim() ? detail : `Request failed (${response.status})`;
  return new ApiError(response.status, message, errors);
}

async function fetchChecked(path: string, init?: RequestInit): Promise<Response> {
  try {
    checkAborted(init?.signal);
    const response = await fetch(`${API_URL}${path}`, { ...init, cache: "no-store" });
    checkAborted(init?.signal);
    if (!response.ok) throw await responseError(response);
    return response;
  } catch (error) {
    normalizeFailure(error, init?.signal);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (typeof window !== "undefined" && !headers.has("Authorization") && !headers.has("X-API-Key")) {
    try {
      const token = window.localStorage.getItem("reprolab_auth_token");
      if (token) headers.set("Authorization", `Bearer ${token}`);
    } catch {
      // Safely ignore storage restrictions
    }
  }
  const response = await fetchChecked(path, { ...init, headers });
  try {
    const text = await response.text();
    checkAborted(init?.signal);
    let payload: unknown = null;
    try { payload = JSON.parse(text); } catch { /* Preserve the generic helper's empty/non-JSON result. */ }
    return payload as T;
  } catch (error) {
    normalizeFailure(error, init?.signal);
  }
}

export type Investigation = {
  id: string;
  paper_id: string | null;
  name: string;
  source_kind: string;
  status: string;
  execution_status: string;
  claim_assessment: string;
  created_at: string;
  updated_at: string;
};

export type RailMetrics = {
  claimed_mean: number | null;
  replicated_mean: number | null;
  wilson_ci_lower: number | null;
  wilson_ci_upper: number | null;
  sample_size: number | null;
  metric_name: string;
};

export type InvestigationSummary = {
  investigation_id: string;
  name: string;
  source_kind: string;
  status: string;
  execution_status: string;
  claim_assessment: string;
  reproduction_verdict: string;
  plain_english_summary: string;
  plain_hindi_summary: string;
  technical_dossier_en: string;
  technical_dossier_hi: string;
  rail_metrics: RailMetrics;
};

export type Claim = {
  id: string;
  investigation_id: string;
  statement: string;
  metric_name: string;
  reported_value: number | null;
  metric_direction: string;
  source_kind: string;
  source_locator: string | null;
  published: boolean;
  verification_status: string;
  created_at: string;
};

export type Evidence = {
  id: string;
  investigation_id: string;
  claim_id: string | null;
  artifact_id: string | null;
  source_url: string | null;
  source_locator: string;
  quoted_text: string | null;
  sha256: string | null;
  verification_status: string;
  verification_notes: string | null;
  created_at: string;
};

export type EvidenceReview = {
  id: string;
  evidence_item_id: string;
  review_method: string;
  outcome: string;
  reviewer_id: string | null;
  reviewer_label: string | null;
  notes: string;
  source_snapshot_hash: string | null;
  reviewed_at: string;
};

export type Protocol = {
  id: string;
  investigation_id: string;
  parent_protocol_id: string | null;
  version_number: number;
  status: string;
  protocol_hash: string;
  protocol: Record<string, any>;
  approved_by: string | null;
  approved_at: string | null;
  frozen_at: string | null;
  created_at: string;
};

export type ResearchArtifact = {
  id: string;
  investigation_id: string;
  protocol_version_id: string;
  kind: string;
  storage_key: string;
  sha256: string;
  size_bytes: number;
  content_type: string;
  producer: string;
  provenance_json: Record<string, any>;
  created_at: string;
};

export type Scientist = {
  role_id: string;
  name: string;
  specialty: string;
  version: string;
  mandate: string;
  responsibilities: string[];
  prohibited_actions: string[];
  permitted_tools: string[];
  permissions: string[];
  availability: string;
};

export type Capabilities = {
  paper_intake: boolean;
  protocol_governance: boolean;
  evidence_review: boolean;
  traceable_findings: boolean;
  scientist_registry: boolean;
  trusted_fixture_scoring: boolean;
  experiment_runner: boolean;
  sandbox_execution: boolean;
  langgraph_workflow: boolean;
  measurements: boolean;
  reports: boolean;
  execution_state: string;
};

export type AttributionInput = {
  recorder_id?: string | null;
  recorder_label: string;
  entry_method?: "manual_entry";
  associated_role_id?: string | null;
  role_association_note?: string | null;
};

export type ConstitutionSnapshot = {
  id: string;
  role_id: string;
  constitution_version: string;
  constitution_json: Record<string, unknown>;
  constitution_hash: string;
  created_at: string;
};

export type RecordAttribution = {
  id: string;
  investigation_id: string;
  recorder_id: string | null;
  recorder_label: string;
  entry_method: string;
  associated_role_id: string | null;
  role_association_note: string | null;
  identity_assurance: string;
  constitution_snapshot: ConstitutionSnapshot | null;
  created_at: string;
};

export type RecordKind = "observation" | "interpretation" | "limitation" | "unresolved_question" | "resolution_note";
export type EvidenceRelationship = "supports" | "contradicts" | "context";

export type EvidenceLinkInput = {
  key: string;
  evidence_item_id: string;
  evidence_review_id?: string | null;
  relationship: EvidenceRelationship;
  rationale: string;
};

export type NumericAssertion = {
  metric_name: string;
  value: string;
  unit: string;
  citation_key: string;
  source_start: number;
  source_end: number;
  source_lexeme: string;
  normalization: "identity" | "percent_to_fraction";
  context: string;
  uncertainty_as_reported?: string | null;
};

export type FindingAssertion = {
  key: string;
  assertion_kind: "source_reported" | "interpretation" | "uncertainty";
  text: string;
  grounding: "source_grounded" | "unresolved";
  citation_keys: string[];
  numbers: NumericAssertion[];
  unresolved_reason?: string | null;
};

export type FindingDefinition = {
  record_kind: RecordKind;
  title: string;
  claim_id?: string | null;
  protocol_version_id?: string | null;
  assertions: FindingAssertion[];
  evidence_links: EvidenceLinkInput[];
  limitations: string[];
};

// These fields are frozen by record_integrity._source_snapshot, not live evidence rows.
export type EvidenceSnapshot = {
  evidence_item_id: string;
  source_url: string | null;
  source_locator: string;
  quoted_text: string | null;
  sha256: string | null;
  verification_status: string;
  verification_notes: string | null;
  created_at: string | null;
  evidence_review?: Omit<EvidenceReview, "evidence_item_id" | "reviewed_at"> & { reviewed_at: string | null };
};

export type FindingEvidenceLink = {
  id: string;
  finding_version_id: string;
  evidence_item_id: string;
  investigation_id: string;
  citation_key: string;
  evidence_review_id: string | null;
  relationship: string;
  rationale: string;
  source_snapshot_json: EvidenceSnapshot;
  snapshot_hash: string;
  created_at: string;
};

export type FindingSummary = {
  id: string;
  investigation_id: string;
  latest_version_id: string;
  latest_version_number: number;
  record_kind: string;
  title: string;
  content_hash: string;
  created_at: string;
};

export type FindingVersion = {
  id: string;
  finding_id: string;
  investigation_id: string;
  parent_version_id: string | null;
  version_number: number;
  record_kind: string;
  claim_id: string | null;
  protocol_version_id: string | null;
  schema_version: string;
  canonical_content_json: FindingDefinition;
  content_hash: string;
  finding: FindingDefinition;
  attribution: RecordAttribution;
  evidence_links: FindingEvidenceLink[];
  created_at: string;
};

export type Finding = {
  id: string;
  investigation_id: string;
  created_at: string;
  versions: FindingVersion[];
};

export type FindingCreate = { attribution: AttributionInput; finding: FindingDefinition };
export type FindingVersionCreate = FindingCreate & { parent_version_id: string };

export type RecordReviewCreate = {
  attribution: AttributionInput;
  expected_content_hash: string;
  review_method?: "manual_review";
  outcome: "accepted_for_inclusion" | "needs_revision" | "abstained";
  notes: string;
  citations_checked: boolean;
  numeric_transcription_checked?: boolean | null;
  limitations_checked: boolean;
  execution_wording_checked: boolean;
  dependency_disclosures?: string[];
};

export type RecordReview = {
  id: string;
  investigation_id: string;
  finding_version_id: string;
  target_content_hash: string;
  reviewer_attribution: RecordAttribution;
  review_method: string;
  outcome: string;
  notes: string;
  citations_checked: boolean;
  numeric_transcription_checked: boolean | null;
  limitations_checked: boolean;
  execution_wording_checked: boolean;
  dependency_disclosures: string[];
  reviewed_at: string;
};

export type ReportSelection = {
  finding_version_id: string;
  finding_content_hash: string;
  section: string;
  position: number;
  disposition: "included" | "excluded_with_reason";
  exclusion_reason?: string | null;
};

export type ReportDefinition = {
  report_kind: "analysis_record";
  title: string;
  scope_claim_ids: string[];
  finding_links: ReportSelection[];
  limitations: string[];
  unresolved_questions: string[];
};

export type ReportSourceContext = {
  investigation: {
    id: string;
    source_kind: "paper" | "synthetic_framework_test";
    paper_id: string | null;
    execution_status: "not_started";
    claim_assessment: "not_assessed" | "framework_test_only";
  };
  claims: Omit<Claim, "investigation_id" | "created_at">[];
  findings: {
    finding_version_id: string;
    finding_id: string;
    finding_content_hash: string;
    finding: FindingDefinition;
    attribution: RecordAttribution;
    evidence_snapshots: {
      citation_key: string;
      relationship: EvidenceRelationship;
      rationale: string;
      snapshot_hash: string;
      source_snapshot: EvidenceSnapshot;
    }[];
  }[];
};

export type ReportFindingLink = Omit<ReportSelection, "disposition" | "exclusion_reason"> & {
  id: string;
  report_version_id: string;
  investigation_id: string;
  disposition: string;
  exclusion_reason: string | null;
  created_at: string;
};

export type ReportVersion = {
  id: string;
  report_id: string;
  investigation_id: string;
  parent_version_id: string | null;
  version_number: number;
  report_kind: string;
  title: string;
  scope_claim_ids: string[];
  limitations: string[];
  unresolved_questions: string[];
  schema_version: string;
  canonical_content_json: ReportDefinition & { source_context: ReportSourceContext };
  content_hash: string;
  finding_links: ReportFindingLink[];
  attribution: RecordAttribution;
  created_at: string;
};

export type ReportEvent = {
  id: string;
  report_id: string;
  report_version_id: string;
  investigation_id: string;
  event_type: string;
  sequence_number: number;
  target_content_hash: string;
  attribution: RecordAttribution;
  notes: string;
  created_at: string;
};

export type Report = {
  id: string;
  investigation_id: string;
  status: string;
  created_by_attribution: RecordAttribution;
  versions: ReportVersion[];
  events: ReportEvent[];
  created_at: string;
};

export type ReportExport = {
  id: string;
  report_version_id: string;
  investigation_id: string;
  report_content_hash: string;
  json_size_bytes: number;
  markdown_size_bytes: number;
  json_sha256: string;
  markdown_sha256: string;
  created_at: string;
};

export type ReportCreate = { attribution: AttributionInput; version: ReportDefinition };
export type ReportVersionCreate = ReportCreate & { parent_version_id: string };
export type ReportTransitionRequest = {
  attribution: AttributionInput;
  notes: string;
  report_version_id?: string | null;
};

function findingPath(iid: string, fid?: string, vid?: string): string {
  const path = `/investigations/${encodeURIComponent(iid)}/findings`;
  return fid === undefined ? path : `${path}/${encodeURIComponent(fid)}${vid === undefined ? "" : `/versions/${encodeURIComponent(vid)}`}`;
}

function reportPath(iid: string, rid?: string, vid?: string): string {
  const path = `/investigations/${encodeURIComponent(iid)}/reports`;
  return rid === undefined ? path : `${path}/${encodeURIComponent(rid)}${vid === undefined ? "" : `/versions/${encodeURIComponent(vid)}`}`;
}

function post<T>(path: string, payload?: unknown): Promise<T> {
  return api<T>(path, { method: "POST", ...(payload === undefined ? {} : { body: JSON.stringify(payload) }) });
}

export const recordsApi = {
  capabilities: (signal?: AbortSignal): Promise<Capabilities> => api("/capabilities", { signal }),
  scientists: (signal?: AbortSignal): Promise<Scientist[]> => api("/scientists", { signal }),
  findings: (iid: string, signal?: AbortSignal): Promise<FindingSummary[]> => api(findingPath(iid), { signal }),
  finding: (iid: string, fid: string, signal?: AbortSignal): Promise<Finding> => api(findingPath(iid, fid), { signal }),
  findingVersion: (iid: string, fid: string, vid: string, signal?: AbortSignal): Promise<FindingVersion> => api(findingPath(iid, fid, vid), { signal }),
  createFinding: (iid: string, payload: FindingCreate): Promise<Finding> => post(findingPath(iid), payload),
  createFindingVersion: (iid: string, fid: string, payload: FindingVersionCreate): Promise<FindingVersion> => post(`${findingPath(iid, fid)}/versions`, payload),
  findingReviews: (iid: string, fid: string, vid: string, signal?: AbortSignal): Promise<RecordReview[]> => api(`${findingPath(iid, fid, vid)}/reviews`, { signal }),
  createFindingReview: (iid: string, fid: string, vid: string, payload: RecordReviewCreate): Promise<RecordReview> => post(`${findingPath(iid, fid, vid)}/reviews`, payload),
  reports: (iid: string, signal?: AbortSignal): Promise<Report[]> => api(reportPath(iid), { signal }),
  report: (iid: string, rid: string, signal?: AbortSignal): Promise<Report> => api(reportPath(iid, rid), { signal }),
  reportVersion: (iid: string, rid: string, vid: string, signal?: AbortSignal): Promise<ReportVersion> => api(reportPath(iid, rid, vid), { signal }),
  createReport: (iid: string, payload: ReportCreate): Promise<Report> => post(reportPath(iid), payload),
  createReportVersion: (iid: string, rid: string, payload: ReportVersionCreate): Promise<ReportVersion> => post(`${reportPath(iid, rid)}/versions`, payload),
  reportEvents: (iid: string, rid: string, signal?: AbortSignal): Promise<ReportEvent[]> => api(`${reportPath(iid, rid)}/events`, { signal }),
  publishReport: (iid: string, rid: string, payload: ReportTransitionRequest): Promise<ReportEvent> => post(`${reportPath(iid, rid)}/publish`, payload),
  withdrawReport: (iid: string, rid: string, payload: ReportTransitionRequest): Promise<ReportEvent> => post(`${reportPath(iid, rid)}/withdraw`, payload),
  exports: (iid: string, rid: string, vid: string, signal?: AbortSignal): Promise<ReportExport[]> => api(`${reportPath(iid, rid, vid)}/exports`, { signal }),
  createExport: (iid: string, rid: string, vid: string): Promise<ReportExport> => post(`${reportPath(iid, rid, vid)}/exports`),
};

// Stage 3 governed assignments, deliverables and review delegations (read models).
export type AssignmentStatus = "assigned" | "in_progress" | "completed" | "revoked" | "blocked" | "abstained" | "handed_off" | "disputed" | "not_required";

export type GovernanceReference = { kind: string; id: string; content_hash?: string | null };

export type AssignmentBudget = { max_model_calls: number; max_input_tokens: number; max_output_tokens: number };

export type Assignment = {
  id: string;
  investigation_id: string;
  role_id: string;
  task_kind: string;
  constitution_version: string;
  constitution_hash: string;
  objective: string;
  input_contract: string | null;
  output_contract: string | null;
  input_references: GovernanceReference[];
  requested_by: string | null;
  budget: AssignmentBudget | null;
  status: AssignmentStatus;
  lifecycle_version: number;
  last_event_hash: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  created_by_attribution_id: string;
  blocked_reason: string | null;
  not_required_reason: string | null;
  revoked_reason: string | null;
};

export type AssignmentEvent = {
  id: string;
  assignment_id: string;
  sequence_number: number;
  event_type: string;
  from_status: AssignmentStatus | null;
  to_status: AssignmentStatus | null;
  actor_role_id: string | null;
  attribution_id: string;
  reason: string | null;
  payload: Record<string, unknown>;
  event_hash: string;
  previous_event_hash: string | null;
  occurred_at: string;
};

export type Deliverable = {
  id: string;
  assignment_id: string;
  kind: string;
  schema_name: string;
  status: string;
  content: Record<string, unknown>;
  content_hash: string;
  input_references: GovernanceReference[];
  limitations: string[];
  created_at: string;
  updated_at: string;
  created_by_attribution_id: string;
};

export type ReviewDelegation = {
  id: string;
  assignment_id: string;
  reviewer_role_id: string;
  target: { kind: string; finding_version_id: string; finding_id: string; content_hash: string };
  delegation_hash: string;
  status: string;
  issued_by_role_id: string | null;
  issued_at: string;
  expires_at: string;
  redeemed_at: string | null;
  revoked_at: string | null;
  lifecycle_version: number;
  max_uses: number;
  use_count: number;
};

// Workflows (Stage 4 analysis-only & Stage 8 full reproduction).
export type WorkflowKind = "analysis_only_v1" | "full_reproduction_v1";
export type WorkflowStatus = "running" | "awaiting_human_review" | "blocked" | "abstained" | "completed" | "cancelled";
export type WorkflowProviderMode = "source_grounded" | "gemini";

export type WorkflowRun = {
  id: string;
  investigation_id: string;
  workflow_kind: WorkflowKind;
  status: WorkflowStatus;
  current_node: string;
  provider_mode: WorkflowProviderMode;
  idempotency_key: string | null;
  lifecycle_version: number;
  latest_checkpoint_seq: number;
  latest_checkpoint_hash: string | null;
  latest_event_hash: string | null;
  blocked_reason: string | null;
  abstained_reason: string | null;
  cancelled_reason: string | null;
  created_by_attribution_id: string;
  created_at: string;
  updated_at: string;
};

export type WorkflowCheckpoint = {
  id: string;
  workflow_run_id: string;
  investigation_id: string;
  sequence_number: number;
  node_name: string;
  stage_status: "entered" | "completed" | "awaiting_human_review" | "blocked" | "abstained";
  role_id: string | null;
  assignment_id: string | null;
  deliverable_id: string | null;
  state_json: Record<string, unknown>;
  state_hash: string;
  previous_checkpoint_hash: string | null;
  checkpoint_hash: string;
  created_at: string;
};

export type WorkflowEvent = {
  id: string;
  workflow_run_id: string;
  investigation_id: string;
  sequence_number: number;
  event_type: string;
  node_name: string;
  role_id: string | null;
  attribution_id: string;
  reason: string | null;
  payload: Record<string, unknown>;
  previous_event_hash: string | null;
  event_hash: string;
  occurred_at: string;
};

export type WorkflowModelCall = {
  id: string;
  workflow_run_id: string;
  investigation_id: string;
  assignment_id: string;
  role_id: string;
  provider: "gemini" | "deterministic_none";
  model_name: string;
  routing_category: string;
  call_index: number;
  max_calls_ceiling: number;
  status: "succeeded" | "skipped_deterministic" | "skipped_conditional_not_needed" | "failed_provider_error" | "blocked_budget";
  prompt_sha256: string;
  response_sha256: string | null;
  input_tokens: number;
  output_tokens: number;
  error_detail: string | null;
  recorded_at: string;
};

export type WorkflowRunCreate = {
  workflow_kind?: WorkflowKind;
  provider_mode: WorkflowProviderMode;
  idempotency_key?: string | null;
  attribution: AttributionInput;
};
export type WorkflowGateDecision = { decision: "approve" | "reject"; expected_lifecycle_version: number; notes: string; attribution: AttributionInput };
export type WorkflowResume = { expected_lifecycle_version: number; notes?: string | null; attribution: AttributionInput };
export type WorkflowCancel = { expected_lifecycle_version: number; reason: string; attribution: AttributionInput };

function invPath(iid: string, suffix: string): string {
  return `/investigations/${encodeURIComponent(iid)}/${suffix}`;
}

function runPath(iid: string, rid: string, suffix = ""): string {
  return invPath(iid, `workflow-runs/${encodeURIComponent(rid)}${suffix ? `/${suffix}` : ""}`);
}

export const governanceApi = {
  assignments: (iid: string, signal?: AbortSignal): Promise<Assignment[]> => api(invPath(iid, "assignments"), { signal }),
  assignmentEvents: (iid: string, aid: string, signal?: AbortSignal): Promise<AssignmentEvent[]> => api(invPath(iid, `assignments/${encodeURIComponent(aid)}/events`), { signal }),
  assignmentDeliverables: (iid: string, aid: string, signal?: AbortSignal): Promise<Deliverable[]> => api(invPath(iid, `assignments/${encodeURIComponent(aid)}/deliverables`), { signal }),
  reviewDelegations: (iid: string, signal?: AbortSignal): Promise<ReviewDelegation[]> => api(invPath(iid, "review-delegations"), { signal }),
};

export const workflowApi = {
  runs: (iid: string, signal?: AbortSignal): Promise<WorkflowRun[]> => api(invPath(iid, "workflow-runs"), { signal }),
  run: (iid: string, rid: string, signal?: AbortSignal): Promise<WorkflowRun> => api(runPath(iid, rid), { signal }),
  checkpoints: (iid: string, rid: string, signal?: AbortSignal): Promise<WorkflowCheckpoint[]> => api(runPath(iid, rid, "checkpoints"), { signal }),
  events: (iid: string, rid: string, signal?: AbortSignal): Promise<WorkflowEvent[]> => api(runPath(iid, rid, "events"), { signal }),
  modelCalls: (iid: string, rid: string, signal?: AbortSignal): Promise<WorkflowModelCall[]> => api(runPath(iid, rid, "model-calls"), { signal }),
  start: (iid: string, payload: WorkflowRunCreate): Promise<WorkflowRun> => post(invPath(iid, "workflow-runs"), payload),
  decideGate: (iid: string, rid: string, payload: WorkflowGateDecision): Promise<WorkflowRun> => post(runPath(iid, rid, "review-gate"), payload),
  resume: (iid: string, rid: string, payload: WorkflowResume): Promise<WorkflowRun> => post(runPath(iid, rid, "resume"), payload),
  cancel: (iid: string, rid: string, payload: WorkflowCancel): Promise<WorkflowRun> => post(runPath(iid, rid, "cancel"), payload),
};

// Stage 6 isolated experiment execution and production measurements
export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled" | "timeout";
export type AttemptStatus = "running" | "completed" | "failed" | "timeout" | "cancelled";
export type ExecutionEventType = "job_submitted" | "attempt_started" | "attempt_finished" | "artifacts_collected" | "scoring_completed" | "job_cancelled" | "job_timeout";

export type AttemptRecord = {
  id: string;
  job_id: string;
  investigation_id: string;
  attempt_number: number;
  status: AttemptStatus;
  exit_code: number | null;
  stdout_excerpt: string | null;
  stderr_excerpt: string | null;
  output_artifact_ids: string[] | null;
  resource_usage_json: {
    cpu_user_seconds?: number;
    wall_time_seconds?: number;
    peak_memory_bytes?: number;
  } | null;
  started_at: string;
  finished_at: string | null;
};

export type ExecutionEvent = {
  id: string;
  job_id: string;
  investigation_id: string;
  attempt_id: string | null;
  sequence_number: number;
  event_type: ExecutionEventType;
  reason: string | null;
  payload: Record<string, unknown>;
  event_hash: string;
  previous_event_hash: string | null;
  occurred_at: string;
};

export type ProductionMeasurement = {
  id: string;
  investigation_id: string;
  job_id: string;
  attempt_id: string;
  metric_name: string;
  value: number;
  unit: string;
  sample_size: number;
  analysis_unit: string;
  confidence_level: number;
  interval_lower: number;
  interval_upper: number;
  scoring_method: string;
  scorer_version: string;
  prediction_artifact_sha256: string;
  manifest_artifact_sha256: string;
  protocol_hash: string;
  recorded_at: string;
};

export type ExperimentJob = {
  id: string;
  investigation_id: string;
  protocol_version_id: string;
  submission_key: string;
  status: JobStatus;
  lifecycle_version: number;
  execution_bundle_hash: string;
  created_by_attribution_id: string;
  cancellation_reason: string | null;
  created_at: string;
  updated_at: string;
  attempts: AttemptRecord[];
  measurements: ProductionMeasurement[];
};

export type ExperimentJobCreate = {
  protocol_version_id: string;
  submission_key: string;
  attribution: AttributionInput;
};

export type ExperimentJobCancel = {
  expected_lifecycle_version: number;
  reason: string;
  attribution: AttributionInput;
};

export const executionApi = {
  jobs: (iid: string, signal?: AbortSignal): Promise<ExperimentJob[]> => api(invPath(iid, "experiment-jobs"), { signal }),
  job: (iid: string, jid: string, signal?: AbortSignal): Promise<ExperimentJob> => api(invPath(iid, `experiment-jobs/${encodeURIComponent(jid)}`), { signal }),
  attempts: (iid: string, jid: string, signal?: AbortSignal): Promise<AttemptRecord[]> => api(invPath(iid, `experiment-jobs/${encodeURIComponent(jid)}/attempts`), { signal }),
  events: (iid: string, jid: string, signal?: AbortSignal): Promise<ExecutionEvent[]> => api(invPath(iid, `experiment-jobs/${encodeURIComponent(jid)}/events`), { signal }),
  measurements: (iid: string, jid: string, signal?: AbortSignal): Promise<ProductionMeasurement[]> => api(invPath(iid, `experiment-jobs/${encodeURIComponent(jid)}/measurements`), { signal }),
  submit: (iid: string, payload: ExperimentJobCreate): Promise<ExperimentJob> => post(invPath(iid, "experiment-jobs"), payload),
  cancel: (iid: string, jid: string, payload: ExperimentJobCancel): Promise<ExperimentJob> => post(invPath(iid, `experiment-jobs/${encodeURIComponent(jid)}/cancel`), payload),
  streamUrl: (iid: string, jid: string): string => `${API_URL}${invPath(iid, `experiment-jobs/${encodeURIComponent(jid)}/stream`)}`,
};

export const investigationApi = {
  summary: (iid: string, signal?: AbortSignal): Promise<InvestigationSummary> =>
    api(invPath(iid, "summary"), { signal }),
};

export type EvaluationVerdict = "reproduced" | "disconfirmed" | "inconclusive" | "execution_failed";

export type ScientificEvaluation = {
  id: string;
  investigation_id: string;
  job_id: string | null;
  claim_id: string | null;
  evaluation_version: string;
  status: string;
  verdict: EvaluationVerdict;
  extraction_quality_score: number;
  extraction_quality_breakdown: Record<string, unknown>;
  technical_reproducibility_score: number;
  technical_reproducibility_breakdown: Record<string, unknown>;
  claim_verification_score: number;
  claim_verification_breakdown: Record<string, unknown>;
  summary_notes: string | null;
  evaluated_at: string;
};

export type EvaluationCreate = {
  job_id?: string | null;
  claim_id?: string | null;
  summary_notes?: string | null;
};

export type HealthDiagnostics = {
  status: string;
  app_version: string;
  uptime_seconds: number;
  database: {
    sanitized_url: string;
    connected: boolean;
  };
  storage: {
    root: string;
    total_bytes: number;
    total_files: number;
  };
  counts: {
    papers: number;
    investigations: number;
    workflow_runs: number;
    experiment_jobs: number;
    scientific_evaluations: number;
    system_backups: number;
  };
  security: {
    auth_enabled: boolean;
    gemini_api_key_configured: boolean;
    gemini_api_key_masked: string | null;
  };
  server_time: string;
};

export type Paper = {
  id: string;
  title: string;
  original_filename: string;
  file_size: number;
  sha256: string;
  created_at: string;
  download_url?: string;
};

export const papersApi = {
  list: (params?: { limit?: number; offset?: number }, signal?: AbortSignal): Promise<Paper[]> => {
    const query = new URLSearchParams();
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    if (params?.offset !== undefined) query.set("offset", String(params.offset));
    const qs = query.toString();
    return api(`/papers${qs ? `?${qs}` : ""}`, { signal });
  },
  count: (signal?: AbortSignal): Promise<{ count: number }> => api("/papers/count", { signal }),
  get: (id: string, signal?: AbortSignal): Promise<Paper> => api(`/papers/${encodeURIComponent(id)}`, { signal }),
  downloadUrl: (id: string): string => `${API_URL}/papers/${encodeURIComponent(id)}/download`,
};

export type Evaluation = ScientificEvaluation;

export const evaluationApi = {
  list: (iid: string, signal?: AbortSignal): Promise<ScientificEvaluation[]> => api(invPath(iid, "evaluations"), { signal }),
  get: (iid: string, eid: string, signal?: AbortSignal): Promise<ScientificEvaluation> => api(invPath(iid, `evaluations/${encodeURIComponent(eid)}`), { signal }),
  create: (iid: string, payload: EvaluationCreate): Promise<ScientificEvaluation> => post(invPath(iid, "evaluations"), payload),
};

export const operationsApi = {
  diagnostics: (signal?: AbortSignal): Promise<HealthDiagnostics> => api("/health/diagnostics", { signal }),
  backup: (): Promise<{ status: string; backup_id: string; manifest_path: string; manifest_sha256: string; total_bytes: number }> => post("/operations/backup", {}),
  backups: (signal?: AbortSignal): Promise<any[]> => api("/operations/backups", { signal }),
};

const MAX_EXPORT_BYTES = 2_097_152;
export type ReportExportFormat = "json" | "markdown";

async function readExportBlob(response: Response, expectedSize: number, type: string, signal?: AbortSignal): Promise<Blob> {
  // Bound streamed bytes as they arrive rather than buffering an arbitrarily large response.
  if (!response.body) return response.blob();
  const reader = response.body.getReader();
  const chunks: BlobPart[] = [];
  let size = 0;
  let complete = false;
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    while (true) {
      checkAborted(signal);
      const { done, value } = await reader.read();
      checkAborted(signal);
      if (done) break;
      size += value.byteLength;
      if (size > MAX_EXPORT_BYTES || size > expectedSize) {
        throw new ApiError(response.status, "Report export exceeds its declared byte length or the 2 MiB limit.");
      }
      chunks.push(value);
    }
    complete = true;
    return new Blob(chunks, { type });
  } finally {
    signal?.removeEventListener("abort", cancel);
    if (!complete) cancel();
    reader.releaseLock();
  }
}

/** Fetch the exact stored bytes, verifying against API metadata rather than CORS response headers. */
export async function fetchVerifiedExport(
  iid: string,
  rid: string,
  reportExport: ReportExport,
  format: ReportExportFormat,
  signal?: AbortSignal,
): Promise<Blob> {
  try {
    checkAborted(signal);
    if (format !== "json" && format !== "markdown") throw new ApiError(0, "Unsupported report export format.");
    if (reportExport.investigation_id !== iid) throw new ApiError(0, "Report export belongs to another investigation.");
    const expectedSize = format === "json" ? reportExport.json_size_bytes : reportExport.markdown_size_bytes;
    const expectedHash = format === "json" ? reportExport.json_sha256 : reportExport.markdown_sha256;
    if (!Number.isSafeInteger(expectedSize) || expectedSize < 0 || expectedSize > MAX_EXPORT_BYTES) {
      throw new ApiError(0, "Report export metadata has an invalid byte length (maximum 2 MiB).");
    }
    if (typeof expectedHash !== "string" || !/^[0-9a-f]{64}$/.test(expectedHash)) {
      throw new ApiError(0, "Report export metadata has an invalid SHA-256 hash.");
    }
    const subtle = globalThis.crypto?.subtle;
    if (!subtle) throw new ApiError(0, "Report export verification requires Web Crypto SHA-256.");
    const path = `${reportPath(iid, rid, reportExport.report_version_id)}/exports/${encodeURIComponent(reportExport.id)}/${format}`;
    const response = await fetchChecked(path, { signal });
    const type = format === "json" ? "application/json" : "text/markdown";
    const blob = await readExportBlob(response, expectedSize, type, signal);
    checkAborted(signal);
    if (blob.size > MAX_EXPORT_BYTES || blob.size !== expectedSize) {
      throw new ApiError(response.status, "Report export byte length does not match its metadata.");
    }
    const bytes = await blob.arrayBuffer();
    checkAborted(signal);
    const digest = await subtle.digest("SHA-256", bytes);
    checkAborted(signal);
    const actualHash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    if (actualHash !== expectedHash) throw new ApiError(response.status, "Report export SHA-256 does not match its metadata.");
    return blob;
  } catch (error) {
    normalizeFailure(error, signal, "Could not read or verify the report export.");
  }
}

/** Start an attachment download only after length/hash verification and cancellation checks. */
export async function downloadReportExport(
  iid: string,
  rid: string,
  reportExport: ReportExport,
  format: ReportExportFormat,
  signal?: AbortSignal,
): Promise<void> {
  const blob = await fetchVerifiedExport(iid, rid, reportExport, format, signal);
  checkAborted(signal);
  const objectURL = URL.createObjectURL(blob);
  let anchor: HTMLAnchorElement | undefined;
  try {
    checkAborted(signal);
    anchor = document.createElement("a");
    anchor.href = objectURL;
    const safeVersion = reportExport.report_version_id.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80) || "export";
    anchor.download = `report-${safeVersion}.${format === "json" ? "json" : "md"}`;
    document.body.appendChild(anchor);
    checkAborted(signal);
    anchor.click();
  } finally {
    // Let the browser consume the attachment before releasing its object URL.
    try { anchor?.remove(); } finally { setTimeout(() => URL.revokeObjectURL(objectURL), 0); }
  }
}
