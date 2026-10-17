import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';
import { ReviewIcon, SearchIcon, CheckIcon, AlertIcon, ClockIcon } from '../../components/common/Icon';
import { reviewApi } from '../../services/api';

function ReviewQueue() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  // Authoritative Review Cases Seed Data (ADR §2.3, §14.1, PWA Plan §3)
  const defaultCases = [
    {
      id: 'case-001-pmgsy',
      title: 'Rural Road Sub-base & Bitumen Pouring Compliance',
      project_id: 'PRJ-001',
      project_name: 'PMGSY Phase 1 Road Works',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      claim_statement: 'Completion of 12.4 km all-weather rural road connectivity milestone.',
      priority: 'HIGH',
      priority_reason: 'Milestone disbursement deadline in 48 hours; geofence bounds pending confirmation',
      status: 'PENDING_REVIEW',
      evidence_count: 2,
      assigned_to: 'Ramesh Sharma (Reviewer)',
      intake_timestamp: '2024-02-15T16:00:00Z',
      department: 'Ministry of Rural Development',
      jurisdiction: 'Pune District, Maharashtra',
      integrity_signals: {
        hash_status: 'COMPUTED',
        geofence_status: 'COMPLIANT',
        temporal_status: 'NORMAL',
        cross_duplicate: 'NONE_DETECTED'
      }
    },
    {
      id: 'case-002-solar',
      title: 'Surat Ward 4 Solar Street Luminaire Installation',
      project_id: 'PRJ-002',
      project_name: 'Solar Street Light Installation',
      scheme: 'Solar Energy Programme',
      claim_statement: 'Installation of 48 standalone 12W LED solar PV luminaire units along rural arterial routes.',
      priority: 'HIGH',
      priority_reason: 'Cross-evidence perceptual duplicate detected with PMGSY roadbed imagery; geofence 12.4 km out-of-bounds',
      status: 'INVESTIGATING',
      evidence_count: 2,
      assigned_to: 'Sunita Patel (Supervisor)',
      intake_timestamp: '2024-02-20T10:15:00Z',
      department: 'Ministry of New & Renewable Energy',
      jurisdiction: 'Surat District, Gujarat',
      integrity_signals: {
        hash_status: 'COMPUTED',
        geofence_status: 'OUT_OF_BOUNDS',
        temporal_status: 'INVERSION_WARNING',
        cross_duplicate: 'DUPLICATE_FLAGGED'
      }
    },
    {
      id: 'case-003-water',
      title: 'RCC Rural Drinking Water Storage Tank Construction',
      project_id: 'PRJ-003',
      project_name: 'Community Water Tank Construction',
      scheme: 'Jal Jeevan Mission',
      claim_statement: 'Construction and curing of 50,000 litre capacity reinforced concrete community water tank.',
      priority: 'MEDIUM',
      priority_reason: 'Sequential progress verification; milestone 2 completion report',
      status: 'OPEN',
      evidence_count: 1,
      assigned_to: 'Unassigned',
      intake_timestamp: '2024-02-22T16:30:00Z',
      department: 'Department of Drinking Water & Sanitation',
      jurisdiction: 'Jaipur District, Rajasthan',
      integrity_signals: {
        hash_status: 'COMPUTED',
        geofence_status: 'COMPLIANT',
        temporal_status: 'NORMAL',
        cross_duplicate: 'NONE_DETECTED'
      }
    },
    {
      id: 'case-004-school',
      title: 'Primary School Structural Roof & Masonry Renovation',
      project_id: 'PRJ-004',
      project_name: 'School Building Renovation',
      scheme: 'Samagra Shiksha Abhiyan',
      claim_statement: 'Structural earthquake-resistant retrofitting and roof slab casting for 4 classrooms.',
      priority: 'LOW',
      priority_reason: 'Routine quarterly verification tranche',
      status: 'RESOLVED',
      decision: 'SUPPORTED',
      decision_rationale: 'All photographic and temporal submissions match drone survey records and structural audit engineer sign-offs.',
      evidence_count: 3,
      assigned_to: 'Ramesh Sharma (Reviewer)',
      intake_timestamp: '2024-02-28T11:00:00Z',
      department: 'Department of School Education & Literacy',
      jurisdiction: 'Mysuru District, Karnataka',
      integrity_signals: {
        hash_status: 'COMPUTED',
        geofence_status: 'COMPLIANT',
        temporal_status: 'NORMAL',
        cross_duplicate: 'NONE_DETECTED'
      }
    },
    {
      id: 'case-005-health',
      title: 'Primary Health Sub-center Boundary Foundation',
      project_id: 'PRJ-005',
      project_name: 'Community Health Center',
      scheme: 'National Health Mission',
      claim_statement: 'Perimeter foundation excavation and plinth beam beam casting for sub-center block.',
      priority: 'HIGH',
      priority_reason: 'Capture EXIF metadata missing camera serial number; inconclusive temporal consistency',
      status: 'DECISION_PENDING',
      evidence_count: 1,
      assigned_to: 'Rajesh Kulkarni (Reviewer)',
      intake_timestamp: '2024-02-26T09:00:00Z',
      department: 'Ministry of Health & Family Welfare',
      jurisdiction: 'Lucknow District, Uttar Pradesh',
      integrity_signals: {
        hash_status: 'COMPUTED',
        geofence_status: 'UNVERIFIED',
        temporal_status: 'INCONCLUSIVE',
        cross_duplicate: 'NONE_DETECTED'
      }
    }
  ];

  useEffect(() => {
    // Attempt to load live review cases from FastAPI /api/v1/review-cases
    reviewApi.getQueue()
      .then(res => {
        if (res.data && Array.isArray(res.data.items)) {
          setCases(res.data.items);
        } else if (Array.isArray(res.data)) {
          setCases(res.data);
        } else {
          setCases(defaultCases);
        }
      })
      .catch(() => {
        // Safe offline / standalone fallback per ADR §22.1 & PWA spec
        setCases(defaultCases);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const filteredCases = cases.filter(item => {
    const q = searchTerm.toLowerCase();
    const matchesSearch =
      item.id.toLowerCase().includes(q) ||
      (item.title && item.title.toLowerCase().includes(q)) ||
      (item.project_name && item.project_name.toLowerCase().includes(q)) ||
      (item.claim_statement && item.claim_statement.toLowerCase().includes(q)) ||
      (item.jurisdiction && item.jurisdiction.toLowerCase().includes(q));

    const matchesPriority = priorityFilter === 'all' || item.priority === priorityFilter;
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    return matchesSearch && matchesPriority && matchesStatus;
  });

  const getPriorityBadge = (priority) => {
    switch (priority) {
      case 'HIGH':
        return {
          bg: 'var(--govt-danger-light)',
          color: 'var(--govt-danger-text)',
          border: '1px solid var(--govt-danger-border)',
          label: 'Priority: HIGH'
        };
      case 'MEDIUM':
        return {
          bg: 'var(--govt-warning-light)',
          color: 'var(--govt-warning-text)',
          border: '1px solid var(--govt-warning-border)',
          label: 'Priority: MEDIUM'
        };
      default:
        return {
          bg: 'var(--govt-blue-light)',
          color: 'var(--govt-blue-primary)',
          border: '1px solid var(--govt-blue-medium)',
          label: 'Priority: LOW'
        };
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'RESOLVED':
        return { bg: 'var(--govt-success-light)', color: 'var(--govt-success-text)', label: 'RESOLVED' };
      case 'INVESTIGATING':
        return { bg: 'var(--govt-warning-light)', color: 'var(--govt-warning-text)', label: 'INVESTIGATING' };
      case 'DECISION_PENDING':
        return { bg: 'var(--govt-warning-light)', color: 'var(--govt-warning-text)', label: 'DECISION PENDING' };
      case 'ESCALATED':
        return { bg: 'var(--govt-danger-light)', color: 'var(--govt-danger-text)', label: 'ESCALATED' };
      default:
        return { bg: 'var(--govt-gray-light)', color: 'var(--govt-gray-dark)', label: 'PENDING REVIEW' };
    }
  };

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '350px',
        flexDirection: 'column',
        gap: '1rem'
      }}>
        <div className="spinner" style={{ width: '40px', height: '40px', borderWidth: '3px' }}></div>
        <p style={{ margin: 0, color: 'var(--govt-gray-dark)', fontSize: '0.9rem' }}>
          Loading authorized review queue...
        </p>
      </div>
    );
  }

  return (
    <div style={{
      padding: '1.75rem 2rem',
      width: '100%',
      boxSizing: 'border-box',
      backgroundColor: 'var(--govt-gray-off-white)',
    }}>
      {/* Header & Core Principles Notice */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '1.75rem',
        flexWrap: 'wrap',
        gap: '1rem'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span style={{ color: 'var(--govt-blue-primary)' }}><ReviewIcon /></span>
            <h1 style={{
              margin: 0,
              color: 'var(--govt-blue-dark)',
              fontSize: '1.65rem',
              fontWeight: 700,
              letterSpacing: '-0.02em'
            }}>
              Reviewer Investigation Queue
            </h1>
          </div>
          <p style={{
            margin: '0.4rem 0 0 0',
            color: 'var(--govt-gray-dark)',
            fontSize: '0.875rem'
          }}>
            Authorized review triage. Evidence intelligence supports human judgment; it does not replace it.
          </p>
        </div>

        {/* Priority Counts */}
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <div style={{
            backgroundColor: 'var(--govt-danger-light)',
            borderLeft: '4px solid var(--govt-danger)',
            padding: '0.5rem 0.85rem',
            borderRadius: 'var(--radius-sm)'
          }}>
            <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--govt-danger-text)', fontWeight: 600 }}>
              High Attention: {cases.filter(c => c.priority === 'HIGH').length} cases
            </p>
          </div>
          <div style={{
            backgroundColor: 'var(--govt-white)',
            border: '1px solid var(--govt-gray-medium)',
            padding: '0.5rem 0.85rem',
            borderRadius: 'var(--radius-sm)'
          }}>
            <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--govt-gray-text)', fontWeight: 600 }}>
              Total Cases: {cases.length}
            </p>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        padding: '1.25rem 1.5rem',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        marginBottom: '1.5rem',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '1rem',
        alignItems: 'center'
      }}>
        <div style={{ flex: '1 1 280px', position: 'relative' }}>
          <input
            type="text"
            placeholder="Search by Case ID, claim statement, scheme, jurisdiction..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              padding: '0.625rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.875rem',
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            style={{
              padding: '0.625rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.85rem',
              backgroundColor: 'var(--govt-white)',
              cursor: 'pointer'
            }}
          >
            <option value="all">All Priorities</option>
            <option value="HIGH">High Priority</option>
            <option value="MEDIUM">Medium Priority</option>
            <option value="LOW">Low Priority</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              padding: '0.625rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.85rem',
              backgroundColor: 'var(--govt-white)',
              cursor: 'pointer'
            }}
          >
            <option value="all">All Statuses</option>
            <option value="PENDING_REVIEW">Pending Review</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="DECISION_PENDING">Decision Pending</option>
            <option value="RESOLVED">Resolved</option>
          </select>

          {(searchTerm || priorityFilter !== 'all' || statusFilter !== 'all') && (
            <button
              type="button"
              onClick={() => { setSearchTerm(''); setPriorityFilter('all'); setStatusFilter('all'); }}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--govt-blue-primary)',
                fontSize: '0.85rem',
                cursor: 'pointer',
                fontWeight: 600
              }}
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {/* Case Table / Card List */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        overflow: 'hidden'
      }}>
        {filteredCases.length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--govt-gray-dark)' }}>
            <p style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>No review cases match the selected filters.</p>
            <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem' }}>Adjust your search terms or filter selection.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{
                  backgroundColor: 'var(--govt-gray-light)',
                  borderBottom: '2px solid var(--govt-gray-medium)',
                  color: 'var(--govt-gray-dark)',
                  fontSize: '0.75rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px'
                }}>
                  <th style={{ padding: '0.85rem 1.25rem' }}>Case Details</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Scheme & Department</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Priority & Reason</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Integrity Signals</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.85rem 1.25rem', textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredCases.map((c) => {
                  const pBadge = getPriorityBadge(c.priority);
                  const sBadge = getStatusBadge(c.status);

                  return (
                    <tr
                      key={c.id}
                      style={{
                        borderBottom: '1px solid var(--govt-gray-medium)',
                        transition: 'background-color 0.15s ease'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--govt-gray-off-white)'}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                    >
                      {/* Case Details */}
                      <td style={{ padding: '1rem 1.25rem', maxWidth: '300px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                          <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--govt-blue-primary)', fontFamily: 'monospace' }}>
                            {c.id}
                          </span>
                          <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)' }}>
                            • {c.evidence_count} evidence item{c.evidence_count === 1 ? '' : 's'}
                          </span>
                        </div>
                        <div style={{ fontWeight: 600, color: 'var(--govt-blue-dark)', fontSize: '0.9rem', marginBottom: '0.2rem' }}>
                          {c.title}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--govt-gray-text)', lineHeight: 1.4 }}>
                          {c.claim_statement}
                        </div>
                      </td>

                      {/* Scheme & Dept */}
                      <td style={{ padding: '1rem', verticalAlign: 'top' }}>
                        <div style={{ fontWeight: 600, color: 'var(--govt-gray-text)', fontSize: '0.82rem' }}>
                          {c.scheme}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', marginTop: '0.2rem' }}>
                          {c.jurisdiction}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', marginTop: '0.15rem' }}>
                          {c.department}
                        </div>
                      </td>

                      {/* Priority & Reason */}
                      <td style={{ padding: '1rem', verticalAlign: 'top', maxWidth: '240px' }}>
                        <span style={{
                          display: 'inline-block',
                          padding: '0.18rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          backgroundColor: pBadge.bg,
                          color: pBadge.color,
                          border: pBadge.border,
                          marginBottom: '0.35rem'
                        }}>
                          {pBadge.label}
                        </span>
                        <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--govt-gray-text)', lineHeight: 1.35 }}>
                          {c.priority_reason}
                        </p>
                      </td>

                      {/* Integrity Signals */}
                      <td style={{ padding: '1rem', verticalAlign: 'top' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', fontSize: '0.72rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <span style={{ color: 'var(--govt-success)' }}>✓</span>
                            <span>SHA-256 Digest: <strong>{c.integrity_signals.hash_status}</strong></span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <span style={{ color: c.integrity_signals.geofence_status === 'COMPLIANT' ? 'var(--govt-success)' : 'var(--govt-danger)' }}>
                              {c.integrity_signals.geofence_status === 'COMPLIANT' ? '✓' : '⚠'}
                            </span>
                            <span>Geofence: <strong>{c.integrity_signals.geofence_status}</strong></span>
                          </div>
                          {c.integrity_signals.cross_duplicate !== 'NONE_DETECTED' && (
                            <div style={{ color: 'var(--govt-danger-text)', fontWeight: 600 }}>
                              ⚠ Cross-Scheme Duplicate
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Status */}
                      <td style={{ padding: '1rem', verticalAlign: 'top' }}>
                        <span style={{
                          display: 'inline-block',
                          padding: '0.2rem 0.55rem',
                          borderRadius: '9999px',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          backgroundColor: sBadge.bg,
                          color: sBadge.color,
                        }}>
                          {sBadge.label}
                        </span>
                        {c.decision && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--govt-blue-primary)', fontWeight: 600, marginTop: '0.35rem' }}>
                            Outcome: {c.decision}
                          </div>
                        )}
                        <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', marginTop: '0.35rem' }}>
                          Intake: {formatDate(c.intake_timestamp)}
                        </div>
                      </td>

                      {/* Action */}
                      <td style={{ padding: '1rem 1.25rem', verticalAlign: 'middle', textAlign: 'right' }}>
                        <Link
                          to={`/review/case?id=${c.id}`}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.35rem',
                            padding: '0.55rem 0.95rem',
                            borderRadius: 'var(--radius-md)',
                            backgroundColor: 'var(--govt-blue-primary)',
                            color: '#ffffff',
                            textDecoration: 'none',
                            fontSize: '0.82rem',
                            fontWeight: 600,
                            boxShadow: 'var(--shadow-xs)',
                            transition: 'background-color 0.15s ease'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--govt-blue-dark)'}
                          onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--govt-blue-primary)'}
                        >
                          Open Workspace →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Reviewer Operating Principles Banner (ADR §2.2) */}
      <div style={{
        marginTop: '1.75rem',
        padding: '1rem 1.25rem',
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--govt-gray-medium)',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.85rem'
      }}>
        <div style={{ color: 'var(--govt-blue-primary)', marginTop: '0.1rem' }}>
          <AlertIcon />
        </div>
        <div>
          <h4 style={{ margin: 0, fontSize: '0.85rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            Reviewer Governance Contract (ADR Section 14)
          </h4>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.78rem', color: 'var(--govt-gray-dark)', lineHeight: 1.45 }}>
            Decisions must be recorded with an explainable rationale of at least 20 characters. Approved outcomes are strictly limited to
            <strong> SUPPORTED</strong>, <strong>CONTRADICTED</strong>, <strong>INCONCLUSIVE</strong>, and <strong>INSUFFICIENT EVIDENCE</strong>.
            A failed integrity signal or missing metadata does not constitute automatic fraud.
          </p>
        </div>
      </div>
    </div>
  );
}

export default ReviewQueue;
