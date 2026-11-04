import api, { evidenceApi, explanationApi, fusionApi, projectApi, reviewApi } from '../../services/api';
import { CaseSchema, DecisionSubmissionSchema } from '../schemas/cases';

const unwrap = (request) => request.then(({ data }) => data);

async function mapCase(row) {
  let project = null;
  if (row.project_id) {
    try { project = await unwrap(projectApi.getById(row.project_id)); } catch { /* Scoped access may hide project details. */ }
  }
  const priority = ({ URGENT: 'CRITICAL', HIGH: 'HIGH', NORMAL: 'MEDIUM', LOW: 'LOW' })[row.priority_band] || 'MEDIUM';
  return CaseSchema.parse({
    id: row.id,
    title: row.claim_id ? `Review claim ${row.claim_id}` : row.evidence_id ? `Review evidence ${row.evidence_id}` : `Review case ${row.id}`,
    claim_summary: row.decision_rationale || '',
    project_id: row.project_id || 'unassigned',
    project_name: project?.name || (row.project_id ? `Project ${row.project_id}` : 'Unassigned project'),
    status: row.status,
    priority,
    priority_reason: row.priority_source || row.priority_band || 'No priority explanation supplied',
    evidence_count: row.evidence_id ? 1 : 0,
    created_at: '',
    last_activity_at: undefined,
  });
}

export async function getReviewCases(params = {}) {
  const response = await unwrap(reviewApi.getQueue(params));
  return Promise.all(response.items.map(mapCase));
}

export async function getCaseById(caseId) {
  if (!caseId) throw new Error('Case ID is required');
  return mapCase(await unwrap(reviewApi.getById(caseId)));
}

async function getCaseRecord(caseId) {
  return unwrap(reviewApi.getById(caseId));
}

export async function getCaseEvidence(caseId) {
  const record = await getCaseRecord(caseId);
  if (!record.evidence_id) return [];
  const evidence = await unwrap(evidenceApi.getById(record.evidence_id));
  let downloadUrl = null;
  try { downloadUrl = (await unwrap(evidenceApi.download(record.evidence_id))).download_url; } catch { /* Sensitive access is separately permissioned. */ }
  return [{
    id: evidence.id,
    case_id: caseId,
    file_name: evidence.filename,
    file_size: evidence.file_size,
    file_type: evidence.content_type || 'application/octet-stream',
    upload_status: 'UPLOADED',
    quarantine_status: 'UNVERIFIED',
    captured_at: undefined,
    uploaded_at: evidence.created_at,
    location: undefined,
    integrity_score: null,
    risk_score: null,
    has_anomaly: false,
    signed_download_url: downloadUrl,
  }];
}

export async function getCaseIntelligence(caseId) {
  const record = await getCaseRecord(caseId);
  if (!record.fusion_run_id) {
    return { analysis_state: 'PENDING', run_timestamp: null, model_version: null, signals: [], limitations: ['No fusion run is linked to this review case.'] };
  }
  const run = await unwrap(fusionApi.getRun(record.fusion_run_id));
  let explanation = null;
  try { explanation = await unwrap(explanationApi.getForRun(record.fusion_run_id)); } catch { /* A materialized explanation may not exist yet. */ }
  return {
    analysis_state: run.run?.status === 'COMPLETED' ? 'AVAILABLE' : run.run?.status === 'FAILED' ? 'FAILED' : 'PENDING',
    run_timestamp: run.run?.completed_at || run.run?.started_at || null,
    model_version: run.run?.method_version || null,
    signals: (explanation?.signals || run.signals || []).map((signal) => ({
      source: signal.source,
      signal_type: signal.signal_type,
      description: signal.reason || signal.method || signal.state,
      score: signal.normalized_value ?? null,
    })),
    limitations: explanation?.unknowns?.map((item) => item.sentence) || [],
  };
}

export async function getCaseHistory(caseId) {
  const response = await unwrap(reviewApi.getHistory(caseId));
  return response.items.map((event) => ({
    id: event.id,
    case_id: caseId,
    event_type: event.event_type,
    actor_identity: event.actor_id || 'System',
    actor_role: undefined,
    timestamp: event.created_at || '',
    rationale: event.to_status ? `${event.from_status || 'Created'} → ${event.to_status}` : undefined,
  }));
}

export async function uploadCaseEvidence(caseId, file) {
  if (!caseId || !file) throw new Error('Case ID and evidence file are required');
  if (file.size > 10 * 1024 * 1024) throw new Error('File exceeds the backend 10 MiB limit.');
  const record = await getCaseRecord(caseId);
  if (!record.project_id) throw new Error('This case has no project context; evidence cannot be linked to it.');
  const { data: uploaded } = await evidenceApi.upload(file);
  await evidenceApi.updateContext(uploaded.evidence_id, { project_id: record.project_id, claim_id: record.claim_id || null });
  return uploaded;
}

export async function submitCaseDecision(caseId, data) {
  const validated = DecisionSubmissionSchema.parse(data);
  return unwrap(reviewApi.recordDecision(caseId, { decision: validated.outcome, rationale: validated.rationale }));
}

export async function createAnalysisJob(evidenceId, jobType = 'fingerprint') {
  return unwrap(evidenceApi.createAnalysisJob({ evidence_id: evidenceId, job_type: jobType }));
}

export async function getAnalysisJob(jobId) {
  return unwrap(evidenceApi.getAnalysisJob(jobId));
}

export async function lookupEvidence(evidenceId) {
  return unwrap(api.get(`/evidence/${evidenceId}`));
}
