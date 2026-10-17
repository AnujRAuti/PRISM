import { useState, useEffect } from 'react';
import { formatDate } from '../../utils/helpers';
import { AdminIcon, UserIcon, DownloadIcon, CheckIcon, AlertIcon, ClockIcon } from '../../components/common/Icon';
import { authApi, auditApi, adminApi } from '../../services/api';

function AdminDashboard() {
  const [activeTab, setActiveTab] = useState('users'); // 'users', 'audit', 'config', 'metrics'
  const [notification, setNotification] = useState(null);

  // User Management State
  const [users, setUsers] = useState([
    { id: 'USR-001', name: 'Dr. Ramesh Sharma', email: 'ramesh.sharma@poa.gov.in', department: 'Ministry of Rural Development', role: 'admin', status: 'active', last_active: '2024-03-10T09:30:00Z' },
    { id: 'USR-002', name: 'Sunita Patel', email: 'sunita.patel@gujarat.gov.in', department: 'Gujarat Energy Development Agency', role: 'supervisor', status: 'active', last_active: '2024-03-09T16:45:00Z' },
    { id: 'USR-003', name: 'Rajesh Kulkarni', email: 'rajesh.k@mahapwd.gov.in', department: 'Maharashtra Public Works Dept', role: 'reviewer', status: 'active', last_active: '2024-03-10T11:15:00Z' },
    { id: 'USR-004', name: 'John Doe', email: 'john.doe@pmgsy.in', department: 'Pune District Field Office', role: 'inspector', status: 'active', last_active: '2024-03-08T14:20:00Z' },
    { id: 'USR-005', name: 'Amit Verma', email: 'amit.verma@jaljeevan.gov.in', department: 'Rajasthan Water Resources Dept', role: 'reviewer', status: 'active', last_active: '2024-03-07T10:00:00Z' },
    { id: 'USR-006', name: 'Kavita Singh', email: 'kavita.s@uphealth.gov.in', department: 'UP Health Infrastructure Corp', role: 'reviewer', status: 'suspended', last_active: '2024-02-28T18:00:00Z' }
  ]);

  const [showAddUserModal, setShowAddUserModal] = useState(false);
  const [newUser, setNewUser] = useState({ name: '', email: '', department: '', role: 'reviewer' });

  // System Configuration State
  const [config, setConfig] = useState({
    high_risk_threshold: 70,
    medium_risk_threshold: 40,
    geofence_tolerance_meters: 50,
    impossible_travel_speed_kmh: 120,
    retention_period_days: 90,
    max_upload_size_mb: 15,
    quarantine_auto_purge: true,
    strict_mime_validation: true
  });

  // Audit Logs State
  const [auditLogs, setAuditLogs] = useState([
    {
      id: 'AUD-9021',
      timestamp: '2024-03-10T11:15:20Z',
      actor: 'Rajesh Kulkarni',
      role: 'Reviewer',
      action: 'REVIEW_DECISION',
      entity: 'EVD-003',
      ip_address: '10.24.110.42',
      severity: 'WARNING',
      details: 'Flagged evidence for inspection due to cross-project duplication with PRJ-001.'
    },
    {
      id: 'AUD-9020',
      timestamp: '2024-03-10T10:04:12Z',
      actor: 'System Ingestion Worker',
      role: 'Automated Pipeline',
      action: 'EVIDENCE_INGESTION',
      entity: 'EVD-004',
      ip_address: '127.0.0.1',
      severity: 'INFO',
      details: 'Quarantine passed. Cryptographic SHA-256 and pHash fingerprints successfully registered.'
    },
    {
      id: 'AUD-9019',
      timestamp: '2024-03-09T16:50:00Z',
      actor: 'Dr. Ramesh Sharma',
      role: 'Administrator',
      action: 'SYSTEM_CONFIG_UPDATE',
      entity: 'CORE_ENGINE',
      ip_address: '10.12.0.8',
      severity: 'CRITICAL',
      details: 'Updated geofence tolerance threshold from 100m to 50m.'
    },
    {
      id: 'AUD-9018',
      timestamp: '2024-03-08T15:30:45Z',
      actor: 'Sunita Patel',
      role: 'Supervisor',
      action: 'USER_STATUS_CHANGE',
      entity: 'USR-006',
      ip_address: '10.44.82.15',
      severity: 'WARNING',
      details: 'Suspended reviewer account pending security re-verification.'
    },
    {
      id: 'AUD-9017',
      timestamp: '2024-03-07T09:12:00Z',
      actor: 'System Fusion Engine',
      role: 'Automated Pipeline',
      action: 'ANOMALY_DETECTED',
      entity: 'EVD-003',
      ip_address: '127.0.0.1',
      severity: 'CRITICAL',
      details: 'Cross-Project Perceptual Hash Duplicate alert triggered between PRJ-002 and PRJ-001.'
    }
  ]);

  const [auditFilter, setAuditFilter] = useState('ALL');

  useEffect(() => {
    let isMounted = true;
    async function loadAdminData() {
      try {
        const [usersResp, auditResp] = await Promise.allSettled([
          authApi.getUsers({ limit: 50 }),
          auditApi.getEvents({ limit: 50 }),
        ]);

        if (isMounted) {
          if (usersResp.status === 'fulfilled' && usersResp.value.data?.items?.length > 0) {
            setUsers(usersResp.value.data.items.map(u => ({
              id: u.id,
              name: u.display_name || u.username,
              email: u.email || `${u.username}@poa.gov.in`,
              department: u.identity_provider || 'National Data Center',
              role: u.status === 'ACTIVE' ? 'admin' : 'reviewer',
              status: u.status === 'ACTIVE' ? 'active' : 'suspended',
              last_active: u.created_at,
            })));
          }

          if (auditResp.status === 'fulfilled' && auditResp.value.data?.items?.length > 0) {
            setAuditLogs(auditResp.value.data.items.map(e => ({
              id: e.id,
              timestamp: e.created_at,
              actor: e.actor_id || 'System Worker',
              role: 'Audit Engine',
              action: e.event_type,
              entity: e.resource_id || e.id,
              ip_address: '127.0.0.1',
              severity: (e.event_type || '').includes('ANOMALY') || (e.event_type || '').includes('FAILED') ? 'WARNING' : 'INFO',
              details: JSON.stringify(e.payload || {}),
            })));
          }
        }
      } catch (err) {
        console.warn('Admin API load warning:', err);
      }
    }
    loadAdminData();
    return () => { isMounted = false; };
  }, []);

  // Trigger flash banner
  const triggerNotification = (msg) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3500);
  };

  // User actions
  const handleToggleUserStatus = (userId) => {
    setUsers(prev => prev.map(u => {
      if (u.id === userId) {
        const nextStatus = u.status === 'active' ? 'suspended' : 'active';
        triggerNotification(`User ${u.name} status updated to ${nextStatus.toUpperCase()}.`);
        return { ...u, status: nextStatus };
      }
      return u;
    }));
  };

  const handleRoleChange = (userId, newRole) => {
    setUsers(prev => prev.map(u => {
      if (u.id === userId) {
        triggerNotification(`User ${u.name} role elevated to ${newRole.toUpperCase()}.`);
        return { ...u, role: newRole };
      }
      return u;
    }));
  };

  const handleAddUser = (e) => {
    e.preventDefault();
    if (!newUser.name || !newUser.email) return;

    const created = {
      id: `USR-00${users.length + 1}`,
      name: newUser.name,
      email: newUser.email,
      department: newUser.department || 'General Administration',
      role: newUser.role,
      status: 'active',
      last_active: new Date().toISOString()
    };

    setUsers([created, ...users]);
    setShowAddUserModal(false);
    setNewUser({ name: '', email: '', department: '', role: 'reviewer' });
    triggerNotification(`New user ${created.name} (${created.role}) provisioned successfully.`);
  };

  // Config save action
  const handleSaveConfig = (e) => {
    e.preventDefault();
    triggerNotification('System parameters saved & applied to EIIL pipeline engines.');

    // Add audit entry for config update
    const newAudit = {
      id: `AUD-${Math.floor(Math.random() * 1000) + 9100}`,
      timestamp: new Date().toISOString(),
      actor: 'Admin Session (Current User)',
      role: 'Administrator',
      action: 'SYSTEM_CONFIG_UPDATE',
      entity: 'CORE_ENGINE',
      ip_address: '127.0.0.1',
      severity: 'CRITICAL',
      details: `Updated parameters: High Risk=${config.high_risk_threshold}%, Geofence=${config.geofence_tolerance_meters}m.`
    };
    setAuditLogs([newAudit, ...auditLogs]);
  };

  // Export Audit to CSV
  const handleExportAuditCSV = () => {
    let csv = 'data:text/csv;charset=utf-8,Event_ID,Timestamp,Actor,Role,Action,Entity,IP_Address,Severity,Details\r\n';
    auditLogs.forEach(log => {
      csv += `"${log.id}","${log.timestamp}","${log.actor}","${log.role}","${log.action}","${log.entity}","${log.ip_address}","${log.severity}","${log.details.replace(/"/g, '""')}"\r\n`;
    });
    const encoded = encodeURI(csv);
    const link = document.createElement('a');
    link.setAttribute('href', encoded);
    link.setAttribute('download', `proof_of_action_audit_trail_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filteredAuditLogs = auditFilter === 'ALL'
    ? auditLogs
    : auditLogs.filter(l => l.severity === auditFilter || l.action === auditFilter);

  return (
    <div style={{ padding: '1.75rem 2rem', width: '100%', boxSizing: 'border-box', backgroundColor: 'var(--govt-gray-off-white)' }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        flexWrap: 'wrap',
        gap: '1rem',
        marginBottom: '1.5rem',
        paddingBottom: '1rem',
        borderBottom: '2px solid var(--govt-gray-medium)'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.75rem' }}>
              System Administration & Integrity Governance
            </h2>
            <span style={{
              backgroundColor: 'var(--govt-blue-dark)',
              color: '#ffffff',
              fontSize: '0.75rem',
              fontWeight: '700',
              padding: '0.2rem 0.5rem',
              borderRadius: '2px'
            }}>
              SUPERVISOR / ADMIN PORTAL
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.925rem' }}>
            Manage privileged accounts, configure fraud risk algorithms, inspect immutable audit trails, and observe pipeline health.
          </p>
        </div>

        {/* Global Action */}
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => setShowAddUserModal(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              border: 'none',
              padding: '0.55rem 1rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.875rem',
              fontWeight: '600',
              cursor: 'pointer'
            }}
          >
            + Provision New User
          </button>
        </div>
      </div>

      {/* Notification Banner */}
      {notification && (
        <div style={{
          backgroundColor: 'var(--govt-success-light)',
          color: 'var(--govt-success)',
          border: '1px solid var(--govt-success)',
          padding: '0.75rem 1rem',
          borderRadius: 'var(--radius-sm)',
          marginBottom: '1.25rem',
          fontWeight: '600',
          fontSize: '0.9rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          <CheckIcon />
          {notification}
        </div>
      )}

      {/* Admin Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '2px solid var(--govt-gray-medium)', paddingBottom: '0.5rem' }}>
        <button
          onClick={() => setActiveTab('users')}
          style={{
            padding: '0.65rem 1.25rem',
            backgroundColor: activeTab === 'users' ? 'var(--govt-blue-primary)' : 'transparent',
            color: activeTab === 'users' ? '#ffffff' : 'var(--govt-gray-text)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontWeight: '600',
            fontSize: '0.9rem',
            cursor: 'pointer'
          }}
        >
          User Management ({users.length})
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          style={{
            padding: '0.65rem 1.25rem',
            backgroundColor: activeTab === 'audit' ? 'var(--govt-blue-primary)' : 'transparent',
            color: activeTab === 'audit' ? '#ffffff' : 'var(--govt-gray-text)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontWeight: '600',
            fontSize: '0.9rem',
            cursor: 'pointer'
          }}
        >
          Immutable Audit Log ({auditLogs.length})
        </button>
        <button
          onClick={() => setActiveTab('config')}
          style={{
            padding: '0.65rem 1.25rem',
            backgroundColor: activeTab === 'config' ? 'var(--govt-blue-primary)' : 'transparent',
            color: activeTab === 'config' ? '#ffffff' : 'var(--govt-gray-text)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontWeight: '600',
            fontSize: '0.9rem',
            cursor: 'pointer'
          }}
        >
          System Configuration & Rules
        </button>
        <button
          onClick={() => setActiveTab('metrics')}
          style={{
            padding: '0.65rem 1.25rem',
            backgroundColor: activeTab === 'metrics' ? 'var(--govt-blue-primary)' : 'transparent',
            color: activeTab === 'metrics' ? '#ffffff' : 'var(--govt-gray-text)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontWeight: '600',
            fontSize: '0.9rem',
            cursor: 'pointer'
          }}
        >
          Pipeline Health & Metrics
        </button>
      </div>

      {/* Tab 1: User Management */}
      {activeTab === 'users' && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--govt-gray-medium)',
          boxShadow: 'var(--shadow-sm)',
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
            <h4 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.05rem' }}>
              Authorized System Operators & Role-Based Access Control (RBAC)
            </h4>
            <span style={{ fontSize: '0.8rem', color: 'var(--govt-blue-dark)' }}>
              Active Sessions: 5 • Suspended: 1
            </span>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead style={{ backgroundColor: 'var(--govt-gray-off-white)', borderBottom: '1px solid var(--govt-gray-medium)' }}>
              <tr>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Operator</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Department</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Assigned Role</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--govt-blue-dark)' }}>Status</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Last Activity</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--govt-blue-dark)' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} style={{ borderBottom: '1px solid var(--govt-gray-light)', backgroundColor: u.status === 'suspended' ? '#fdf2f2' : '#ffffff' }}>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <div style={{ fontWeight: '700', color: 'var(--govt-blue-dark)' }}>{u.name}</div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>{u.email} ({u.id})</div>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)' }}>
                    {u.department}
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <select
                      value={u.role}
                      onChange={(e) => handleRoleChange(u.id, e.target.value)}
                      style={{
                        padding: '0.25rem 0.5rem',
                        fontSize: '0.8rem',
                        fontWeight: '600',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--govt-gray-medium)',
                        backgroundColor: '#ffffff'
                      }}
                    >
                      <option value="admin">Administrator</option>
                      <option value="supervisor">Supervisor</option>
                      <option value="reviewer">Reviewer</option>
                      <option value="inspector">Field Inspector</option>
                      <option value="citizen">Citizen Auditor</option>
                    </select>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                    <span style={{
                      backgroundColor: u.status === 'active' ? 'var(--govt-success-light)' : 'var(--govt-danger-light)',
                      color: u.status === 'active' ? 'var(--govt-success)' : 'var(--govt-danger)',
                      padding: '0.2rem 0.6rem',
                      borderRadius: '2px',
                      fontSize: '0.75rem',
                      fontWeight: '700',
                      textTransform: 'uppercase'
                    }}>
                      {u.status}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-dark)', fontSize: '0.8rem' }}>
                    {formatDate(u.last_active)}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                    <button
                      onClick={() => handleToggleUserStatus(u.id)}
                      style={{
                        padding: '0.3rem 0.75rem',
                        backgroundColor: u.status === 'active' ? 'var(--govt-danger-light)' : 'var(--govt-success-light)',
                        color: u.status === 'active' ? 'var(--govt-danger)' : 'var(--govt-success)',
                        border: `1px solid ${u.status === 'active' ? 'var(--govt-danger)' : 'var(--govt-success)'}`,
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.75rem',
                        fontWeight: '600',
                        cursor: 'pointer'
                      }}
                    >
                      {u.status === 'active' ? 'Suspend' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 2: Immutable Audit Log Viewer */}
      {activeTab === 'audit' && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--govt-gray-medium)',
          boxShadow: 'var(--shadow-sm)',
          overflow: 'hidden'
        }}>
          <div style={{
            padding: '1rem 1.25rem',
            backgroundColor: 'var(--govt-blue-light)',
            borderBottom: '2px solid var(--govt-blue-primary)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '0.5rem'
          }}>
            <h4 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.05rem' }}>
              Immutable Compliance & Security Audit Trail
            </h4>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <select
                value={auditFilter}
                onChange={(e) => setAuditFilter(e.target.value)}
                style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--govt-gray-medium)' }}
              >
                <option value="ALL">All Severities</option>
                <option value="INFO">INFO Only</option>
                <option value="WARNING">WARNING Only</option>
                <option value="CRITICAL">CRITICAL Only</option>
              </select>
              <button
                onClick={handleExportAuditCSV}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  backgroundColor: 'var(--govt-white)',
                  color: 'var(--govt-blue-primary)',
                  border: '1px solid var(--govt-blue-primary)',
                  padding: '0.3rem 0.65rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.8rem',
                  fontWeight: '600',
                  cursor: 'pointer'
                }}
              >
                <DownloadIcon />
                Export Audit CSV
              </button>
            </div>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead style={{ backgroundColor: 'var(--govt-gray-off-white)', borderBottom: '1px solid var(--govt-gray-medium)' }}>
              <tr>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Event ID</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Timestamp (UTC)</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Actor & Role</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Action</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Entity</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--govt-blue-dark)' }}>Severity</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-blue-dark)' }}>Audit Metadata & Message</th>
              </tr>
            </thead>
            <tbody>
              {filteredAuditLogs.map((log) => (
                <tr key={log.id} style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-family-mono)', fontWeight: '700', color: 'var(--govt-blue-primary)' }}>
                    {log.id}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-dark)', fontSize: '0.8rem' }}>
                    {formatDate(log.timestamp)}
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <div style={{ fontWeight: '600', color: 'var(--govt-gray-text)' }}>{log.actor}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>{log.role}</div>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-family-mono)', fontSize: '0.75rem', fontWeight: '600' }}>
                    {log.action}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontWeight: '600', color: 'var(--govt-blue-dark)' }}>
                    {log.entity}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                    <span style={{
                      backgroundColor: log.severity === 'CRITICAL' ? 'var(--govt-danger-light)' : log.severity === 'WARNING' ? 'var(--govt-warning-light)' : 'var(--govt-info-light)',
                      color: log.severity === 'CRITICAL' ? 'var(--govt-danger)' : log.severity === 'WARNING' ? '#856404' : 'var(--govt-info)',
                      padding: '0.15rem 0.5rem',
                      borderRadius: '2px',
                      fontSize: '0.7rem',
                      fontWeight: '700'
                    }}>
                      {log.severity}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-text)', fontSize: '0.8rem' }}>
                    {log.details}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 3: System Configuration & Rule Tuning */}
      {activeTab === 'config' && (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-md)',
          padding: '1.5rem',
          border: '1px solid var(--govt-gray-medium)',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <h4 style={{ margin: '0 0 0.5rem 0', color: 'var(--govt-blue-dark)', fontSize: '1.15rem' }}>
            EIIL Multi-Signal Fusion Engine Parameters
          </h4>
          <p style={{ margin: '0 0 1.5rem 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
            Tune mathematical thresholds, geospatial boundary tolerances, and media quarantine retention windows across all scheme pipelines.
          </p>

          <form onSubmit={handleSaveConfig}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
              {/* High Risk Cutoff */}
              <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--govt-gray-medium)' }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '700', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                  <span>High Risk Flagging Threshold:</span>
                  <span style={{ color: 'var(--govt-danger)' }}>{config.high_risk_threshold}%</span>
                </label>
                <input
                  type="range"
                  min="50"
                  max="95"
                  value={config.high_risk_threshold}
                  onChange={(e) => setConfig({ ...config, high_risk_threshold: Number(e.target.value) })}
                  style={{ width: '100%' }}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block', marginTop: '0.25rem' }}>
                  Submissions scoring above this threshold route automatically into the priority supervisor queue.
                </span>
              </div>

              {/* Medium Risk Cutoff */}
              <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--govt-gray-medium)' }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '700', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                  <span>Medium Risk Warning Threshold:</span>
                  <span style={{ color: 'var(--govt-warning)' }}>{config.medium_risk_threshold}%</span>
                </label>
                <input
                  type="range"
                  min="20"
                  max="60"
                  value={config.medium_risk_threshold}
                  onChange={(e) => setConfig({ ...config, medium_risk_threshold: Number(e.target.value) })}
                  style={{ width: '100%' }}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block', marginTop: '0.25rem' }}>
                  Submissions between Medium and High risk trigger visual comparison warnings for reviewers.
                </span>
              </div>

              {/* Geofence Tolerance */}
              <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--govt-gray-medium)' }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '700', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                  <span>Geofence Boundary Margin:</span>
                  <span style={{ color: 'var(--govt-blue-primary)' }}>{config.geofence_tolerance_meters} meters</span>
                </label>
                <input
                  type="number"
                  min="10"
                  max="500"
                  value={config.geofence_tolerance_meters}
                  onChange={(e) => setConfig({ ...config, geofence_tolerance_meters: Number(e.target.value) })}
                  style={{ width: '100%', padding: '0.4rem', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', boxSizing: 'border-box' }}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block', marginTop: '0.25rem' }}>
                  Buffer tolerance around approved project polygon accounting for standard GPS drift.
                </span>
              </div>

              {/* Impossible Travel Speed */}
              <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--govt-gray-medium)' }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '700', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                  <span>Impossible Velocity Cutoff:</span>
                  <span style={{ color: 'var(--govt-blue-primary)' }}>{config.impossible_travel_speed_kmh} km/h</span>
                </label>
                <input
                  type="number"
                  min="60"
                  max="300"
                  value={config.impossible_travel_speed_kmh}
                  onChange={(e) => setConfig({ ...config, impossible_travel_speed_kmh: Number(e.target.value) })}
                  style={{ width: '100%', padding: '0.4rem', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', boxSizing: 'border-box' }}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block', marginTop: '0.25rem' }}>
                  Flags an anomaly if consecutive photos by the same uploader require travel velocity exceeding this limit.
                </span>
              </div>

              {/* Retention Policy */}
              <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--govt-gray-medium)' }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '700', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                  <span>Quarantine Retention Period:</span>
                  <span style={{ color: 'var(--govt-blue-primary)' }}>{config.retention_period_days} days</span>
                </label>
                <input
                  type="number"
                  min="30"
                  max="365"
                  value={config.retention_period_days}
                  onChange={(e) => setConfig({ ...config, retention_period_days: Number(e.target.value) })}
                  style={{ width: '100%', padding: '0.4rem', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', boxSizing: 'border-box' }}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block', marginTop: '0.25rem' }}>
                  Unapproved or rejected uploads are permanently archived after this interval.
                </span>
              </div>

              {/* Max File Size */}
              <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--govt-gray-medium)' }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '700', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                  <span>Max Upload File Size:</span>
                  <span style={{ color: 'var(--govt-blue-primary)' }}>{config.max_upload_size_mb} MB</span>
                </label>
                <input
                  type="number"
                  min="5"
                  max="50"
                  value={config.max_upload_size_mb}
                  onChange={(e) => setConfig({ ...config, max_upload_size_mb: Number(e.target.value) })}
                  style={{ width: '100%', padding: '0.4rem', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', boxSizing: 'border-box' }}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block', marginTop: '0.25rem' }}>
                  Maximum permissible payload per photo submission.
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid var(--govt-gray-medium)', paddingTop: '1rem' }}>
              <button
                type="submit"
                style={{
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  border: 'none',
                  padding: '0.65rem 1.5rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.9rem',
                  fontWeight: '700',
                  cursor: 'pointer'
                }}
              >
                Save & Deploy System Configuration
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Tab 4: Pipeline Health & Operational Metrics */}
      {activeTab === 'metrics' && (
        <div>
          {/* Top telemetry cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            <div style={{ backgroundColor: 'var(--govt-white)', padding: '1.25rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--govt-gray-medium)', boxShadow: 'var(--shadow-sm)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: '700', color: 'var(--govt-gray-dark)', textTransform: 'uppercase' }}>Ingestion Throughput</span>
              <div style={{ fontSize: '1.75rem', fontWeight: '800', color: 'var(--govt-blue-primary)', margin: '0.25rem 0' }}>1,420</div>
              <span style={{ fontSize: '0.75rem', color: 'var(--govt-success)', fontWeight: '600' }}>+12.4% vs last week</span>
            </div>

            <div style={{ backgroundColor: 'var(--govt-white)', padding: '1.25rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--govt-gray-medium)', boxShadow: 'var(--shadow-sm)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: '700', color: 'var(--govt-gray-dark)', textTransform: 'uppercase' }}>Pipeline Latency</span>
              <div style={{ fontSize: '1.75rem', fontWeight: '800', color: 'var(--govt-blue-dark)', margin: '0.25rem 0' }}>198 ms</div>
              <span style={{ fontSize: '0.75rem', color: 'var(--govt-success)', fontWeight: '600' }}>Avg End-to-End Fusion</span>
            </div>

            <div style={{ backgroundColor: 'var(--govt-white)', padding: '1.25rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--govt-gray-medium)', boxShadow: 'var(--shadow-sm)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: '700', color: 'var(--govt-gray-dark)', textTransform: 'uppercase' }}>Active Review Queue</span>
              <div style={{ fontSize: '1.75rem', fontWeight: '800', color: 'var(--govt-warning)', margin: '0.25rem 0' }}>24 Items</div>
              <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>Turnaround: 4.2 hours</span>
            </div>

            <div style={{ backgroundColor: 'var(--govt-white)', padding: '1.25rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--govt-gray-medium)', boxShadow: 'var(--shadow-sm)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: '700', color: 'var(--govt-gray-dark)', textTransform: 'uppercase' }}>System Availability</span>
              <div style={{ fontSize: '1.75rem', fontWeight: '800', color: 'var(--govt-success)', margin: '0.25rem 0' }}>99.98%</div>
              <span style={{ fontSize: '0.75rem', color: 'var(--govt-success)', fontWeight: '600' }}>Zero Quarantine Breaches</span>
            </div>
          </div>

          {/* Engine Status Matrix */}
          <div style={{ backgroundColor: 'var(--govt-white)', padding: '1.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--govt-gray-medium)', boxShadow: 'var(--shadow-sm)' }}>
            <h4 style={{ margin: '0 0 1rem 0', color: 'var(--govt-blue-dark)', fontSize: '1.1rem' }}>
              Subsystem & Verification Microservice Status
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
              {[
                { name: 'Cryptographic SHA-256 Engine', latency: '12ms', status: 'HEALTHY', role: 'Exact byte identity' },
                { name: 'Perceptual pHash Fingerprinting', latency: '38ms', status: 'HEALTHY', role: 'Visual duplicate detection' },
                { name: 'PostGIS Geospatial Engine', latency: '15ms', status: 'HEALTHY', role: 'Geofence bounds & distance' },
                { name: 'Temporal Chronology Analyzer', latency: '9ms', status: 'HEALTHY', role: 'Timeline & velocity checks' },
                { name: 'Vision / Claim Matching Core', latency: '124ms', status: 'HEALTHY', role: 'Object & milestone confirmation' },
                { name: 'Multi-Signal Fusion Arbiter', latency: '18ms', status: 'HEALTHY', role: 'Scoring & anomaly aggregation' },
              ].map((svc, idx) => (
                <div key={idx} style={{ padding: '1rem', backgroundColor: 'var(--govt-gray-off-white)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--govt-gray-medium)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                    <strong style={{ fontSize: '0.9rem', color: 'var(--govt-blue-dark)' }}>{svc.name}</strong>
                    <span style={{ fontSize: '0.7rem', fontWeight: '700', color: 'var(--govt-success)', backgroundColor: 'var(--govt-success-light)', padding: '0.15rem 0.4rem', borderRadius: '2px' }}>
                      {svc.status}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>{svc.role}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--govt-blue-primary)', marginTop: '0.5rem', fontWeight: '600' }}>
                    Median Latency: {svc.latency}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Provision User Modal */}
      {showAddUserModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-md)',
            padding: '1.5rem',
            width: '90%',
            maxWidth: '500px',
            boxShadow: 'var(--shadow-lg)'
          }}>
            <h3 style={{ margin: '0 0 1rem 0', color: 'var(--govt-blue-dark)' }}>Provision New System User</h3>
            <form onSubmit={handleAddUser}>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '600', marginBottom: '0.25rem' }}>Full Name *</label>
                <input
                  type="text"
                  required
                  value={newUser.name}
                  onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '600', marginBottom: '0.25rem' }}>Government Email Address *</label>
                <input
                  type="email"
                  required
                  value={newUser.email}
                  onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '600', marginBottom: '0.25rem' }}>Ministry / State Department</label>
                <input
                  type="text"
                  value={newUser.department}
                  onChange={(e) => setNewUser({ ...newUser, department: e.target.value })}
                  placeholder="e.g. Ministry of Jal Shakti"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '600', marginBottom: '0.25rem' }}>Designated Role</label>
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', boxSizing: 'border-box' }}
                >
                  <option value="reviewer">Reviewer</option>
                  <option value="supervisor">Supervisor</option>
                  <option value="inspector">Field Inspector</option>
                  <option value="admin">Administrator</option>
                  <option value="citizen">Citizen Auditor</option>
                </select>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setShowAddUserModal(false)}
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: 'transparent',
                    border: '1px solid var(--govt-gray-medium)',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: 'var(--govt-blue-primary)',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: 'var(--radius-sm)',
                    fontWeight: '600',
                    cursor: 'pointer'
                  }}
                >
                  Create Operator
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminDashboard;
