import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import {
  FileCheck2,
  Search,
  Filter,
  Download,
  Copy,
  Check,
  ShieldCheck,
  UserCheck,
  Cpu,
  Clock,
  ExternalLink,
} from 'lucide-react';

export default function AuditLog() {
  const { auditEvents, addToast } = useApp();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedActorFilter, setSelectedActorFilter] = useState('ALL');
  const [copiedId, setCopiedId] = useState(null);

  const filteredEvents = (auditEvents || []).filter((ev) => {
    if (selectedActorFilter !== 'ALL' && !ev.actorRole?.includes(selectedActorFilter)) return false;
    if (searchQuery.trim() !== '') {
      const q = searchQuery.toLowerCase();
      return (
        ev.id?.toLowerCase().includes(q) ||
        ev.evidenceId?.toLowerCase().includes(q) ||
        ev.projectId?.toLowerCase().includes(q) ||
        ev.actorName?.toLowerCase().includes(q) ||
        ev.reason?.toLowerCase().includes(q) ||
        ev.sha256Hash?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const handleCopyHash = (hash, id) => {
    navigator.clipboard.writeText(hash);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
    addToast({
      title: 'Cryptographic Hash Copied',
      description: 'Event SHA-256 fingerprint copied to clipboard.',
      type: 'info',
    });
  };

  const handleExportAuditJson = () => {
    const jsonStr =
      'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(filteredEvents, null, 2));
    const link = document.createElement('a');
    link.setAttribute('href', jsonStr);
    link.setAttribute('download', `PRISM_Audit_Ledger_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    addToast({
      title: 'Audit Ledger Exported',
      description: 'Cryptographically verified audit trail saved as JSON.',
      type: 'success',
    });
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid var(--govt-gray-medium, #e2e8f0)',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1
              style={{
                margin: 0,
                fontSize: '1.5rem',
                fontWeight: 700,
                color: 'var(--govt-blue-dark, #0f172a)',
                letterSpacing: '-0.02em',
              }}
            >
              Immutable Event Ledger & Audit Trail
            </h1>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '4px',
                backgroundColor: 'rgba(5, 150, 105, 0.12)',
                color: 'var(--govt-success, #059669)',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              <ShieldCheck size={14} />
              Tamper-Evident SHA-256 Ledger
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
            Section 58 compliance: Cryptographically hashed event chain recording every evidence upload, AI scoring, and reviewer decision.
          </p>
        </div>

        <button
          type="button"
          onClick={handleExportAuditJson}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.5rem 1rem',
            borderRadius: '6px',
            backgroundColor: 'var(--govt-gray-light)',
            border: '1px solid var(--govt-gray-medium)',
            color: 'var(--govt-gray-title)',
            fontSize: '0.825rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Download size={15} />
          <span>Export Audit Ledger (JSON)</span>
        </button>
      </div>

      {/* Search and Filters Bar */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium)',
          borderRadius: '8px',
          padding: '0.75rem 1rem',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          marginBottom: '1rem',
          fontSize: '0.825rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '240px' }}>
          <Search size={16} color="var(--govt-gray-dark)" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by Event ID, Evidence ID, Reason, Hash..."
            style={{
              width: '100%',
              maxWidth: '360px',
              border: 'none',
              outline: 'none',
              fontSize: '0.825rem',
              color: 'var(--govt-gray-title)',
            }}
          />
        </div>

        <select
          value={selectedActorFilter}
          onChange={(e) => setSelectedActorFilter(e.target.value)}
          style={{
            padding: '0.4rem 0.75rem',
            borderRadius: '6px',
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            fontSize: '0.8rem',
            fontWeight: 600,
            color: 'var(--govt-gray-title)',
            outline: 'none',
            cursor: 'pointer',
          }}
        >
          <option value="ALL">All Actor Categories</option>
          <option value="AI">AI Automated Engines</option>
          <option value="REVIEWER">Evidence Reviewers</option>
          <option value="ADMIN">Program Administrators</option>
          <option value="SUPERVISOR">Field Supervisors</option>
        </select>
      </div>

      {/* Immutable Event Timeline & Table */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium)',
          borderRadius: 'var(--radius-lg, 12px)',
          boxShadow: 'var(--shadow-sm)',
          overflow: 'hidden',
        }}
      >
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left' }}>
            <thead>
              <tr
                style={{
                  backgroundColor: 'var(--govt-gray-off-white)',
                  borderBottom: '1px solid var(--govt-gray-medium)',
                  color: 'var(--govt-gray-dark)',
                  textTransform: 'uppercase',
                  fontSize: '0.725rem',
                  letterSpacing: '0.04em',
                }}
              >
                <th style={{ padding: '0.75rem 1rem' }}>Event ID</th>
                <th style={{ padding: '0.75rem 1rem' }}>Evidence & Project</th>
                <th style={{ padding: '0.75rem 1rem' }}>Actor & Role</th>
                <th style={{ padding: '0.75rem 1rem' }}>Action</th>
                <th style={{ padding: '0.75rem 1rem' }}>State Transition</th>
                <th style={{ padding: '0.75rem 1rem' }}>Reason & Justification</th>
                <th style={{ padding: '0.75rem 1rem' }}>Cryptographic Hash</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: '2rem', textAlign: 'center', color: 'var(--govt-gray-dark)' }}>
                    No audit events match your search filters.
                  </td>
                </tr>
              ) : (
                filteredEvents.map((ev) => (
                  <tr
                    key={ev.id}
                    style={{
                      borderBottom: '1px solid var(--govt-gray-light)',
                      transition: 'background-color 0.15s ease',
                    }}
                  >
                    <td style={{ padding: '0.85rem 1rem', fontFamily: 'monospace', fontWeight: 700, whiteSpace: 'nowrap' }}>
                      {ev.id}
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                        <Link
                          to={`/evidence/${ev.evidenceId}`}
                          style={{
                            fontFamily: 'monospace',
                            fontWeight: 600,
                            color: 'var(--govt-blue-primary)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.25rem',
                            textDecoration: 'none',
                          }}
                        >
                          <span>{ev.evidenceId}</span>
                          <ExternalLink size={12} color="var(--govt-gray-dark)" />
                        </Link>
                        <span style={{ fontSize: '0.725rem', color: 'var(--govt-gray-dark)' }}>{ev.projectId}</span>
                      </div>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        {ev.actorRole?.includes('AI') ? (
                          <Cpu size={15} color="var(--govt-blue-primary)" />
                        ) : (
                          <UserCheck size={15} color="var(--govt-warning)" />
                        )}
                        <div>
                          <div style={{ fontWeight: 600, color: 'var(--govt-gray-title)' }}>{ev.actorName}</div>
                          <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>{ev.actorRole}</div>
                        </div>
                      </div>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          backgroundColor:
                            ev.action === 'APPROVE'
                              ? 'rgba(5, 150, 105, 0.12)'
                              : ev.action === 'FLAG_CRITICAL' || ev.action === 'REJECT'
                              ? 'rgba(220, 38, 38, 0.12)'
                              : ev.action === 'OVERRIDE'
                              ? 'rgba(217, 119, 6, 0.12)'
                              : 'var(--govt-gray-light)',
                          color:
                            ev.action === 'APPROVE'
                              ? 'var(--govt-success)'
                              : ev.action === 'FLAG_CRITICAL' || ev.action === 'REJECT'
                              ? 'var(--govt-danger)'
                              : ev.action === 'OVERRIDE'
                              ? 'var(--govt-warning)'
                              : 'var(--govt-gray-title)',
                        }}
                      >
                        {ev.action}
                      </span>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                        <span style={{ color: 'var(--govt-gray-dark)' }}>{ev.previousState}</span>
                        <span>→</span>
                        <span style={{ fontWeight: 700, color: 'var(--govt-gray-title)' }}>{ev.newState}</span>
                      </div>
                    </td>

                    <td
                      style={{
                        padding: '0.85rem 1rem',
                        maxWidth: '280px',
                        fontSize: '0.75rem',
                        color: 'var(--govt-gray-text)',
                        lineHeight: 1.35,
                      }}
                    >
                      {ev.reason}
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span
                          style={{
                            fontFamily: 'monospace',
                            fontSize: '0.725rem',
                            color: 'var(--govt-gray-dark)',
                            backgroundColor: 'var(--govt-gray-light)',
                            padding: '0.15rem 0.35rem',
                            borderRadius: '3px',
                          }}
                        >
                          {ev.sha256Hash?.substring(0, 10)}...
                        </span>
                        <button
                          type="button"
                          onClick={() => handleCopyHash(ev.sha256Hash, ev.id)}
                          title="Copy SHA-256 fingerprint"
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            color: copiedId === ev.id ? 'var(--govt-success)' : 'var(--govt-gray-dark)',
                            padding: '2px',
                          }}
                        >
                          {copiedId === ev.id ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                      </div>
                    </td>

                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right', whiteSpace: 'nowrap', fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                      {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
