import { useState, useEffect } from 'react';
import { formatDate } from '../../utils/helpers';
import { AdminIcon, UserIcon, DownloadIcon, CheckIcon, AlertIcon, ClockIcon } from '../../components/common/Icon';
import { auditApi, governanceApi, adminApi } from '../../services/api';
import BackendApiWorkbench from './BackendApiWorkbench';

function AdminDashboard() {
  const [activeTab, setActiveTab] = useState('audit'); // 'audit', 'retention', 'users', 'telemetry'
  const [verifyingLedger, setVerifyingLedger] = useState(false);
  const [ledgerVerificationResult, setLedgerVerificationResult] = useState(null);
  const [notification, setNotification] = useState(null);

  const [auditEvents, setAuditEvents] = useState([]);
  const [retentionPolicies, setRetentionPolicies] = useState([]);
  const [activeHolds, setActiveHolds] = useState([]);
  const [users, setUsers] = useState([]);
  const [systemConfig, setSystemConfig] = useState({});

  useEffect(() => {
    let active = true;
    Promise.allSettled([
      auditApi.getEvents({ limit: 100 }),
      governanceApi.getPolicies({ limit: 100 }),
      governanceApi.getHolds({ limit: 100 }),
      adminApi.getUsers({ limit: 100 }),
      adminApi.getHealthSnapshot(),
    ]).then(([events, policies, holds, principals, health]) => {
      if (!active) return;
      if (events.status === 'fulfilled') setAuditEvents((events.value.data.items || []).map((event) => ({
        id: event.id, timestamp: event.created_at, event_type: event.event_type, actor_id: event.actor_id,
        actor_name: event.actor_id || 'System', resource_type: event.resource_type, resource_id: event.resource_id,
        hash: event.event_hash, prev_hash: event.previous_hash,
      })));
      if (policies.status === 'fulfilled') setRetentionPolicies(policies.value.data.items || []);
      if (holds.status === 'fulfilled') setActiveHolds((holds.value.data.items || []).filter((hold) => hold.status === 'ACTIVE').map((hold) => ({
        id: hold.id, project_id: hold.project_id || hold.case_id || hold.resource_id || hold.organization_id || hold.scope,
        reason: hold.reason, applied_by: hold.created_by || 'Not provided', created_at: hold.created_at, status: hold.status,
      })));
      if (principals.status === 'fulfilled') setUsers((principals.value.data.items || []).map((principal) => ({
        id: principal.id, name: principal.display_name || principal.username, email: principal.email,
        role: (principal.roles || []).join(', ') || 'No role assigned', department: principal.identity_provider,
        assigned_projects: 'View scoped assignments', status: principal.status,
      })));
      if (health.status === 'fulfilled') setSystemConfig(health.value.data || {});
      const failed = [events, policies, holds, principals, health].find((result) => result.status === 'rejected');
      if (failed) setNotification(failed.reason?.response?.data?.detail || failed.reason?.message || 'One or more backend governance views could not be loaded.');
    });
    return () => { active = false; };
  }, []);

  const handleVerifyLedger = async () => {
    setVerifyingLedger(true);
    setLedgerVerificationResult(null);
    setNotification(null);
    try {
      const { data } = await auditApi.verifyAnchored();
      setLedgerVerificationResult(data);
    } catch (cause) {
      setNotification(cause.response?.data?.detail || cause.message || 'Audit ledger verification failed.');
    } finally {
      setVerifyingLedger(false);
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span style={{ color: 'var(--govt-blue-primary)' }}><AdminIcon /></span>
          <h1 style={{
            margin: 0,
            color: 'var(--govt-blue-dark)',
            fontSize: '1.65rem',
            fontWeight: 700,
            letterSpacing: '-0.02em'
          }}>
            Platform Governance & Audit Ledger
          </h1>
        </div>
        <p style={{
          margin: '0.35rem 0 0 0',
          color: 'var(--govt-gray-dark)',
          fontSize: '0.875rem'
        }}>
          Tamper-evident audit ledger, legal retention holds, pre-provisioned role controls, and system telemetry.
        </p>
      </div>

      {notification && <div role="alert" style={{ padding: '0.75rem 1rem', marginBottom: '1rem', borderRadius: 8, background: '#fef2f2', color: '#991b1b' }}>{notification}</div>}

      {/* Tabs */}
      <div style={{
        display: 'flex',
        gap: '0.5rem',
        borderBottom: '2px solid var(--govt-gray-medium)',
        marginBottom: '1.75rem'
      }}>
        {[
          { id: 'audit', label: '1. Tamper-Evident Audit Ledger (BE-030)' },
          { id: 'retention', label: '2. Retention Policies & Legal Holds' },
          { id: 'users', label: '3. Identity & Role Assignments' },
          { id: 'telemetry', label: '4. System Policy & Architecture Config' },
          { id: 'api', label: 'Backend API capabilities' },
        ].map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '0.75rem 1.25rem',
              border: 'none',
              backgroundColor: 'transparent',
              fontSize: '0.875rem',
              fontWeight: activeTab === tab.id ? 700 : 500,
              color: activeTab === tab.id ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
              borderBottom: activeTab === tab.id ? '3px solid var(--govt-blue-primary)' : '3px solid transparent',
              cursor: 'pointer',
              marginBottom: '-2px'
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 1: AUDIT LEDGER */}
      {activeTab === 'audit' && (
        <div>
          {/* Verification Banner */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)',
            padding: '1.5rem',
            marginBottom: '1.5rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '1rem'
          }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                Append-Only Cryptographic Audit Ledger (BE-015, BE-030)
              </h3>
              <p style={{ margin: '0.35rem 0 0', fontSize: '0.82rem', color: 'var(--govt-gray-dark)', maxWidth: '620px', lineHeight: 1.4 }}>
                Every critical event (case decision, evidence upload, project creation) is cryptographically hash-chained to the previous block.
                Mathematical verification proves that historical records have not been altered or deleted.
              </p>
            </div>
            <button
              type="button"
              disabled={verifyingLedger}
              onClick={handleVerifyLedger}
              style={{
                padding: '0.65rem 1.35rem',
                backgroundColor: verifyingLedger ? 'var(--govt-gray-medium)' : 'var(--govt-blue-primary)',
                color: '#ffffff',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: verifyingLedger ? 'not-allowed' : 'pointer',
                boxShadow: 'var(--shadow-sm)'
              }}
            >
              {verifyingLedger ? 'Verifying Hash Chain...' : '⚡ Verify Hash-Chain Integrity'}
            </button>
          </div>

          {/* Verification Success Box */}
          {ledgerVerificationResult && (
            <div style={{
              backgroundColor: ledgerVerificationResult.valid ? 'var(--govt-success-light)' : 'var(--govt-danger-light)',
              border: `1px solid ${ledgerVerificationResult.valid ? 'var(--govt-success-border)' : 'var(--govt-danger-border)'}`,
              borderRadius: 'var(--radius-lg)',
              padding: '1.25rem 1.5rem',
              marginBottom: '1.5rem',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '1rem'
            }}>
              <span style={{ color: ledgerVerificationResult.valid ? 'var(--govt-success-text)' : 'var(--govt-danger-text)', fontSize: '1.4rem' }}>{ledgerVerificationResult.valid ? '✓' : '!'}</span>
              <div>
                <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-success-text)' }}>
                  {ledgerVerificationResult.valid ? 'Audit ledger integrity verified' : 'Audit ledger verification found integrity issues'}
                </h4>
                <p style={{ margin: '0.35rem 0 0', fontSize: '0.82rem', color: ledgerVerificationResult.valid ? 'var(--govt-success-text)' : 'var(--govt-danger-text)', lineHeight: 1.45 }}>
                  Verified <strong>{ledgerVerificationResult.checked_events} consecutive event blocks</strong> across the ledger chain.
                  {(ledgerVerificationResult.failures || []).length} verification issue(s). Tip hash: <code style={{ wordBreak: 'break-all' }}>{(ledgerVerificationResult.checkpoint?.tail_event_hash || 'not provided').slice(0, 32)}...</code>
                </p>
              </div>
            </div>
          )}

          {/* Ledger Table */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)',
            overflow: 'hidden'
          }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{
                    backgroundColor: 'var(--govt-gray-light)',
                    borderBottom: '2px solid var(--govt-gray-medium)',
                    color: 'var(--govt-gray-dark)',
                    fontSize: '0.75rem',
                    textTransform: 'uppercase'
                  }}>
                    <th style={{ padding: '0.85rem 1.25rem' }}>Event ID & Time</th>
                    <th style={{ padding: '0.85rem 1rem' }}>Event Type</th>
                    <th style={{ padding: '0.85rem 1rem' }}>Actor Attribution</th>
                    <th style={{ padding: '0.85rem 1rem' }}>Resource Scope</th>
                    <th style={{ padding: '0.85rem 1.25rem' }}>Cryptographic SHA-256 Block Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {auditEvents.map(evt => (
                    <tr key={evt.id} style={{ borderBottom: '1px solid var(--govt-gray-medium)' }}>
                      <td style={{ padding: '0.9rem 1.25rem' }}>
                        <div style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-blue-primary)', fontSize: '0.78rem' }}>
                          {evt.id}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)', marginTop: '0.2rem' }}>
                          {evt.timestamp ? formatDate(evt.timestamp) : 'Time not supplied'}
                        </div>
                      </td>
                      <td style={{ padding: '0.9rem 1rem' }}>
                        <span style={{
                          padding: '0.2rem 0.55rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          backgroundColor: 'var(--govt-blue-light)',
                          color: 'var(--govt-blue-primary)',
                          fontFamily: 'monospace'
                        }}>
                          {evt.event_type}
                        </span>
                      </td>
                      <td style={{ padding: '0.9rem 1rem' }}>
                        <div style={{ fontWeight: 600, color: 'var(--govt-blue-dark)', fontSize: '0.82rem' }}>
                          {evt.actor_name}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)', fontFamily: 'monospace' }}>
                          {evt.actor_id}
                        </div>
                      </td>
                      <td style={{ padding: '0.9rem 1rem' }}>
                        <div style={{ fontSize: '0.8rem', color: 'var(--govt-gray-text)' }}>
                          <strong>{evt.resource_type}:</strong> {evt.resource_id}
                        </div>
                      </td>
                      <td style={{ padding: '0.9rem 1.25rem', maxWidth: '280px' }}>
                        <div style={{
                          fontFamily: 'monospace',
                          fontSize: '0.72rem',
                          backgroundColor: 'var(--govt-gray-light)',
                          padding: '0.25rem 0.45rem',
                          borderRadius: 'var(--radius-sm)',
                          wordBreak: 'break-all',
                          color: 'var(--govt-blue-dark)'
                        }}>
                          {evt.hash}
                        </div>
                        <div style={{ fontSize: '0.68rem', color: 'var(--govt-gray-dark)', marginTop: '0.2rem' }}>
                          prev: {(evt.prev_hash || 'not provided').slice(0, 24)}...
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: RETENTION & HOLDS */}
      {activeTab === 'retention' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
          {/* Active Legal Holds */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)',
            overflow: 'hidden'
          }}>
            <div style={{
              padding: '1rem 1.25rem',
              backgroundColor: 'var(--govt-gray-light)',
              borderBottom: '1px solid var(--govt-gray-medium)',
              fontWeight: 700,
              color: 'var(--govt-blue-dark)',
              fontSize: '0.95rem'
            }}>
              Active Retention Holds (Legal & Investigation Preservation)
            </div>
            <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {activeHolds.map(hold => (
                <div key={hold.id} style={{
                  padding: '1rem',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'var(--govt-warning-light)',
                  border: '1px solid var(--govt-warning-border)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '0.75rem'
                }}>
                  <div>
                    <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-warning-text)' }}>
                      {hold.id} • Scope: {hold.project_id}
                    </span>
                    <p style={{ margin: '0.25rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)', fontSize: '0.85rem' }}>
                      {hold.reason}
                    </p>
                    <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)' }}>
                      Applied by {hold.applied_by} on {formatDate(hold.created_at)}
                    </span>
                  </div>
                  <span style={{
                    padding: '0.2rem 0.6rem',
                    borderRadius: '9999px',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    backgroundColor: 'var(--govt-warning)',
                    color: '#ffffff'
                  }}>
                    {hold.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Retention Policies Catalogue */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--govt-gray-medium)',
            overflow: 'hidden'
          }}>
            <div style={{
              padding: '1rem 1.25rem',
              backgroundColor: 'var(--govt-gray-light)',
              borderBottom: '1px solid var(--govt-gray-medium)',
              fontWeight: 700,
              color: 'var(--govt-blue-dark)',
              fontSize: '0.95rem'
            }}>
              Configured Retention Policies (BE-017 & Scope Policy P1/P2/P3)
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{
                    backgroundColor: 'var(--govt-gray-off-white)',
                    borderBottom: '1px solid var(--govt-gray-medium)',
                    color: 'var(--govt-gray-dark)',
                    fontSize: '0.75rem',
                    textTransform: 'uppercase'
                  }}>
                    <th style={{ padding: '0.75rem 1.25rem' }}>Policy ID & Name</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Scope Level</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Retention Period</th>
                    <th style={{ padding: '0.75rem 1.25rem' }}>Rule Description</th>
                  </tr>
                </thead>
                <tbody>
                  {retentionPolicies.map(pol => (
                    <tr key={pol.id} style={{ borderBottom: '1px solid var(--govt-gray-medium)' }}>
                      <td style={{ padding: '0.85rem 1.25rem' }}>
                        <div style={{ fontWeight: 700, color: 'var(--govt-blue-dark)' }}>{pol.name}</div>
                        <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: 'var(--govt-gray-dark)' }}>{pol.id}</span>
                      </td>
                      <td style={{ padding: '0.85rem 1rem' }}>
                        <span style={{
                          padding: '0.15rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          backgroundColor: 'var(--govt-blue-light)',
                          color: 'var(--govt-blue-primary)'
                        }}>
                          {pol.scope_type}
                        </span>
                      </td>
                      <td style={{ padding: '0.85rem 1rem', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                        {pol.resource_type}
                      </td>
                      <td style={{ padding: '0.85rem 1.25rem', fontSize: '0.8rem', color: 'var(--govt-gray-text)' }}>
                        {pol.description || 'No description provided'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: IDENTITY & ROLES */}
      {activeTab === 'users' && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          overflow: 'hidden'
        }}>
          <div style={{
            padding: '1rem 1.25rem',
            backgroundColor: 'var(--govt-gray-light)',
            borderBottom: '1px solid var(--govt-gray-medium)',
            fontWeight: 700,
            color: 'var(--govt-blue-dark)',
            fontSize: '0.95rem'
          }}>
            Backend managed users and identity-provider links
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{
                  backgroundColor: 'var(--govt-gray-off-white)',
                  borderBottom: '1px solid var(--govt-gray-medium)',
                  color: 'var(--govt-gray-dark)',
                  fontSize: '0.75rem',
                  textTransform: 'uppercase'
                }}>
                  <th style={{ padding: '0.75rem 1.25rem' }}>Principal</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Role Assignment</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Department Unit</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Authorized Project Scopes</th>
                  <th style={{ padding: '0.75rem 1.25rem' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} style={{ borderBottom: '1px solid var(--govt-gray-medium)' }}>
                    <td style={{ padding: '0.85rem 1.25rem' }}>
                      <div style={{ fontWeight: 700, color: 'var(--govt-blue-dark)' }}>{u.name}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>{u.email}</div>
                    </td>
                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span style={{
                        padding: '0.15rem 0.5rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        backgroundColor: 'var(--govt-blue-light)',
                        color: 'var(--govt-blue-primary)'
                      }}>
                        {u.role}
                      </span>
                    </td>
                    <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: 'var(--govt-gray-text)' }}>
                      {u.department}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--govt-blue-dark)' }}>
                      {u.assigned_projects}
                    </td>
                    <td style={{ padding: '0.85rem 1.25rem' }}>
                      <span style={{
                        padding: '0.15rem 0.5rem',
                        borderRadius: '9999px',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        backgroundColor: 'var(--govt-success-light)',
                        color: 'var(--govt-success-text)'
                      }}>
                        {u.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 4: SYSTEM POLICY & CONFIG */}
      {activeTab === 'telemetry' && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.5rem',
          maxWidth: '780px'
        }}>
          <h3 style={{ margin: '0 0 1.25rem', fontSize: '1.05rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            Active Platform Engineering Rules & Constraints
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.85rem' }}>
            {Object.entries(systemConfig).map(([key, val]) => (
              <div key={key} style={{
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--govt-gray-off-white)',
                border: '1px solid var(--govt-gray-medium)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.5rem'
              }}>
                <span style={{ fontWeight: 600, color: 'var(--govt-blue-dark)', textTransform: 'capitalize' }}>
                  {key.replace(/_/g, ' ')}
                </span>
                <span style={{ fontFamily: 'monospace', color: 'var(--govt-blue-primary)', fontWeight: 600 }}>
                  {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'api' && <BackendApiWorkbench />}
    </div>
  );
}

export default AdminDashboard;
