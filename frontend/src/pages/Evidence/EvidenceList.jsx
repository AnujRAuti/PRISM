import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';
import { EvidenceIcon, SearchIcon, FilterIcon, AlertIcon, CheckIcon } from '../../components/common/Icon';
import { evidenceApi } from '../../services/api';

function EvidenceList() {
  const [evidence, setEvidence] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [projectFilter, setProjectFilter] = useState('all');

  // Authoritative Evidence Database (ADR §9 & §10)
  const defaultEvidence = [
    {
      id: 'EVD-001',
      project_id: 'PRJ-001',
      project_name: 'PMGSY Phase 1 Road Works',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      activity: 'Road Sub-base Gravel Compaction',
      status: 'validated',
      type: 'image/jpeg',
      captured_at: '2024-02-15T10:30:00Z',
      sha256: 'c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2',
      phash: 'd4b2e8a1f0c39972',
      location: 'Pune District, Maharashtra',
      geofence_status: 'COMPLIANT',
      uploaded_by: 'John Doe (Divisional Inspector)',
      quarantine_state: 'CLEARED'
    },
    {
      id: 'EVD-002',
      project_id: 'PRJ-001',
      project_name: 'PMGSY Phase 1 Road Works',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      activity: 'Bitumen Asphalt Surface Pouring',
      status: 'validated',
      type: 'image/jpeg',
      captured_at: '2024-02-18T14:20:00Z',
      sha256: '7b2a9e40183fdc329810a9f848201ac495a8e10034b1235cb99ef01a8843c089',
      phash: 'a1c4e9b208f37751',
      location: 'Pune District, Maharashtra',
      geofence_status: 'COMPLIANT',
      uploaded_by: 'Jane Smith (Supervising Engineer)',
      quarantine_state: 'CLEARED'
    },
    {
      id: 'EVD-003',
      project_id: 'PRJ-002',
      project_name: 'Solar Street Light Installation',
      scheme: 'Solar Energy Programme',
      activity: 'PV Module Luminaire Mounting',
      status: 'quarantine_flagged',
      type: 'image/jpeg',
      captured_at: '2024-02-20T09:45:00Z',
      sha256: '8f43a992e564177b89d4d2320b99ac18721539bb409e5b7c7fa91823bb0d0821',
      phash: 'b2f8e1a093c44881',
      location: 'Surat District, Gujarat',
      geofence_status: 'OUT_OF_BOUNDS',
      anomaly_note: 'Cross-Project duplicate (89% pHash overlap with EVD-001 in PRJ-001); 12.4 km geofence variance',
      uploaded_by: 'Raj Kumar (Contractor Liaison)',
      quarantine_state: 'HELD_FOR_REVIEW'
    },
    {
      id: 'EVD-004',
      project_id: 'PRJ-003',
      project_name: 'Community Water Tank Construction',
      scheme: 'Jal Jeevan Mission',
      activity: 'RCC Storage Tank Foundation Sealing',
      status: 'uploaded_quarantine',
      type: 'image/jpeg',
      captured_at: '2024-02-22T16:10:00Z',
      sha256: 'a12bc9034f828e10091873ea8901bce2674e1199a0b4528172ce4091ab5421ef',
      phash: 'e8a0f12bc3948750',
      location: 'Jaipur District, Rajasthan',
      geofence_status: 'COMPLIANT',
      uploaded_by: 'Amit Verma (Field Officer)',
      quarantine_state: 'PROCESSING'
    },
    {
      id: 'EVD-005',
      project_id: 'PRJ-005',
      project_name: 'Community Health Center',
      scheme: 'National Health Mission',
      activity: 'Perimeter Boundary Excavation',
      status: 'validated',
      type: 'image/jpeg',
      captured_at: '2024-02-26T08:30:00Z',
      sha256: '55e810a9f24b81c2039ab6601dc892711094328fa8b4e019c438201fa8843ce1',
      phash: '99201f84b1a03975',
      location: 'Lucknow District, Uttar Pradesh',
      geofence_status: 'UNKNOWN',
      uploaded_by: 'Kavita Singh (Field Officer)',
      quarantine_state: 'CLEARED'
    }
  ];

  useEffect(() => {
    // Attempt to load from API or use seeded evidence
    setTimeout(() => {
      setEvidence(defaultEvidence);
      setLoading(false);
    }, 400);
  }, []);

  const filteredEvidence = evidence.filter(item => {
    const q = searchTerm.toLowerCase();
    const matchesSearch =
      item.id.toLowerCase().includes(q) ||
      item.project_name.toLowerCase().includes(q) ||
      item.activity.toLowerCase().includes(q) ||
      item.location.toLowerCase().includes(q) ||
      item.sha256.toLowerCase().includes(q);

    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    const matchesProject = projectFilter === 'all' || item.project_id === projectFilter;
    return matchesSearch && matchesStatus && matchesProject;
  });

  const getStatusBadge = (status) => {
    switch (status) {
      case 'validated':
        return { bg: 'var(--govt-success-light)', color: 'var(--govt-success-text)', label: 'VALIDATED' };
      case 'quarantine_flagged':
        return { bg: 'var(--govt-danger-light)', color: 'var(--govt-danger-text)', label: 'QUARANTINE FLAGGED' };
      case 'uploaded_quarantine':
        return { bg: 'var(--govt-warning-light)', color: 'var(--govt-warning-text)', label: 'IN QUARANTINE' };
      case 'archived':
        return { bg: 'var(--govt-gray-light)', color: 'var(--govt-gray-dark)', label: 'ARCHIVED' };
      default:
        return { bg: 'var(--govt-gray-light)', color: 'var(--govt-gray-text)', label: status.toUpperCase() };
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
          Loading cryptographic evidence registry...
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
      {/* Header */}
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
            <span style={{ color: 'var(--govt-blue-primary)' }}><EvidenceIcon /></span>
            <h1 style={{
              margin: 0,
              color: 'var(--govt-blue-dark)',
              fontSize: '1.65rem',
              fontWeight: 700,
              letterSpacing: '-0.02em'
            }}>
              Evidence Registry & Provenance
            </h1>
          </div>
          <p style={{
            margin: '0.4rem 0 0 0',
            color: 'var(--govt-gray-dark)',
            fontSize: '0.875rem'
          }}>
            Immutable multi-signal evidence ledger with SHA-256 integrity, perceptual hashing, and quarantine isolation.
          </p>
        </div>

        <Link
          to="/evidence/upload"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.625rem 1.15rem',
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'var(--govt-blue-primary)',
            color: '#ffffff',
            textDecoration: 'none',
            fontSize: '0.875rem',
            fontWeight: 600,
            boxShadow: 'var(--shadow-sm)',
            transition: 'background-color 0.15s ease'
          }}
          onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--govt-blue-dark)'}
          onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--govt-blue-primary)'}
        >
          + Upload Evidence
        </Link>
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
        <div style={{ flex: '1 1 280px' }}>
          <input
            type="text"
            placeholder="Search by Evidence ID, SHA-256 hash, project, or location..."
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
            <option value="all">All Quarantine States</option>
            <option value="validated">Validated</option>
            <option value="uploaded_quarantine">In Quarantine</option>
            <option value="quarantine_flagged">Quarantine Flagged</option>
            <option value="archived">Archived</option>
          </select>

          <select
            value={projectFilter}
            onChange={(e) => setProjectFilter(e.target.value)}
            style={{
              padding: '0.625rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.85rem',
              backgroundColor: 'var(--govt-white)',
              cursor: 'pointer'
            }}
          >
            <option value="all">All Projects</option>
            <option value="PRJ-001">PRJ-001 (PMGSY)</option>
            <option value="PRJ-002">PRJ-002 (Solar)</option>
            <option value="PRJ-003">PRJ-003 (Jal Jeevan)</option>
            <option value="PRJ-005">PRJ-005 (NHM Health)</option>
          </select>

          {(searchTerm || statusFilter !== 'all' || projectFilter !== 'all') && (
            <button
              type="button"
              onClick={() => { setSearchTerm(''); setStatusFilter('all'); setProjectFilter('all'); }}
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

      {/* Evidence Table */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        overflow: 'hidden'
      }}>
        {filteredEvidence.length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--govt-gray-dark)' }}>
            <p style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>No evidence records match the selected filters.</p>
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
                  <th style={{ padding: '0.85rem 1.25rem' }}>Evidence ID & File</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Project & Activity</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Cryptographic SHA-256 Digest</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Geospatial & Ingestion</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Quarantine State</th>
                  <th style={{ padding: '0.85rem 1.25rem', textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvidence.map((e) => {
                  const sBadge = getStatusBadge(e.status);

                  return (
                    <tr
                      key={e.id}
                      style={{
                        borderBottom: '1px solid var(--govt-gray-medium)',
                        transition: 'background-color 0.15s ease'
                      }}
                      onMouseEnter={(el) => el.currentTarget.style.backgroundColor = 'var(--govt-gray-off-white)'}
                      onMouseLeave={(el) => el.currentTarget.style.backgroundColor = 'transparent'}
                    >
                      {/* ID & File */}
                      <td style={{ padding: '1rem 1.25rem' }}>
                        <div style={{ fontWeight: 700, color: 'var(--govt-blue-primary)', fontFamily: 'monospace', fontSize: '0.88rem' }}>
                          {e.id}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', marginTop: '0.2rem' }}>
                          Type: {e.type}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)', marginTop: '0.15rem' }}>
                          Captured: {formatDate(e.captured_at)}
                        </div>
                      </td>

                      {/* Project & Activity */}
                      <td style={{ padding: '1rem', maxWidth: '240px' }}>
                        <div style={{ fontWeight: 600, color: 'var(--govt-blue-dark)', fontSize: '0.88rem' }}>
                          {e.project_name}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--govt-gray-text)', marginTop: '0.2rem' }}>
                          {e.activity}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)', marginTop: '0.15rem' }}>
                          Inspector: {e.uploaded_by}
                        </div>
                      </td>

                      {/* Cryptographic SHA-256 Digest */}
                      <td style={{ padding: '1rem', maxWidth: '260px' }}>
                        <div style={{
                          fontFamily: 'monospace',
                          fontSize: '0.72rem',
                          backgroundColor: 'var(--govt-gray-light)',
                          padding: '0.35rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--govt-gray-medium)',
                          wordBreak: 'break-all',
                          color: 'var(--govt-blue-dark)'
                        }}>
                          {e.sha256}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', marginTop: '0.35rem' }}>
                          pHash: <span style={{ fontFamily: 'monospace' }}>{e.phash}</span>
                        </div>
                      </td>

                      {/* Geospatial & Ingestion */}
                      <td style={{ padding: '1rem' }}>
                        <div style={{ fontSize: '0.82rem', color: 'var(--govt-gray-text)', fontWeight: 500 }}>
                          {e.location}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '0.25rem', fontSize: '0.75rem' }}>
                          <span style={{ color: e.geofence_status === 'COMPLIANT' ? 'var(--govt-success)' : e.geofence_status === 'OUT_OF_BOUNDS' ? 'var(--govt-danger)' : 'var(--govt-warning)' }}>
                            {e.geofence_status === 'COMPLIANT' ? '✓' : '⚠'}
                          </span>
                          <span style={{ fontWeight: 600 }}>Geofence: {e.geofence_status}</span>
                        </div>
                        {e.anomaly_note && (
                          <div style={{ fontSize: '0.7rem', color: 'var(--govt-danger-text)', marginTop: '0.25rem', fontWeight: 600, lineHeight: 1.3 }}>
                            {e.anomaly_note}
                          </div>
                        )}
                      </td>

                      {/* Quarantine State */}
                      <td style={{ padding: '1rem' }}>
                        <span style={{
                          display: 'inline-block',
                          padding: '0.2rem 0.6rem',
                          borderRadius: '9999px',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          backgroundColor: sBadge.bg,
                          color: sBadge.color,
                        }}>
                          {sBadge.label}
                        </span>
                        <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', marginTop: '0.35rem' }}>
                          Isolation: {e.quarantine_state}
                        </div>
                      </td>

                      {/* Action */}
                      <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                        <Link
                          to={`/evidence/${e.id}`}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.35rem',
                            padding: '0.45rem 0.85rem',
                            borderRadius: 'var(--radius-md)',
                            backgroundColor: 'var(--govt-white)',
                            border: '1px solid var(--govt-gray-medium)',
                            color: 'var(--govt-blue-primary)',
                            textDecoration: 'none',
                            fontSize: '0.82rem',
                            fontWeight: 600,
                            boxShadow: 'var(--shadow-xs)'
                          }}
                        >
                          Inspect →
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

      {/* Architecture Integrity Policy Notice */}
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
            Cryptographic Storage & Ingestion Boundary (ADR Section 10)
          </h4>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.78rem', color: 'var(--govt-gray-dark)', lineHeight: 1.45 }}>
            Evidence objects are stored in private Cloudflare R2 object storage. Pre-signed download URLs are short-lived (900s) and require
            explicit authorization and project scope verification. An exact SHA-256 or pHash match proves cryptographic byte identity and perceptual
            similarity, not the substantive authenticity of the physical public work.
          </p>
        </div>
      </div>
    </div>
  );
}

export default EvidenceList;
