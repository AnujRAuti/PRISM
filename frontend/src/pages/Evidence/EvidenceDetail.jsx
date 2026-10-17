import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';
import { GraphIcon, ReviewIcon, AlertIcon, CheckIcon, DownloadIcon } from '../../components/common/Icon';
import { evidenceApi } from '../../services/api';

function EvidenceDetail() {
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [evidence, setEvidence] = useState(null);
  const [copiedHash, setCopiedHash] = useState(false);

  // Authoritative Evidence Database (ADR §9, §10, §13)
  const mockDatabase = {
    'EVD-001': {
      id: 'EVD-001',
      project_id: 'PRJ-001',
      project_name: 'PMGSY Phase 1 Road Works',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      activity: 'Road Sub-base Gravel Compaction',
      status: 'validated',
      quarantine_state: 'CLEARED',
      type: 'image/jpeg',
      captured_at: '2024-02-15T10:30:00Z',
      uploaded_at: '2024-02-15T11:05:00Z',
      uploaded_by: 'John Doe (Divisional Inspector - Pune Division)',
      location: 'Pune District, Maharashtra',
      gps: { latitude: '18.5204° N', longitude: '73.8567° E', accuracy: '3.2 meters', geofence: 'COMPLIANT (14m variance)' },
      description: 'Compacted gravel sub-base layer inspection along Sector 4 rural stretch.',
      file_meta: {
        filename: 'IMG_20240215_103000.jpg',
        file_size: '3.4 MB',
        dimensions: '3840 x 2160 px',
        mime_type: 'image/jpeg',
        camera_make: 'Samsung',
        camera_model: 'Galaxy S21 Ultra',
        focal_length: '24mm',
        exposure: '1/500s at f/1.8'
      },
      sha256: 'c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2',
      phash: 'd4b2e8a1f0c39972',
      signals: [
        { name: 'Cryptographic SHA-256', value: 'c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2', state: 'COMPUTED', status: 'PASS', note: 'Recorded immutably during initial quarantine receipt.' },
        { name: 'Perceptual Hash (pHash)', value: 'd4b2e8a1f0c39972', state: 'COMPUTED', status: 'PASS', note: 'No identical or near-duplicate frames detected across scheme database.' },
        { name: 'Geospatial Geofence', value: '18.5204, 73.8567', state: 'COMPLIANT', status: 'PASS', note: 'Coordinates are strictly within approved project boundary polygon.' },
        { name: 'Temporal Consistency', value: '2024-02-15 10:30 IST', state: 'CONSISTENT', status: 'PASS', note: 'Timestamp conforms with milestone schedule and inspector transit logs.' },
        { name: 'Vision / Claim Observation', value: 'Roadbed, Gravel, Compactor', state: 'OBSERVED', status: 'PASS', note: 'Object detection identifies sub-base gravel aggregate and compaction equipment.' }
      ],
      anomalies: [],
      related_cases: [
        { id: 'case-001-pmgsy', title: 'Rural Road Sub-base & Bitumen Pouring Compliance', priority: 'HIGH', status: 'PENDING_REVIEW' }
      ]
    },
    'EVD-003': {
      id: 'EVD-003',
      project_id: 'PRJ-002',
      project_name: 'Solar Street Light Installation',
      scheme: 'Solar Energy Programme',
      activity: 'PV Module Luminaire Mounting',
      status: 'quarantine_flagged',
      quarantine_state: 'HELD_FOR_REVIEW',
      type: 'image/jpeg',
      captured_at: '2024-02-20T09:45:00Z',
      uploaded_at: '2024-02-20T10:12:00Z',
      uploaded_by: 'Raj Kumar (Contractor Liaison)',
      location: 'Surat District, Gujarat',
      gps: { latitude: '21.1702° N', longitude: '72.8311° E', accuracy: '45.0 meters', geofence: 'OUT_OF_BOUNDS (12.4 km variance)' },
      description: 'Erected 12W LED solar street light luminaire and PV module atop galvanized pole.',
      file_meta: {
        filename: 'solar_panel_photo_final.jpg',
        file_size: '2.1 MB',
        dimensions: '1920 x 1080 px',
        mime_type: 'image/jpeg',
        camera_make: 'Xiaomi',
        camera_model: 'Redmi Note 10',
        focal_length: '26mm',
        exposure: '1/250s at f/2.0'
      },
      sha256: '8f43a992e564177b89d4d2320b99ac18721539bb409e5b7c7fa91823bb0d0821',
      phash: 'b2f8e1a093c44881',
      signals: [
        { name: 'Cryptographic SHA-256', value: '8f43a992e564177b89d4d2320b99ac18721539bb409e5b7c7fa91823bb0d0821', state: 'COMPUTED', status: 'PASS', note: 'File byte stream is well-formed and verified against intake ledger.' },
        { name: 'Perceptual Hash (pHash)', value: 'b2f8e1a093c44881', state: 'DUPLICATE_FLAGGED', status: 'FLAGGED', note: 'Visual fingerprint shares 89% hamming similarity with evidence EVD-001 from PRJ-001.' },
        { name: 'Geospatial Geofence', value: '21.1702, 72.8311', state: 'OUT_OF_BOUNDS', status: 'FLAGGED', note: 'Capture coordinates fall 12.4 km outside sanctioned village boundary polygon.' },
        { name: 'Temporal Consistency', value: '2024-02-20 09:45 IST', state: 'INVERSION_WARNING', status: 'WARNING', note: 'Photo creation timestamp precedes work-order release date by 3 days.' },
        { name: 'Vision / Claim Observation', value: 'Solar Pole, Vegetation', state: 'OBSERVED', status: 'PASS', note: 'Objects align with claim, but duplicate angle strongly suspected.' }
      ],
      anomalies: [
        { code: 'CROSS_PROJECT_DUPLICATE', severity: 'HIGH', title: 'Cross-Project Visual Near-Duplicate', explanation: 'This image exhibits 89% perceptual feature overlap with evidence EVD-001 originally submitted under Project PRJ-001 in another jurisdiction.' },
        { code: 'GEOFENCE_VIOLATION', severity: 'HIGH', title: 'Geofence Boundary Violation', explanation: 'Calculated GPS coordinates (21.1702, 72.8311) are 12.4 km beyond the approved geofenced boundary for village ward 4.' },
        { code: 'TIMELINE_INVERSION', severity: 'MEDIUM', title: 'Timeline Inversion Detected', explanation: 'EXIF internal capture timestamp precedes activity commencement authorization.' }
      ],
      related_cases: [
        { id: 'case-002-solar', title: 'Surat Ward 4 Solar Street Luminaire Installation', priority: 'HIGH', status: 'INVESTIGATING' }
      ]
    }
  };

  useEffect(() => {
    const selected = mockDatabase[id] || mockDatabase['EVD-001'];
    setEvidence(selected);
    setLoading(false);
  }, [id]);

  const copyHash = (hash) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  if (loading || !evidence) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', margin: '0 auto 1rem' }}></div>
        <p style={{ color: 'var(--govt-gray-dark)' }}>Loading evidence verification details...</p>
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
      {/* Breadcrumb Navigation */}
      <div style={{ marginBottom: '1.25rem', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
        <Link to="/evidence" style={{ color: 'var(--govt-blue-primary)', textDecoration: 'none' }}>
          Evidence Registry
        </Link>
        {' / '}
        <span style={{ fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{evidence.id}</span>
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
              Evidence Inspection: {evidence.id}
            </h1>
            <span style={{
              padding: '0.2rem 0.65rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 700,
              backgroundColor: evidence.status === 'validated' ? 'var(--govt-success-light)' : 'var(--govt-danger-light)',
              color: evidence.status === 'validated' ? 'var(--govt-success-text)' : 'var(--govt-danger-text)',
            }}>
              {evidence.status === 'validated' ? 'QUARANTINE CLEARED' : 'QUARANTINE FLAGGED'}
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
            Project: <Link to={`/projects/${evidence.project_id}`} style={{ color: 'var(--govt-blue-primary)', textDecoration: 'none', fontWeight: 600 }}>{evidence.project_name}</Link> ({evidence.scheme})
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          {evidence.related_cases && evidence.related_cases.length > 0 && (
            <Link
              to={`/review/case?id=${evidence.related_cases[0].id}`}
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
              Open Review Workspace →
            </Link>
          )}
        </div>
      </div>

      {/* Grid: Preview & Cryptographic Digest */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
        gap: '1.5rem',
        marginBottom: '1.75rem'
      }}>
        {/* Evidence Preview Card */}
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
            Captured Media & Provenance
          </div>
          <div style={{
            height: '260px',
            backgroundColor: '#0f172a',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative'
          }}>
            <img
              src="/prism-symbol-transparent.png"
              alt="Evidence Inspection"
              style={{ maxHeight: '180px', objectFit: 'contain', opacity: 0.85 }}
            />
            <div style={{
              position: 'absolute',
              bottom: '10px',
              left: '12px',
              backgroundColor: 'rgba(15, 23, 42, 0.75)',
              padding: '0.25rem 0.6rem',
              borderRadius: 'var(--radius-sm)',
              color: '#ffffff',
              fontSize: '0.72rem',
              fontFamily: 'monospace'
            }}>
              {evidence.file_meta.dimensions} • {evidence.file_meta.file_size}
            </div>
          </div>
          <div style={{ padding: '1.25rem' }}>
            <p style={{ margin: '0 0 1rem', fontSize: '0.875rem', color: 'var(--govt-gray-text)', lineHeight: 1.45 }}>
              {evidence.description}
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.78rem' }}>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Camera Device:</span>
                <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                  {evidence.file_meta.camera_make} {evidence.file_meta.camera_model}
                </p>
              </div>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Exposure / Optics:</span>
                <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                  {evidence.file_meta.exposure} ({evidence.file_meta.focal_length})
                </p>
              </div>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Captured Timestamp:</span>
                <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                  {formatDate(evidence.captured_at)}
                </p>
              </div>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Server Intake Timestamp:</span>
                <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                  {formatDate(evidence.uploaded_at)}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Cryptographic Digest & Quarantine Card */}
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{
            padding: '1rem 1.25rem',
            borderBottom: '1px solid var(--govt-gray-medium)',
            backgroundColor: 'var(--govt-gray-light)',
            fontWeight: 700,
            color: 'var(--govt-blue-dark)',
            fontSize: '0.9rem'
          }}>
            Cryptographic Integrity & Hashes (ADR Section 10.5)
          </div>

          <div style={{ padding: '1.25rem', flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--govt-gray-dark)', letterSpacing: '0.5px' }}>
                  SHA-256 BINARY DIGEST
                </span>
                <button
                  type="button"
                  onClick={() => copyHash(evidence.sha256)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--govt-blue-primary)',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    fontWeight: 600
                  }}
                >
                  {copiedHash ? '✓ Copied' : 'Copy Digest'}
                </button>
              </div>
              <div style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-md)',
                padding: '0.625rem 0.75rem',
                fontFamily: 'monospace',
                fontSize: '0.78rem',
                wordBreak: 'break-all',
                color: 'var(--govt-blue-dark)'
              }}>
                {evidence.sha256}
              </div>
            </div>

            <div>
              <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--govt-gray-dark)', letterSpacing: '0.5px' }}>
                PERCEPTUAL HASH (pHash)
              </span>
              <div style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-md)',
                padding: '0.625rem 0.75rem',
                fontFamily: 'monospace',
                fontSize: '0.78rem',
                marginTop: '0.35rem',
                color: 'var(--govt-blue-dark)'
              }}>
                {evidence.phash}
              </div>
            </div>

            <div>
              <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--govt-gray-dark)', letterSpacing: '0.5px' }}>
                GEOSPATIAL POSTGIS COORDINATES & GEOFENCE
              </span>
              <div style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-md)',
                padding: '0.625rem 0.75rem',
                fontSize: '0.8rem',
                marginTop: '0.35rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <span>{evidence.gps.latitude}, {evidence.gps.longitude}</span>
                <span style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  color: evidence.gps.geofence.includes('COMPLIANT') ? 'var(--govt-success)' : 'var(--govt-danger)'
                }}>
                  {evidence.gps.geofence}
                </span>
              </div>
            </div>

            <div style={{
              marginTop: 'auto',
              padding: '0.75rem 1rem',
              backgroundColor: 'var(--govt-blue-light)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-blue-medium)'
            }}>
              <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--govt-blue-dark)', lineHeight: 1.4 }}>
                <strong>Truthful Intelligence Principle:</strong> A hash match establishes byte-level cryptographic similarity. It is an analytical signal for human review and does not independently prove or disprove physical work.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Signals Breakdown Table */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        overflow: 'hidden',
        marginBottom: '1.75rem'
      }}>
        <div style={{
          padding: '1rem 1.25rem',
          borderBottom: '1px solid var(--govt-gray-medium)',
          backgroundColor: 'var(--govt-gray-light)',
          fontWeight: 700,
          color: 'var(--govt-blue-dark)',
          fontSize: '0.9rem'
        }}>
          Multi-Signal Observation Ledger (ADR Section 13.5)
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
                <th style={{ padding: '0.75rem 1.25rem' }}>Analytical Signal</th>
                <th style={{ padding: '0.75rem 1rem' }}>Extracted Value</th>
                <th style={{ padding: '0.75rem 1rem' }}>Computed State</th>
                <th style={{ padding: '0.75rem 1.25rem' }}>Explainable Methodology Note</th>
              </tr>
            </thead>
            <tbody>
              {evidence.signals.map((sig, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid var(--govt-gray-medium)' }}>
                  <td style={{ padding: '0.85rem 1.25rem', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                    {sig.name}
                  </td>
                  <td style={{ padding: '0.85rem 1rem', fontFamily: sig.value.length > 20 ? 'monospace' : 'inherit', fontSize: '0.8rem' }}>
                    {sig.value}
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span style={{
                      padding: '0.15rem 0.5rem',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      backgroundColor: sig.status === 'PASS' ? 'var(--govt-success-light)' : 'var(--govt-danger-light)',
                      color: sig.status === 'PASS' ? 'var(--govt-success-text)' : 'var(--govt-danger-text)',
                    }}>
                      {sig.state}
                    </span>
                  </td>
                  <td style={{ padding: '0.85rem 1.25rem', fontSize: '0.78rem', color: 'var(--govt-gray-text)' }}>
                    {sig.note}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Anomalies / Flagged Overlaps if any */}
      {evidence.anomalies && evidence.anomalies.length > 0 && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-danger-border)',
          overflow: 'hidden'
        }}>
          <div style={{
            padding: '1rem 1.25rem',
            backgroundColor: 'var(--govt-danger-light)',
            borderBottom: '1px solid var(--govt-danger-border)',
            fontWeight: 700,
            color: 'var(--govt-danger-text)',
            fontSize: '0.9rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem'
          }}>
            <span>⚠</span> Cross-Evidence Anomalies Requiring Human Review
          </div>
          <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            {evidence.anomalies.map((anom, idx) => (
              <div key={idx} style={{
                padding: '0.85rem 1rem',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--govt-gray-off-white)',
                borderLeft: '4px solid var(--govt-danger)'
              }}>
                <div style={{ fontWeight: 700, color: 'var(--govt-blue-dark)', fontSize: '0.88rem' }}>
                  {anom.title}
                </div>
                <p style={{ margin: '0.25rem 0 0', fontSize: '0.8rem', color: 'var(--govt-gray-text)', lineHeight: 1.45 }}>
                  {anom.explanation}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default EvidenceDetail;
