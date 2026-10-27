import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function Profile() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const userRoles = {
    citizen: 'Citizen - Can upload and view evidence',
    reviewer: 'Reviewer - Can review and decide on evidence',
    supervisor: 'Supervisor - Can manage projects and reviews',
    admin: 'Administrator - Full system access',
  };

  const permissionsMap = {
    'evidence.read': 'View evidence',
    'evidence.upload': 'Upload evidence',
    'evidence.analyze': 'Analyze evidence',
    'review.read': 'View review queue',
    'review.decide': 'Make review decisions',
    'review.override': 'Override decisions',
    'project.create': 'Create projects',
    'project.update': 'Update projects',
    'audit.read': 'View audit logs',
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
          Loading profile...
        </p>
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{
        padding: '1.5rem',
        maxWidth: '800px',
        margin: '0 auto',
        backgroundColor: 'var(--govt-gray-off-white)',
        minHeight: 'calc(100vh - 60px)',
        textAlign: 'center'
      }}>
        <div style={{
          padding: '3rem 1rem',
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)'
        }}>
          <h2 style={{ color: 'var(--govt-danger)' }}>Not Logged In</h2>
          <p style={{ color: 'var(--govt-gray-dark)', marginTop: '1rem' }}>
            Please log in to view your profile.
          </p>
          <Link to="/login" style={{
            backgroundColor: 'var(--govt-blue-primary)',
            color: '#ffffff',
            padding: '0.75rem 1.5rem',
            textDecoration: 'none',
            borderRadius: 'var(--radius-sm)',
            marginTop: '1.5rem',
            display: 'inline-block',
            fontWeight: '600'
          }}>
            Go to Login
          </Link>
        </div>
      </div>
    );
  }

  const roles = Array.isArray(user.roles) ? user.roles : [user.role || 'citizen'];

  return (
    <div style={{
      padding: '1.5rem',
      maxWidth: '1000px',
      margin: '0 auto',
      backgroundColor: 'var(--govt-gray-off-white)',
      minHeight: 'calc(100vh - 60px)'
    }}>
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{
          margin: 0,
          color: 'var(--govt-blue-primary)',
          fontSize: '1.75rem'
        }}>
          User Profile
        </h2>
        <p style={{
          margin: '0.5rem 0 0 0',
          color: 'var(--govt-gray-dark)',
          fontSize: '0.95rem'
        }}>
          Account information and settings
        </p>
      </div>

      {/* Profile Header */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        overflow: 'hidden'
      }}>
        <div style={{
          backgroundColor: 'var(--govt-blue-dark)',
          color: '#ffffff',
          padding: '1.5rem 2rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
            <div style={{
              width: '80px',
              height: '80px',
              backgroundColor: 'rgba(255,255,255,0.2)',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '2rem'
            }}>
              <span>{user.name?.charAt(0) || user.username?.charAt(0) || 'U'}</span>
            </div>
            <div>
              <h3 style={{ margin: 0, color: '#ffffff', fontSize: '1.5rem' }}>
                {user.name || user.username || 'User'}
              </h3>
              <p style={{ margin: '0.25rem 0 0 0', color: 'rgba(255,255,255,0.8)' }}>
                {user.email || 'Not provided'}
              </p>
              {user.created_at && (
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>
                  Member since {new Date(user.created_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>
        </div>

        <div style={{ padding: '2rem' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
            gap: '2rem'
          }}>
            {/* Basic Info */}
            <div>
              <h4 style={{
                color: 'var(--govt-blue-primary)',
                fontSize: '1.1rem',
                marginBottom: '1rem',
                paddingBottom: '0.5rem',
                borderBottom: '2px solid var(--govt-blue-primary)'
              }}>
                Basic Information
              </h4>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <tbody>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{
                      padding: '0.75rem 0',
                      color: 'var(--govt-gray-dark)',
                      fontWeight: '500',
                      width: '40%'
                    }}>
                      User ID
                    </td>
                    <td style={{ padding: '0.75rem 0', color: 'var(--govt-gray-text)' }}>
                      {user.id || 'N/A'}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{
                      padding: '0.75rem 0',
                      color: 'var(--govt-gray-dark)',
                      fontWeight: '500'
                    }}>
                      Username
                    </td>
                    <td style={{ padding: '0.75rem 0', color: 'var(--govt-gray-text)' }}>
                      {user.username}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                    <td style={{
                      padding: '0.75rem 0',
                      color: 'var(--govt-gray-dark)',
                      fontWeight: '500'
                    }}>
                      Email
                    </td>
                    <td style={{ padding: '0.75rem 0', color: 'var(--govt-gray-text)' }}>
                      {user.email || 'Not provided'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Roles & Permissions */}
            <div>
              <h4 style={{
                color: 'var(--govt-blue-primary)',
                fontSize: '1.1rem',
                marginBottom: '1rem',
                paddingBottom: '0.5rem',
                borderBottom: '2px solid var(--govt-blue-primary)'
              }}>
                Roles & Permissions
              </h4>
              <div style={{ marginBottom: '1rem' }}>
                <div style={{
                  backgroundColor: 'var(--govt-blue-light)',
                  color: 'var(--govt-blue-primary)',
                  padding: '0.5rem 1rem',
                  borderRadius: 'var(--radius-sm)',
                  fontWeight: '600',
                  marginBottom: '0.5rem'
                }}>
                  Current Roles
                </div>
                {roles.map((role, index) => (
                  <div key={index} style={{
                    padding: '0.5rem 0.75rem',
                    backgroundColor: 'var(--govt-gray-off-white)',
                    borderRadius: 'var(--radius-sm)',
                    marginBottom: '0.25rem',
                    fontSize: '0.9rem'
                  }}>
                    {userRoles[role] || role}
                  </div>
                ))}
              </div>

              <div>
                <div style={{
                  backgroundColor: 'var(--govt-info-light)',
                  color: 'var(--govt-info-text)',
                  padding: '0.5rem 1rem',
                  borderRadius: 'var(--radius-sm)',
                  fontWeight: '600',
                  marginBottom: '0.5rem'
                }}>
                  Permissions
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--govt-gray-text)' }}>
                  {user.permissions && user.permissions.length > 0 ? (
                    user.permissions.map((perm, index) => (
                      <div key={index} style={{ padding: '0.25rem 0' }}>
                        {permissionsMap[perm] || perm}
                      </div>
                    ))
                  ) : (
                    <div style={{ color: 'var(--govt-gray-dark)', fontStyle: 'italic' }}>
                      No specific permissions assigned
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Account Actions */}
          <div style={{
            marginTop: '2rem',
            paddingTop: '2rem',
            borderTop: '1px solid var(--govt-gray-light)',
            display: 'flex',
            gap: '1rem'
          }}>
            <Link to="/profile/edit" style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              textDecoration: 'none',
              borderRadius: 'var(--radius-sm)',
              fontWeight: '600'
            }}>
              Edit Profile
            </Link>
            <button
              onClick={async () => {
                await logout();
                navigate('/login');
              }}
              style={{
                padding: '0.75rem 1.5rem',
                backgroundColor: 'var(--govt-danger)',
                color: '#ffffff',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                fontWeight: '600',
                cursor: 'pointer'
              }}
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Profile;
