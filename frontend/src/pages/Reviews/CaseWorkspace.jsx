import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import {
  getCaseById,
  getCaseEvidence,
  getCaseIntelligence,
  getCaseHistory,
  uploadCaseEvidence,
  submitCaseDecision,
} from '../../lib/api/cases';
import {
  CheckIcon,
  CrossIcon,
  AlertIcon,
  ClockIcon,
  DownloadIcon,
  UploadIcon,
  EvidenceIcon,
} from '../../components/common/Icon';
import { formatDate, formatFileSize } from '../../utils/helpers';

export default function CaseWorkspace() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const caseId = searchParams.get('id');

  // Core Data States
  const [caseData, setCaseData] = useState(null);
  const [evidenceList, setEvidenceList] = useState([]);
  const [intelligence, setIntelligence] = useState(null);
  const [history, setHistory] = useState([]);
  const [activeTab, setActiveTab] = useState('overview'); // overview, evidence, intelligence, history, decision

  // Status & Error States
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [forbidden, setForbidden] = useState(false);

  // Decision Form States (Section 3.6)
  const [selectedOutcome, setSelectedOutcome] = useState('');
  const [rationale, setRationale] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [decisionError, setDecisionError] = useState(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [decisionSuccess, setDecisionSuccess] = useState(null);

  // Evidence Upload Modal States (Section 3.4)
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  useEffect(() => {
    if (!caseId) {
      setError('Missing case identifier. Please select a valid case from the queue.');
      setLoading(false);
      return;
    }
    loadCaseWorkspace(caseId);
  }, [caseId]);

  const loadCaseWorkspace = async (id) => {
    setLoading(true);
    setError(null);
    setForbidden(false);

    try {
      const [caseRes, evidenceRes, intelRes, historyRes] = await Promise.all([
        getCaseById(id),
        getCaseEvidence(id),
        getCaseIntelligence(id),
        getCaseHistory(id),
      ]);

      setCaseData(caseRes);
      setEvidenceList(evidenceRes);
      setIntelligence(intelRes);
      setHistory(historyRes);
    } catch (err) {
      if (err.category === 'FORBIDDEN' || err.status === 403) {
        setForbidden(true);
      } else {
        setError(err.message || 'Failed to load case workspace from backend.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Decision Submission Handler
  const handleDecisionSubmit = async () => {
    if (!selectedOutcome) {
      setDecisionError('Please select one of the four supported human decision outcomes.');
      return;
    }
    if (rationale.trim().length < 20) {
      setDecisionError('Rationale must be at least 20 characters explaining the factual basis.');
      return;
    }

    setSubmitting(true);
    setDecisionError(null);

    try {
      const res = await submitCaseDecision(caseId, {
        outcome: selectedOutcome,
        rationale: rationale.trim(),
      });

      setDecisionSuccess(res);
      setShowConfirmModal(false);
      // Reload authoritative server state
      await loadCaseWorkspace(caseId);
    } catch (err) {
      setDecisionError(err.message || 'Outcome unknown; checking server state. Please do not re-submit blindly.');
    } finally {
      setSubmitting(false);
    }
  };

  // Evidence Upload Handler (10 MiB limit enforced)
  const handleUploadSubmit = async (e) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError('Please select an image file to upload.');
      return;
    }

    const MAX_SIZE = 10 * 1024 * 1024;
    if (uploadFile.size > MAX_SIZE) {
      setUploadError('File exceeds the 10 MiB limit enforced for verification security.');
      return;
    }

    setUploading(true);
    setUploadError(null);

    try {
      await uploadCaseEvidence(caseId, uploadFile);
      setUploadFile(null);
      setShowUploadModal(false);
      // Refresh authoritative case evidence list
      const updatedEvidence = await getCaseEvidence(caseId);
      setEvidenceList(updatedEvidence);
      const updatedHistory = await getCaseHistory(caseId);
      setHistory(updatedHistory);
    } catch (err) {
      setUploadError(err.message || 'Failed to ingest evidence. Reconciling with server...');
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '3rem 2rem', textAlign: 'center', width: '100%', boxSizing: 'border-box' }}>
        <div className="spinner" style={{ width: '42px', height: '42px', margin: '0 auto 1rem' }}></div>
        <h3 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.1rem' }}>
          Authorizing Case Access...
        </h3>
        <p style={{ margin: '0.4rem 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.85rem' }}>
          Verifying Supabase JWT permissions and project boundary scopes.
        </p>
      </div>
    );
  }

  if (forbidden) {
    return (
      <div style={{ padding: '3rem 2rem', maxWidth: '600px', margin: '0 auto', textAlign: 'center' }}>
        <div style={{ color: 'var(--govt-danger)', marginBottom: '1rem' }}>
          <AlertIcon />
        </div>
        <h2 style={{ color: 'var(--govt-blue-dark)', fontSize: '1.4rem', margin: '0 0 0.5rem 0' }}>
          403 Access Forbidden
        </h2>
        <p style={{ color: 'var(--govt-gray-dark)', fontSize: '0.9rem', lineHeight: '1.5' }}>
          Your authenticated reviewer credentials do not grant access to case <code>{caseId}</code> or its parent project scope.
        </p>
        <Link
          to="/review"
          style={{
            display: 'inline-block',
            marginTop: '1rem',
            padding: '0.6rem 1.25rem',
            backgroundColor: 'var(--govt-blue-primary)',
            color: '#ffffff',
            borderRadius: 'var(--radius-md)',
            fontWeight: '600',
            fontSize: '0.875rem',
          }}
        >
          Return to Authorized Queue
        </Link>
      </div>
    );
  }

  if (error || !caseData) {
    return (
      <div style={{ padding: '3rem 2rem', maxWidth: '600px', margin: '0 auto', textAlign: 'center' }}>
        <h2 style={{ color: 'var(--govt-blue-dark)', fontSize: '1.3rem', margin: '0 0 0.5rem 0' }}>
          Case Unavailable
        </h2>
        <p style={{ color: 'var(--govt-danger)', fontSize: '0.9rem', marginBottom: '1.25rem' }}>
          {error || 'Unable to retrieve case record.'}
        </p>
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
          <button
            onClick={() => loadCaseWorkspace(caseId)}
            style={{
              padding: '0.55rem 1rem',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              fontWeight: '600',
              cursor: 'pointer',
            }}
          >
            Retry Safe Read
          </button>
          <Link
            to="/review"
            style={{
              padding: '0.55rem 1rem',
              backgroundColor: 'var(--govt-white)',
              color: 'var(--govt-gray-text)',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-md)',
              fontWeight: '600',
              textDecoration: 'none',
            }}
          >
            Back to Queue
          </Link>
        </div>
      </div>
    );
  }

  const outcomeColors = {
    SUPPORTED: { bg: 'var(--govt-success-light)', border: 'var(--govt-success)', text: 'var(--govt-success-text)' },
    CONTRADICTED: { bg: 'var(--govt-danger-light)', border: 'var(--govt-danger)', text: 'var(--govt-danger-text)' },
    INCONCLUSIVE: { bg: 'var(--govt-warning-light)', border: 'var(--govt-warning)', text: 'var(--govt-warning-text)' },
    INSUFFICIENT_EVIDENCE: { bg: 'var(--govt-info-light)', border: 'var(--govt-info)', text: 'var(--govt-info-text)' },
  };

  return (
    <div style={{ padding: '1.75rem 2rem', width: '100%', boxSizing: 'border-box', backgroundColor: 'var(--govt-gray-off-white)' }}>
      {/* Top Breadcrumb & Status Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        flexWrap: 'wrap',
        gap: '1rem',
        marginBottom: '1.5rem',
        paddingBottom: '1.25rem',
        borderBottom: '1px solid var(--govt-gray-medium)',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', color: 'var(--govt-gray-dark)', marginBottom: '0.35rem' }}>
            <Link to="/review" style={{ color: 'var(--govt-blue-primary)', fontWeight: '600' }}>Reviewer Queue</Link>
            <span>/</span>
            <span style={{ fontFamily: 'var(--font-family-mono)', color: 'var(--govt-gray-title)' }}>{caseData.id}</span>
          </div>
          <h1 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.55rem', fontWeight: '700', letterSpacing: '-0.02em' }}>
            {caseData.title}
          </h1>
          <p style={{ margin: '0.3rem 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
            {caseData.project_name} · {caseData.scheme || 'Public Infrastructure'}
          </p>
        </div>

        {/* Priority & Status Badges */}
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span style={{
            fontSize: '0.75rem',
            fontWeight: '700',
            padding: '0.25rem 0.65rem',
            borderRadius: 'var(--radius-full)',
            backgroundColor: caseData.priority === 'CRITICAL' ? 'var(--govt-danger-light)' : 'var(--govt-blue-light)',
            color: caseData.priority === 'CRITICAL' ? 'var(--govt-danger-text)' : 'var(--govt-blue-primary)',
            border: `1px solid ${caseData.priority === 'CRITICAL' ? 'var(--govt-danger-border)' : 'rgba(37, 99, 235, 0.2)'}`,
          }}>
            Priority: {caseData.priority}
          </span>
          <span style={{
            fontSize: '0.75rem',
            fontWeight: '700',
            padding: '0.25rem 0.65rem',
            borderRadius: 'var(--radius-full)',
            backgroundColor: caseData.status === 'DECIDED' ? 'var(--govt-success-light)' : 'var(--govt-warning-light)',
            color: caseData.status === 'DECIDED' ? 'var(--govt-success-text)' : 'var(--govt-warning-text)',
            border: `1px solid ${caseData.status === 'DECIDED' ? 'var(--govt-success-border)' : 'var(--govt-warning-border)'}`,
          }}>
            {caseData.status.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* 5-Section Nav Tabs (Section 3.3) */}
      <div style={{
        display: 'flex',
        gap: '0.5rem',
        borderBottom: '1px solid var(--govt-gray-medium)',
        marginBottom: '1.5rem',
        overflowX: 'auto',
      }}>
        {[
          { key: 'overview', label: '1. Overview' },
          { key: 'evidence', label: `2. Evidence (${evidenceList.length})` },
          { key: 'intelligence', label: '3. Intelligence Signals' },
          { key: 'history', label: `4. Timeline (${history.length})` },
          { key: 'decision', label: '5. Reviewer Decision' },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              padding: '0.65rem 1.15rem',
              backgroundColor: 'transparent',
              border: 'none',
              borderBottom: activeTab === tab.key ? '2.5px solid var(--govt-blue-primary)' : '2.5px solid transparent',
              color: activeTab === tab.key ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
              fontSize: '0.875rem',
              fontWeight: activeTab === tab.key ? '700' : '500',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'all 0.15s ease',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* SECTION 1: OVERVIEW */}
      {activeTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem', alignItems: 'start' }}>
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--govt-gray-medium)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <h2 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', color: 'var(--govt-blue-dark)', fontWeight: '700' }}>
              Claim Statement & Context
            </h2>
            <p style={{ fontSize: '0.95rem', color: 'var(--govt-gray-text)', lineHeight: 1.6, margin: '0 0 1.5rem' }}>
              {caseData.claim_summary || 'No claim summary provided.'}
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', borderTop: '1px solid var(--govt-gray-light)', paddingTop: '1.25rem' }}>
              <div>
                <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--govt-gray-dark)', textTransform: 'uppercase', fontWeight: '700' }}>
                  Project ID
                </span>
                <strong style={{ fontSize: '0.875rem', color: 'var(--govt-blue-primary)' }}>{caseData.project_id}</strong>
              </div>
              <div>
                <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--govt-gray-dark)', textTransform: 'uppercase', fontWeight: '700' }}>
                  Jurisdiction
                </span>
                <span style={{ fontSize: '0.875rem', color: 'var(--govt-gray-text)' }}>{caseData.location}</span>
              </div>
              <div>
                <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--govt-gray-dark)', textTransform: 'uppercase', fontWeight: '700' }}>
                  Intake Timestamp
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--govt-gray-text)' }}>{formatDate(caseData.created_at)}</span>
              </div>
              <div>
                <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--govt-gray-dark)', textTransform: 'uppercase', fontWeight: '700' }}>
                  Department
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--govt-gray-text)' }}>{caseData.department}</span>
              </div>
            </div>
          </div>

          {/* Review Priority Explanation */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--govt-gray-medium)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <h2 style={{ margin: '0 0 0.75rem 0', fontSize: '1rem', color: 'var(--govt-blue-dark)', fontWeight: '700' }}>
              Priority Evaluation
            </h2>
            <div style={{
              backgroundColor: 'var(--govt-gray-off-white)',
              border: '1px solid var(--govt-gray-medium)',
              borderLeft: '4px solid var(--govt-blue-primary)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.85rem 1rem',
              fontSize: '0.85rem',
              color: 'var(--govt-gray-text)',
              lineHeight: 1.5,
            }}>
              <strong>Reason: </strong>
              {caseData.priority_reason}
            </div>
            <p style={{ margin: '1rem 0 0', fontSize: '0.78rem', color: 'var(--govt-gray-dark)' }}>
              Priority is assigned by intake policy rules to facilitate timely reviewer attention, not as a final fraud verdict.
            </p>
          </div>
        </div>
      )}

      {/* SECTION 2: EVIDENCE */}
      {activeTab === 'evidence' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--govt-blue-dark)', fontWeight: '700' }}>
              Case Associated Evidence
            </h2>
            <button
              onClick={() => setShowUploadModal(true)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                backgroundColor: 'var(--govt-blue-primary)',
                color: '#ffffff',
                border: 'none',
                padding: '0.55rem 1rem',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.85rem',
                fontWeight: '600',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              <UploadIcon />
              Upload Case Evidence
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
            {evidenceList.map((item) => (
              <div
                key={item.id}
                style={{
                  backgroundColor: 'var(--govt-white)',
                  borderRadius: 'var(--radius-lg)',
                  border: item.quarantine_status === 'QUARANTINED' ? '1.5px solid var(--govt-danger-border)' : '1px solid var(--govt-gray-medium)',
                  padding: '1.25rem',
                  boxShadow: 'var(--shadow-sm)',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.65rem' }}>
                    <span style={{
                      fontSize: '0.72rem',
                      fontWeight: '700',
                      padding: '0.15rem 0.55rem',
                      borderRadius: 'var(--radius-full)',
                      backgroundColor: item.quarantine_status === 'QUARANTINED' ? 'var(--govt-danger-light)' : 'var(--govt-blue-light)',
                      color: item.quarantine_status === 'QUARANTINED' ? 'var(--govt-danger-text)' : 'var(--govt-blue-primary)',
                    }}>
                      {item.quarantine_status}
                    </span>
                    <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-family-mono)', color: 'var(--govt-gray-dark)' }}>
                      {item.id}
                    </span>
                  </div>

                  <h3 style={{ margin: '0 0 0.35rem', fontSize: '0.95rem', fontWeight: '700', color: 'var(--govt-gray-title)' }}>
                    {item.file_name}
                  </h3>
                  <p style={{ margin: '0 0 0.85rem', fontSize: '0.78rem', color: 'var(--govt-gray-dark)' }}>
                    {formatFileSize(item.file_size)} · {formatDate(item.uploaded_at)}
                  </p>

                  {item.has_anomaly && (
                    <div style={{
                      backgroundColor: 'var(--govt-danger-light)',
                      border: '1px solid var(--govt-danger-border)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '0.5rem 0.75rem',
                      fontSize: '0.78rem',
                      color: 'var(--govt-danger-text)',
                      fontWeight: '600',
                      marginBottom: '0.85rem',
                    }}>
                      ⚠️ {item.anomaly_title}
                    </div>
                  )}

                  <div style={{ fontSize: '0.78rem', color: 'var(--govt-gray-text)', backgroundColor: 'var(--govt-gray-off-white)', padding: '0.6rem 0.75rem', borderRadius: 'var(--radius-sm)', marginBottom: '0.85rem' }}>
                    <div style={{ marginBottom: '0.2rem' }}>
                      <span style={{ color: 'var(--govt-gray-dark)' }}>Location: </span>
                      {item.location}
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)' }}>SHA-256: </span>
                      <code style={{ fontSize: '0.72rem' }}>{item.sha256 ? `${item.sha256.slice(0, 16)}...` : 'N/A'}</code>
                    </div>
                  </div>
                </div>

                {/* Authorized Retrieval Action */}
                <div style={{ borderTop: '1px solid var(--govt-gray-light)', paddingTop: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  {item.signed_download_url ? (
                    <a
                      href={item.signed_download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontSize: '0.8rem',
                        fontWeight: '600',
                        color: 'var(--govt-blue-primary)',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.35rem',
                      }}
                    >
                      <DownloadIcon />
                      Authorized View / Download
                    </a>
                  ) : (
                    <span style={{ fontSize: '0.78rem', color: 'var(--govt-danger)', fontWeight: '600' }}>
                      Download restricted (Quarantine Policy)
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SECTION 3: INTELLIGENCE */}
      {activeTab === 'intelligence' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--govt-gray-medium)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--govt-blue-dark)', fontWeight: '700' }}>
                Multi-Signal Analysis Intelligence
              </h2>
              <span style={{
                fontSize: '0.75rem',
                fontWeight: '700',
                padding: '0.25rem 0.65rem',
                borderRadius: 'var(--radius-full)',
                backgroundColor: intelligence?.analysis_state === 'AVAILABLE' ? 'var(--govt-success-light)' : 'var(--govt-warning-light)',
                color: intelligence?.analysis_state === 'AVAILABLE' ? 'var(--govt-success-text)' : 'var(--govt-warning-text)',
              }}>
                Status: {intelligence?.analysis_state || 'PENDING'}
              </span>
            </div>

            {intelligence?.analysis_state === 'AVAILABLE' ? (
              <div>
                <p style={{ fontSize: '0.85rem', color: 'var(--govt-gray-dark)', margin: '0 0 1.25rem' }}>
                  Engine: <strong>{intelligence.model_version}</strong> · Run at: <strong>{formatDate(intelligence.run_timestamp)}</strong>
                </p>

                <h3 style={{ fontSize: '0.95rem', color: 'var(--govt-blue-dark)', margin: '0 0 0.75rem' }}>
                  Corroborating Signals:
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', marginBottom: '1.5rem' }}>
                  {intelligence.signals.map((sig, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '0.85rem 1rem',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'var(--govt-gray-off-white)',
                        border: '1px solid var(--govt-gray-medium)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <strong style={{ fontSize: '0.85rem', color: 'var(--govt-blue-primary)', display: 'block' }}>
                          {sig.signal_type} ({sig.source})
                        </strong>
                        <span style={{ fontSize: '0.825rem', color: 'var(--govt-gray-text)' }}>
                          {sig.description}
                        </span>
                      </div>
                      {sig.score !== null && sig.score !== undefined && (
                        <span style={{
                          fontSize: '0.85rem',
                          fontWeight: '700',
                          color: sig.score >= 0.8 ? 'var(--govt-success)' : 'var(--govt-warning)',
                        }}>
                          {(sig.score * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  ))}
                </div>

                <h3 style={{ fontSize: '0.95rem', color: 'var(--govt-blue-dark)', margin: '0 0 0.5rem' }}>
                  Method Limitations & Unknowns:
                </h3>
                <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.85rem', color: 'var(--govt-gray-dark)', lineHeight: 1.5 }}>
                  {intelligence.limitations.map((lim, idx) => (
                    <li key={idx}>{lim}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '2rem 1rem' }}>
                <ClockIcon />
                <h3 style={{ margin: '0.75rem 0 0.35rem', color: 'var(--govt-blue-dark)', fontSize: '1rem' }}>
                  Analysis Unavailable / Pending
                </h3>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-gray-dark)', maxWidth: '440px', marginLeft: 'auto', marginRight: 'auto' }}>
                  Automated neural vision models or perceptual hash worker orchestration have not run on this case. Truthful state reported; no synthetic findings fabricated.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* SECTION 4: TIMELINE / WORKFLOW HISTORY */}
      {activeTab === 'history' && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.5rem',
          boxShadow: 'var(--shadow-sm)',
        }}>
          <h2 style={{ margin: '0 0 1.25rem 0', fontSize: '1.1rem', color: 'var(--govt-blue-dark)', fontWeight: '700' }}>
            Append-Only Audit Workflow History
          </h2>
          <div style={{ position: 'relative', paddingLeft: '1.5rem', borderLeft: '2px solid var(--govt-gray-medium)' }}>
            {history.map((event, idx) => (
              <div key={event.id || idx} style={{ marginBottom: '1.5rem', position: 'relative' }}>
                <div style={{
                  position: 'absolute',
                  left: '-1.95rem',
                  top: '0.2rem',
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  backgroundColor: 'var(--govt-blue-primary)',
                  border: '2px solid #ffffff',
                }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                  <strong style={{ fontSize: '0.9rem', color: 'var(--govt-blue-dark)' }}>
                    {event.event_type.replace('_', ' ')}
                  </strong>
                  <span style={{ fontSize: '0.78rem', color: 'var(--govt-gray-dark)' }}>
                    {formatDate(event.timestamp)}
                  </span>
                </div>
                <p style={{ margin: '0 0 0.35rem', fontSize: '0.825rem', color: 'var(--govt-gray-dark)' }}>
                  By: <strong>{event.actor_identity}</strong> ({event.actor_role || 'reviewer'})
                </p>
                {event.outcome && (
                  <span style={{
                    display: 'inline-block',
                    fontSize: '0.72rem',
                    fontWeight: '700',
                    padding: '0.15rem 0.55rem',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: outcomeColors[event.outcome]?.bg || 'var(--govt-gray-light)',
                    color: outcomeColors[event.outcome]?.text || 'var(--govt-gray-text)',
                    marginBottom: '0.35rem',
                  }}>
                    Outcome: {event.outcome}
                  </span>
                )}
                {event.rationale && (
                  <div style={{
                    fontSize: '0.85rem',
                    color: 'var(--govt-gray-text)',
                    backgroundColor: 'var(--govt-gray-off-white)',
                    padding: '0.65rem 0.85rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--govt-gray-medium)',
                  }}>
                    "{event.rationale}"
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SECTION 5: DECISION */}
      {activeTab === 'decision' && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.75rem',
          boxShadow: 'var(--shadow-sm)',
          maxWidth: '780px',
        }}>
          <h2 style={{ margin: '0 0 0.5rem 0', fontSize: '1.15rem', color: 'var(--govt-blue-dark)', fontWeight: '700' }}>
            Submit Human Reviewer Verdict
          </h2>
          <p style={{ margin: '0 0 1.5rem 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)', lineHeight: 1.5 }}>
            Select one of the four supported outcomes and provide a factual rationale (minimum 20 characters) citing the inspected evidence or noted anomalies.
          </p>

          {decisionSuccess && (
            <div style={{
              backgroundColor: 'var(--govt-success-light)',
              border: '1px solid var(--govt-success-border)',
              color: 'var(--govt-success-text)',
              padding: '1rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.875rem',
              fontWeight: '600',
              marginBottom: '1.5rem',
            }}>
              ✓ Decision successfully recorded to server! Persisted event ID: <code>{decisionSuccess.decision_id}</code>. Case status updated to <strong>DECIDED</strong>.
            </div>
          )}

          {decisionError && (
            <div style={{
              backgroundColor: 'var(--govt-danger-light)',
              border: '1px solid var(--govt-danger-border)',
              color: 'var(--govt-danger-text)',
              padding: '0.85rem 1rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.85rem',
              fontWeight: '600',
              marginBottom: '1.25rem',
            }}>
              ⚠️ {decisionError}
            </div>
          )}

          {/* 4 Outcome Selectors */}
          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: '700', color: 'var(--govt-gray-title)', textTransform: 'uppercase', marginBottom: '0.65rem' }}>
              Select Human Determination
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '0.75rem' }}>
              {[
                { key: 'SUPPORTED', label: 'SUPPORTED', desc: 'Evidence corroborates claimed milestone' },
                { key: 'CONTRADICTED', label: 'CONTRADICTED', desc: 'Evidence disproves claim or visual duplicate' },
                { key: 'INCONCLUSIVE', label: 'INCONCLUSIVE', desc: 'Conflicting or ambiguous signals' },
                { key: 'INSUFFICIENT_EVIDENCE', label: 'INSUFFICIENT', desc: 'Missing required photographs or data' },
              ].map((opt) => (
                <button
                  type="button"
                  key={opt.key}
                  onClick={() => setSelectedOutcome(opt.key)}
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: 'var(--radius-md)',
                    border: selectedOutcome === opt.key ? `2px solid ${outcomeColors[opt.key].border}` : '1px solid var(--govt-gray-medium)',
                    backgroundColor: selectedOutcome === opt.key ? outcomeColors[opt.key].bg : 'var(--govt-white)',
                    color: selectedOutcome === opt.key ? outcomeColors[opt.key].text : 'var(--govt-gray-text)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <strong style={{ display: 'block', fontSize: '0.85rem' }}>{opt.label}</strong>
                  <span style={{ fontSize: '0.72rem', opacity: 0.85 }}>{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Meaningful Rationale (20-char minimum constraint) */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <label htmlFor="rationale" style={{ fontSize: '0.8rem', fontWeight: '700', color: 'var(--govt-gray-title)', textTransform: 'uppercase' }}>
                Factual Rationale (Min 20 characters)
              </label>
              <span style={{
                fontSize: '0.75rem',
                fontWeight: '600',
                color: rationale.trim().length >= 20 ? 'var(--govt-success)' : 'var(--govt-danger)',
              }}>
                {rationale.trim().length} / 20 chars
              </span>
            </div>
            <textarea
              id="rationale"
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder="Detail the factual basis for this review outcome. Reference inspected photo timestamps, coordinates, or missing milestone claims..."
              rows={4}
              style={{
                width: '100%',
                padding: '0.75rem',
                fontSize: '0.875rem',
                border: rationale.trim().length > 0 && rationale.trim().length < 20 ? '1.5px solid var(--govt-danger)' : '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-md)',
                boxSizing: 'border-box',
                outline: 'none',
                fontFamily: 'inherit',
                lineHeight: 1.5,
              }}
            />
          </div>

          <button
            type="button"
            onClick={() => {
              if (!selectedOutcome) {
                setDecisionError('Please select one of the four supported outcomes.');
                return;
              }
              if (rationale.trim().length < 20) {
                setDecisionError('Rationale must meet the 20-character minimum requirement.');
                return;
              }
              setDecisionError(null);
              setShowConfirmModal(true);
            }}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.9rem',
              fontWeight: '600',
              cursor: 'pointer',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            Review & Confirm Verdict →
          </button>
        </div>
      )}

      {/* CONFIRMATION SUMMARY MODAL (Section 3.6 step 5) */}
      {showConfirmModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.65)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '1rem',
        }}>
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-xl)',
            padding: '2rem',
            maxWidth: '520px',
            width: '100%',
            boxShadow: 'var(--shadow-lg)',
          }}>
            <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.2rem', color: 'var(--govt-blue-dark)' }}>
              Confirm Authoritative Review Decision
            </h3>
            <p style={{ margin: '0 0 1.25rem', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
              This decision will be immutably recorded into the append-only audit history for case <strong>{caseId}</strong>.
            </p>

            <div style={{
              backgroundColor: 'var(--govt-gray-off-white)',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-md)',
              padding: '1rem',
              marginBottom: '1.5rem',
            }}>
              <div style={{ marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block' }}>Verdict Outcome</span>
                <strong style={{ fontSize: '0.95rem', color: outcomeColors[selectedOutcome]?.text }}>{selectedOutcome}</strong>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block' }}>Rationale</span>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-gray-text)', fontStyle: 'italic' }}>
                  "{rationale}"
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                disabled={submitting}
                onClick={() => setShowConfirmModal(false)}
                style={{
                  padding: '0.6rem 1.15rem',
                  backgroundColor: 'var(--govt-white)',
                  color: 'var(--govt-gray-text)',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-md)',
                  fontWeight: '600',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={handleDecisionSubmit}
                style={{
                  padding: '0.6rem 1.25rem',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  fontWeight: '600',
                  cursor: submitting ? 'not-allowed' : 'pointer',
                }}
              >
                {submitting ? 'Persisting Decision...' : 'Commit Immutable Verdict'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* EVIDENCE UPLOAD MODAL (Section 3.4) */}
      {showUploadModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.65)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '1rem',
        }}>
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-xl)',
            padding: '2rem',
            maxWidth: '480px',
            width: '100%',
            boxShadow: 'var(--shadow-lg)',
          }}>
            <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.2rem', color: 'var(--govt-blue-dark)' }}>
              Upload Case Evidence
            </h3>
            <p style={{ margin: '0 0 1.25rem', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
              Ingest field photograph directly into authorized case <strong>{caseId}</strong>. Maximum size: <strong>10 MiB</strong>.
            </p>

            {uploadError && (
              <div style={{
                backgroundColor: 'var(--govt-danger-light)',
                border: '1px solid var(--govt-danger-border)',
                color: 'var(--govt-danger-text)',
                padding: '0.75rem',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.8rem',
                marginBottom: '1rem',
              }}>
                {uploadError}
              </div>
            )}

            <form onSubmit={handleUploadSubmit}>
              <div style={{ marginBottom: '1.25rem' }}>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => {
                    const file = e.target.files[0];
                    setUploadFile(file);
                    setUploadError(null);
                  }}
                  style={{
                    width: '100%',
                    padding: '0.65rem',
                    border: '1px solid var(--govt-gray-medium)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: '0.85rem',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => setShowUploadModal(false)}
                  style={{
                    padding: '0.6rem 1rem',
                    backgroundColor: 'var(--govt-white)',
                    color: 'var(--govt-gray-text)',
                    border: '1px solid var(--govt-gray-medium)',
                    borderRadius: 'var(--radius-md)',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading || !uploadFile}
                  style={{
                    padding: '0.6rem 1.25rem',
                    backgroundColor: 'var(--govt-blue-primary)',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                    fontWeight: '600',
                    cursor: uploading ? 'not-allowed' : 'pointer',
                  }}
                >
                  {uploading ? 'Ingesting Evidence...' : 'Upload Evidence'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
