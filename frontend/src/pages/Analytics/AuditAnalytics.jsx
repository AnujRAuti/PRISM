import React, { useState } from 'react';
import { useApp } from '../../context/AppContext';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import {
  BarChart3,
  Award,
  Download,
  Printer,
  QrCode,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Building2,
  FileCheck2,
  MapPin,
  Clock,
  Sparkles,
} from 'lucide-react';

export default function AuditAnalytics() {
  const { evidenceList, projects, addToast } = useApp();

  const approvedEvidence = (evidenceList || []).filter((e) => e.auditStatus === 'APPROVED');
  const [selectedCertId, setSelectedCertId] = useState(
    approvedEvidence[0]?.id || evidenceList?.[0]?.id || 'EVD-2026-8812'
  );

  const certEvidence = (evidenceList || []).find((e) => e.id === selectedCertId) || evidenceList?.[0] || {
    id: 'EVD-2026-8812',
    projectId: 'PRJ-PMGSY-MH-401',
    integrityScore: 94,
    auditStatus: 'APPROVED',
    sha256: '9f83a48e71b29d8164bc77f202e88a014902cd51772183e89f8a31362e08c491',
    modelVersion: 'eiil-vision-v2.4-pmgsy',
    location: { lat: 18.2814, lng: 74.0156, accuracyMeters: 4.2 },
  };

  const certProject = (projects || []).find((p) => p.id === certEvidence.projectId) || projects?.[0] || {
    name: 'Purandar Taluka Rural Bitumen Road Reconstruction',
    scheme: 'PMGSY (Rural Roads)',
    block: 'Purandar',
    district: 'Pune',
    state: 'Maharashtra',
    contractor: 'Sahyadri Infrastructure Ltd.',
  };

  const handlePrintCertificate = () => {
    window.print();
    addToast({
      title: 'Certificate Print Dialog Opened',
      description: 'Document ready for official archival printing or PDF export.',
      type: 'info',
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
              Program Analytics & Evidence Integrity Certificates
            </h1>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '4px',
                backgroundColor: 'rgba(5, 150, 105, 0.12)',
                color: 'var(--govt-success, #059669)',
                fontWeight: 700,
              }}
            >
              Statutory Provenance (Section 86)
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
            Institutional verification metrics and tamper-proof Evidence Integrity Certificates for milestone disbursement clearance.
          </p>
        </div>

        <button
          type="button"
          onClick={handlePrintCertificate}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.5rem 1rem',
            borderRadius: '6px',
            backgroundColor: 'var(--govt-blue-primary)',
            color: '#ffffff',
            fontSize: '0.825rem',
            fontWeight: 700,
            border: 'none',
            cursor: 'pointer',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <Printer size={15} />
          <span>Print / Save Certificate PDF</span>
        </button>
      </div>

      {/* Top Analytics Summary Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}
      >
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: '8px',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', display: 'block' }}>
            Cross-District Duplicate Prevention
          </span>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', margin: '0.35rem 0' }}>
            <span style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--govt-blue-dark)', fontFamily: 'monospace' }}>
              99.2%
            </span>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-success)' }}>
              14/14 Caught
            </span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
            Near-duplicate perceptual embeddings intercepted before intake
          </span>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: '8px',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', display: 'block' }}>
            Average Reviewer Turnaround
          </span>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', margin: '0.35rem 0' }}>
            <span style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--govt-blue-dark)', fontFamily: 'monospace' }}>
              4.2h
            </span>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-success)' }}>
              -68% vs baseline
            </span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
            Triage queue prioritized by AI risk score & impossible travel flags
          </span>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: '8px',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', display: 'block' }}>
            Certificates Issued This Quarter
          </span>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', margin: '0.35rem 0' }}>
            <span style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--govt-blue-dark)', fontFamily: 'monospace' }}>
              842
            </span>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-blue-primary)' }}>
              Cryptographically Signed
            </span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
            Disbursement audit certificates legally tied to Section 86
          </span>
        </div>
      </div>

      {/* Main Certificate Section */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            marginBottom: '1rem',
          }}
        >
          <h2 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            Official Evidence Integrity Certificate (Sample Generator)
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
            <span style={{ color: 'var(--govt-gray-dark)', fontWeight: 600 }}>Select Evidence Item:</span>
            <select
              value={selectedCertId}
              onChange={(e) => setSelectedCertId(e.target.value)}
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
              {(evidenceList || []).map((e) => (
                <option key={e.id} value={e.id}>
                  {e.id} • Score: {e.integrityScore}% ({e.auditStatus})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Printable Institutional Certificate Box */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '2px solid var(--govt-gray-medium, #cbd5e1)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '2.5rem',
            boxShadow: 'var(--shadow-md)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {/* Subtle Top Accent Band */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: '4px',
              background: 'linear-gradient(90deg, #f59e0b 33%, #ffffff 33%, #ffffff 66%, #10b981 66%)',
            }}
          />

          {/* Certificate Header Lockup */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1.5rem',
              borderBottom: '1px solid var(--govt-gray-medium)',
              paddingBottom: '1.5rem',
              marginBottom: '1.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '10px',
                  backgroundColor: '#0f172a',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <img
                  src="/prism-symbol-transparent.png"
                  alt="National Seal"
                  style={{ width: '32px', height: '32px', objectFit: 'contain' }}
                />
              </div>
              <div>
                <span
                  style={{
                    fontSize: '0.75rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    fontWeight: 700,
                    color: 'var(--govt-gray-dark)',
                    display: 'block',
                  }}
                >
                  GOVERNMENT OF INDIA • DIGITAL PUBLIC INFRASTRUCTURE
                </span>
                <h3
                  style={{
                    margin: '0.2rem 0',
                    fontSize: '1.25rem',
                    fontWeight: 700,
                    color: 'var(--govt-blue-dark)',
                  }}
                >
                  Official Certificate of Evidence Integrity (EIIL)
                </h3>
                <span style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                  Statutory Audit Record pursuant to Public Works Oversight Guidelines (Section 86)
                </span>
              </div>
            </div>

            <div style={{ textAlign: 'right', fontFamily: 'monospace', fontSize: '0.8rem' }}>
              <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.7rem', display: 'block' }}>
                CERTIFICATE SERIAL NO:
              </span>
              <span style={{ fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                EIIL-CERT-2026-{certEvidence.id?.replace('EVD-', '')}
              </span>
              <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.7rem', display: 'block', marginTop: '0.2rem' }}>
                ISSUED: {new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
              </span>
            </div>
          </div>

          {/* Certificate Body Columns */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.5rem' }}>
            {/* Column 1: Asset & Scheme Details */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8rem' }}>
              <h4
                style={{
                  margin: 0,
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: 'var(--govt-gray-dark)',
                  borderBottom: '1px solid var(--govt-gray-medium)',
                  paddingBottom: '0.35rem',
                }}
              >
                Asset & Scheme Dossier
              </h4>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Scheme Track:</span>
                <span style={{ fontWeight: 600, color: 'var(--govt-blue-primary)' }}>{certProject.scheme}</span>
              </div>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Project Name:</span>
                <span style={{ fontWeight: 600, color: 'var(--govt-gray-title)' }}>{certProject.name}</span>
              </div>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Location:</span>
                <span style={{ fontWeight: 500 }}>{certProject.block}, {certProject.district}, {certProject.state}</span>
              </div>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Contractor Entity:</span>
                <span style={{ fontWeight: 500 }}>{certProject.contractor}</span>
              </div>
            </div>

            {/* Column 2: Cryptographic Provenance */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8rem' }}>
              <h4
                style={{
                  margin: 0,
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: 'var(--govt-gray-dark)',
                  borderBottom: '1px solid var(--govt-gray-medium)',
                  paddingBottom: '0.35rem',
                }}
              >
                Cryptographic Provenance
              </h4>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>SHA-256 Digest:</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600, wordBreak: 'break-all', fontSize: '0.75rem' }}>
                  {certEvidence.sha256}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Captured Coordinates:</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                  {certEvidence.location?.lat?.toFixed(4)}° N, {certEvidence.location?.lng?.toFixed(4)}° E (±{certEvidence.location?.accuracyMeters}m)
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>AI Model Version:</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>{certEvidence.modelVersion}</span>
              </div>
            </div>

            {/* Column 3: Integrity Score & Determination */}
            <div
              style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: '8px',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                textAlign: 'center',
                gap: '0.75rem',
              }}
            >
              <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--govt-gray-dark)' }}>
                Audit Determination Index
              </span>
              <IntegrityArc score={certEvidence.integrityScore} size="md" showRiskBadge />
              <div style={{ fontSize: '0.8rem', fontWeight: 700 }}>
                {certEvidence.auditStatus === 'APPROVED' ? (
                  <span style={{ color: 'var(--govt-success)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    <CheckCircle2 size={16} /> Approved for Milestone Release
                  </span>
                ) : (
                  <span style={{ color: 'var(--govt-danger)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    <AlertTriangle size={16} /> Under Audit Investigation
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Certificate Sign-Off Footer */}
          <div
            style={{
              marginTop: '2rem',
              paddingTop: '1.5rem',
              borderTop: '1px solid var(--govt-gray-medium)',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <div
                style={{
                  width: '64px',
                  height: '64px',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '4px',
                }}
              >
                <QrCode size={48} color="var(--govt-gray-title)" />
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                <span style={{ fontWeight: 700, color: 'var(--govt-gray-title)', display: 'block' }}>
                  VERIFIABLE DIGITAL SEAL
                </span>
                <span>Scan QR code to verify immutable cryptographic block on the National EIIL Node.</span>
              </div>
            </div>

            <div style={{ textAlign: 'right', fontSize: '0.8rem' }}>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-blue-dark)', display: 'block' }}>
                DIGITALLY SIGNED & CLEARED
              </span>
              <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.75rem' }}>
                Public Works Quality Assurance Division • NIC National Cloud
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
