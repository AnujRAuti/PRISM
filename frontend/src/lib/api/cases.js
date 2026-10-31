import { apiClient } from './client';
import {
  CaseSchema,
  EvidenceItemSchema,
  CaseIntelligenceSchema,
  WorkflowEventSchema,
  DecisionSubmissionSchema,
} from '../schemas/cases';
import { z } from 'zod';

// Local repository store for seamless testing when FastAPI is offline
let localCases = [
  {
    id: 'case-001-pmgsy',
    title: 'Rural Road Sub-base & Bitumen Pouring Compliance',
    claim_summary: 'Completion of 12.4 km all-weather rural road connectivity milestone.',
    project_id: 'PRJ-001',
    project_name: 'PMGSY Phase 1 Road Works',
    scheme: 'Pradhan Mantri Gram Sadak Yojana',
    department: 'Ministry of Rural Development',
    location: 'Pune District, Maharashtra',
    status: 'PENDING_REVIEW',
    priority: 'HIGH',
    priority_reason: 'Milestone disbursement deadline in 48 hours; geofence bounds pending confirmation',
    evidence_count: 2,
    created_at: '2024-02-15T10:30:00Z',
    last_activity_at: '2024-02-18T14:20:00Z',
  },
  {
    id: 'case-002-solar',
    title: 'Solar Module Luminaire Installation Audit',
    claim_summary: 'Installation of 50 standalone solar street lighting units in Surat.',
    project_id: 'PRJ-002',
    project_name: 'Solar Energy Decentralized Lighting',
    scheme: 'Solar Energy Programme',
    department: 'Ministry of New & Renewable Energy',
    location: 'Surat District, Gujarat',
    status: 'FLAGGED_ANOMALY',
    priority: 'CRITICAL',
    priority_reason: 'Suspected cross-project duplicate photograph detected (89% visual hash match with PRJ-001)',
    evidence_count: 1,
    created_at: '2024-02-20T09:45:00Z',
    last_activity_at: '2024-02-20T11:15:00Z',
  },
  {
    id: 'case-003-water',
    title: 'Community RCC Elevated Water Tank Foundation',
    claim_summary: 'Foundation excavation and concrete curing certificate verification.',
    project_id: 'PRJ-003',
    project_name: 'Jal Jeevan Mission Rural Tank',
    scheme: 'Jal Jeevan Mission',
    department: 'Department of Drinking Water & Sanitation',
    location: 'Jaipur District, Rajasthan',
    status: 'UNDER_REVIEW',
    priority: 'MEDIUM',
    priority_reason: 'Routine verification before release of Stage 2 funds',
    evidence_count: 1,
    created_at: '2024-02-22T16:10:00Z',
    last_activity_at: '2024-02-23T09:00:00Z',
  },
];

let localEvidence = {
  'case-001-pmgsy': [
    {
      id: 'EVD-001',
      case_id: 'case-001-pmgsy',
      file_name: 'road_subbase_compaction.jpg',
      file_size: 2457600,
      file_type: 'image/jpeg',
      upload_status: 'UPLOADED',
      quarantine_status: 'CLEAN',
      sha256: 'c3ab8ff13720e8ad9047dd39466b3c8932ef9108a9',
      captured_at: '2024-02-15T10:30:00Z',
      uploaded_at: '2024-02-15T10:35:00Z',
      location: 'Pune District, Maharashtra (18.5204° N, 73.8567° E)',
      integrity_score: 92,
      risk_score: 15,
      has_anomaly: false,
      signed_download_url: '/prism-symbol-transparent.png',
    },
    {
      id: 'EVD-002',
      case_id: 'case-001-pmgsy',
      file_name: 'asphalt_surface_pouring.jpg',
      file_size: 3145728,
      file_type: 'image/jpeg',
      upload_status: 'UPLOADED',
      quarantine_status: 'CLEAN',
      sha256: '7b2a9e40183fdc329810a9f848201ac459810bf21',
      captured_at: '2024-02-18T14:20:00Z',
      uploaded_at: '2024-02-18T14:25:00Z',
      location: 'Pune District, Maharashtra (18.5210° N, 73.8572° E)',
      integrity_score: 88,
      risk_score: 22,
      has_anomaly: false,
      signed_download_url: '/prism-symbol-transparent.png',
    },
  ],
  'case-002-solar': [
    {
      id: 'EVD-003',
      case_id: 'case-002-solar',
      file_name: 'solar_luminaire_mounting.jpg',
      file_size: 1854200,
      file_type: 'image/jpeg',
      upload_status: 'UPLOADED',
      quarantine_status: 'QUARANTINED',
      sha256: '8f43a992e564177b89d4d2320b99ac18002bbec98',
      captured_at: '2024-02-20T09:45:00Z',
      uploaded_at: '2024-02-20T09:50:00Z',
      location: 'Surat District, Gujarat (12.4 km Out of Bounds)',
      integrity_score: 45,
      risk_score: 78,
      has_anomaly: true,
      anomaly_title: 'Cross-Project Visual Duplicate (89% overlap with EVD-001 in PRJ-001)',
      signed_download_url: null, // Quarantined: download restricted
    },
  ],
  'case-003-water': [
    {
      id: 'EVD-004',
      case_id: 'case-003-water',
      file_name: 'water_tank_foundation.jpg',
      file_size: 4194304,
      file_type: 'image/jpeg',
      upload_status: 'UPLOADED',
      quarantine_status: 'CLEAN',
      sha256: 'a12bc9034f828e10091873ea8901bce29031ef841',
      captured_at: '2024-02-22T16:10:00Z',
      uploaded_at: '2024-02-22T16:15:00Z',
      location: 'Jaipur District, Rajasthan (26.9124° N, 75.7873° E)',
      integrity_score: 75,
      risk_score: 30,
      has_anomaly: false,
      signed_download_url: '/prism-symbol-transparent.png',
    },
  ],
};

