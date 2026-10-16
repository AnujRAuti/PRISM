import { z } from 'zod';

/**
 * 4 Supported Human Decision Outcomes
 * (Per PoA PWA Plan Section 3.6)
 */
export const DecisionOutcomeEnum = z.enum([
  'SUPPORTED',
  'CONTRADICTED',
  'INCONCLUSIVE',
  'INSUFFICIENT_EVIDENCE',
]);

/**
 * Case Status Enum
 */
export const CaseStatusEnum = z.enum([
  'PENDING_REVIEW',
  'UNDER_REVIEW',
  'DECIDED',
  'FLAGGED_ANOMALY',
  'CLOSED',
]);

/**
 * Evidence Ingestion & Quarantine Status
 */
export const QuarantineStatusEnum = z.enum([
  'CLEAN',
  'QUARANTINED',
  'SUSPECT_METADATA',
  'UNVERIFIED',
]);

/**
 * Critical Case Response Schema
 */
export const CaseSchema = z.object({
  id: z.string().min(1, 'Case UUID required'),
  title: z.string().min(1, 'Case title required'),
  claim_summary: z.string().optional().default(''),
  project_id: z.string().min(1),
  project_name: z.string().min(1),
  scheme: z.string().optional().default(''),
  department: z.string().optional().default(''),
  location: z.string().optional().default(''),
  status: z.string(),
  priority: z.enum(['HIGH', 'MEDIUM', 'LOW', 'CRITICAL']).optional().default('MEDIUM'),
  priority_reason: z.string().optional().default('Standard intake workflow'),
  evidence_count: z.number().int().nonnegative().optional().default(0),
  created_at: z.string(),
  last_activity_at: z.string().optional(),
});

/**
 * Critical Evidence Item Schema
 */
export const EvidenceItemSchema = z.object({
  id: z.string(),
  case_id: z.string(),
  file_name: z.string(),
  file_size: z.number().int().nonnegative(),
  file_type: z.string(),
  upload_status: z.enum(['UPLOADED', 'PENDING', 'PROCESSING', 'FAILED']),
  quarantine_status: QuarantineStatusEnum.default('UNVERIFIED'),
  sha256: z.string().optional(),
  captured_at: z.string().optional(),
  uploaded_at: z.string().optional(),
  location: z.string().optional(),
  integrity_score: z.number().min(0).max(100).nullable().optional(),
  risk_score: z.number().min(0).max(100).nullable().optional(),
  has_anomaly: z.boolean().optional().default(false),
  anomaly_title: z.string().nullable().optional(),
  signed_download_url: z.string().nullable().optional(),
});

/**
 * Case Intelligence Schema (Truthful states, no fake findings)
 */
export const CaseIntelligenceSchema = z.object({
  analysis_state: z.enum(['AVAILABLE', 'PENDING', 'UNAVAILABLE', 'FAILED']),
  run_timestamp: z.string().nullable().optional(),
  model_version: z.string().nullable().optional(),
  signals: z.array(z.object({
    source: z.string(),
    signal_type: z.string(),
    description: z.string(),
    score: z.number().nullable().optional(),
  })).optional().default([]),
  limitations: z.array(z.string()).optional().default([]),
});

/**
 * Workflow History Event Schema
 */
export const WorkflowEventSchema = z.object({
  id: z.string(),
  case_id: z.string(),
  event_type: z.string(),
  actor_identity: z.string(),
  actor_role: z.string().optional(),
  timestamp: z.string(),
  outcome: DecisionOutcomeEnum.optional(),
  rationale: z.string().optional(),
});

/**
 * Decision Submission Form Schema
 * Enforces 20-character minimum rationale constraint (Section 3.6)
 */
export const DecisionSubmissionSchema = z.object({
  outcome: DecisionOutcomeEnum,
  rationale: z.string()
    .trim()
    .min(20, 'Rationale must be at least 20 characters explaining the factual basis of the decision.'),
});
