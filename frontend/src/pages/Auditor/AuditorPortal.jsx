import React, { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import IntegrityArc from '../../components/ui/IntegrityArc';
import {
  ShieldCheck,
  Award,
  CheckCircle2,
  FileText,
  Search,
  ExternalLink,
  Printer,
  Copy,
  Check,
  AlertTriangle,
  QrCode,
  Hash,
  ArrowRight,
  Database,
  Lock
} from 'lucide-react';

export default function AuditorPortal() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') || 'compliance';
  const [activeTab, setActiveTab] = useState(initialTab);

  const { evidenceList, auditEvents, verifyHashInLedger, currentUser } = useApp();

  // Certificate selection
  const approvedItems = evidenceList.filter((e) => e.auditStatus === 'APPROVED' || e.integrityScore >= 80);
  const [selectedCertId, setSelectedCertId] = useState(approvedItems[0]?.id || evidenceList[0]?.id);
  const selectedEvidence = evidenceList.find((e) => e.id === selectedCertId) || evidenceList[0];

  // Hash Verifier state
  const [inputHash, setInputHash] = useState(selectedEvidence?.sha256 || '');
  const [verificationResult, setVerificationResult] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [copiedHash, setCopiedHash] = useState(false);

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && ['compliance', 'certificates', 'verifier', 'anomalies'].includes(tab)) {
      setActiveTab(tab);
    }
  }, [searchParams]);

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  const handleVerify = (e) => {
    if (e) e.preventDefault();
    if (!inputHash) return;

    setVerifying(true);
    setTimeout(() => {
      const res = verifyHashInLedger(inputHash);
      setVerificationResult(res);
      setVerifying(false);
    }, 400);
  };

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', paddingBottom: '3rem' }}>
      {/* GovTech Statutory Header */}
      <div
        style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.5rem 2rem',
          marginBottom: '1.5rem',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.4rem' }}>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  color: 'var(--govt-blue-dark)',
                  backgroundColor: 'rgba(30, 41, 59, 0.08)',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '999px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                }}
              >
                <Award size={14} /> Section 86 Statutory Provenance Directorate
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                • Office of the Principal Auditor & CAG Quality Vigilance
              </span>
            </div>
            <h1 style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--govt-blue-dark)', margin: 0 }}>
              Statutory Evidence Audit & Compliance Suite
            </h1>
            <p style={{ margin: '0.4rem 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
              Independent cryptographic verification, Section 86 disbursement certificates, and Section 58 non-repudiation ledger oversight.
            </p>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.85rem',
              backgroundColor: 'var(--govt-gray-off-white)',
              padding: '0.6rem 1rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                {currentUser?.name || 'Dr. Anand Swaroop'}
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>
                Principal Statutory Auditor (CAG)
              </div>
            </div>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                backgroundColor: 'var(--govt-blue-dark)',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 700,
                fontSize: '0.9rem',
              }}
            >
              ⚖️
            </div>
          </div>
        </div>

        {/* Tab Controls */}
        <div
          style={{
            display: 'flex',
            gap: '0.75rem',
            marginTop: '1.5rem',
            borderTop: '1px solid var(--govt-gray-medium)',
            paddingTop: '1.25rem',
          }}
        >
          <button
            type="button"
            onClick={() => handleTabChange('compliance')}
            style={{
              padding: '0.6rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              fontWeight: activeTab === 'compliance' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              border: 'none',
              backgroundColor: activeTab === 'compliance' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-off-white)',
              color: activeTab === 'compliance' ? '#ffffff' : 'var(--govt-gray-dark)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <ShieldCheck size={16} /> 1. Compliance Analytics
          </button>

          <button
            type="button"
            onClick={() => handleTabChange('certificates')}
            style={{
              padding: '0.6rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              fontWeight: activeTab === 'certificates' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              border: 'none',
              backgroundColor: activeTab === 'certificates' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-off-white)',
              color: activeTab === 'certificates' ? '#ffffff' : 'var(--govt-gray-dark)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <Award size={16} /> 2. Section 86 Certificates ({approvedItems.length})
          </button>

          <button
            type="button"
            onClick={() => handleTabChange('verifier')}
            style={{
              padding: '0.6rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              fontWeight: activeTab === 'verifier' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              border: 'none',
              backgroundColor: activeTab === 'verifier' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-off-white)',
              color: activeTab === 'verifier' ? '#ffffff' : 'var(--govt-gray-dark)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <Hash size={16} /> 3. Section 58 Hash Verifier
          </button>

          <button
            type="button"
            onClick={() => handleTabChange('anomalies')}
            style={{
              padding: '0.6rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              fontWeight: activeTab === 'anomalies' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              border: 'none',
              backgroundColor: activeTab === 'anomalies' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-off-white)',
              color: activeTab === 'anomalies' ? '#ffffff' : 'var(--govt-gray-dark)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <AlertTriangle size={16} /> 4. Cross-Scheme Anomaly Registry
          </button>
        </div>
      </div>

      {/* TAB 1: COMPLIANCE OVERVIEW */}
      {activeTab === 'compliance' && (
        <div>
          {/* Metrics row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.25rem', marginBottom: '1.5rem' }}>
            <div style={{ backgroundColor: 'var(--govt-white)', padding: '1.5rem', borderRadius: 'var(--radius-lg)', border: '1px solid var(--govt-gray-medium)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', fontWeight: 700, textTransform: 'uppercase' }}>
                Cross-District Duplicate Interception
              </div>
              <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--govt-success)', margin: '0.5rem 0' }}>
                99.2%
              </div>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                14 of 14 cross-project recycled photos intercepted before payment clearance.
              </p>
            </div>

            <div style={{ backgroundColor: 'var(--govt-white)', padding: '1.5rem', borderRadius: 'var(--radius-lg)', border: '1px solid var(--govt-gray-medium)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', fontWeight: 700, textTransform: 'uppercase' }}>
                Average Reviewer Turnaround
              </div>
              <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--govt-blue-primary)', margin: '0.5rem 0' }}>
                4.2 hours
              </div>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                -68% faster than paper inspection tranches via AI risk triage queue.
              </p>
            </div>

            <div style={{ backgroundColor: 'var(--govt-white)', padding: '1.5rem', borderRadius: 'var(--radius-lg)', border: '1px solid var(--govt-gray-medium)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', fontWeight: 700, textTransform: 'uppercase' }}>
                Statutory Certificates Cleared
              </div>
              <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--govt-blue-dark)', margin: '0.5rem 0' }}>
                842
              </div>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                Legally tied to Section 86 Public Works Oversight and disbursement ledgers.
              </p>
            </div>
          </div>

          {/* Scheme-wise Audit Breakdown */}
          <div
            style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--govt-gray-medium)',
              padding: '1.5rem',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--govt-blue-dark)', margin: '0 0 1rem 0' }}>
              Statutory Scheme Integrity & Disbursement Status
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {[
                { name: 'Pradhan Mantri Gram Sadak Yojana (PMGSY)', code: 'PRJ-PMGSY-MH-401', score: 94, state: 'CLEARED', budget: '₹3.45 Cr', note: 'Bitumen homography and compaction verified.' },
                { name: 'Jal Jeevan Mission (Har Ghar Jal)', code: 'PRJ-JJM-RJ-108', score: 28, state: 'CRITICAL_HOLD', budget: '₹1.82 Cr', note: 'Recycled solar pump detected from Jodhpur district (94.7% vector match).' },
                { name: 'Samagra Shiksha Abhiyan (School Repairs)', code: 'PRJ-SSA-UP-512', score: 41, state: 'INVESTIGATION', budget: '₹0.46 Cr', note: 'Impossible travel velocity flagged between Varanasi and Prayagraj.' },
                { name: 'PM-KUSUM Feeder Level Solarization', code: 'PRJ-KUSUM-KA-204', score: 82, state: 'CLEARED', budget: '₹1.65 Cr', note: 'Earthing pit and 12-panel array verified against geofence.' },
              ].map((sch) => (
                <div
                  key={sch.code}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '1rem',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--govt-gray-medium)',
                    backgroundColor: sch.state === 'CRITICAL_HOLD' ? 'rgba(239, 68, 68, 0.04)' : 'var(--govt-gray-off-white)',
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.2rem' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, fontFamily: 'var(--font-family-mono)', color: 'var(--govt-gray-dark)' }}>
                        {sch.code}
                      </span>
                      <strong style={{ fontSize: '0.9rem', color: 'var(--govt-blue-dark)' }}>{sch.name}</strong>
                    </div>
                    <div style={{ fontSize: '0.775rem', color: 'var(--govt-gray-dark)' }}>
                      Budget: <strong>{sch.budget}</strong> • Audit Note: {sch.note}
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <div style={{ textAlign: 'center' }}>
                      <span
                        style={{
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          padding: '0.25rem 0.65rem',
                          borderRadius: '999px',
                          backgroundColor:
                            sch.state === 'CLEARED'
                              ? 'rgba(22, 101, 52, 0.1)'
                              : sch.state === 'CRITICAL_HOLD'
                              ? 'rgba(239, 68, 68, 0.1)'
                              : 'rgba(234, 88, 12, 0.1)',
                          color:
                            sch.state === 'CLEARED'
                              ? 'var(--govt-success)'
                              : sch.state === 'CRITICAL_HOLD'
                              ? 'var(--govt-danger)'
                              : 'var(--govt-warning)',
                        }}
                      >
                        {sch.state === 'CLEARED' ? '✓ Section 86 Cleared' : sch.state === 'CRITICAL_HOLD' ? '⛔ Disbursement Held' : '⚠️ Pending Re-Inspection'}
                      </span>
                    </div>

                    <Link
                      to={`/projects/${sch.code}`}
                      style={{
                        padding: '0.45rem 0.85rem',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--govt-gray-medium)',
                        backgroundColor: '#fff',
                        color: 'var(--govt-blue-dark)',
                        fontSize: '0.775rem',
                        fontWeight: 600,
                        textDecoration: 'none',
                      }}
                    >
                      Audit Record →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: SECTION 86 CERTIFICATES */}
      {activeTab === 'certificates' && (
        <div>
          {/* Certificate Selection Bar */}
          <div
            style={{
              backgroundColor: 'var(--govt-white)',
              padding: '1rem 1.5rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
              marginBottom: '1.25rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <label style={{ fontSize: '0.825rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                Select Cleared Evidence Item:
              </label>
              <select
                value={selectedCertId}
                onChange={(e) => setSelectedCertId(e.target.value)}
                style={{
                  padding: '0.5rem 0.85rem',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--govt-gray-medium)',
                  fontSize: '0.825rem',
                  backgroundColor: '#fff',
                }}
              >
                {approvedItems.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.id} • {e.projectName} (Score: {e.integrityScore}%)
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={handlePrint}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.55rem 1.15rem',
                backgroundColor: 'var(--govt-blue-primary)',
                color: '#fff',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.825rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              <Printer size={16} /> Print / Export Certificate PDF
            </button>
          </div>

          {/* Official Printable Certificate Document */}
          <div
            id="statutory-certificate"
            style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              border: '2px solid var(--govt-blue-dark)',
              padding: '2.5rem',
              boxShadow: 'var(--shadow-md)',
              position: 'relative',
            }}
          >
            {/* Top Ornamental Header */}
            <div style={{ textAlign: 'center', borderBottom: '2px double var(--govt-gray-medium)', paddingBottom: '1.5rem', marginBottom: '1.75rem' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--govt-gray-dark)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                GOVERNMENT OF INDIA • DIGITAL PUBLIC INFRASTRUCTURE
              </div>
              <h2 style={{ fontSize: '1.6rem', fontWeight: 900, color: 'var(--govt-blue-dark)', margin: '0.35rem 0 0.25rem 0' }}>
                Official Certificate of Evidence Integrity (EIIL)
              </h2>
              <div style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                Issued pursuant to Statutory Public Works Quality Oversight Guidelines (Section 86)
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '2rem', marginBottom: '2rem' }}>
              <div>
                <h4 style={{ fontSize: '0.8rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--govt-gray-dark)', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>
                  Asset & Scheme Dossier
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '0.5rem', fontSize: '0.825rem' }}>
                  <span style={{ color: 'var(--govt-gray-dark)' }}>Scheme:</span>
                  <strong style={{ color: 'var(--govt-blue-primary)' }}>{selectedEvidence?.scheme}</strong>

                  <span style={{ color: 'var(--govt-gray-dark)' }}>Project Name:</span>
                  <strong style={{ color: 'var(--govt-blue-dark)' }}>{selectedEvidence?.projectName}</strong>

                  <span style={{ color: 'var(--govt-gray-dark)' }}>Evidence ID:</span>
                  <span style={{ fontFamily: 'var(--font-family-mono)', fontWeight: 700 }}>{selectedEvidence?.id}</span>

                  <span style={{ color: 'var(--govt-gray-dark)' }}>Jurisdiction:</span>
                  <span>{selectedEvidence?.district}, {selectedEvidence?.state}</span>

                  <span style={{ color: 'var(--govt-gray-dark)' }}>Captured At:</span>
                  <span>{selectedEvidence?.captureDate}</span>
                </div>
              </div>

              <div>
                <h4 style={{ fontSize: '0.8rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--govt-gray-dark)', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>
                  Cryptographic Provenance
                </h4>
                <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '0.85rem', borderRadius: 'var(--radius-md)', fontSize: '0.75rem', fontFamily: 'var(--font-family-mono)' }}>
                  <div style={{ color: 'var(--govt-gray-dark)', marginBottom: '0.25rem' }}>SHA-256 Binary Digest:</div>
                  <div style={{ wordBreak: 'break-all', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                    {selectedEvidence?.sha256}
                  </div>
                  <div style={{ marginTop: '0.5rem', color: 'var(--govt-success)', fontWeight: 700 }}>
                    ✓ Hardware Camera Sensor Seal Validated
                  </div>
                </div>
              </div>
            </div>

            {/* Evidence Image Preview */}
            <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
              <img
                src={selectedEvidence?.photoUrl}
                alt="Verified Milestone Evidence"
                style={{ maxHeight: '240px', borderRadius: 'var(--radius-md)', border: '1px solid var(--govt-gray-medium)', objectFit: 'cover' }}
              />
              <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', marginTop: '0.4rem' }}>
                Figure: Milestone Evidence Photo Registered under Geofence Bounds ({selectedEvidence?.location})
              </div>
            </div>

            {/* Signatures & Seal Footer */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-end',
                borderTop: '1px solid var(--govt-gray-medium)',
                paddingTop: '1.5rem',
              }}
            >
              <div>
                <div style={{ width: '80px', height: '80px', border: '1px dashed var(--govt-gray-medium)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '0.4rem' }}>
                  <QrCode size={56} style={{ color: 'var(--govt-blue-dark)' }} />
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>Scan to verify on NIC portal</div>
              </div>

              <div style={{ textAlign: 'center' }}>
                <div style={{ borderBottom: '1px solid var(--govt-gray-dark)', width: '180px', height: '40px', marginBottom: '0.4rem' }}>
                  <span style={{ fontSize: '0.85rem', fontFamily: 'cursive', color: 'var(--govt-blue-dark)', display: 'block', paddingTop: '15px' }}>
                    Dr. Anand Swaroop
                  </span>
                </div>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>Principal Statutory Auditor</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>Comptroller and Auditor General Directorate</div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <span
                  style={{
                    display: 'inline-block',
                    padding: '0.4rem 0.85rem',
                    backgroundColor: 'rgba(22, 101, 52, 0.1)',
                    border: '1px solid var(--govt-success)',
                    color: 'var(--govt-success)',
                    fontWeight: 800,
                    fontSize: '0.85rem',
                    borderRadius: '4px',
                  }}
                >
                  DISBURSEMENT CLEARED
                </span>
                <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', marginTop: '0.35rem' }}>
                  Certificate ID: EIIL-CERT-2026-{selectedEvidence?.id}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: SECTION 58 HASH VERIFIER */}
      {activeTab === 'verifier' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '1.5rem' }}>
          <div
            style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--govt-gray-medium)',
              padding: '1.75rem',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <span style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)', color: 'var(--govt-blue-primary)', padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 700 }}>
                NON-REPUDIATION VERIFIER
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>Pursuant to Section 58 Cryptographic Proof</span>
            </div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--govt-blue-dark)', margin: '0 0 1rem 0' }}>
              Verify Binary Hash Against Chained Ledger
            </h2>

            <form onSubmit={handleVerify}>
              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                  Input SHA-256 Digest or Evidence ID:
                </label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input
                    type="text"
                    value={inputHash}
                    onChange={(e) => setInputHash(e.target.value)}
                    placeholder="e.g. 9f83a48e71b29d8164bc77f202e88a014902cd51772183e89f8a31362e08c491"
                    style={{
                      flex: 1,
                      padding: '0.65rem 0.85rem',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--govt-gray-medium)',
                      fontSize: '0.825rem',
                      fontFamily: 'var(--font-family-mono)',
                    }}
                  />
                  <button
                    type="submit"
                    disabled={verifying}
                    style={{
                      padding: '0.65rem 1.25rem',
                      backgroundColor: 'var(--govt-blue-primary)',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 'var(--radius-md)',
                      fontWeight: 700,
                      fontSize: '0.85rem',
                      cursor: verifying ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {verifying ? 'Computing...' : 'Verify Hash'}
                  </button>
                </div>
              </div>
            </form>

            {/* Preset quick test buttons */}
            <div style={{ marginBottom: '1.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block', marginBottom: '0.4rem' }}>
                Or select an active benchmark evidence hash:
              </span>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {evidenceList.slice(0, 3).map((e) => (
                  <button
                    key={e.id}
                    type="button"
                    onClick={() => {
                      setInputHash(e.sha256);
                      const res = verifyHashInLedger(e.sha256);
                      setVerificationResult(res);
                    }}
                    style={{
                      fontSize: '0.725rem',
                      padding: '0.35rem 0.65rem',
                      borderRadius: '4px',
                      border: '1px solid var(--govt-gray-medium)',
                      backgroundColor: 'var(--govt-gray-off-white)',
                      cursor: 'pointer',
                    }}
                  >
                    {e.id} ({e.scheme.split(' ')[0]})
                  </button>
                ))}
              </div>
            </div>

            {/* Verification Result Output */}
            {verificationResult && (
              <div
                style={{
                  backgroundColor: verificationResult.verified ? 'rgba(22, 101, 52, 0.05)' : 'rgba(239, 68, 68, 0.05)',
                  border: `1.5px solid ${verificationResult.verified ? 'var(--govt-success)' : 'var(--govt-danger)'}`,
                  borderRadius: 'var(--radius-md)',
                  padding: '1.25rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  {verificationResult.verified ? (
                    <>
                      <CheckCircle2 size={20} style={{ color: 'var(--govt-success)' }} />
                      <strong style={{ fontSize: '0.95rem', color: 'var(--govt-success)' }}>
                        Cryptographic Non-Repudiation Verified (Tamper-Free)
                      </strong>
                    </>
                  ) : (
                    <>
                      <AlertTriangle size={20} style={{ color: 'var(--govt-danger)' }} />
                      <strong style={{ fontSize: '0.95rem', color: 'var(--govt-danger)' }}>
                        Hash Not Found in Ledger
                      </strong>
                    </>
                  )}
                </div>

                <div style={{ fontSize: '0.8rem', display: 'grid', gridTemplateColumns: '140px 1fr', gap: '0.4rem' }}>
                  <span style={{ color: 'var(--govt-gray-dark)' }}>Status:</span>
                  <strong>{verificationResult.status}</strong>

                  <span style={{ color: 'var(--govt-gray-dark)' }}>Target Hash:</span>
                  <span style={{ fontFamily: 'var(--font-family-mono)', wordBreak: 'break-all' }}>
                    {verificationResult.hash}
                  </span>

                  {verificationResult.verified && (
                    <>
                      <span style={{ color: 'var(--govt-gray-dark)' }}>Evidence ID:</span>
                      <strong>{verificationResult.evidenceId}</strong>

                      <span style={{ color: 'var(--govt-gray-dark)' }}>Project:</span>
                      <span>{verificationResult.projectName}</span>

                      <span style={{ color: 'var(--govt-gray-dark)' }}>Ledger Ingestion:</span>
                      <span>{verificationResult.timestamp}</span>

                      <span style={{ color: 'var(--govt-gray-dark)' }}>Actor:</span>
                      <span>{verificationResult.actor}</span>

                      <span style={{ color: 'var(--govt-gray-dark)' }}>Merkle Root:</span>
                      <span style={{ fontFamily: 'var(--font-family-mono)', fontSize: '0.75rem' }}>
                        {verificationResult.merkleRoot}
                      </span>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>

          <div>
            <div
              style={{
                backgroundColor: 'var(--govt-white)',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--govt-gray-medium)',
                padding: '1.5rem',
              }}
            >
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)', margin: '0 0 0.85rem 0' }}>
                Section 58 Legal Standards
              </h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)', lineHeight: 1.5, margin: '0 0 1rem 0' }}>
                Under Section 58 of the Public Records Evidence Act, cryptographic hashing performed at point of mobile capture creates a statutory presumption of integrity.
              </p>
              <div
                style={{
                  backgroundColor: 'var(--govt-gray-off-white)',
                  padding: '0.85rem',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.775rem',
                }}
              >
                <div style={{ fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.25rem' }}>
                  Chaining Invariant:
                </div>
                <code style={{ fontSize: '0.725rem', color: 'var(--govt-gray-dark)' }}>
                  Hash_N = SHA256(Block_N || Hash_(N-1) || Actor || Payload)
                </code>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: CROSS-SCHEME ANOMALY REGISTRY */}
      {activeTab === 'anomalies' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {evidenceList.filter((e) => e.auditStatus === 'FLAGGED' || e.riskLevel === 'CRITICAL' || e.riskLevel === 'HIGH').map((anom) => (
            <div
              key={anom.id}
              style={{
                backgroundColor: 'var(--govt-white)',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--govt-gray-medium)',
                padding: '1.25rem 1.5rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '1rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
                <img
                  src={anom.photoUrl}
                  alt="Anomaly thumbnail"
                  style={{ width: '80px', height: '80px', borderRadius: 'var(--radius-md)', objectFit: 'cover' }}
                />
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.2rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, fontFamily: 'var(--font-family-mono)', color: 'var(--govt-danger)' }}>
                      {anom.id}
                    </span>
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, backgroundColor: 'rgba(239, 68, 68, 0.1)', color: 'var(--govt-danger)', padding: '0.15rem 0.5rem', borderRadius: '999px' }}>
                      {anom.riskLevel} ANOMALY
                    </span>
                  </div>
                  <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)', margin: '0 0 0.25rem 0' }}>
                    {anom.title}
                  </h4>
                  <p style={{ margin: 0, fontSize: '0.775rem', color: 'var(--govt-gray-dark)' }}>
                    {anom.findings}
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--govt-danger)' }}>
                    {anom.integrityScore}%
                  </div>
                  <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>Integrity Score</span>
                </div>

                <Link
                  to={`/evidence/${anom.id}`}
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: 'var(--govt-blue-primary)',
                    color: '#fff',
                    borderRadius: 'var(--radius-md)',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    textDecoration: 'none',
                  }}
                >
                  Audit Dossier →
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
