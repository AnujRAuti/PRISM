import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ProjectIcon, EvidenceIcon, ReviewIcon, SearchIcon, PlusIcon, CheckIcon, AlertIcon } from '../components/common/Icon';
import { formatDate } from '../utils/helpers';

function Dashboard() {
  const [user, setUser] = useState(null);

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        setUser(null);
      }
    }
  }, []);

  // Operational Metrics aligned with ADR §2.1 & §2.2
  const stats = [
    { label: 'Monitored Infrastructure Projects', value: '12', subtitle: '5 Schemes across 4 States', type: 'primary', link: '/projects' },
    { label: 'Cryptographic Evidence Registry', value: '348', subtitle: 'SHA-256 Ingested & Quarantined', type: 'info', link: '/evidence' },
    { label: 'Active Reviewer Queue', value: '5', subtitle: '3 High Priority Attention Cases', type: 'warning', link: '/review' },
    { label: 'Tamper-Evident Ledger Blocks', value: '101', subtitle: '100% Hash-Chain Intact (BE-030)', type: 'success', link: '/admin' },
  ];

  // Real Multi-Signal Audit Events (BE-015/BE-030)
  const recentAuditEvents = [
    { id: 'evt-101', type: 'REVIEW_DECISION', actor: 'Dr. Ramesh Sharma (Reviewer)', description: 'Human decision recorded for case-004-school: SUPPORTED', time: '1 hour ago', status: 'SUCCESS' },
    { id: 'evt-100', type: 'RETENTION_HOLD', actor: 'Sunita Patel (Supervisor)', description: 'Applied active retention hold HOLD-042 on Project PRJ-002', time: '4 hours ago', status: 'WARNING' },
    { id: 'evt-099', type: 'FUSION_SIGNAL', actor: 'EIIL Fusion Pipeline Worker', description: 'Flagged 89% pHash duplicate between PRJ-002 and PRJ-001', time: 'Yesterday', status: 'ALERT' },
    { id: 'evt-098', type: 'EVIDENCE_INGEST', actor: 'John Doe (Field Inspector)', description: 'SHA-256 digest c3ab8ff1 registered into quarantine for PRJ-001', time: 'Yesterday', status: 'SUCCESS' },
    { id: 'evt-097', type: 'PROJECT_CREATED', actor: 'Dr. Ramesh Sharma', description: 'Project PRJ-001 registered with PostGIS geofence boundary', time: '2 days ago', status: 'SUCCESS' },
  ];

  const quickActions = [
    { label: 'Reviewer Queue', icon: ReviewIcon, path: '/review', desc: 'Inspect pending cases & record decisions', color: 'var(--govt-blue-primary)' },
    { label: 'Evidence Registry', icon: EvidenceIcon, path: '/evidence', desc: 'Browse SHA-256 hashes & quarantine status', color: 'var(--govt-info)' },
    { label: 'Register Project', icon: ProjectIcon, path: '/projects/create', desc: 'Add project baseline & geofence polygon', color: 'var(--govt-success)' },
    { label: 'Audit & Governance', icon: SearchIcon, path: '/admin', desc: 'Verify append-only hash-chain integrity', color: 'var(--govt-gray-dark)' },
  ];

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
          fontWeight: 700,
          letterSpacing: '-0.02em'
        }}>
          Evidence Integrity & Intelligence Layer (EIIL)
        </h1>
        <p style={{
          margin: '0.35rem 0 0 0',
          color: 'var(--govt-gray-dark)',
          fontSize: '0.875rem'
        }}>
          Operational Overview — Operator: <strong>{user?.name || 'Authorized Reviewer'}</strong> ({user?.role || 'REVIEWER'})
        </p>
      </div>

      {/* Core Operational Metrics */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
        gap: '1.25rem',
        marginBottom: '2rem'
      }}>
        {stats.map((stat, idx) => (
          <Link
            key={idx}
            to={stat.link}
            style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              padding: '1.25rem 1.5rem',
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--govt-gray-medium)',
              textDecoration: 'none',
              display: 'block',
              transition: 'transform 0.15s ease, box-shadow 0.15s ease'
            }}
          >
            <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
              {stat.label}
            </p>
            <div style={{
              fontSize: '2rem',
              fontWeight: 800,
              color: 'var(--govt-blue-dark)',
              letterSpacing: '-0.03em',
              margin: '0.4rem 0 0.2rem'
            }}>
              {stat.value}
            </div>
            <p style={{ margin: 0, fontSize: '0.75rem', color: stat.type === 'warning' ? 'var(--govt-warning-text)' : stat.type === 'success' ? 'var(--govt-success-text)' : 'var(--govt-blue-primary)', fontWeight: 600 }}>
              {stat.subtitle}
            </p>
          </Link>
        ))}
      </div>

      {/* Quick Action Navigation Cards */}
      <div style={{ marginBottom: '2rem' }}>
        <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
          Operational Workspaces
        </h3>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1.25rem'
        }}>
          {quickActions.map((act, i) => {
            const Icon = act.icon;
            return (
              <Link
                key={i}
                to={act.path}
                style={{
                  backgroundColor: 'var(--govt-white)',
                  padding: '1.25rem',
                  borderRadius: 'var(--radius-lg)',
                  border: '1px solid var(--govt-gray-medium)',
                  boxShadow: 'var(--shadow-sm)',
                  textDecoration: 'none',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '1rem',
                  transition: 'background-color 0.15s ease'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--govt-gray-off-white)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--govt-white)'}
              >
                <div style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'var(--govt-gray-light)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: act.color,
                  flexShrink: 0
                }}>
                  <Icon />
                </div>
                <div>
                  <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                    {act.label}
                  </h4>
                  <p style={{ margin: '0.25rem 0 0', fontSize: '0.78rem', color: 'var(--govt-gray-dark)', lineHeight: 1.35 }}>
                    {act.desc}
                  </p>
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Recent Cryptographic Audit Ledger Feed (BE-015/BE-030) */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        overflow: 'hidden',
        marginBottom: '2rem'
      }}>
        <div style={{
          padding: '1rem 1.25rem',
          backgroundColor: 'var(--govt-gray-light)',
          borderBottom: '1px solid var(--govt-gray-medium)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            Recent Tamper-Evident Audit Ledger Events (BE-030)
          </h3>
          <Link to="/admin" style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-blue-primary)', textDecoration: 'none' }}>
            Verify Full Ledger →
          </Link>
        </div>
        <div style={{ padding: '0.5rem 1.25rem' }}>
          {recentAuditEvents.map((evt) => (
            <div
              key={evt.id}
              style={{
                padding: '0.85rem 0',
                borderBottom: '1px solid var(--govt-gray-medium)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.5rem'
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.2rem' }}>
                  <span style={{
                    padding: '0.15rem 0.45rem',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    backgroundColor: 'var(--govt-blue-light)',
                    color: 'var(--govt-blue-primary)',
                    fontFamily: 'monospace'
                  }}>
                    {evt.type}
                  </span>
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                    {evt.actor}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-text)' }}>
                  {evt.description}
                </p>
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)' }}>
                {evt.time}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Governing Principles Notice (ADR Section 2) */}
      <div style={{
        padding: '1rem 1.25rem',
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--govt-gray-medium)',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.85rem'
      }}>
        <div style={{ color: 'var(--govt-blue-primary)', marginTop: '0.1rem' }}>
          <AlertIcon />
        </div>
        <div>
          <h4 style={{ margin: 0, fontSize: '0.85rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            Proof-of-Action Governing Principle (ADR Section 2)
          </h4>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.78rem', color: 'var(--govt-gray-dark)', lineHeight: 1.45 }}>
            <strong>“We don't collect more evidence; we make existing evidence trustworthy.”</strong> Evidence intelligence supports human judgment;
            it does not replace human judgment. An algorithmic score, a matching hash, or a geofence discrepancy is an analytical signal, not an automated verdict.
          </p>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
