import React, { useState } from 'react';
import { useApp } from '../../context/AppContext';
import {
  Settings as SettingsIcon,
  Key,
  Webhook,
  Bell,
  Globe,
  Sun,
  Moon,
  Laptop,
  Copy,
  Check,
  Play,
  Code,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';

export default function Settings() {
  const { role, loginUser, density, setDensity, addToast } = useApp();

  const [apiKey, setApiKey] = useState('eiil_live_9f83a48e71b29d8164bc77f202e88a01');
  const [isCopiedKey, setIsCopiedKey] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState('https://pmgsy.nic.in/api/v1/eiil-webhook');
  const [webhookEvent, setWebhookEvent] = useState('evidence.flagged_critical');
  const [webhookResponse, setWebhookResponse] = useState(null);

  const handleCopyKey = () => {
    navigator.clipboard.writeText(apiKey);
    setIsCopiedKey(true);
    setTimeout(() => setIsCopiedKey(false), 2000);
    addToast({
      title: 'API Key Copied',
      description: 'Bearer token copied to clipboard.',
      type: 'info',
    });
  };

  const handleGenerateKey = () => {
    const newKey =
      'eiil_live_' +
      Array.from(crypto.getRandomValues(new Uint8Array(16)))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
    setApiKey(newKey);
    addToast({
      title: 'New API Key Provisioned',
      description: 'Previous key invalidated. Update client service headers.',
      type: 'success',
    });
  };

  const handleTestWebhook = () => {
    setWebhookResponse('Dispatching event payload...');
    setTimeout(() => {
      setWebhookResponse(
        JSON.stringify(
          {
            status: 200,
            event: webhookEvent,
            dispatchedAt: new Date().toISOString(),
            destination: webhookUrl,
            sha256Signature: '7a21f8c49e15903b68f5c22e4d9b01a23847e51c8901b2a4c8e71629d8164bc7',
            deliveryDurationMs: 42,
            acknowledgement: 'ACK_RECEIVED_BY_PMGSY_GATEWAY',
          },
          null,
          2
        )
      );
      addToast({
        title: 'Webhook Delivered (HTTP 200)',
        description: 'Target gateway acknowledged statutory event payload.',
        type: 'success',
      });
    }, 600);
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1000px', margin: '0 auto' }}>
      {/* Top Header */}
      <div
        style={{
          paddingBottom: '1rem',
          borderBottom: '1px solid var(--govt-gray-medium, #e2e8f0)',
          marginBottom: '1.5rem',
        }}
      >
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
            System Settings & Integration APIs
          </h1>
          <span
            style={{
              fontSize: '0.75rem',
              padding: '0.2rem 0.6rem',
              borderRadius: '4px',
              backgroundColor: 'var(--govt-gray-light)',
              border: '1px solid var(--govt-gray-medium)',
              color: 'var(--govt-gray-dark)',
              fontWeight: 600,
            }}
          >
            DPI Administration
          </span>
        </div>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
          Configure reviewer operations, role context, automated webhooks, and secure API keys.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* Active Role Configuration */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <UserCheck size={18} color="var(--govt-blue-primary)" />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              Operator Persona & Role Simulation
            </h3>
          </div>
          <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
            Switch roles to test tailored portals, permissions, and validation registers.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
            {[
              { id: 'REVIEWER', name: '🛡️ Evidence Reviewer (Lead)', desc: 'High-velocity review queue, CV inspection, formal overrides' },
              { id: 'AUDITOR', name: '⚖️ Statutory Auditor (CAG)', desc: 'Section 86 compliance, EIIL certificates, non-repudiation ledger verifier' },
              { id: 'CITIZEN', name: '👥 Citizen / Resident', desc: 'Discover state projects, file civic grievances, track inspection status' },
              { id: 'ADMIN', name: '⚙️ Platform Administrator', desc: 'RBAC user management, legal retention holds, system rule tuning' },
            ].map((r) => {
              const isSelected = (role || 'REVIEWER') === r.id;
              return (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => loginUser(r.id)}
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: '8px',
                    textAlign: 'left',
                    cursor: 'pointer',
                    border: isSelected ? '1.5px solid var(--govt-blue-accent)' : '1px solid var(--govt-gray-medium)',
                    backgroundColor: isSelected ? 'var(--govt-blue-light)' : '#ffffff',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                      {r.name}
                    </span>
                    {isSelected && <span style={{ color: 'var(--govt-blue-primary)', fontSize: '0.8rem' }}>✓</span>}
                  </div>
                  <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                    {r.desc}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Table Density Preference */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <SettingsIcon size={18} color="var(--govt-blue-primary)" />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              Queue Display Density
            </h3>
          </div>
          <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
            Choose how much evidence data to display per screen in the review queue.
          </p>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              type="button"
              onClick={() => setDensity('comfortable')}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                border: density === 'comfortable' ? '1.5px solid var(--govt-blue-accent)' : '1px solid var(--govt-gray-medium)',
                backgroundColor: density === 'comfortable' ? 'var(--govt-blue-light)' : '#ffffff',
                fontSize: '0.825rem',
                fontWeight: density === 'comfortable' ? 700 : 500,
                color: density === 'comfortable' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-title)',
                cursor: 'pointer',
              }}
            >
              Comfortable (Detailed Multi-line)
            </button>
            <button
              type="button"
              onClick={() => setDensity('compact')}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                border: density === 'compact' ? '1.5px solid var(--govt-blue-accent)' : '1px solid var(--govt-gray-medium)',
                backgroundColor: density === 'compact' ? 'var(--govt-blue-light)' : '#ffffff',
                fontSize: '0.825rem',
                fontWeight: density === 'compact' ? 700 : 500,
                color: density === 'compact' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-title)',
                cursor: 'pointer',
              }}
            >
              Compact (High-Velocity Row)
            </button>
          </div>
        </div>

        {/* API Key Provisioner */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <Key size={18} color="var(--govt-blue-primary)" />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              Developer API Keys & Bearer Tokens
            </h3>
          </div>
          <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
            Authenticate programmatic calls from NIC ministries and departmental portal pipelines.
          </p>

          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="text"
              readOnly
              value={apiKey}
              style={{
                flex: 1,
                minWidth: '280px',
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                backgroundColor: 'var(--govt-gray-off-white)',
                border: '1px solid var(--govt-gray-medium)',
                fontFamily: 'monospace',
                fontSize: '0.85rem',
                color: 'var(--govt-gray-title)',
              }}
            />
            <button
              type="button"
              onClick={handleCopyKey}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.5rem 0.85rem',
                borderRadius: '6px',
                border: '1px solid var(--govt-gray-medium)',
                backgroundColor: '#ffffff',
                fontSize: '0.825rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {isCopiedKey ? <Check size={14} color="var(--govt-success)" /> : <Copy size={14} />}
              <span>{isCopiedKey ? 'Copied' : 'Copy Key'}</span>
            </button>
            <button
              type="button"
              onClick={handleGenerateKey}
              style={{
                padding: '0.5rem 0.85rem',
                borderRadius: '6px',
                backgroundColor: 'var(--govt-gray-light)',
                border: '1px solid var(--govt-gray-medium)',
                fontSize: '0.825rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Regenerate
            </button>
          </div>
        </div>

        {/* Real-time Webhook Dispatch Simulator */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <Webhook size={18} color="var(--govt-blue-primary)" />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              Disbursement Gateway Webhook Simulator
            </h3>
          </div>
          <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
            Dispatches instantaneous JSON payloads to departmental gateways upon anomaly triggers or approvals.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', display: 'block', marginBottom: '0.25rem' }}>
                Webhook Endpoint URL:
              </label>
              <input
                type="text"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '6px',
                  border: '1px solid var(--govt-gray-medium)',
                  fontSize: '0.825rem',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
              <select
                value={webhookEvent}
                onChange={(e) => setWebhookEvent(e.target.value)}
                style={{
                  padding: '0.45rem 0.75rem',
                  borderRadius: '6px',
                  border: '1px solid var(--govt-gray-medium)',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                }}
              >
                <option value="evidence.flagged_critical">evidence.flagged_critical</option>
                <option value="evidence.approved">evidence.approved</option>
                <option value="evidence.rejected">evidence.rejected</option>
                <option value="certificate.issued">certificate.issued</option>
              </select>

              <button
                type="button"
                onClick={handleTestWebhook}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.45rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <Play size={14} fill="#ffffff" />
                <span>Dispatch Test Event</span>
              </button>
            </div>

            {webhookResponse && (
              <pre
                style={{
                  margin: '0.5rem 0 0',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  backgroundColor: '#0f172a',
                  color: '#38bdf8',
                  fontFamily: 'monospace',
                  fontSize: '0.75rem',
                  overflowX: 'auto',
                }}
              >
                {webhookResponse}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
