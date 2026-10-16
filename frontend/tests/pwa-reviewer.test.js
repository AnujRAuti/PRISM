import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  DecisionOutcomeEnum,
  DecisionSubmissionSchema,
  CaseSchema,
  EvidenceItemSchema,
  QuarantineStatusEnum,
  CaseIntelligenceSchema,
} from '../src/lib/schemas/cases.js';

describe('PoA PWA Reviewer Workflow & Contracts (Section 3.6 & 9)', () => {
  test('Decision outcome enum strictly allows the 4 supported outcomes', () => {
    const validOutcomes = ['SUPPORTED', 'CONTRADICTED', 'INCONCLUSIVE', 'INSUFFICIENT_EVIDENCE'];
    for (const outcome of validOutcomes) {
      assert.equal(DecisionOutcomeEnum.parse(outcome), outcome);
    }
  });

  test('Decision outcome enum rejects arbitrary or legacy statuses', () => {
    const invalidOutcomes = ['APPROVED', 'REJECTED', 'PASS', 'FAIL', ''];
    for (const invalid of invalidOutcomes) {
      assert.throws(() => DecisionOutcomeEnum.parse(invalid));
    }
  });

  test('Decision submission schema enforces 20-character minimum rationale constraint', () => {
    // Under 20 characters: must throw
    assert.throws(() => {
      DecisionSubmissionSchema.parse({
        outcome: 'SUPPORTED',
        rationale: 'Too short rationale', // 19 chars
      });
    }, /at least 20 characters/);

    // 20 characters exactly: must pass
    const exactly20 = DecisionSubmissionSchema.parse({
      outcome: 'SUPPORTED',
      rationale: '12345678901234567890',
    });
    assert.equal(exactly20.rationale.length, 20);

    // Realistic factual rationale: must pass
    const valid = DecisionSubmissionSchema.parse({
      outcome: 'CONTRADICTED',
      rationale: 'Inspected photographic evidence reveals 89% cross-project visual overlap with EVD-001 in PRJ-001.',
    });
    assert.equal(valid.outcome, 'CONTRADICTED');
  });

  test('Case schema validates required fields and priority', () => {
    const rawCase = {
      id: 'case-test-uuid-001',
      title: 'Solar Panel Array Inspection',
      project_id: 'PRJ-002',
      project_name: 'Solar Phase 1',
      status: 'PENDING_REVIEW',
      priority: 'HIGH',
      priority_reason: 'Disbursement milestone within 48h',
      evidence_count: 3,
      created_at: '2024-02-20T10:00:00Z',
    };

    const parsed = CaseSchema.parse(rawCase);
    assert.equal(parsed.id, 'case-test-uuid-001');
    assert.equal(parsed.priority, 'HIGH');
  });

  test('Evidence item schema validates quarantine policy and size limits', () => {
    const cleanEvidence = {
      id: 'EVD-999',
      case_id: 'case-test-uuid-001',
      file_name: 'inspection_site.jpg',
      file_size: 5242880, // 5 MiB (within 10 MiB limit)
      file_type: 'image/jpeg',
      upload_status: 'UPLOADED',
      quarantine_status: 'CLEAN',
      sha256: '9901bfd14820acbd7401928374a81b23',
    };

    const parsed = EvidenceItemSchema.parse(cleanEvidence);
    assert.equal(parsed.quarantine_status, 'CLEAN');
    assert.equal(parsed.file_size, 5242880);

    // Quarantine status enum strictly validated
    assert.equal(QuarantineStatusEnum.parse('QUARANTINED'), 'QUARANTINED');
    assert.throws(() => QuarantineStatusEnum.parse('INVALID_QUARANTINE_STATE'));
  });

  test('Intelligence schema requires truthful analysis state without fabricated scores', () => {
    const truthfulPending = {
      analysis_state: 'PENDING',
      signals: [],
      limitations: ['Worker analysis pending.'],
    };

    const parsed = CaseIntelligenceSchema.parse(truthfulPending);
    assert.equal(parsed.analysis_state, 'PENDING');
    assert.equal(parsed.run_timestamp, undefined);
  });
});