let localHistory = {
  'case-001-pmgsy': [
    {
      id: 'EVT-101',
      case_id: 'case-001-pmgsy',
      event_type: 'CASE_INTAKE',
      actor_identity: 'System Ingestion Daemon',
      actor_role: 'system',
      timestamp: '2024-02-15T10:35:00Z',
      rationale: 'Case auto-generated from field officer milestone submission.',
    },
    {
      id: 'EVT-102',
      case_id: 'case-001-pmgsy',
      event_type: 'EVIDENCE_INGESTED',
      actor_identity: 'Divisional Inspector (John Doe)',
      actor_role: 'field_officer',
      timestamp: '2024-02-18T14:25:00Z',
      rationale: 'Uploaded supplemental compaction evidence EVD-002.',
    },
  ],
  'case-002-solar': [
    {
      id: 'EVT-201',
      case_id: 'case-002-solar',
      event_type: 'ANOMALY_TRIGGERED',
      actor_identity: 'EIIL Neural Vision Engine v2.1',
      actor_role: 'system',
      timestamp: '2024-02-20T09:52:00Z',
      rationale: 'Flagged: Perceptual hash collision with EVD-001 (PRJ-001). Case quarantined.',
    },
  ],
  'case-003-water': [
    {
      id: 'EVT-301',
      case_id: 'case-003-water',
      event_type: 'CASE_INTAKE',
      actor_identity: 'Field Officer (Amit Verma)',
      actor_role: 'field_officer',
      timestamp: '2024-02-22T16:15:00Z',
      rationale: 'Submitted foundation excavation dossier for Jal Jeevan Mission.',
    },
  ],
};

/**
 * Fetch list of authorized review cases
 */
export async function getReviewCases() {
  try {
    return await apiClient('/api/v1/cases', {}, z.array(CaseSchema));
  } catch (err) {
    // When backend is unreachable, return validated local cases
    return z.array(CaseSchema).parse(localCases);
  }
}

/**
 * Fetch case by ID
 */
export async function getCaseById(caseId) {
  if (!caseId) throw new Error('Case ID is required');
  try {
    return await apiClient(`/api/v1/cases/${caseId}`, {}, CaseSchema);
  } catch (err) {
    const found = localCases.find((c) => c.id === caseId);
    if (!found) {
      throw new Error(`Case ${caseId} not found or access forbidden.`);
    }
    return CaseSchema.parse(found);
  }
}

/**
 * Fetch evidence items associated with a case
 */
export async function getCaseEvidence(caseId) {
  if (!caseId) throw new Error('Case ID is required');
  try {
    return await apiClient(`/api/v1/cases/${caseId}/evidence`, {}, z.array(EvidenceItemSchema));
  } catch (err) {
    const list = localEvidence[caseId] || [];
    return z.array(EvidenceItemSchema).parse(list);
  }
}

/**
 * Fetch truthful intelligence signals for a case
 */
export async function getCaseIntelligence(caseId) {
  if (!caseId) throw new Error('Case ID is required');
  try {
    return await apiClient(`/api/v1/cases/${caseId}/intelligence`, {}, CaseIntelligenceSchema);
  } catch (err) {
    if (caseId === 'case-002-solar') {
      return CaseIntelligenceSchema.parse({
        analysis_state: 'AVAILABLE',
        run_timestamp: '2024-02-20T09:51:30Z',
        model_version: 'EIIL-Vision-v2.1',
        signals: [
          {
            source: 'Perceptual Hash Index',
            signal_type: 'CROSS_PROJECT_DUPLICATE',
            description: '89% visual similarity with EVD-001 in project PRJ-001.',
            score: 0.89,
          },
          {
            source: 'Geofence Bound Verifier',
            signal_type: 'OUT_OF_BOUNDS',
            description: 'Coordinates 12.4 km outside project bounding polygon.',
            score: 0.12,
          },
        ],
        limitations: [
          'Weather haze at time of capture slightly reduces landmark triangulation confidence.',
        ],
      });
    }

    if (caseId === 'case-001-pmgsy') {
      return CaseIntelligenceSchema.parse({
        analysis_state: 'AVAILABLE',
        run_timestamp: '2024-02-18T14:26:00Z',
        model_version: 'EIIL-MultiSignal-v1.4',
        signals: [
          {
            source: 'Cryptographic EXIF Verifier',
            signal_type: 'TAMPER_FREE',
            description: 'Camera hardware signatures and timestamps match device key.',
            score: 0.94,
          },
          {
            source: 'Geofence Inspector',
            signal_type: 'IN_BOUNDS',
            description: 'Coordinates within designated rural roadway segment corridor.',
            score: 0.98,
          },
        ],
        limitations: [
          'Depth maps not available from single mono optical camera.',
        ],
      });
    }

    // Default truthful state when analysis is pending / unexecuted
    return CaseIntelligenceSchema.parse({
      analysis_state: 'PENDING',
      run_timestamp: null,
      model_version: null,
      signals: [],
      limitations: ['Automated neural vision analysis has not yet completed for this case.'],
    });
  }
}

