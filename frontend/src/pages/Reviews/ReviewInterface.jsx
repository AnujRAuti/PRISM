import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';

function ReviewInterface() {
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [decision, setDecision] = useState('');
  const [comments, setComments] = useState('');
  const [showSuccess, setShowSuccess] = useState(false);

  // Mock evidence data
  const [evidence, setEvidence] = useState({
    id: 'EVD-003',
    project_id: 'PRJ-002',
    project_name: 'Solar Street Light Installation',
    activity: 'Installation',
    status: 'flagged',
    type: 'image',
    captured_at: '2024-02-20T09:45:00Z',
    integrity_score: 45,
    risk_score: 78,
    location: 'Gujarat',
    uploaded_by: 'Raj Kumar',
    description: 'Photograph of solar street light installation',
    metadata: {
      camera: 'Samsung Galaxy S21',
      dimensions: '1920x1080',
      file_size: '2.4 MB',
      mime_type: 'image/jpeg',
      created_at: '2024-02-20T09:45:00Z'
    },
    signals: {
      gps: { score: 85, status: 'PASS' },
      temporal: { score: 60, status: 'WARNING' },
      duplicate: { score: 45, status: 'WARNING' },
      metadata: { score: 70, status: 'WARNING' },
      visual: { score: 55, status: 'WARNING' }
    },
    anomalies: [
      { type: 'DUPLICATE_FOUND', severity: 'HIGH', confidence: 0.85, description: 'Visually similar image found in project PRJ-001' },
      { type: 'LOCATION_MISMATCH', severity: 'MEDIUM', confidence: 0.72, description: 'GPS coordinates are 12 km outside project geofence' }
    ],
    similar_evidence: [
      { id: 'EVD-003-alt', project: 'PRJ-001', similarity: 78, type: 'PERCEPTUAL' }
    ],
    analysis_result: {
      integrity: { score: 45, confidence: 0.82 },
      risk: { score: 78, level: 'HIGH' },
      explanation: 'Evidence has multiple anomalies indicating potential issues with authenticity or location'
    }
  });

  useEffect(() => {
    setTimeout(() => {
      setLoading(false);
    }, 500);
  }, [id]);

  const getIntegrityColor = (score) => {
    if (score >= 80) return { bg: 'var(--govt-success)', text: '#ffffff' };
    if (score >= 60) return { bg: 'var(--govt-warning)', text: '#333333' };
    return { bg: 'var(--govt-danger)', text: '#ffffff' };
  };

  const getRiskColor = (score) => {
    if (score <= 25) return { bg: 'var(--govt-success)', text: '#ffffff' };
    if (score <= 50) return { bg: 'var(--govt-warning)', text: '#333333' };
    return { bg: 'var(--govt-danger)', text: '#ffffff' };
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'CRITICAL': return { bg: 'var(--govt-danger)', text: '#ffffff' };
      case 'HIGH': return { bg: '#ff6b6b', text: '#ffffff' };
      case 'MEDIUM': return { bg: 'var(--govt-warning)', text: '#333333' };
      case 'LOW': return { bg: 'var(--govt-info)', text: '#ffffff' };
      default: return { bg: 'var(--govt-gray-medium)', text: '#ffffff' };
    }
  };

  const handleDecision = async () => {
    if (!decision) {
      alert('Please select a decision');
      return;
    }

    setLoading(true);
    // Simulate API call
    setTimeout(() => {
      setShowSuccess(true);
      setTimeout(() => {
        setShowSuccess(false);
        setLoading(false);
        // Reset form
        setDecision('');
        setComments('');
      }, 2000);
    }, 1000);
  };

  if (loading && !showSuccess) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '300px',
        flexDirection: 'column'
      }}>
        <div className="spinner" style={{
          width: '40px',
          height: '40px',
          borderWidth: '3px'
        }}></div>
        <p style={{ marginTop: '1rem', color: 'var(--govt-gray-dark)' }}>
          Loading evidence details...
        </p>
      </div>
    );
  }

  if (showSuccess) {
    return (
      <div style={{
        padding: '1.5rem',
        maxWidth: '1200px',
        margin: '0 auto',
        backgroundColor: 'var(--govt-gray-off-white)',
        minHeight: 'calc(100vh - 60px)',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center'
      }}>
        <div style={{
          width: '80px',
          height: '80px',
          backgroundColor: 'var(--govt-success)',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '1.5rem'
        }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M20 6L9 17l-5-5" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <h2 style={{ color: 'var(--govt-success)', marginBottom: '0.5rem' }}>
          Decision Saved
        </h2>
        <p style={{ color: 'var(--govt-gray-dark)' }}>
          Your review has been recorded successfully.
        </p>
        <Link to="/reviews" style={{
          backgroundColor: 'var(--govt-blue-primary)',
          color: '#ffffff',
          padding: '0.75rem 1.5rem',
          textDecoration: 'none',
          borderRadius: 'var(--radius-sm)',
          marginTop: '1.5rem',
          display: 'inline-block'
        }}>
          Back to Review Queue
        </Link>
      </div>
    );
  }

  return (
    <div style={{
      padding: '1.75rem 2rem',
      width: '100%',
      boxSizing: 'border-box',
    }}>
      {/* Breadcrumb */}
      <nav style={{ marginBottom: '1.5rem' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          fontSize: '0.9rem'
        }}>
          <Link to="/reviews" style={{ color: 'var(--govt-blue-medium)', textDecoration: 'none' }}>
            Review Queue
          </Link>
          <span style={{ color: 'var(--govt-gray-dark)' }}>→</span>
          <span style={{ color: 'var(--govt-gray-text)', fontWeight: '500' }}>
            Evidence {evidence.id}
          </span>
        </div>
      </nav>

      <h2 style={{
        margin: 0,
        color: 'var(--govt-blue-primary)',
        fontSize: '1.75rem',
        marginBottom: '1.5rem'
      }}>
        Review Evidence: {evidence.id}
      </h2>

      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '1.5rem'
      }}>
        {/* Left Column - Evidence Preview */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Evidence Preview */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)'
          }}>
            <div style={{
              backgroundColor: 'var(--govt-blue-dark)',
              color: '#ffffff',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md) var(--radius-md) 0 0'
            }}>
              <h4 style={{ margin: 0, fontSize: '1rem' }}>
                Evidence Preview
              </h4>
            </div>
            <div style={{
              padding: '1.25rem',
              backgroundColor: 'var(--govt-gray-off-white)',
              textAlign: 'center',
              minHeight: '200px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <div style={{
                padding: '2rem',
                backgroundColor: '#ffffff',
                borderRadius: 'var(--radius-md)',
                boxShadow: 'var(--shadow-sm)'
              }}>
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2z" stroke="var(--govt-gray-dark)" strokeWidth="2"/>
                  <path d="M8 15a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" stroke="var(--govt-gray-dark)" strokeWidth="2"/>
                </svg>
                <p style={{ marginTop: '1rem', color: 'var(--govt-gray-dark)' }}>
                  {evidence.metadata?.mime_type || 'image/jpeg'}
                  <br />
                  {evidence.metadata?.dimensions || '1920x1080'}
                  <br />
                  {evidence.metadata?.file_size || '2.4 MB'}
                </p>
              </div>
            </div>
            <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid var(--govt-gray-light)' }}>
              <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
                <strong>Location:</strong> {evidence.location}
              </p>
              <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
                <strong>Uploaded by:</strong> {evidence.uploaded_by}
              </p>
              <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
                <strong>Captured at:</strong> {formatDate(evidence.captured_at)}
              </p>
            </div>
          </div>

          {/* Project Info */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)'
          }}>
            <div style={{
              backgroundColor: 'var(--govt-gray-light)',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md) var(--radius-md) 0 0'
            }}>
              <h5 style={{ margin: 0, fontSize: '0.95rem', fontWeight: '600' }}>
                Project Information
              </h5>
            </div>
            <div style={{ padding: '1.25rem' }}>
              <div style={{ marginBottom: '0.75rem' }}>
                <strong style={{ color: 'var(--govt-gray-dark)' }}>Project:</strong>{' '}
                <span style={{ color: 'var(--govt-blue-primary)' }}>{evidence.project_name}</span>
              </div>
              <div style={{ marginBottom: '0.75rem' }}>
                <strong style={{ color: 'var(--govt-gray-dark)' }}>Activity:</strong>{' '}
                <span style={{ color: 'var(--govt-gray-text)' }}>{evidence.activity}</span>
              </div>
              <div style={{ marginBottom: '0.75rem' }}>
                <strong style={{ color: 'var(--govt-gray-dark)' }}>Current Status:</strong>{' '}
                <span style={{
                  backgroundColor: evidence.status === 'flagged' ? 'var(--govt-danger-light)' : 'var(--govt-warning-light)',
                  color: evidence.status === 'flagged' ? 'var(--govt-danger-text)' : 'var(--govt-warning-text)',
                  padding: '0.25rem 0.625rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.75rem',
                  fontWeight: '600'
                }}>
                  {evidence.status.toUpperCase()}
                </span>
              </div>
              <div>
                <strong style={{ color: 'var(--govt-gray-dark)' }}>Description:</strong>{' '}
                <span style={{ color: 'var(--govt-gray-text)' }}>{evidence.description}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column - Analysis & Decision */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Analysis Summary */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)'
          }}>
            <div style={{
              backgroundColor: 'var(--govt-blue-dark)',
              color: '#ffffff',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md) var(--radius-md) 0 0'
            }}>
              <h4 style={{ margin: 0, fontSize: '1rem' }}>
                Analysis Summary
              </h4>
            </div>
            <div style={{ padding: '1.25rem' }}>
              <div style={{
                display: 'flex',
                gap: '1.5rem',
                marginBottom: '1.5rem'
              }}>
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <div style={{
                    width: '80px',
                    height: '80px',
                    margin: '0 auto',
                    backgroundColor: getIntegrityColor(evidence.integrity_score).bg,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: getIntegrityColor(evidence.integrity_score).text
                  }}>
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M12 2l9 4-4 9 4 9-9 4-9-4 4-9-4-9z" fill="currentColor"/>
                    </svg>
                  </div>
                  <p style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
                    Integrity Score
                  </p>
                  <p style={{ fontSize: '1.5rem', fontWeight: '600', color: 'var(--govt-blue-primary)' }}>
                    {evidence.integrity_score}%
                  </p>
                </div>
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <div style={{
                    width: '80px',
                    height: '80px',
                    margin: '0 auto',
                    backgroundColor: getRiskColor(evidence.risk_score).bg,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: getRiskColor(evidence.risk_score).text
                  }}>
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="currentColor"/>
                    </svg>
                  </div>
                  <p style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
                    Risk Score
                  </p>
                  <p style={{ fontSize: '1.5rem', fontWeight: '600', color: 'var(--govt-blue-primary)' }}>
                    {evidence.risk_score}%
                  </p>
                </div>
              </div>

              {/* Explanation */}
              <div style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                padding: '1rem',
                borderRadius: 'var(--radius-sm)',
                marginBottom: '1rem'
              }}>
                <h6 style={{
                  margin: '0 0 0.5rem 0',
                  fontSize: '0.9rem',
                  color: 'var(--govt-gray-text)'
                }}>
                  Analysis Result
                </h6>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
                  {evidence.analysis_result.explanation}
                </p>
              </div>

              {/* Signal Breakdown */}
              <h6 style={{
                margin: '1rem 0 0.5rem 0',
                fontSize: '0.9rem',
                color: 'var(--govt-gray-text)'
              }}>
                Signal Breakdown
              </h6>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem' }}>
                {Object.entries(evidence.signals).map(([signal, data]) => {
                  const color = data.score >= 70 ? 'var(--govt-success)' : data.score >= 50 ? 'var(--govt-warning)' : 'var(--govt-danger)';
                  return (
                    <div key={signal} style={{
                      padding: '0.75rem',
                      backgroundColor: 'var(--govt-gray-off-white)',
                      borderRadius: 'var(--radius-sm)',
                      textAlign: 'center'
                    }}>
                      <div style={{ textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: '600', color: 'var(--govt-gray-dark)' }}>
                        {signal}
                      </div>
                      <div style={{ fontSize: '1.25rem', fontWeight: '600', color: color }}>
                        {data.score}%
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>
                        {data.status}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Anomalies */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)'
          }}>
            <div style={{
              backgroundColor: 'var(--govt-danger-light)',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md) var(--radius-md) 0 0'
            }}>
              <h5 style={{ margin: 0, fontSize: '0.95rem', fontWeight: '600', color: 'var(--govt-danger-text)' }}>
                Anomalies Detected
              </h5>
            </div>
            <div style={{ padding: '1.25rem' }}>
              {evidence.anomalies.length === 0 ? (
                <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--govt-success)' }}>
                  No anomalies detected
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {evidence.anomalies.map((anomaly, index) => {
                    const severityColor = getSeverityColor(anomaly.severity);
                    return (
                      <div key={index} style={{
                        padding: '0.75rem 1rem',
                        backgroundColor: 'var(--govt-gray-off-gray)',
                        borderRadius: 'var(--radius-sm)',
                        borderLeft: `3px solid ${severityColor.bg}`
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                          <strong style={{ color: 'var(--govt-gray-text)', fontSize: '0.85rem', textTransform: 'uppercase' }}>
                            {anomaly.type}
                          </strong>
                          <span style={{
                            backgroundColor: severityColor.bg,
                            color: severityColor.text,
                            padding: '0.125rem 0.5rem',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.7rem',
                            fontWeight: '600'
                          }}>
                            {anomaly.severity}
                          </span>
                        </div>
                        <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                          {anomaly.description}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Review Decision */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)'
          }}>
            <div style={{
              backgroundColor: 'var(--govt-blue-dark)',
              color: '#ffffff',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md) var(--radius-md) 0 0'
            }}>
              <h4 style={{ margin: 0, fontSize: '1rem' }}>
                Review Decision
              </h4>
            </div>
            <div style={{ padding: '1.25rem' }}>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{
                  display: 'block',
                  marginBottom: '0.5rem',
                  fontWeight: '600',
                  color: 'var(--govt-gray-text)'
                }}>
                  Decision <span style={{ color: 'var(--govt-danger)' }}>*</span>
                </label>
                <select
                  value={decision}
                  onChange={(e) => setDecision(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.625rem',
                    border: '1px solid var(--govt-gray-medium)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '1rem'
                  }}
                >
                  <option value="">Select a decision...</option>
                  <option value="APPROVE">Approve - Evidence is valid</option>
                  <option value="REJECT">Reject - Evidence is invalid</option>
                  <option value="FLAG">Flag for further review</option>
                  <option value="REQUEST_RESUBMISSION">Request resubmission</option>
                  <option value="REQUEST_FIELD_INSPECTION">Request field inspection</option>
                </select>
              </div>

              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{
                  display: 'block',
                  marginBottom: '0.5rem',
                  fontWeight: '600',
                  color: 'var(--govt-gray-text)'
                }}>
                  Comments (Optional)
                </label>
                <textarea
                  placeholder="Add your review comments..."
                  value={comments}
                  onChange={(e) => setComments(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.625rem',
                    border: '1px solid var(--govt-gray-medium)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '1rem',
                    minHeight: '100px',
                    resize: 'vertical'
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: '1rem' }}>
                <Link to="/reviews" style={{
                  padding: '0.75rem 1.5rem',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--govt-gray-text)',
                  textDecoration: 'none',
                  fontWeight: '500',
                  flex: 1,
                  textAlign: 'center'
                }}>
                  Skip
                </Link>
                <button
                  onClick={handleDecision}
                  disabled={loading}
                  style={{
                    padding: '0.75rem 1.5rem',
                    backgroundColor: decision === 'APPROVE' ? 'var(--govt-success)' : 'var(--govt-blue-primary)',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: 'var(--radius-sm)',
                    fontWeight: '600',
                    cursor: 'pointer',
                    flex: 1,
                    fontSize: '1rem'
                  }}
                >
                  {loading ? 'Submitting...' : 'Submit Decision'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReviewInterface;
