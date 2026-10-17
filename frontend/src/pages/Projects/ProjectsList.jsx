import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';
import { PlusIcon, ProjectIcon, EvidenceIcon } from '../../components/common/Icon';
import { projectApi } from '../../services/api';

function ProjectsList() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  // Mock data for development (will be replaced with API)
  const mockProjects = [
    {
      id: 'PRJ-001',
      name: 'Rural Road Construction - Phase 1',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      status: 'active',
      location: 'Maharashtra',
      evidence_count: 45,
      created_at: '2024-01-15T10:30:00Z',
      start_date: '2024-01-01',
      end_date: '2024-12-31',
    },
    {
      id: 'PRJ-002',
      name: 'Solar Street Light Installation',
      scheme: 'Solar Energy Programme',
      status: 'active',
      location: 'Gujarat',
      evidence_count: 28,
      created_at: '2024-02-20T14:00:00Z',
      start_date: '2024-02-01',
      end_date: '2024-08-31',
    },
    {
      id: 'PRJ-003',
      name: 'Water Tank Construction',
      scheme: 'Jal Jeevan Mission',
      status: 'completed',
      location: 'Rajasthan',
      evidence_count: 67,
      created_at: '2023-06-10T09:15:00Z',
      start_date: '2023-06-01',
      end_date: '2024-01-31',
    },
    {
      id: 'PRJ-004',
      name: 'School Building Renovation',
      scheme: 'Samagra Shiksha Abhiyan',
      status: 'draft',
      location: 'Karnataka',
      evidence_count: 0,
      created_at: '2024-03-05T11:45:00Z',
      start_date: '2024-04-01',
      end_date: '2024-09-30',
    },
    {
      id: 'PRJ-005',
      name: 'Community Health Center',
      scheme: 'National Health Mission',
      status: 'active',
      location: 'Uttar Pradesh',
      evidence_count: 12,
      created_at: '2024-02-28T16:20:00Z',
      start_date: '2024-03-01',
      end_date: '2024-12-31',
    },
  ];

  useEffect(() => {
    let isMounted = true;
    async function loadProjects() {
      try {
        const response = await projectApi.getAll({ limit: 100 });
        const items = response.data?.items || [];
        if (isMounted) {
          if (items.length > 0) {
            const mapped = items.map(p => ({
              id: p.id,
              name: p.name,
              scheme: p.name.includes(' - ') ? p.name.split(' - ')[0] : 'PRISM Infrastructure Program',
              status: 'active',
              location: 'GovTech Node',
              evidence_count: 0,
              created_at: p.created_at,
              start_date: p.created_at ? p.created_at.split('T')[0] : '2026-01-01',
              end_date: '2026-12-31',
            }));
            setProjects(mapped);
          } else {
            setProjects(mockProjects);
          }
        }
      } catch (err) {
        console.warn('Backend API unreachable, using demonstration projects:', err);
        if (isMounted) {
          setProjects(mockProjects);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }
    loadProjects();
    return () => { isMounted = false; };
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return { bg: 'var(--govt-success-light)', text: 'var(--govt-success-text)' };
      case 'completed': return { bg: 'var(--govt-info-light)', text: 'var(--govt-info-text)' };
      case 'draft': return { bg: 'var(--govt-gray-light)', text: 'var(--govt-gray-text)' };
      default: return { bg: 'var(--govt-cream)', text: 'var(--govt-gray-muted)' };
    }
  };

  const filteredProjects = projects.filter(project => {
    const matchesSearch = project.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          project.scheme.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          project.location.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || project.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

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
          Loading projects...
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
            color: 'var(--govt-blue-dark)',
            fontSize: '1.75rem'
          }}>
            Projects
          </h2>
          <p style={{
            margin: '0.5rem 0 0 0',
            color: 'var(--govt-gray-muted)',
            fontSize: '0.95rem'
          }}>
            Manage and view all government projects
          </p>
        </div>
        <Link to="/projects/create" style={{
          backgroundColor: 'var(--govt-blue-dark)',
          color: '#ffffff',
          padding: '0.75rem 1.25rem',
          textDecoration: 'none',
          borderRadius: 'var(--radius-sm)',
          fontSize: '0.9rem',
          fontWeight: '500',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          <PlusIcon />
          Create New Project
        </Link>
      </div>

      {/* Filters */}
      <div style={{
        backgroundColor: 'var(--govt-cream-light)',
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
              fontWeight: '500',
              color: 'var(--govt-blue-dark)'
            }}>
              Search
            </label>
            <input
              type="text"
              placeholder="Search by name, scheme, or location..."
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
              fontWeight: '500',
              color: 'var(--govt-blue-dark)'
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
              <option value="active">Active</option>
              <option value="completed">Completed</option>
              <option value="draft">Draft</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button
              onClick={() => { setSearchTerm(''); setStatusFilter('all'); }}
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

      {/* Projects Table */}
      <div style={{
        backgroundColor: 'var(--govt-cream-light)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        overflow: 'hidden'
      }}>
        {/* Table Header */}
        <div style={{
          backgroundColor: 'var(--govt-blue-dark)',
          color: '#ffffff',
          padding: '1rem 1.25rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span style={{ fontSize: '1rem', fontWeight: '500' }}>
            Projects List
          </span>
          <span style={{
            backgroundColor: '#ffffff',
            color: 'var(--govt-blue-dark)',
            padding: '0.25rem 0.75rem',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.8rem',
            fontWeight: '500'
          }}>
            {filteredProjects.length} projects
          </span>
        </div>

        {/* Table Body */}
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
                  color: 'var(--govt-blue-dark)',
                  whiteSpace: 'nowrap'
                }}>
                  Project ID
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-dark)',
                  whiteSpace: 'nowrap'
                }}>
                  Project Name
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-dark)',
                  whiteSpace: 'nowrap'
                }}>
                  Scheme
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-dark)',
                  whiteSpace: 'nowrap'
                }}>
                  Location
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-dark)',
                  whiteSpace: 'nowrap'
                }}>
                  Status
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-dark)',
                  whiteSpace: 'nowrap'
                }}>
                  Evidence
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-dark)',
                  whiteSpace: 'nowrap'
                }}>
                  Created Date
                </th>
                <th style={{
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  fontWeight: '600',
                  color: 'var(--govt-blue-dark)',
                  whiteSpace: 'nowrap'
                }}>
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredProjects.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ padding: '2rem', textAlign: 'center', color: 'var(--govt-gray-muted)' }}>
                    No projects found
                  </td>
                </tr>
              ) : (
                filteredProjects.map((project, index) => {
                  const statusColor = getStatusColor(project.status);
                  return (
                    <tr key={project.id} style={{
                      borderBottom: '1px solid var(--govt-gray-light)',
                      backgroundColor: index % 2 === 0 ? 'var(--govt-cream-light)' : '#ffffff'
                    }}>
                      <td style={{ padding: '0.75rem 1rem', fontWeight: '600', color: 'var(--govt-blue-dark)' }}>
                        {project.id}
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <Link to={`/projects/${project.id}`} style={{
                          color: 'var(--govt-blue-medium)',
                          textDecoration: 'none',
                          fontWeight: '500'
                        }}>
                          {project.name}
                        </Link>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                        {project.scheme}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                        {project.location}
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span style={{
                          backgroundColor: statusColor.bg,
                          color: statusColor.text,
                          padding: '0.25rem 0.75rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.75rem',
                          fontWeight: '500'
                        }}>
                          {project.status.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span style={{
                          backgroundColor: 'var(--govt-info)',
                          color: '#ffffff',
                          padding: '0.25rem 0.75rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.75rem',
                          fontWeight: '500'
                        }}>
                          {project.evidence_count}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-muted)' }}>
                        {formatDate(project.created_at)}
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <Link to={`/projects/${project.id}`} style={{
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
                          <Link to={`/projects/${project.id}/edit`} style={{
                            backgroundColor: 'transparent',
                            border: '1px solid var(--govt-gray-medium)',
                            color: 'var(--govt-gray-text)',
                            padding: '0.375rem 0.75rem',
                            textDecoration: 'none',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.8rem'
                          }}>
                            Edit
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

        {/* Table Footer */}
        <div style={{
          backgroundColor: 'var(--govt-gray-light)',
          padding: '1rem 1.25rem',
          borderTop: '1px solid var(--govt-gray-medium)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--govt-gray-muted)' }}>
            Showing {filteredProjects.length} of {projects.length} projects
          </span>
          <div style={{ display: 'flex', gap: '0.25rem' }}>
            <button style={{
              backgroundColor: 'var(--govt-cream-light)',
              border: '1px solid var(--govt-gray-medium)',
              color: 'var(--govt-gray-muted)',
              padding: '0.375rem 0.75rem',
              fontSize: '0.8rem',
              cursor: 'not-allowed',
              opacity: 0.5,
              borderRadius: 'var(--radius-sm)'
            }} disabled>
              Previous
            </button>
            <button style={{
              backgroundColor: 'var(--govt-blue-dark)',
              border: '1px solid var(--govt-blue-dark)',
              color: '#ffffff',
              padding: '0.375rem 0.75rem',
              fontSize: '0.8rem',
              cursor: 'default',
              borderRadius: 'var(--radius-sm)'
            }}>
              1
            </button>
            <button style={{
              backgroundColor: 'var(--govt-cream-light)',
              border: '1px solid var(--govt-gray-medium)',
              color: 'var(--govt-gray-muted)',
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

export default ProjectsList;
