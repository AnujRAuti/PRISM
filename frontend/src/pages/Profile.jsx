import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { UserIcon, CheckIcon, AlertIcon } from '../components/common/Icon';
import { authApi } from '../services/api';

function Profile() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        setUser(null);
      }
    } else {
      // Default operator context
      setUser({
        id: 'usr-ramesh-sharma-01',
        name: 'Dr. Ramesh Sharma',
        email: 'ramesh.sharma@prism.gov.in',
        role: 'REVIEWER',
        organization: 'Ministry of Rural Development',
        department: 'National Rural Infrastructure Monitoring Division',
        jurisdiction: 'Pune & Western Zone Operations',
        scope_rule: 'P1 (Project-Scoped Access)',
        assigned_projects: ['PRJ-001 (PMGSY Road Works)', 'PRJ-004 (Samagra Shiksha)'],
        permissions: [
          'evidence.read',
          'review.read',
          'review.decide',
          'intelligence.read',
          'graph.read',
          'audit.read'
        ]
      });
    }
    setLoading(false);
  }, []);

  const handleLogout = () => {
    authApi.logout();
    navigate('/login');
  };

  if (loading) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', margin: '0 auto 1rem' }}></div>
        <p style={{ color: 'var(--govt-gray-dark)' }}>Loading operator profile...</p>
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span style={{ color: 'var(--govt-blue-primary)' }}><UserIcon /></span>
            <h1 style={{
              margin: 0,
              color: 'var(--govt-blue-dark)',
              fontSize: '1.65rem',
              fontWeight: 700,
              letterSpacing: '-0.02em'
            }}>
              Operator Profile & Authorization Scopes
            </h1>
          </div>
          <p style={{
            margin: '0.35rem 0 0 0',
            color: 'var(--govt-gray-dark)',
            fontSize: '0.875rem'
          }}>
            Authenticated principal identity, organization scope constraints (Rule P1/P2), and role permissions.
          </p>
        </div>

        <button
          type="button"
          onClick={handleLogout}
          style={{
            padding: '0.55rem 1.15rem',
            backgroundColor: 'var(--govt-white)',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--govt-danger-text)',
            fontSize: '0.85rem',
            fontWeight: 600,
            cursor: 'pointer'
          }}
        >
          Sign Out of PRISM
        </button>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
        gap: '1.5rem',
        marginBottom: '1.75rem'
      }}>
        {/* Principal Identity Card */}
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.5rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              backgroundColor: 'var(--govt-blue-light)',
              color: 'var(--govt-blue-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.5rem',
              fontWeight: 700
            }}>
              {user?.name ? user.name.charAt(0) : 'U'}
            </div>
            <div>
              <h3 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.1rem', fontWeight: 700 }}>
                {user?.name || 'Operator'}
              </h3>
              <p style={{ margin: '0.15rem 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.85rem' }}>
                {user?.email || 'operator@prism.gov.in'}
              </p>
              <span style={{
                display: 'inline-block',
                marginTop: '0.4rem',
                padding: '0.15rem 0.55rem',
                borderRadius: '9999px',
                fontSize: '0.72rem',
                fontWeight: 700,
                backgroundColor: 'var(--govt-blue-light)',
                color: 'var(--govt-blue-primary)'
              }}>
                ROLE: {user?.role || 'REVIEWER'}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.82rem', borderTop: '1px solid var(--govt-gray-medium)', paddingTop: '1rem' }}>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Organization:</span>
              <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                {user?.organization || 'Ministry of Rural Development'}
              </p>
            </div>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Department Unit:</span>
              <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                {user?.department || 'National Rural Infrastructure Monitoring Division'}
              </p>
            </div>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Jurisdiction:</span>
              <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                {user?.jurisdiction || 'Pune & Western Zone Operations'}
              </p>
            </div>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Principal Identifier:</span>
              <p style={{ margin: '0.15rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)', fontFamily: 'monospace' }}>
                {user?.id || 'usr-ramesh-sharma-01'}
              </p>
            </div>
          </div>
        </div>

        {/* Scope Boundaries Card (ADR §27 & Scope Policy 2026-10-17) */}
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.5rem'
        }}>
          <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            Authorization Scope Classification (Policy P1 / P2)
          </h3>
          <p style={{ margin: '0 0 1rem', fontSize: '0.82rem', color: 'var(--govt-gray-text)', lineHeight: 1.45 }}>
            Per the owner-approved Authorization Scope Policy (2026-10-17), access is strictly constrained to projects the principal is authorized to access. A grant for Project A never reads Project B's rows.
          </p>

          <div style={{
            backgroundColor: 'var(--govt-gray-off-white)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--govt-gray-medium)',
            padding: '0.85rem 1rem',
            marginBottom: '1rem'
          }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-gray-dark)', textTransform: 'uppercase' }}>
              Authorized Project Scopes:
            </span>
            <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem', fontSize: '0.82rem', color: 'var(--govt-blue-dark)' }}>
              <li><strong>PRJ-001:</strong> PMGSY Phase 1 Road Works (Maharashtra)</li>
              <li><strong>PRJ-004:</strong> Samagra Shiksha School Renovation (Karnataka)</li>
            </ul>
          </div>

          <div style={{
            padding: '0.75rem 1rem',
            backgroundColor: 'var(--govt-blue-light)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--govt-blue-medium)',
            fontSize: '0.75rem',
            color: 'var(--govt-blue-dark)',
            lineHeight: 1.4
          }}>
            <strong>Scope Constraint P4:</strong> Ownership assignment derives strictly from the authenticated principal. Delegated ownership requires explicit GLOBAL administrative authorization.
          </div>
        </div>
      </div>

      {/* Assigned Permissions */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        padding: '1.5rem'
      }}>
        <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
          Assigned Permissions in Active Scope
        </h3>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '0.75rem'
        }}>
          {(user?.permissions || ['evidence.read', 'review.read', 'review.decide', 'intelligence.read', 'graph.read', 'audit.read']).map(perm => (
            <div key={perm} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.5rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--govt-gray-off-white)',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.78rem',
              fontFamily: 'monospace',
              color: 'var(--govt-blue-dark)'
            }}>
              <span style={{ color: 'var(--govt-success)' }}>✓</span>
              <span>{perm}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default Profile;
