import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';
import { projectApi } from '../../services/api';

function ProjectDetail() {
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [loading, setLoading] = useState(true);

  // Mock data for development
  const mockProject = {
    id: 'PRJ-001',
    name: 'Rural Road Construction - Phase 1',
    scheme: 'Pradhan Mantri Gram Sadak Yojana',
    description: 'Construction of all-weather rural roads connecting villages to main roads under the Pradhan Mantri Gram Sadak Yojana scheme.',
    status: 'active',
    location: 'Pune District',
    state: 'Maharashtra',
    district: 'Pune',
    start_date: '2024-01-01',
    end_date: '2024-12-31',
    created_at: '2024-01-15T10:30:00Z',
    evidence_count: 45,
    activities: [
      { id: 'ACT-001', name: 'Site Survey', status: 'completed', progress: 100 },
      { id: 'ACT-002', name: 'Foundation Work', status: 'completed', progress: 100 },
      { id: 'ACT-003', name: 'Road Base Layer', status: 'active', progress: 65 },
      { id: 'ACT-004', name: 'Surface Work', status: 'pending', progress: 0 },
      { id: 'ACT-005', name: 'Final Inspection', status: 'pending', progress: 0 },
    ],
  };

  const mockEvidence = [
    { id: 'EVD-001', type: 'image', status: 'approved', captured_at: '2024-02-15T10:30:00Z', integrity: 92, risk: 15 },
    { id: 'EVD-002', type: 'image', status: 'approved', captured_at: '2024-02-18T14:20:00Z', integrity: 88, risk: 22 },
    { id: 'EVD-003', type: 'image', status: 'flagged', captured_at: '2024-02-20T09:45:00Z', integrity: 45, risk: 78 },
    { id: 'EVD-004', type: 'image', status: 'pending', captured_at: '2024-02-22T16:10:00Z', integrity: 75, risk: 30 },
    { id: 'EVD-005', type: 'image', status: 'approved', captured_at: '2024-02-25T11:00:00Z', integrity: 95, risk: 10 },
  ];

  useEffect(() => {
    let isMounted = true;
    async function loadProject() {
      try {
        const response = await projectApi.getById(id);
        const data = response.data;
        if (isMounted && data) {
          let activities = [];
          try {
            const actResp = await projectApi.getActivities(id);
            activities = (actResp.data?.items || []).map(a => ({
              id: a.id,
              name: a.verb,
              status: 'completed',
              progress: 100,
            }));
          } catch {
            activities = mockProject.activities;
          }

          setProject({
            ...mockProject,
            id: data.id,
            name: data.name,
            created_at: data.created_at,
            activities: activities.length > 0 ? activities : mockProject.activities,
          });
          setEvidence(mockEvidence);
        }
      } catch (err) {
        console.warn('Backend fetch failed, using demonstration project details:', err);
        if (isMounted) {
          setProject({ ...mockProject, id });
          setEvidence(mockEvidence);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }
    loadProject();
    return () => { isMounted = false; };
  }, [id]);

  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
      case 'completed':
      case 'approved':
        return { bg: 'var(--govt-success-light)', text: 'var(--govt-success-text)' };
      case 'pending':
      case 'draft':
        return { bg: 'var(--govt-gray-light)', text: 'var(--govt-gray-text)' };
      case 'flagged':
        return { bg: 'var(--govt-danger-light)', text: 'var(--govt-danger-text)' };
      default:
        return { bg: 'var(--govt-info-light)', text: 'var(--govt-info-text)' };
    }
  };

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
        <p style={{ marginTop: '1rem', color: 'var(--govt-gray-muted)' }}>
          Loading project details...
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
      {/* Breadcrumb */}
      <nav style={{ marginBottom: '1.5rem' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          fontSize: '0.9rem'
        }}>
          <Link to="/projects" style={{ color: 'var(--govt-blue-medium)', textDecoration: 'none' }}>
            Projects
          </Link>
          <span style={{ color: 'var(--govt-gray-muted)' }}>→</span>
          <span style={{ color: 'var(--govt-gray-text)', fontWeight: '500' }}>
            {project.name}
          </span>
        </div>
      </nav>

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
            color: 'var(--govt-blue-dark)',
            fontSize: '1.75rem',
            lineHeight: '1.2'
          }}>
            {project.name}
          </h2>
          <p style={{
            margin: '0.5rem 0 0 0',
            color: 'var(--govt-gray-muted)',
            fontSize: '0.95rem'
          }}>
            {project.scheme}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Link to={`/projects/${project.id}/edit`} style={{
            backgroundColor: 'transparent',
            border: '1px solid var(--govt-blue-medium)',
            color: 'var(--govt-blue-medium)',
            padding: '0.5rem 1rem',
            textDecoration: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.9rem',
            fontWeight: '500'
          }}>
            Edit Project
          </Link>
          <Link to={`/evidence/upload?project=${project.id}`} style={{
            backgroundColor: 'var(--govt-blue-dark)',
            color: '#ffffff',
            padding: '0.5rem 1rem',
            textDecoration: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.9rem',
            fontWeight: '500'
          }}>
            Upload Evidence
          </Link>
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 2fr',
        gap: '1.5rem'
      }}>
        {/* Left Column - Project Info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Project Information */}
          <div style={{
            backgroundColor: 'var(--govt-cream-light)',
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
                Project Information
              </h4>
            </div>
            <div style={{ padding: '0' }}>
              <table style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '0.9rem'
              }}>
                <tbody>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{
                      padding: '0.75rem 1rem',
                      color: 'var(--govt-gray-muted)',
                      fontWeight: '500',
                      width: '40%'
                    }}>
                      Project ID
                    </td>
                    <td style={{
                      padding: '0.75rem 1rem',
                      color: 'var(--govt-gray-text)',
                      fontWeight: '600'
                    }}>
                      {project.id}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-muted)', fontWeight: '500' }}>
                      Status
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span style={{
                        backgroundColor: getStatusColor(project.status).bg,
                        color: getStatusColor(project.status).text,
                        padding: '0.25rem 0.75rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.75rem',
                        fontWeight: '500'
                      }}>
                        {project.status.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-muted)', fontWeight: '500' }}>
                      State
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                      {project.state}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-muted)', fontWeight: '500' }}>
                      District
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                      {project.district}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-muted)', fontWeight: '500' }}>
                      Location
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                      {project.location}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-muted)', fontWeight: '500' }}>
                      Start Date
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                      {project.start_date}
                    </td>
                  </tr>
                  <tr>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-muted)', fontWeight: '500' }}>
                      End Date
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                      {project.end_date}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Description */}
          <div style={{
            backgroundColor: 'var(--govt-cream-light)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)',
            flex: 1
          }}>
            <div style={{
              backgroundColor: 'var(--govt-gray-light)',
              color: 'var(--govt-gray-text)',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md) var(--radius-md) 0 0'
            }}>
              <h5 style={{ margin: 0, fontSize: '0.95rem', fontWeight: '600' }}>
                Description
              </h5>
            </div>
            <div style={{ padding: '1.25rem' }}>
              <p style={{
                margin: 0,
                fontSize: '0.9rem',
                color: 'var(--govt-gray-text)',
                lineHeight: '1.6'
              }}>
                {project.description}
              </p>
            </div>
          </div>
        </div>

        {/* Right Column - Activities & Evidence */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Activities */}
          <div style={{
            backgroundColor: 'var(--govt-cream-light)',
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
                Project Activities
              </h4>
            </div>
            <div style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {project.activities.map((activity) => (
                  <div key={activity.id}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '0.5rem'
                    }}>
                      <span style={{
                        color: 'var(--govt-gray-text)',
                        fontSize: '0.9rem',
                        fontWeight: '500'
                      }}>
                        {activity.name}
                      </span>
                      <span style={{
                        backgroundColor: getStatusColor(activity.status).bg,
                        color: getStatusColor(activity.status).text,
                        padding: '0.25rem 0.75rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.75rem',
                        fontWeight: '500'
                      }}>
                        {activity.status.toUpperCase()}
                      </span>
                    </div>
                    <div style={{
                      height: '8px',
                      backgroundColor: 'var(--govt-gray-light)',
                      borderRadius: '4px',
                      overflow: 'hidden'
                    }}>
                      <div style={{
                        height: '100%',
                        backgroundColor: activity.progress === 100 ? 'var(--govt-success)' : 'var(--govt-info)',
                        width: `${activity.progress}%`,
                        borderRadius: '4px'
                      }} />
                    </div>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginTop: '0.25rem'
                    }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-muted)' }}>
                        Progress
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-text)', fontWeight: '500' }}>
                        {activity.progress}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Evidence */}
          <div style={{
            backgroundColor: 'var(--govt-cream-light)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)'
          }}>
            <div style={{
              backgroundColor: 'var(--govt-blue-dark)',
              color: '#ffffff',
              padding: '1rem 1.25rem',
              borderRadius: 'var(--radius-md) var(--radius-md) 0 0',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <h4 style={{ margin: 0, fontSize: '1rem' }}>
                Project Evidence
              </h4>
              <span style={{
                backgroundColor: '#ffffff',
                color: 'var(--govt-blue-dark)',
                padding: '0.25rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                fontWeight: '500'
              }}>
                {project.evidence_count} items
              </span>
            </div>
            <div style={{ padding: '0' }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '0.9rem'
                }}>
                  <thead>
                    <tr style={{
                      backgroundColor: 'var(--govt-gray-light)',
                      borderBottom: '1px solid var(--govt-gray-medium)'
                    }}>
                      <th style={{
                        padding: '0.75rem 1rem',
                        textAlign: 'left',
                        fontWeight: '600',
                        color: 'var(--govt-blue-dark)'
                      }}>
                        Evidence ID
                      </th>
                      <th style={{
                        padding: '0.75rem 1rem',
                        textAlign: 'left',
                        fontWeight: '600',
                        color: 'var(--govt-blue-dark)'
                      }}>
                        Captured Date
                      </th>
                      <th style={{
                        padding: '0.75rem 1rem',
                        textAlign: 'left',
                        fontWeight: '600',
                        color: 'var(--govt-blue-dark)'
                      }}>
                        Status
                      </th>
                      <th style={{
                        padding: '0.75rem 1rem',
                        textAlign: 'left',
                        fontWeight: '600',
                        color: 'var(--govt-blue-dark)'
                      }}>
                        Integrity
                      </th>
                      <th style={{
                        padding: '0.75rem 1rem',
                        textAlign: 'left',
                        fontWeight: '600',
                        color: 'var(--govt-blue-dark)'
                      }}>
                        Risk
                      </th>
                      <th style={{
                        padding: '0.75rem 1rem',
                        textAlign: 'left',
                        fontWeight: '600',
                        color: 'var(--govt-blue-dark)'
                      }}>
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidence.map((item) => {
                      const integrityColor = getIntegrityColor(item.integrity);
                      const riskColor = getRiskColor(item.risk);
                      return (
                        <tr key={item.id} style={{
                          borderBottom: '1px solid var(--govt-gray-light)'
                        }}>
                          <td style={{ padding: '0.75rem 1rem', fontWeight: '600', color: 'var(--govt-blue-dark)' }}>
                            {item.id}
                          </td>
                          <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                            {formatDate(item.captured_at)}
                          </td>
                          <td style={{ padding: '0.75rem 1rem' }}>
                            <span style={{
                              backgroundColor: getStatusColor(item.status).bg,
                              color: getStatusColor(item.status).text,
                              padding: '0.25rem 0.75rem',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.75rem',
                              fontWeight: '500'
                            }}>
                              {item.status.toUpperCase()}
                            </span>
                          </td>
                          <td style={{ padding: '0.75rem 1rem' }}>
                            <span style={{
                              backgroundColor: integrityColor.bg,
                              color: integrityColor.text,
                              padding: '0.25rem 0.75rem',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.75rem',
                              fontWeight: '500'
                            }}>
                              {item.integrity}%
                            </span>
                          </td>
                          <td style={{ padding: '0.75rem 1rem' }}>
                            <span style={{
                              backgroundColor: riskColor.bg,
                              color: riskColor.text,
                              padding: '0.25rem 0.75rem',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.75rem',
                              fontWeight: '500'
                            }}>
                              {item.risk}%
                            </span>
                          </td>
                          <td style={{ padding: '0.75rem 1rem' }}>
                            <Link to={`/evidence/${item.id}`} style={{
                              backgroundColor: 'transparent',
                              border: '1px solid var(--govt-blue-medium)',
                              color: 'var(--govt-blue-medium)',
                              padding: '0.375rem 0.75rem',
                              textDecoration: 'none',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.8rem'
                            }}>
                              View
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <div style={{
              padding: '1rem 1.25rem',
              borderTop: '1px solid var(--govt-gray-medium)',
              textAlign: 'center'
            }}>
              <Link to={`/evidence?project=${project.id}`} style={{
                color: 'var(--govt-blue-medium)',
                textDecoration: 'none',
                fontSize: '0.9rem'
              }}>
                View All Evidence
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ProjectDetail;
