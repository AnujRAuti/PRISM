import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ProjectIcon, EvidenceIcon, ReviewIcon, SearchIcon, PlusIcon } from '../components/common/Icon';

function Dashboard() {
  const { user } = useAuth();

  // Mock data - will be replaced with API calls later
  const stats = [
    { label: 'Total Projects', value: '12', change: '+2 this month', type: 'primary' },
    { label: 'Evidence Submitted', value: '348', change: '+15% vs last month', type: 'info' },
    { label: 'Pending Reviews', value: '24', change: 'High priority', type: 'warning' },
    { label: 'Flagged Evidence', value: '8', change: 'Needs attention', type: 'danger' },
  ];

  const recentActivity = [
    { id: 1, type: 'upload', user: 'John Doe', description: 'Uploaded evidence for Project Alpha', time: '2 hours ago' },
    { id: 2, type: 'review', user: 'Jane Smith', description: 'Completed review of evidence #452', time: '4 hours ago' },
    { id: 3, type: 'project', user: 'System', description: 'New project "Road Infrastructure" created', time: 'Yesterday' },
    { id: 4, type: 'flag', user: 'System', description: 'Evidence #387 flagged for review', time: 'Yesterday' },
  ];

  const quickActions = [
    { label: 'Create Project', icon: ProjectIcon, path: '/projects/create', color: 'var(--govt-blue-medium)' },
    { label: 'Upload Evidence', icon: EvidenceIcon, path: '/evidence/upload', color: 'var(--govt-info)' },
    { label: 'View Reviews', icon: ReviewIcon, path: '/reviews', color: 'var(--govt-success)' },
    { label: 'Search Evidence', icon: SearchIcon, path: '/search', color: 'var(--govt-gray-dark)' },
  ];

  const getStatusColor = (type) => {
    switch (type) {
      case 'upload': return { bg: 'var(--govt-info-light)', text: 'var(--govt-info-text)' };
      case 'review': return { bg: 'var(--govt-success-light)', text: 'var(--govt-success-text)' };
      case 'flag': return { bg: 'var(--govt-danger-light)', text: 'var(--govt-danger-text)' };
      default: return { bg: 'var(--govt-gray-light)', text: 'var(--govt-gray-text)' };
    }
  };

  return (
    <div style={{
      padding: '1.75rem 2rem',
      width: '100%',
      boxSizing: 'border-box',
      backgroundColor: 'var(--govt-gray-off-white)',
    }}>
      {/* Header */}
      <div style={{ marginBottom: '1.75rem' }}>
        <h1 style={{
          margin: 0,
          color: 'var(--govt-blue-dark)',
          fontSize: '1.65rem',
          fontWeight: '700',
          letterSpacing: '-0.02em'
        }}>
          Dashboard
        </h1>
        <p style={{
          margin: '0.35rem 0 0 0',
          color: 'var(--govt-gray-dark)',
          fontSize: '0.875rem'
        }}>
          Welcome back, {user?.name || 'Operator'}. System operational overview.
        </p>
      </div>

      {/* Stats Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '1.25rem',
        marginBottom: '2rem'
      }}>
        {stats.map((stat, index) => {
          const changeColors = {
            primary: '#1d4ed8',
            info: '#059669',
            warning: '#d97706',
            danger: '#dc2626',
          };

          return (
            <div key={index} style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              padding: '1.25rem 1.5rem',
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--govt-gray-medium)'
            }}>
              <p style={{
                margin: 0,
                color: 'var(--govt-gray-dark)',
                fontSize: '0.78rem',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                fontWeight: '600'
              }}>
                {stat.label}
              </p>
              <h3 style={{
                margin: '0.5rem 0 0.25rem 0',
                color: 'var(--govt-gray-title)',
                fontSize: '2rem',
                fontWeight: '700'
              }}>
                {stat.value}
              </h3>
              <p style={{
                margin: 0,
                fontSize: '0.825rem',
                fontWeight: '500',
                color: changeColors[stat.type] || 'var(--govt-gray-dark)'
              }}>
                {stat.change}
              </p>
            </div>
          );
        })}
      </div>

      {/* Quick Actions */}
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{
          margin: '0 0 1rem 0',
          color: 'var(--govt-blue-dark)',
          fontSize: '1.1rem',
          fontWeight: '600',
        }}>
          Quick Actions
        </h2>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '1rem'
        }}>
          {quickActions.map((action, index) => {
            const Icon = action.icon;
            return (
              <Link
                key={index}
                to={action.path}
                style={{
                  backgroundColor: 'var(--govt-white)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '1.25rem 1rem',
                  textAlign: 'center',
                  textDecoration: 'none',
                  color: 'var(--govt-gray-text)',
                  boxShadow: 'var(--shadow-sm)',
                  border: '1px solid var(--govt-gray-medium)',
                  transition: 'all 0.2s ease',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                  e.currentTarget.style.borderColor = 'var(--govt-blue-primary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
                  e.currentTarget.style.borderColor = 'var(--govt-gray-medium)';
                }}
              >
                <div style={{
                  marginBottom: '0.65rem',
                  color: action.color,
                  display: 'flex',
                  justifyContent: 'center'
                }}>
                  <Icon />
                </div>
                <h3 style={{
                  margin: 0,
                  color: 'var(--govt-gray-title)',
                  fontSize: '0.9rem',
                  fontWeight: '600'
                }}>
                  {action.label}
                </h3>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Main Content Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '2fr 1fr',
        gap: '1.5rem',
        alignItems: 'start'
      }}>
        {/* Recent Activity */}
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          overflow: 'hidden'
        }}>
          <div style={{
            padding: '1.1rem 1.25rem',
            borderBottom: '1px solid var(--govt-gray-medium)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <h2 style={{ margin: 0, fontSize: '0.975rem', fontWeight: '700', color: 'var(--govt-blue-dark)' }}>
              Recent Activity
            </h2>
            <span style={{ fontSize: '0.78rem', color: 'var(--govt-gray-dark)' }}>Live audit stream</span>
          </div>
          <div style={{ padding: '0' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '0.875rem'
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
                      fontSize: '0.78rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em'
                    }}>
                      Type
                    </th>
                    <th style={{
                      padding: '0.75rem 1rem',
                      textAlign: 'left',
                      fontWeight: '600',
                      color: 'var(--govt-blue-dark)',
                      fontSize: '0.78rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em'
                    }}>
                      User
                    </th>
                    <th style={{
                      padding: '0.75rem 1rem',
                      textAlign: 'left',
                      fontWeight: '600',
                      color: 'var(--govt-blue-dark)',
                      fontSize: '0.78rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em'
                    }}>
                      Description
                    </th>
                    <th style={{
                      padding: '0.75rem 1rem',
                      textAlign: 'left',
                      fontWeight: '600',
                      color: 'var(--govt-blue-dark)',
                      fontSize: '0.78rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em'
                    }}>
                      Time
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recentActivity.map((activity) => {
                    const statusColor = getStatusColor(activity.type);
                    return (
                      <tr key={activity.id} style={{
                        borderBottom: '1px solid var(--govt-gray-light)',
                        transition: 'background-color 0.15s'
                      }}>
                        <td style={{ padding: '0.85rem 1rem' }}>
                          <span style={{
                            backgroundColor: statusColor.bg,
                            color: statusColor.text,
                            padding: '0.2rem 0.55rem',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.72rem',
                            fontWeight: '600',
                            letterSpacing: '0.03em'
                          }}>
                            {activity.type.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: '0.85rem 1rem', color: 'var(--govt-gray-text)', fontWeight: '500' }}>
                          {activity.user}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', color: 'var(--govt-gray-text)' }}>
                          {activity.description}
                        </td>
                        <td style={{ padding: '0.85rem 1rem', color: 'var(--govt-gray-dark)', fontSize: '0.8rem' }}>
                          {activity.time}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div style={{
            padding: '0.85rem 1.25rem',
            borderTop: '1px solid var(--govt-gray-medium)',
            textAlign: 'center',
            backgroundColor: 'var(--govt-gray-off-white)'
          }}>
            <Link to="/activity" style={{
              color: 'var(--govt-blue-primary)',
              textDecoration: 'none',
              fontSize: '0.85rem',
              fontWeight: '600'
            }}>
              View All Activity →
            </Link>
          </div>
        </div>

        {/* Sidebar Widgets */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Notifications */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)',
            overflow: 'hidden'
          }}>
            <div style={{
              padding: '1.1rem 1.25rem',
              borderBottom: '1px solid var(--govt-gray-medium)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <h2 style={{ margin: 0, fontSize: '0.975rem', fontWeight: '700', color: 'var(--govt-blue-dark)' }}>
                System Alerts
              </h2>
              <span style={{
                fontSize: '0.72rem',
                backgroundColor: 'var(--govt-danger-light)',
                color: 'var(--govt-danger-text)',
                padding: '0.15rem 0.5rem',
                borderRadius: 'var(--radius-full)',
                fontWeight: '600'
              }}>
                Action required
              </span>
            </div>
            <div style={{ padding: '1.15rem' }}>
              <div style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                border: '1px solid var(--govt-gray-medium)',
                borderLeft: '4px solid var(--govt-danger)',
                padding: '0.85rem 1rem',
                marginBottom: '0.85rem',
                borderRadius: 'var(--radius-sm)'
              }}>
                <h3 style={{
                  margin: '0 0 0.35rem 0',
                  color: 'var(--govt-danger-text)',
                  fontSize: '0.875rem',
                  fontWeight: '600'
                }}>
                  High Priority Reviews
                </h3>
                <p style={{
                  margin: 0,
                  fontSize: '0.825rem',
                  color: 'var(--govt-gray-dark)'
                }}>
                  24 items need review within 24 hours.
                </p>
              </div>
              <div style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                border: '1px solid var(--govt-gray-medium)',
                borderLeft: '4px solid var(--govt-info)',
                padding: '0.85rem 1rem',
                borderRadius: 'var(--radius-sm)'
              }}>
                <h3 style={{
                  margin: '0 0 0.35rem 0',
                  color: 'var(--govt-info-text)',
                  fontSize: '0.875rem',
                  fontWeight: '600'
                }}>
                  New Evidence Incoming
                </h3>
                <p style={{
                  margin: 0,
                  fontSize: '0.825rem',
                  color: 'var(--govt-gray-dark)'
                }}>
                  5 new evidence items uploaded in the last hour.
                </p>
              </div>
            </div>
          </div>

          {/* Help Card */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)',
            overflow: 'hidden'
          }}>
            <div style={{
              padding: '1.1rem 1.25rem',
              borderBottom: '1px solid var(--govt-gray-medium)'
            }}>
              <h2 style={{ margin: 0, fontSize: '0.975rem', fontWeight: '700', color: 'var(--govt-blue-dark)' }}>
                Verification Support
              </h2>
            </div>
            <div style={{ padding: '1.25rem' }}>
              <p style={{
                margin: '0 0 1rem 0',
                fontSize: '0.85rem',
                color: 'var(--govt-gray-dark)',
                lineHeight: '1.5'
              }}>
                For assistance with PRISM multi-signal cryptographic verification or node configuration, contact technical operations.
              </p>
              <a href="mailto:support@prism.gov.in" style={{
                display: 'block',
                backgroundColor: 'var(--govt-blue-primary)',
                color: '#ffffff',
                padding: '0.65rem 1rem',
                textAlign: 'center',
                textDecoration: 'none',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.85rem',
                fontWeight: '600',
                transition: 'background-color 0.15s ease'
              }}>
                Contact Operations
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
