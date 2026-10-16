import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';
import { GraphIcon, ReviewIcon, AlertIcon } from '../../components/common/Icon';

function EvidenceDetail() {
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [evidence, setEvidence] = useState(null);

  // Pre-populated evidence database for demo / dev
  const mockDatabase = {
    'EVD-001': {
      id: 'EVD-001',
      project_id: 'PRJ-001',
      project_name: 'Rural Road Construction - Phase 1',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      activity: 'Road Base Layer',
      status: 'approved',
      type: 'image',
      captured_at: '2024-02-15T10:30:00Z',
      uploaded_at: '2024-02-15T11:05:00Z',
      uploaded_by: 'John Doe (Field Inspector - Pune Division)',
      location: 'Pune District, Maharashtra',
      gps: { latitude: '18.5204° N', longitude: '73.8567° E', accuracy: '3.2 meters' },
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
      integrity_score: 92,
      risk_score: 15,
      signals: [
        { name: 'Cryptographic SHA-256', value: 'c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2', status: 'PASS', score: 100, note: 'Hash recorded immutably at initial quarantine ingestion.' },
        { name: 'Perceptual Hash (pHash)', value: 'd4b2e8a1f0c39972', status: 'PASS', score: 95, note: 'No identical or near-duplicate frames detected across scheme database.' },
        { name: 'Geospatial Geofence', value: '18.5204, 73.8567', status: 'PASS', score: 94, note: 'Coordinates are strictly within approved project boundary polygon (variance 14m).' },
        { name: 'Temporal Consistency', value: '2024-02-15 10:30 IST', status: 'PASS', score: 90, note: 'Timestamp conforms with milestone schedule and inspector transit logs.' },
        { name: 'Vision / Claim Matching', value: 'Compacted Gravel, Roadbed, Roller', status: 'PASS', score: 88, note: 'Object detection confirms sub-base gravel aggregate and compaction equipment.' }
      ],
      anomalies: [],
      similar_evidence: [
        { id: 'EVD-002', project: 'PRJ-001', match_type: 'Sequential Corroboration', similarity: '82%', status: 'Approved' }
      ]
    },
    'EVD-003': {
      id: 'EVD-003',
      project_id: 'PRJ-002',
      project_name: 'Solar Street Light Installation',
      scheme: 'Solar Energy Programme',
      activity: 'Pole & Panel Installation',
      status: 'flagged',
      type: 'image',
      captured_at: '2024-02-20T09:45:00Z',
      uploaded_at: '2024-02-20T10:12:00Z',
      uploaded_by: 'Raj Kumar (Contractor Liaison)',
      location: 'Surat District, Gujarat',
      gps: { latitude: '21.1702° N', longitude: '72.8311° E', accuracy: '45.0 meters' },
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
      integrity_score: 45,
      risk_score: 78,
      signals: [
        { name: 'Cryptographic SHA-256', value: '8f43a992e564177b89d4d2320b99ac18721539bb409e5b7c7fa91823bb0d0821', status: 'PASS', score: 90, note: 'File binary byte-stream is well-formed.' },
        { name: 'Perceptual Hash (pHash)', value: 'b2f8e1a093c44881', status: 'FLAGGED', score: 32, note: 'Visual fingerprint shares 89% hamming similarity with evidence from PRJ-001.' },
        { name: 'Geospatial Geofence', value: '21.1702, 72.8311', status: 'FLAGGED', score: 40, note: 'Capture coordinates fall 12.4 km outside sanctioned village boundary polygon.' },
        { name: 'Temporal Consistency', value: '2024-02-20 09:45 IST', status: 'WARNING', score: 55, note: 'Photo creation timestamp precedes work-order release date by 3 days.' },
        { name: 'Vision / Claim Matching', value: 'Solar Pole, Vegetation, Road', status: 'PASS', score: 75, note: 'Objects align with claim, but duplicate angle strongly suspected.' }
      ],
      anomalies: [
        { code: 'CROSS_PROJECT_DUPLICATE', severity: 'HIGH', title: 'Cross-Project Visual Near-Duplicate', explanation: 'This image exhibits 89% perceptual feature overlap with evidence EVD-001 originally submitted under Project PRJ-001 in another state.' },
        { code: 'GEOFENCE_VIOLATION', severity: 'HIGH', title: 'Geofence Boundary Violation', explanation: 'Calculated GPS coordinates (21.1702, 72.8311) are 12.4 km beyond the approved geofenced boundary for village ward 4.' },
        { code: 'TIMELINE_INVERSION', severity: 'MEDIUM', title: 'Timeline Inversion Detected', explanation: 'EXIF internal capture timestamp precedes activity commencement authorization.' }
      ],
      similar_evidence: [
        { id: 'EVD-001', project: 'PRJ-001 (Maharashtra)', match_type: 'Perceptual Hash Duplicate', similarity: '89%', status: 'Flagged for Review' },
        { id: 'EVD-002', project: 'PRJ-001 (Maharashtra)', match_type: 'Vector Embedding Overlap', similarity: '74%', status: 'Under Review' }
      ]
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      const selected = mockDatabase[id] || {
        ...mockDatabase['EVD-001'],
        id: id || 'EVD-004',
        status: 'pending',
        integrity_score: 75,
        risk_score: 30,
        anomalies: [
          { code: 'METADATA_INCOMPLETE', severity: 'LOW', title: 'Missing Lens Aperture Metadata', explanation: 'Camera application did not serialize complete optical parameters.' }
        ]
      };
      setEvidence(selected);
      setLoading(false);
    }, 400);

    return () => clearTimeout(timer);
  }, [id]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh', flexDirection: 'column' }}>
        <div className="spinner" style={{ width: '40px', height: '40px' }}></div>
        <p style={{ marginTop: '1rem', color: 'var(--govt-gray-dark)', fontSize: '0.95rem' }}>Loading evidence dossiers and signal telemetry...</p>
      </div>
    );
  }

  if (!evidence) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <h3>Evidence not found</h3>
        <Link to="/evidence" className="btn btn-primary mt-3">Back to Evidence List</Link>
      </div>
    );
  }

  const getScoreColor = (score, isRisk = false) => {
    if (isRisk) {
      if (score >= 60) return { bg: 'var(--govt-danger)', light: 'var(--govt-danger-light)', text: '#ffffff', label: 'HIGH RISK' };
      if (score >= 35) return { bg: 'var(--govt-warning)', light: 'var(--govt-warning-light)', text: '#212529', label: 'MEDIUM RISK' };
      return { bg: 'var(--govt-success)', light: 'var(--govt-success-light)', text: '#ffffff', label: 'LOW RISK' };
    }
    if (score >= 80) return { bg: 'var(--govt-success)', light: 'var(--govt-success-light)', text: '#ffffff', label: 'HIGH INTEGRITY' };
    if (score >= 55) return { bg: 'var(--govt-warning)', light: 'var(--govt-warning-light)', text: '#212529', label: 'MODERATE INTEGRITY' };
    return { bg: 'var(--govt-danger)', light: 'var(--govt-danger-light)', text: '#ffffff', label: 'LOW INTEGRITY' };
  };

  const integrityStyle = getScoreColor(evidence.integrity_score, false);
  const riskStyle = getScoreColor(evidence.risk_score, true);

  return (
    <div style={{ padding: '1.75rem 2rem', width: '100%', boxSizing: 'border-box', backgroundColor: 'var(--govt-gray-off-white)' }}>
      {/* Breadcrumb Navigation */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', fontSize: '0.875rem', color: 'var(--govt-gray-dark)' }}>
        <Link to="/dashboard" style={{ color: 'var(--govt-blue-primary)', textDecoration: 'none' }}>Dashboard</Link>
        <span>/</span>
        <Link to="/evidence" style={{ color: 'var(--govt-blue-primary)', textDecoration: 'none' }}>Evidence Registry</Link>
        <span>/</span>
        <span style={{ fontWeight: '600', color: 'var(--govt-gray-text)' }}>{evidence.id}</span>
      </div>

      {/* Header and Action Bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        flexWrap: 'wrap',
        gap: '1rem',
        marginBottom: '1.5rem',
        paddingBottom: '1rem',
        borderBottom: '2px solid var(--govt-gray-medium)'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h2 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.75rem' }}>
              Evidence Dossier: {evidence.id}
            </h2>
            <span style={{
              backgroundColor: evidence.status === 'flagged' ? 'var(--govt-danger-light)' : evidence.status === 'approved' ? 'var(--govt-success-light)' : 'var(--govt-warning-light)',
              color: evidence.status === 'flagged' ? 'var(--govt-danger)' : evidence.status === 'approved' ? 'var(--govt-success)' : 'var(--govt-warning)',
              border: `1px solid ${evidence.status === 'flagged' ? 'var(--govt-danger)' : evidence.status === 'approved' ? 'var(--govt-success)' : 'var(--govt-warning)'}`,
              padding: '0.2rem 0.6rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.75rem',
              fontWeight: '700',
              textTransform: 'uppercase'
            }}>
              {evidence.status}
            </span>
          </div>
          <p style={{ margin: 0, color: 'var(--govt-gray-dark)', fontSize: '0.95rem' }}>
            Scheme: <strong>{evidence.scheme}</strong> • Project: <Link to={`/projects/${evidence.project_id}`} style={{ color: 'var(--govt-blue-primary)' }}>{evidence.project_name}</Link>
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <Link
            to={`/graph?highlight=${evidence.id}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              backgroundColor: 'var(--govt-white)',
              color: 'var(--govt-blue-primary)',
              border: '1px solid var(--govt-blue-primary)',
              padding: '0.625rem 1rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.9rem',
              fontWeight: '600',
              textDecoration: 'none'
            }}
          >
            <GraphIcon />
            View in Evidence Graph
          </Link>
          {evidence.status === 'flagged' && (
            <Link
              to={`/review/${evidence.id}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                backgroundColor: 'var(--govt-danger)',
                color: '#ffffff',
                border: 'none',
                padding: '0.625rem 1rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.9rem',
                fontWeight: '600',
                textDecoration: 'none'
              }}
            >
              <ReviewIcon />
              Review Anomaly
            </Link>
          )}
        </div>
      </div>

      {/* Main Grid: Left Column Details & Preview, Right Column Fusion Engine Scores */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Left: Visual Evidence Card */}
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-md)',
          padding: '1.5rem',
          border: '1px solid var(--govt-gray-medium)',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <h4 style={{ margin: '0 0 1rem 0', color: 'var(--govt-blue-primary)', fontSize: '1.1rem' }}>
            Submitted Field Media
          </h4>

          {/* Media Simulated Viewport */}
          <div style={{
            position: 'relative',
            height: '260px',
            backgroundColor: '#1a202c',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '1rem',
            border: '2px solid var(--govt-gray-light)'
          }}>
            <div style={{ textAlign: 'center', color: '#e2e8f0', padding: '1rem' }}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ margin: '0 auto 0.5rem auto', opacity: 0.8 }}>
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <polyline points="21 15 16 10 5 21"/>
              </svg>
              <p style={{ margin: 0, fontWeight: '600', fontSize: '0.9rem' }}>{evidence.file_meta.filename}</p>
              <span style={{ fontSize: '0.75rem', opacity: 0.75 }}>{evidence.file_meta.dimensions} • {evidence.file_meta.file_size} • {evidence.file_meta.mime_type}</span>
            </div>

            {/* Overlaid GPS watermark */}
            <div style={{
              position: 'absolute',
              bottom: '8px',
              left: '8px',
              backgroundColor: 'rgba(0, 0, 0, 0.75)',
              color: '#ffffff',
              padding: '0.3rem 0.6rem',
              fontSize: '0.7rem',
              borderRadius: '2px',
              fontFamily: 'var(--font-family-mono)'
            }}>
              GPS: {evidence.gps.latitude}, {evidence.gps.longitude}
            </div>
          </div>

          <div style={{ fontSize: '0.9rem', color: 'var(--govt-gray-text)', marginBottom: '1rem' }}>
            <p style={{ margin: '0 0 0.5rem 0' }}><strong>Activity Claim:</strong> {evidence.activity}</p>
            <p style={{ margin: 0 }}><strong>Field Description:</strong> {evidence.description}</p>
          </div>

          {/* Metadata Grid */}
          <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '0.85rem', borderRadius: 'var(--radius-sm)', fontSize: '0.825rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              <div><span style={{ color: 'var(--govt-gray-dark)' }}>Camera Device:</span> <div><strong>{evidence.file_meta.camera_make} {evidence.file_meta.camera_model}</strong></div></div>
              <div><span style={{ color: 'var(--govt-gray-dark)' }}>Capture Time:</span> <div><strong>{formatDate(evidence.captured_at)}</strong></div></div>
              <div><span style={{ color: 'var(--govt-gray-dark)' }}>Exposure / Lens:</span> <div><strong>{evidence.file_meta.focal_length} ({evidence.file_meta.exposure})</strong></div></div>
              <div><span style={{ color: 'var(--govt-gray-dark)' }}>Uploaded By:</span> <div><strong>{evidence.uploaded_by}</strong></div></div>
            </div>
          </div>
        </div>

        {/* Right: Multi-Signal Fusion Engine Output */}
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-md)',
          padding: '1.5rem',
          border: '1px solid var(--govt-gray-medium)',
          boxShadow: 'var(--shadow-sm)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between'
        }}>
          <div>
            <h4 style={{ margin: '0 0 1rem 0', color: 'var(--govt-blue-primary)', fontSize: '1.1rem' }}>
              EIIL Multi-Signal Fusion Output
            </h4>

            {/* Scores Dual Panel */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
              {/* Integrity Score */}
              <div style={{
                padding: '1.25rem',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--govt-gray-off-white)',
                borderLeft: `5px solid ${integrityStyle.bg}`,
                boxShadow: 'var(--shadow-sm)'
              }}>
                <span style={{ fontSize: '0.75rem', fontWeight: '700', color: 'var(--govt-gray-dark)', textTransform: 'uppercase' }}>
                  Integrity Rating
                </span>
                <div style={{ fontSize: '2.25rem', fontWeight: '800', color: integrityStyle.bg, margin: '0.25rem 0' }}>
                  {evidence.integrity_score}<span style={{ fontSize: '1rem', color: 'var(--govt-gray-dark)' }}>/100</span>
                </div>
                <span style={{
                  display: 'inline-block',
                  backgroundColor: integrityStyle.bg,
                  color: integrityStyle.text,
                  fontSize: '0.7rem',
                  fontWeight: '700',
                  padding: '0.15rem 0.5rem',
                  borderRadius: '2px'
                }}>
                  {integrityStyle.label}
                </span>
              </div>

              {/* Risk Score */}
              <div style={{
                padding: '1.25rem',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--govt-gray-off-white)',
                borderLeft: `5px solid ${riskStyle.bg}`,
                boxShadow: 'var(--shadow-sm)'
              }}>
                <span style={{ fontSize: '0.75rem', fontWeight: '700', color: 'var(--govt-gray-dark)', textTransform: 'uppercase' }}>
                  Fraud Risk Rating
                </span>
                <div style={{ fontSize: '2.25rem', fontWeight: '800', color: riskStyle.bg, margin: '0.25rem 0' }}>
                  {evidence.risk_score}<span style={{ fontSize: '1rem', color: 'var(--govt-gray-dark)' }}>/100</span>
                </div>
                <span style={{
                  display: 'inline-block',
                  backgroundColor: riskStyle.bg,
                  color: riskStyle.text,
                  fontSize: '0.7rem',
                  fontWeight: '700',
                  padding: '0.15rem 0.5rem',
                  borderRadius: '2px'
                }}>
                  {riskStyle.label}
                </span>
              </div>
            </div>

            {/* Core Principle Notice */}
            <div style={{
              backgroundColor: 'var(--govt-blue-light)',
              border: '1px solid var(--govt-blue-primary)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.85rem',
              fontSize: '0.85rem',
              color: 'var(--govt-blue-dark)',
              marginBottom: '1rem'
            }}>
              <strong>Evidence Verification Principle:</strong> Integrity measures technical consistency & completeness of evidence; Risk evaluates patterns indicating duplication or geographic discrepancies. Neither score constitutes unilateral approval or rejection without authorized review.
            </div>
          </div>

          <div style={{ fontSize: '0.85rem', color: 'var(--govt-gray-dark)', borderTop: '1px solid var(--govt-gray-light)', paddingTop: '0.75rem' }}>
            Verification Engine: <strong>EIIL Fusion v1.2</strong> • Rule Version: <strong>2026.10-IN</strong>
          </div>
        </div>
      </div>

      {/* Anomalies Alert Box (if present) */}
      {evidence.anomalies.length > 0 && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-md)',
          padding: '1.5rem',
          border: '1px solid var(--govt-danger)',
          borderLeft: '6px solid var(--govt-danger)',
          marginBottom: '1.5rem',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--govt-danger)', marginBottom: '1rem' }}>
            <AlertIcon />
            <h4 style={{ margin: 0, fontSize: '1.15rem' }}>
              Detected Anomalies & Inconsistencies ({evidence.anomalies.length})
            </h4>
          </div>

          <div style={{ display: 'grid', gap: '0.75rem' }}>
            {evidence.anomalies.map((ano, idx) => (
              <div key={idx} style={{
                backgroundColor: 'var(--govt-danger-light)',
                padding: '1rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid rgba(220, 53, 69, 0.2)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                  <strong style={{ color: 'var(--govt-danger)', fontSize: '0.95rem' }}>{ano.title}</strong>
                  <span style={{
                    backgroundColor: ano.severity === 'HIGH' ? 'var(--govt-danger)' : 'var(--govt-warning)',
                    color: '#ffffff',
                    fontSize: '0.7rem',
                    fontWeight: '700',
                    padding: '0.15rem 0.5rem',
                    borderRadius: '2px'
                  }}>
                    {ano.severity} SEVERITY
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: '0.85rem', color: '#491217', lineHeight: 1.4 }}>
                  {ano.explanation}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Independent Signals Breakdown Table */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--govt-gray-medium)',
        marginBottom: '1.5rem',
        boxShadow: 'var(--shadow-sm)',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: '1rem 1.25rem',
          backgroundColor: 'var(--govt-blue-light)',
          borderBottom: '2px solid var(--govt-blue-primary)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <h4 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.05rem' }}>
            Independent Signal Assessment Matrix
          </h4>
          <span style={{ fontSize: '0.8rem', color: 'var(--govt-blue-dark)' }}>
            5 of 5 Analyzers Completed
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--govt-gray-off-white)', borderBottom: '1px solid var(--govt-gray-medium)' }}>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Signal Category</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Diagnostic Signature / Value</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--govt-blue-dark)' }}>Score</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--govt-blue-dark)' }}>Verification Status</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Engine Finding</th>
              </tr>
            </thead>
            <tbody>
              {evidence.signals.map((sig, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                  <td style={{ padding: '0.75rem 1rem', fontWeight: '600', color: 'var(--govt-gray-text)' }}>
                    {sig.name}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-family-mono)', fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                    {sig.value}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'center', fontWeight: '700' }}>
                    {sig.score}%
                  </td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-block',
                      backgroundColor: sig.status === 'PASS' ? 'var(--govt-success-light)' : sig.status === 'FLAGGED' ? 'var(--govt-danger-light)' : 'var(--govt-warning-light)',
                      color: sig.status === 'PASS' ? 'var(--govt-success)' : sig.status === 'FLAGGED' ? 'var(--govt-danger)' : '#856404',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '2px',
                      fontSize: '0.75rem',
                      fontWeight: '700'
                    }}>
                      {sig.status}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)', fontSize: '0.825rem' }}>
                    {sig.note}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Corroboration & Similar Evidence Across Projects */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        padding: '1.25rem 1.5rem',
        border: '1px solid var(--govt-gray-medium)',
        boxShadow: 'var(--shadow-sm)'
      }}>
        <h4 style={{ margin: '0 0 1rem 0', color: 'var(--govt-blue-primary)', fontSize: '1.05rem' }}>
          Cross-Evidence Corroboration & Duplication Matches
        </h4>

        {evidence.similar_evidence.length === 0 ? (
          <p style={{ margin: 0, color: 'var(--govt-gray-dark)', fontSize: '0.9rem' }}>
            No near-duplicates or conflicting media identified across the repository.
          </p>
        ) : (
          <div style={{ display: 'grid', gap: '0.75rem' }}>
            {evidence.similar_evidence.map((sim, idx) => (
              <div key={idx} style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '0.75rem 1rem',
                backgroundColor: 'var(--govt-gray-off-white)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--govt-gray-medium)',
                flexWrap: 'wrap',
                gap: '0.5rem'
              }}>
                <div>
                  <Link to={`/evidence/${sim.id}`} style={{ fontWeight: '600', color: 'var(--govt-blue-primary)', marginRight: '0.5rem' }}>
                    {sim.id}
                  </Link>
                  <span style={{ fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>({sim.project})</span>
                  <div style={{ fontSize: '0.8rem', color: 'var(--govt-gray-text)', marginTop: '0.2rem' }}>
                    Relationship: <strong>{sim.match_type}</strong>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>Hamming Similarity</span>
                    <div style={{ fontWeight: '700', color: 'var(--govt-blue-dark)' }}>{sim.similarity}</div>
                  </div>
                  <Link to={`/graph?highlight=${evidence.id}&compare=${sim.id}`} style={{
                    backgroundColor: 'var(--govt-blue-primary)',
                    color: '#ffffff',
                    padding: '0.35rem 0.75rem',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.8rem',
                    textDecoration: 'none',
                    fontWeight: '600'
                  }}>
                    Compare in Graph
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default EvidenceDetail;
