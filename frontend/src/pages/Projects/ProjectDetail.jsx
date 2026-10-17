import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';
import { ProjectIcon, EvidenceIcon, ReviewIcon, AlertIcon, CheckIcon } from '../../components/common/Icon';

function ProjectDetail() {
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [project, setProject] = useState(null);

  // Authoritative Project Domain Record (ADR Section 9)
  const mockProject = {
    id: id || 'PRJ-001',
    name: 'PMGSY Phase 1 Road Works — Taluka Baramati',
    scheme: 'Pradhan Mantri Gram Sadak Yojana',
    department: 'Ministry of Rural Development',
    description: 'Construction and quality monitoring of 12.4 km all-weather rural bituminous road connecting 4 habitations to the state highway network.',
    status: 'ACTIVE',
    location: 'Pune District, Maharashtra',
    state: 'Maharashtra',
    district: 'Pune District',
    supervisor: 'Sunita Patel (Divisional Supervisor)',
    start_date: '2024-01-01',
    target_date: '2024-12-31',
    created_at: '2024-01-15T10:30:00Z',
    geofence: {
      polygon: '18.5204,73.8567; 18.5300,73.8650; 18.5150,73.8700; 18.5204,73.8567',
      bounds: 'Baramati Taluka Ward 4 Boundary Polygon (Active PostGIS spatial filter)',
      status: 'VERIFIED_ACTIVE'
    },
    // Domain Hierarchy: Activities (Work Units)
    activities: [
      { id: 'ACT-001', name: 'Site Survey & Alignment Clearance', status: 'COMPLETED', progress: 100, completed_at: '2024-01-20' },
      { id: 'ACT-002', name: 'Sub-grade Excavation & Soil Compaction', status: 'COMPLETED', progress: 100, completed_at: '2024-02-05' },
      { id: 'ACT-003', name: 'Water Bound Macadam (WBM) Base Layer', status: 'IN_PROGRESS', progress: 75, completed_at: null },
      { id: 'ACT-004', name: 'Bitumen Asphalt Surfacing Pouring', status: 'IN_PROGRESS', progress: 40, completed_at: null },
      { id: 'ACT-005', name: 'Culvert Drainage & Road Signage', status: 'PENDING', progress: 0, completed_at: null },
    ],
    // Canonical Claims (Section 9)
    claims: [
      { id: 'CLM-001', statement: 'Completion of 12.4 km all-weather rural road connectivity milestone.', status: 'PENDING_REVIEW', case_id: 'case-001-pmgsy' },
      { id: 'CLM-002', statement: 'Sub-base gravel compaction density exceeds 98% Proctor standard.', status: 'SUPPORTED', case_id: null },
    ],
    // Associated Evidence
    evidence: [
      {
        id: 'EVD-001',
        activity: 'Road Sub-base Gravel Compaction',
        type: 'image/jpeg',
        status: 'validated',
        captured_at: '2024-02-15T10:30:00Z',
        sha256: 'c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2',
        geofence_status: 'COMPLIANT'
      },
      {
        id: 'EVD-002',
        activity: 'Bitumen Asphalt Surface Pouring',
        type: 'image/jpeg',
        status: 'validated',
        captured_at: '2024-02-18T14:20:00Z',
        sha256: '7b2a9e40183fdc329810a9f848201ac495a8e10034b1235cb99ef01a8843c089',
        geofence_status: 'COMPLIANT'
      }
    ],
    // Review Cases
    review_cases: [
      {
        id: 'case-001-pmgsy',
        title: 'Rural Road Sub-base & Bitumen Pouring Compliance',
        priority: 'HIGH',
        status: 'PENDING_REVIEW',
        reason: 'Milestone disbursement deadline in 48 hours; geofence bounds pending confirmation',
        evidence_count: 2
      }
    ]
  };

  useEffect(() => {
    setTimeout(() => {
      setProject(mockProject);
      setLoading(false);
    }, 350);
  }, [id]);

  if (loading || !project) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', margin: '0 auto 1rem' }}></div>
        <p style={{ color: 'var(--govt-gray-dark)' }}>Loading project domain hierarchy...</p>
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
      {/* Breadcrumb */}
      <div style={{ marginBottom: '1.25rem', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
        <Link to="/projects" style={{ color: 'var(--govt-blue-primary)', textDecoration: 'none' }}>
          Projects
        </Link>
        {' / '}
        <span style={{ fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{project.id}</span>
      </div>

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
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1 style={{
              margin: 0,
              color: 'var(--govt-blue-dark)',
              fontSize: '1.65rem',
              fontWeight: 700,
              letterSpacing: '-0.02em'
            }}>
              {project.name}
            </h1>
            <span style={{
              padding: '0.2rem 0.65rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 700,
              backgroundColor: 'var(--govt-success-light)',
              color: 'var(--govt-success-text)'
            }}>
              {project.status}
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
            {project.scheme} • {project.department} • {project.location}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Link
            to={`/evidence/upload?case_id=${project.review_cases[0]?.id || ''}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.6rem 1rem',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              textDecoration: 'none',
              fontSize: '0.85rem',
              fontWeight: 600,
              boxShadow: 'var(--shadow-sm)'
            }}
          >
            + Upload Evidence
          </Link>
        </div>
      </div>

      {/* Project Metadata & Geofence Baseline */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: '1.5rem',
        marginBottom: '1.75rem'
      }}>
        {/* Scope Summary */}
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.25rem 1.5rem'
        }}>
          <h3 style={{ margin: '0 0 0.85rem', fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            Operational Scope & Timeline
          </h3>
          <p style={{ margin: '0 0 1rem', fontSize: '0.85rem', color: 'var(--govt-gray-text)', lineHeight: 1.45 }}>
            {project.description}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.78rem' }}>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Sanction Date:</span>
              <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{formatDate(project.start_date)}</p>
            </div>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Target Completion:</span>
              <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{formatDate(project.target_date)}</p>
            </div>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Supervisor:</span>
              <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{project.supervisor}</p>
            </div>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Sanctioned Identifier:</span>
              <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)', fontFamily: 'monospace' }}>{project.id}</p>
            </div>
          </div>
        </div>

        {/* Spatial Baseline & Geofence */}
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.25rem 1.5rem'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              Geospatial Geofence Baseline (ADR §16)
            </h3>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--govt-success-text)', backgroundColor: 'var(--govt-success-light)', padding: '0.15rem 0.5rem', borderRadius: '4px' }}>
              {project.geofence.status}
            </span>
          </div>
          <p style={{ margin: '0 0 0.75rem', fontSize: '0.8rem', color: 'var(--govt-gray-text)' }}>
            {project.geofence.bounds}
          </p>
          <div style={{
            backgroundColor: 'var(--govt-gray-off-white)',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-md)',
            padding: '0.625rem 0.75rem',
            fontFamily: 'monospace',
            fontSize: '0.75rem',
            wordBreak: 'break-all',
            color: 'var(--govt-blue-dark)',
            marginBottom: '0.75rem'
          }}>
            {project.geofence.polygon}
          </div>
          <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)', display: 'block', lineHeight: 1.4 }}>
            Evidence coordinates captured outside this polygon generate geofence variance warnings for reviewer attention.
          </span>
        </div>
      </div>

      {/* Domain Section 1: Canonical Claims (ADR §9) */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        marginBottom: '1.75rem',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: '1rem 1.25rem',
          borderBottom: '1px solid var(--govt-gray-medium)',
          backgroundColor: 'var(--govt-gray-light)',
          fontWeight: 700,
          color: 'var(--govt-blue-dark)',
          fontSize: '0.9rem'
        }}>
          Sanctioned Milestone Claims (ADR Section 9)
        </div>
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          {project.claims.map(claim => (
            <div
              key={claim.id}
              style={{
                padding: '1rem',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--govt-gray-medium)',
                backgroundColor: 'var(--govt-gray-off-white)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.75rem'
              }}
            >
              <div>
                <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-blue-primary)' }}>
                  {claim.id}
                </span>
                <p style={{ margin: '0.2rem 0 0', fontSize: '0.88rem', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                  {claim.statement}
                </p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{
                  padding: '0.2rem 0.55rem',
                  borderRadius: '9999px',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  backgroundColor: claim.status === 'SUPPORTED' ? 'var(--govt-success-light)' : 'var(--govt-warning-light)',
                  color: claim.status === 'SUPPORTED' ? 'var(--govt-success-text)' : 'var(--govt-warning-text)'
                }}>
                  {claim.status}
                </span>
                {claim.case_id && (
                  <Link
                    to={`/review/case?id=${claim.case_id}`}
                    style={{
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      color: 'var(--govt-blue-primary)',
                      textDecoration: 'none'
                    }}
                  >
                    Open Case →
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Domain Section 2: Activities & Work Units */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        marginBottom: '1.75rem',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: '1rem 1.25rem',
          borderBottom: '1px solid var(--govt-gray-medium)',
          backgroundColor: 'var(--govt-gray-light)',
          fontWeight: 700,
          color: 'var(--govt-blue-dark)',
          fontSize: '0.9rem'
        }}>
          Inspection Activities & Work Progress Units
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                borderBottom: '1px solid var(--govt-gray-medium)',
                color: 'var(--govt-gray-dark)',
                fontSize: '0.75rem',
                textTransform: 'uppercase'
              }}>
                <th style={{ padding: '0.75rem 1.25rem' }}>Activity ID</th>
                <th style={{ padding: '0.75rem 1rem' }}>Activity Title</th>
                <th style={{ padding: '0.75rem 1rem' }}>Progress</th>
                <th style={{ padding: '0.75rem 1rem' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {project.activities.map(act => (
                <tr key={act.id} style={{ borderBottom: '1px solid var(--govt-gray-medium)' }}>
                  <td style={{ padding: '0.85rem 1.25rem', fontFamily: 'monospace', fontWeight: 600, color: 'var(--govt-blue-primary)' }}>
                    {act.id}
                  </td>
                  <td style={{ padding: '0.85rem 1rem', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                    {act.name}
                  </td>
                  <td style={{ padding: '0.85rem 1rem', width: '220px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      <div style={{
                        flex: 1,
                        height: '8px',
                        backgroundColor: 'var(--govt-gray-medium)',
                        borderRadius: '9999px',
                        overflow: 'hidden'
                      }}>
                        <div style={{
                          width: `${act.progress}%`,
                          height: '100%',
                          backgroundColor: act.progress === 100 ? 'var(--govt-success)' : 'var(--govt-blue-primary)'
                        }}></div>
                      </div>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', width: '32px' }}>
                        {act.progress}%
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span style={{
                      padding: '0.15rem 0.5rem',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      backgroundColor: act.status === 'COMPLETED' ? 'var(--govt-success-light)' : act.status === 'IN_PROGRESS' ? 'var(--govt-blue-light)' : 'var(--govt-gray-light)',
                      color: act.status === 'COMPLETED' ? 'var(--govt-success-text)' : act.status === 'IN_PROGRESS' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                    }}>
                      {act.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Domain Section 3: Linked Evidence Items */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: '1rem 1.25rem',
          borderBottom: '1px solid var(--govt-gray-medium)',
          backgroundColor: 'var(--govt-gray-light)',
          fontWeight: 700,
          color: 'var(--govt-blue-dark)',
          fontSize: '0.9rem'
        }}>
          Associated Cryptographic Evidence
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                borderBottom: '1px solid var(--govt-gray-medium)',
                color: 'var(--govt-gray-dark)',
                fontSize: '0.75rem',
                textTransform: 'uppercase'
              }}>
                <th style={{ padding: '0.75rem 1.25rem' }}>Evidence ID</th>
                <th style={{ padding: '0.75rem 1rem' }}>Inspection Activity</th>
                <th style={{ padding: '0.75rem 1rem' }}>SHA-256 Digest</th>
                <th style={{ padding: '0.75rem 1rem' }}>Geofence</th>
                <th style={{ padding: '0.75rem 1.25rem', textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {project.evidence.map(ev => (
                <tr key={ev.id} style={{ borderBottom: '1px solid var(--govt-gray-medium)' }}>
                  <td style={{ padding: '0.85rem 1.25rem', fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-blue-primary)' }}>
                    {ev.id}
                  </td>
                  <td style={{ padding: '0.85rem 1rem', fontSize: '0.85rem', color: 'var(--govt-blue-dark)', fontWeight: 500 }}>
                    {ev.activity}
                  </td>
                  <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontSize: '0.72rem', color: 'var(--govt-gray-text)' }}>
                    {ev.sha256.slice(0, 32)}...
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--govt-success-text)' }}>
                      ✓ {ev.geofence_status}
                    </span>
                  </td>
                  <td style={{ padding: '0.85rem 1.25rem', textAlign: 'right' }}>
                    <Link
                      to={`/evidence/${ev.id}`}
                      style={{
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        color: 'var(--govt-blue-primary)',
                        textDecoration: 'none'
                      }}
                    >
                      Inspect →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default ProjectDetail;