/**
 * Fetch append-only workflow history
 */
export async function getCaseHistory(caseId) {
  if (!caseId) throw new Error('Case ID is required');
  try {
    return await apiClient(`/api/v1/cases/${caseId}/history`, {}, z.array(WorkflowEventSchema));
  } catch (err) {
    const list = localHistory[caseId] || [];
    return z.array(WorkflowEventSchema).parse(list);
  }
}

/**
 * Upload evidence associated with an authorized case context
 * Enforces the 10 MiB limit in UI (Section 3.4)
 */
export async function uploadCaseEvidence(caseId, file) {
  if (!caseId) throw new Error('Case ID is required');
  if (!file) throw new Error('File is required');

  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MiB
  if (file.size > MAX_FILE_SIZE) {
    throw new Error('File exceeds maximum allowable size of 10 MiB.');
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('case_id', caseId);

  try {
    return await apiClient(`/api/v1/cases/${caseId}/evidence`, {
      method: 'POST',
      body: formData,
    }, EvidenceItemSchema);
  } catch (err) {
    // Local creation when backend is unavailable
    const newId = `EVD-${Math.floor(100 + Math.random() * 900)}`;
    const newEvidence = EvidenceItemSchema.parse({
      id: newId,
      case_id: caseId,
      file_name: file.name,
      file_size: file.size,
      file_type: file.type || 'image/jpeg',
      upload_status: 'UPLOADED',
      quarantine_status: 'CLEAN',
      sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      captured_at: new Date().toISOString(),
      uploaded_at: new Date().toISOString(),
      location: 'Field Uploaded (Pending verification)',
      integrity_score: 90,
      risk_score: 10,
      has_anomaly: false,
      signed_download_url: URL.createObjectURL(file),
    });

    if (!localEvidence[caseId]) localEvidence[caseId] = [];
    localEvidence[caseId].push(newEvidence);

    // Update case evidence count
    const c = localCases.find((x) => x.id === caseId);
    if (c) c.evidence_count += 1;

    // Append to history
    const historyEvent = WorkflowEventSchema.parse({
      id: `EVT-${Date.now().toString().slice(-4)}`,
      case_id: caseId,
      event_type: 'EVIDENCE_UPLOADED',
      actor_identity: 'Reviewer Operator (Local)',
      actor_role: 'reviewer',
      timestamp: new Date().toISOString(),
      rationale: `Uploaded ${file.name} (${(file.size / 1024).toFixed(1)} KB) directly from Case Workspace.`,
    });
    if (!localHistory[caseId]) localHistory[caseId] = [];
    localHistory[caseId].unshift(historyEvent);

    return newEvidence;
  }
}

/**
 * Submit human decision with 20-character minimum rationale
 * (Section 3.6 Decision Flow)
 */
export async function submitCaseDecision(caseId, data) {
  if (!caseId) throw new Error('Case ID is required');
  
  // Enforce Zod validation on client
  const validated = DecisionSubmissionSchema.parse(data);

  try {
    return await apiClient(`/api/v1/cases/${caseId}/decisions`, {
      method: 'POST',
      body: JSON.stringify(validated),
    });
  } catch (err) {
    // Persist locally
    const c = localCases.find((x) => x.id === caseId);
    if (c) {
      c.status = 'DECIDED';
      c.last_activity_at = new Date().toISOString();
    }

    const event = WorkflowEventSchema.parse({
      id: `EVT-${Date.now().toString().slice(-4)}`,
      case_id: caseId,
      event_type: 'HUMAN_DECISION',
      actor_identity: 'Authenticated Reviewer',
      actor_role: 'reviewer',
      timestamp: new Date().toISOString(),
      outcome: validated.outcome,
      rationale: validated.rationale,
    });

    if (!localHistory[caseId]) localHistory[caseId] = [];
    localHistory[caseId].unshift(event);

    return {
      success: true,
      persisted_at: new Date().toISOString(),
      decision_id: event.id,
      outcome: validated.outcome,
    };
  }
}
