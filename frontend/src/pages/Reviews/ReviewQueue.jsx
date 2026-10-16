import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';

function ReviewQueue() {
  const [evidence, setEvidence] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('pending');

  // Mock data for development
  const mockEvidence = [
    {
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
      risk_level: 'HIGH'
    },
    {
      id: 'EVD-006',
      project_id: 'PRJ-005',
      project_name: 'Community Health Center',
      activity: 'Site Survey',
      status: 'pending',
      type: 'image',
      captured_at: '2024-02-26T08:30:00Z',
      integrity_score: 55,
      risk_score: 65,
      location: 'Uttar Pradesh',
      uploaded_by: 'Amit Sharma',
      risk_level: 'HIGH'
    },
    {
      id: 'EVD-004',
      project_id: 'PRJ-003',
      project_name: 'Water Tank Construction',
      activity: 'Completion',
      status: 'pending',
      type: 'image',
      captured_at: '2024-02-22T16:10:00Z',
      integrity_score: 75,
      risk_score: 30,
      location: 'Rajasthan',
      uploaded_by: 'Priya Patel',
      risk_level: 'MEDIUM'
    },
    {
      id: 'EVD-007',
      project_id: 'PRJ-002',
      project_name: 'Solar Street Light Installation',
      activity: 'Installation',
      status: 'approved',
      type: 'image',
      captured_at: '2024-02-27T15:45:00Z',
      integrity_score: 89,
      risk_score: 18,
      location: 'Gujarat',
      uploaded_by: 'Suresh Reddy',
      risk_level: 'LOW'
    },
    {
      id: 'EVD-008',
      project_id: 'PRJ-004',
      project_name: 'School Building Renovation',
      activity: 'Site Survey',
      status: 'pending',
      type: 'image',
      captured_at: '2024-02-28T10:20:00Z',
      integrity_score: 72,
      risk_score: 35,
      location: 'Karnataka',
      uploaded_by: 'Meera Iyer',
      risk_level: 'MEDIUM'
    },
    {
      id: 'EVD-009',
      project_id: 'PRJ-001',
      project_name: 'Rural Road Construction - Phase 1',
      activity: 'Surface Work',
      status: 'flagged',
      type: 'image',
      captured_at: '2024-02-29T14:00:00Z',
      integrity_score: 60,
      risk_score: 55,
      location: 'Maharashtra',
      uploaded_by: 'John Doe',
      risk_level: 'HIGH'
    },
  ];

  useEffect(() => {
    setTimeout(() => {
      setEvidence(mockEvidence);
      setLoading(false);
    }, 500);
  }, []);

  const filteredEvidence = evidence.filter(item => {
    const matchesSearch = item.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          item.project_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          item.location.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRisk = riskFilter === 'all' || item.risk_level === riskFilter;
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    return matchesSearch && matchesRisk && matchesStatus;
  });

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

  if (loading) {
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
          Loading review queue...
        </p>
      </div>
    );
  }

  return (
    <div style={{
      padding: '1.75rem 2rem',
      width: '100%',
      boxSizing: 'border-box',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '2rem',
        flexWrap: 'wrap',
        gap: '1rem'
      }}>
        <div>
          <h2 style={{
            margin: 0,
            color: 'var(--govt-blue-primary)',
            fontSize: '1.75rem'
          }}>
            Review Queue
          </h2>
          <p style={{
            margin: '0.5rem 0 0 0',
            color: 'var(--govt-gray-dark)',
            fontSize: '0.95rem'
          }}>
            Evidence requiring human review and decision
          </p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <div style={{
            backgroundColor: 'var(--govt-danger-light)',
            borderLeft: '4px solid var(--govt-danger)',
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-sm)'
          }}>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-danger-text)' }}>
              <strong>High Priority:</strong> {filteredEvidence.filter(e => e.risk_level === 'HIGH').length} items
            </p>
          </div>
          <div style={{
            backgroundColor: 'var(--govt-warning-light)',
            borderLeft: '4px solid var(--govt-warning)',
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-sm)'
          }}>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-warning-text)' }}>
              <strong>Total Pending:</strong> {filteredEvidence.filter(e => e.status === 'pending' || e.status === 'flagged').length} items
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        padding: '1.25rem',
        marginBottom: '1.5rem',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)'
      }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem'
        }}>
          <div>
            <label style={{
              display: 'block',
              marginBottom: '0.5rem',
              fontSize: '0.85rem',
              fontWeight: '600',
              color: 'var(--govt-gray-text)'
            }}>
              Search
            </label>
            <input
              type="text"
              placeholder="Search by ID, project, location..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                width: '100%',
                padding: '0.625rem',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.9rem'
              }}
            />
          </div>
          <div>
            <label style={{
              display: 'block',
              marginBottom: '0.5rem',
              fontSize: '0.85rem',
              fontWeight: '600',
              color: 'var(--govt-gray-text)'
            }}>
              Risk Level
            </label>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '0.625rem',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Risk Levels</option>
              <option value="HIGH">High Risk</option>
              <option value="MEDIUM">Medium Risk</option>
              <option value="LOW">Low Risk</option>
            </select>
          </div>
          <div>
            <label style={{
              display: 'block',
              marginBottom: '0.5rem',
              fontSize: '0.85rem',
              fontWeight: '600',
              color: 'var(--govt-gray-text)'
            }}>
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '0.625rem',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.9rem'
              }}
            >
              <option value="pending">Pending Review</option>
              <option value="flagged">Flagged Only</option>
              <option value="approved">Approved</option>
              <option value="all">All Status</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button
              onClick={() => { setSearchTerm(''); setRiskFilter('all'); setStatusFilter('pending'); }}
              style={{
                backgroundColor: 'transparent',
                border: '1px solid var(--govt-gray-dark)',
                color: 'var(--govt-gray-text)',
                padding: '0.625rem 1rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.9rem',
                cursor: 'pointer'
              }}
            >
              Clear Filters
            </button>
          </div>
        </div>
      </div>

      {/* Review Queue Table */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
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
          <span style={{ fontSize: '1rem', fontWeight: '600', color: 'var(--govt-blue-primary)' }}>
            Review Queue
          </span>
          <span style={{
            backgroundColor: '#ffffff',
            color: 'var(--govt-blue-primary)',
            padding: '0.25rem 0.75rem',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.8rem',
            fontWeight: '600'
          }}>
            {filteredEvidence.length} items
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '0.9rem'
          }}>
            <thead>
              <tr style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                borderBottom: '1px solid var(--govt-gray-medium)'
              }}>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-primary)'
                }}>
                  Evidence ID
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-primary)'
                }}>
                  Project
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-primary)'
                }}>
                  Location
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-primary)'
                }}>
                  Integrity
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-primary)'
                }}>
                  Risk
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-primary)'
                }}>
                  Status
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-primary)'
                }}>
                  Risk Level
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-primary)'
                }}>
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredEvidence.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ padding: '2rem', textAlign: 'center', color: 'var(--govt-gray-dark)' }}>
                    No evidence found matching your criteria
                  </td>
                </tr>
              ) : (
                filteredEvidence.map((item) => {
                  const integrityColor = getIntegrityColor(item.integrity_score);
                  const riskColor = getRiskColor(item.risk_score);
                  const statusColor = {
                    pending: { bg: 'var(--govt-warning-light)', text: 'var(--govt-warning-text)' },
                    flagged: { bg: 'var(--govt-danger-light)', text: 'var(--govt-danger-text)' },
                    approved: { bg: 'var(--govt-success-light)', text: 'var(--govt-success-text)' },
                  }[item.status];
                  const riskLevelColor = {
                    HIGH: { bg: 'var(--govt-danger)', text: '#ffffff' },
                    MEDIUM: { bg: 'var(--govt-warning)', text: '#333333' },
                    LOW: { bg: 'var(--govt-success)', text: '#ffffff' },
                  }[item.risk_level];

                  return (
                    <tr key={item.id} style={{
                      borderBottom: '1px solid var(--govt-gray-light)',
                      backgroundColor: item.risk_level === 'HIGH' ? '#fff5f5' : 'var(--govt-white)'
                    }}>
                      <td style={{ padding: '0.75rem 1rem', fontWeight: '600', color: 'var(--govt-blue-primary)' }}>
                        {item.id}
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <div style={{ fontWeight: '500', color: 'var(--govt-gray-text)' }}>
                          {item.project_name}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                          {item.activity}
                        </div>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                        {item.location}
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span style={{
                          backgroundColor: integrityColor.bg,
                          color: integrityColor.text,
                          padding: '0.25rem 0.625rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.75rem',
                          fontWeight: '600'
                        }}>
                          {item.integrity_score}%
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span style={{
                          backgroundColor: riskColor.bg,
                          color: riskColor.text,
                          padding: '0.25rem 0.625rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.75rem',
                          fontWeight: '600'
                        }}>
                          {item.risk_score}%
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span style={{
                          backgroundColor: statusColor.bg,
                          color: statusColor.text,
                          padding: '0.25rem 0.625rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.75rem',
                          fontWeight: '600'
                        }}>
                          {item.status.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span style={{
                          backgroundColor: riskLevelColor.bg,
                          color: riskLevelColor.text,
                          padding: '0.25rem 0.625rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.75rem',
                          fontWeight: '600'
                        }}>
                          {item.risk_level}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <div style={{ display: 'flex', gap: '0.4rem', justifyContent: 'flex-end' }}>
                          <Link
                            to={`/review/case?id=${item.case_id || (item.id === 'EVD-003' ? 'case-002-solar' : item.id === 'EVD-004' ? 'case-003-water' : 'case-001-pmgsy')}`}
                            style={{
                              backgroundColor: 'var(--govt-blue-primary)',
                              color: '#ffffff',
                              border: 'none',
                              padding: '0.35rem 0.65rem',
                              textDecoration: 'none',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.78rem',
                              fontWeight: '600',
                            }}
                          >
                            Case Workspace →
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div style={{
          padding: '1rem 1.25rem',
          borderTop: '1px solid var(--govt-gray-light)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
            Showing {filteredEvidence.length} of {evidence.length} items
          </span>
          <div style={{ display: 'flex', gap: '0.25rem' }}>
            <button style={{
              backgroundColor: 'var(--govt-gray-off-white)',
              border: '1px solid var(--govt-gray-medium)',
              color: 'var(--govt-gray-dark)',
              padding: '0.375rem 0.75rem',
              fontSize: '0.8rem',
              cursor: 'not-allowed',
              opacity: 0.5,
              borderRadius: 'var(--radius-sm)'
            }} disabled>
              Previous
            </button>
            <button style={{
              backgroundColor: 'var(--govt-blue-primary)',
              border: '1px solid var(--govt-blue-primary)',
              color: '#ffffff',
              padding: '0.375rem 0.75rem',
              fontSize: '0.8rem',
              cursor: 'default',
              borderRadius: 'var(--radius-sm)'
            }}>
              1
            </button>
            <button style={{
              backgroundColor: 'var(--govt-gray-off-white)',
              border: '1px solid var(--govt-gray-medium)',
              color: 'var(--govt-gray-dark)',
              padding: '0.375rem 0.75rem',
              fontSize: '0.8rem',
              cursor: 'not-allowed',
              opacity: 0.5,
              borderRadius: 'var(--radius-sm)'
            }} disabled>
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReviewQueue;
