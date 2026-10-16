import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';

function EvidenceList() {
  const [evidence, setEvidence] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [projectFilter, setProjectFilter] = useState('all');

  // Mock data for development
  const mockEvidence = [
    {
      id: 'EVD-001',
      project_id: 'PRJ-001',
      project_name: 'Rural Road Construction - Phase 1',
      activity: 'Road Base Layer',
      status: 'approved',
      type: 'image',
      captured_at: '2024-02-15T10:30:00Z',
      integrity_score: 92,
      risk_score: 15,
      location: 'Maharashtra',
      uploaded_by: 'John Doe'
    },
    {
      id: 'EVD-002',
      project_id: 'PRJ-001',
      project_name: 'Rural Road Construction - Phase 1',
      activity: 'Road Base Layer',
      status: 'approved',
      type: 'image',
      captured_at: '2024-02-18T14:20:00Z',
      integrity_score: 88,
      risk_score: 22,
      location: 'Maharashtra',
      uploaded_by: 'Jane Smith'
    },
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
      uploaded_by: 'Raj Kumar'
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
      uploaded_by: 'Priya Patel'
    },
    {
      id: 'EVD-005',
      project_id: 'PRJ-001',
      project_name: 'Rural Road Construction - Phase 1',
      activity: 'Foundation Work',
      status: 'approved',
      type: 'image',
      captured_at: '2024-02-25T11:00:00Z',
      integrity_score: 95,
      risk_score: 10,
      location: 'Maharashtra',
      uploaded_by: 'John Doe'
    },
    {
      id: 'EVD-006',
      project_id: 'PRJ-005',
      project_name: 'Community Health Center',
      activity: 'Site Survey',
      status: 'flagged',
      type: 'image',
      captured_at: '2024-02-26T08:30:00Z',
      integrity_score: 55,
      risk_score: 65,
      location: 'Uttar Pradesh',
      uploaded_by: 'Amit Sharma'
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
      uploaded_by: 'Suresh Reddy'
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
      uploaded_by: 'Meera Iyer'
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
                          item.location.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          item.uploaded_by.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    const matchesProject = projectFilter === 'all' || item.project_id === projectFilter;
    return matchesSearch && matchesStatus && matchesProject;
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
          Loading evidence...
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
            Evidence
          </h2>
          <p style={{
            margin: '0.5rem 0 0 0',
            color: 'var(--govt-gray-dark)',
            fontSize: '0.95rem'
          }}>
            Manage and review submitted evidence
          </p>
        </div>
        <Link to="/evidence/upload" style={{
          backgroundColor: 'var(--govt-blue-primary)',
          color: '#ffffff',
          padding: '0.75rem 1.25rem',
          textDecoration: 'none',
          borderRadius: 'var(--radius-sm)',
          fontSize: '0.9rem',
          fontWeight: '600',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          Upload Evidence
        </Link>
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
              <option value="all">All Status</option>
              <option value="approved">Approved</option>
              <option value="pending">Pending Review</option>
              <option value="flagged">Flagged</option>
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
              Project
            </label>
            <select
              value={projectFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '0.625rem',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Projects</option>
              <option value="PRJ-001">Rural Road Construction</option>
              <option value="PRJ-002">Solar Street Lights</option>
              <option value="PRJ-003">Water Tank Construction</option>
              <option value="PRJ-004">School Building Renovation</option>
              <option value="PRJ-005">Community Health Center</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button
              onClick={() => { setSearchTerm(''); setStatusFilter('all'); setProjectFilter('all'); }}
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

      {/* Evidence Table */}
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
            Evidence List
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
                  ID
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
                  Uploaded
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
                    No evidence found
                  </td>
                </tr>
              ) : (
                filteredEvidence.map((item) => {
                  const integrityColor = getIntegrityColor(item.integrity_score);
                  const riskColor = getRiskColor(item.risk_score);
                  const statusColor = {
                    approved: { bg: 'var(--govt-success-light)', text: 'var(--govt-success-text)' },
                    pending: { bg: 'var(--govt-warning-light)', text: 'var(--govt-warning-text)' },
                    flagged: { bg: 'var(--govt-danger-light)', text: 'var(--govt-danger-text)' },
                  }[item.status];

                  return (
                    <tr key={item.id} style={{
                      borderBottom: '1px solid var(--govt-gray-light)',
                      backgroundColor: 'var(--govt-white)'
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
                      <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-dark)' }}>
                        {formatDate(item.captured_at)}
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <Link to={`/evidence/${item.id}`} style={{
                            backgroundColor: 'transparent',
                            border: '1px solid var(--govt-blue-primary)',
                            color: 'var(--govt-blue-primary)',
                            padding: '0.375rem 0.625rem',
                            textDecoration: 'none',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.8rem'
                          }}>
                            View
                          </Link>
                          {item.status === 'flagged' && (
                            <Link to={`/review/${item.id}`} style={{
                              backgroundColor: 'var(--govt-success)',
                              color: '#ffffff',
                              border: 'none',
                              padding: '0.375rem 0.625rem',
                              textDecoration: 'none',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.8rem'
                        }}>
                            Review
                          </Link>
                        )}
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

export default EvidenceList;
