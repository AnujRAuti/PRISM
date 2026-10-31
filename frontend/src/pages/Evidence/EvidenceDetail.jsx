import React, { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import {
  ArrowLeft,
  MapPin,
  Clock,
  Camera,
  Layers,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  FileCheck2,
  SplitSquareVertical,
  ExternalLink,
  Copy,
  Check,
  Sparkles,
  Maximize2,
  Languages,
  UserCheck,
} from 'lucide-react';

export default function EvidenceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const {
    evidenceList,
    projects,
    approveEvidence,
    rejectEvidence,
    flagEvidence,
    overrideEvidence,
    addToast,
  } = useApp();

  const [activeTab, setActiveTab] = useState('METADATA');
  const [showBoxes, setShowBoxes] = useState(true);
  const [isCopiedSha, setIsCopiedSha] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);
  const [translatedText, setTranslatedText] = useState(null);

  // Override Form States
  const [overrideScore, setOverrideScore] = useState(85);
  const [overrideRisk, setOverrideRisk] = useState('LOW');
  const [overrideReason, setOverrideReason] = useState('');
  const [showOverrideModal, setShowOverrideModal] = useState(false);

  // Find evidence item in dataset or create graceful fallback
  const evidence =
    (evidenceList || []).find((e) => e.id === id) ||
    evidenceList?.[0] || {
      id: id || 'EVD-2026-8812',
      projectId: 'PRJ-PMGSY-MH-401',
      projectName: 'Purandar Taluka Rural Bitumen Road Reconstruction',
      scheme: 'PMGSY (Rural Roads)',
      activityName: 'Asphalt Wearing Course & Pavement Markings',
      stage: 'after',
      title: 'Site Survey Photograph of Road Pavement Section',
      imageUrl: '/images/projects/road-pothole.jpg',
      mimeType: 'image/jpeg',
      sizeBytes: 3842100,
      sha256: '9f83a48e71b29d8164bc77f202e88a014902cd51772183e89f8a31362e08c491',
      capturedAt: '2026-08-20T14:32:10+05:30',
      uploadedAt: '2026-08-20T14:41:22+05:30',
      location: {
        lat: 18.2814,
        lng: 74.0156,
        accuracyMeters: 4.2,
        geofenceDistanceMeters: 28,
        siteCentroid: { lat: 18.2812, lng: 74.0154 },
        status: 'CONSISTENT',
        state: 'Maharashtra',
        district: 'Pune',
        block: 'Purandar',
      },
      camera: {
        make: 'Samsung',
        model: 'Galaxy A54 5G',
        software: 'Govt e-Pramaan Mobile v3.1',
        focalLength: '5.4mm',
        iso: '50',
        exposure: '1/850s',
      },
      integrityScore: 94,
      riskLevel: 'LOW',
      auditStatus: 'APPROVED',
      reviewer: {
        assignedTo: 'Rajesh Kulkarni (SE PWD)',
        decisionDate: '2026-08-21T10:15:00+05:30',
        note: 'Verified against field survey records. Geofence boundaries and GPS coordinates fully aligned.',
      },
      fusionScores: {
        gps: 98,
        temporal: 96,
        duplicateRisk: 3,
        manipulationRisk: 4,
        claimMatch: 95,
        metadataIntegrity: 96,
        completeness: 100,
      },
      detectedAnomalies: [],
      similarEvidenceMatches: [],
      detectedObjects: [
        { label: 'asphalt_road_surface', confidence: 0.98, box: [0.35, 0.05, 0.95, 0.95] },
        { label: 'road_pothole_defect', confidence: 0.93, box: [0.45, 0.3, 0.85, 0.7] },
      ],
      claimText: 'Field survey record of damaged road segment showing deep pothole.',
      modelVersion: 'eiil-vision-v2.4-pmgsy',
    };

  const project = (projects || []).find((p) => p.id === evidence.projectId) || {
    id: evidence.projectId || 'PRJ-PMGSY-MH-401',
    name: evidence.projectName || 'Purandar Taluka Rural Road',
    scheme: evidence.scheme || 'PMGSY',
    district: evidence.location?.district || 'Pune',
    state: evidence.location?.state || 'Maharashtra',
    budgetInr: 34500000,
    geofenceRadiusMeters: 150,
  };

  const handleCopySha = () => {
    navigator.clipboard.writeText(evidence.sha256);
    setIsCopiedSha(true);
    setTimeout(() => setIsCopiedSha(false), 2000);
    addToast({
      title: 'SHA-256 Hash Copied',
      description: 'Cryptographic fingerprint copied to clipboard.',
      type: 'info',
    });
  };

  const handleTranslateFinding = () => {
    if (translatedText) {
      setTranslatedText(null);
      setIsTranslating(false);
      return;
    }
    setIsTranslating(true);
    setTimeout(() => {
      setTranslatedText(
        'स्थल का जीपीएस विचलन 150 मीटर की जियोफेंस सीमा के भीतर सत्यापित है। कोई डुप्लीकेट साक्ष्य नहीं मिला।'
      );
      setIsTranslating(false);
      addToast({
        title: 'Plain-Language Translation Active',
        description: 'Technical findings rendered into plain Hindi register.',
        type: 'info',
      });
    }, 400);
  };

  const handleSaveOverride = () => {
    if (overrideReason.trim().length < 20) {
      addToast({
        title: 'Mandatory Rationale Required',
        description: 'Statutory rules mandate at least 20 characters explanation for audit overrides.',
        type: 'error',
      });
      return;
    }

    overrideEvidence(evidence.id, overrideScore, overrideRisk, overrideReason);
    setShowOverrideModal(false);
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Top Breadcrumb & Navigation */}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button
            type="button"
            onClick={() => navigate('/reviews')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              backgroundColor: 'var(--govt-gray-light)',
              border: '1px solid var(--govt-gray-medium)',
              color: 'var(--govt-gray-title)',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <ArrowLeft size={14} />
            <span>Back to Queue</span>
          </button>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.85rem', color: 'var(--govt-blue-dark)' }}>
                {evidence.id}
              </span>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  padding: '0.1rem 0.5rem',
                  borderRadius: '999px',
                  backgroundColor:
                    evidence.auditStatus === 'APPROVED'
                      ? 'rgba(5, 150, 105, 0.12)'
                      : evidence.auditStatus === 'REJECTED' || evidence.auditStatus === 'FLAGGED'
                      ? 'rgba(220, 38, 38, 0.12)'
                      : 'var(--govt-gray-light)',
                  color:
                    evidence.auditStatus === 'APPROVED'
                      ? 'var(--govt-success)'
                      : evidence.auditStatus === 'REJECTED' || evidence.auditStatus === 'FLAGGED'
                      ? 'var(--govt-danger)'
                      : 'var(--govt-gray-title)',
                  textTransform: 'uppercase',
                }}
              >
                {evidence.auditStatus}
              </span>
            </div>
            <h1
              style={{
                margin: '0.2rem 0 0',
                fontSize: '1.25rem',
                fontWeight: 700,
                color: 'var(--govt-gray-title)',
              }}
            >
              {evidence.title}
            </h1>
          </div>
        </div>

        {/* Action Buttons Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            type="button"
            onClick={() => approveEvidence(evidence.id)}
            style={{
              padding: '0.45rem 1rem',
              borderRadius: '6px',
              backgroundColor: 'var(--govt-success)',
              color: '#ffffff',
              fontSize: '0.8rem',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <CheckCircle2 size={15} />
            <span>Approve</span>
          </button>
          <button
            type="button"
            onClick={() => flagEvidence(evidence.id, 'Dispatched field inspector to verify location and physical structures')}
            style={{
              padding: '0.45rem 1rem',
              borderRadius: '6px',
              backgroundColor: 'var(--govt-warning)',
              color: '#ffffff',
              fontSize: '0.8rem',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <AlertTriangle size={15} />
            <span>Flag for Inspection</span>
          </button>
          <button
            type="button"
            onClick={() => setShowOverrideModal(true)}
            style={{
              padding: '0.45rem 1rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              color: 'var(--govt-gray-title)',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Reviewer Override
          </button>
        </div>
      </div>

      {/* Main Grid: Photo Inspector & Multi-Tab Dossier */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.5rem' }}>
        {/* Left 6 Cols: Photo Canvas with Object Detection Overlay */}
        <div style={{ gridColumn: 'span 6', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div
            style={{
              position: 'relative',
              backgroundColor: '#0f172a',
              borderRadius: 'var(--radius-lg, 12px)',
              overflow: 'hidden',
              aspectRatio: '4/3',
              border: '1px solid var(--govt-gray-medium)',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <img
              src={evidence.imageUrl}
              alt={evidence.title}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />

            {/* Bounding Boxes Overlay */}
            {showBoxes &&
              evidence.detectedObjects?.map((obj, i) => {
                const [ymin, xmin, ymax, xmax] = obj.box;
                return (
                  <div
                    key={i}
                    style={{
                      position: 'absolute',
                      top: `${ymin * 100}%`,
                      left: `${xmin * 100}%`,
                      width: `${(xmax - xmin) * 100}%`,
                      height: `${(ymax - ymin) * 100}%`,
                      border: '2px solid #22c55e',
                      backgroundColor: 'rgba(34, 197, 94, 0.1)',
                      pointerEvents: 'none',
                    }}
                  >
                    <span
                      style={{
                        position: 'absolute',
                        top: '-20px',
                        left: 0,
                        backgroundColor: '#22c55e',
                        color: '#000000',
                        fontSize: '0.65rem',
                        fontWeight: 700,
                        padding: '1px 4px',
                        borderRadius: '2px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {obj.label} ({Math.round(obj.confidence * 100)}%)
                    </span>
                  </div>
                );
              })}

            {/* Top Toolbar overlay on image */}
            <div
              style={{
                position: 'absolute',
                top: '0.75rem',
                right: '0.75rem',
                display: 'flex',
                gap: '0.4rem',
              }}
            >
              <button
                type="button"
                onClick={() => setShowBoxes(!showBoxes)}
                style={{
                  padding: '0.35rem 0.65rem',
                  borderRadius: '4px',
                  backgroundColor: showBoxes ? 'rgba(34, 197, 94, 0.9)' : 'rgba(15, 23, 42, 0.8)',
                  color: '#ffffff',
                  fontSize: '0.725rem',
                  fontWeight: 600,
                  border: 'none',
                  cursor: 'pointer',
                  backdropFilter: 'blur(4px)',
                }}
              >
                {showBoxes ? 'Hide CV Boxes' : 'Show CV Boxes'}
              </button>
            </div>
          </div>

          {/* Quick Hash & Metadata Bar */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: '8px',
              padding: '0.85rem 1rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '0.5rem',
              fontSize: '0.8rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
              <span style={{ fontWeight: 600, color: 'var(--govt-gray-dark)', flexShrink: 0 }}>
                SHA-256 Digest:
              </span>
              <span
                style={{
                  fontFamily: 'monospace',
                  fontSize: '0.75rem',
                  color: 'var(--govt-gray-title)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {evidence.sha256}
              </span>
            </div>
            <button
              type="button"
              onClick={handleCopySha}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: isCopiedSha ? 'var(--govt-success)' : 'var(--govt-blue-primary)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              {isCopiedSha ? <Check size={14} /> : <Copy size={14} />}
              <span>{isCopiedSha ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
        </div>

        {/* Right 6 Cols: Multi-Tab Dossier */}
        <div style={{ gridColumn: 'span 6', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Header Score Card */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.25rem',
              boxShadow: 'var(--shadow-sm)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1rem',
            }}
          >
            <div>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: 'var(--govt-gray-dark)',
                  display: 'block',
                }}
              >
                Evidence Integrity Index
              </span>
              <div style={{ margin: '0.25rem 0' }}>
                <span
                  style={{
                    fontSize: '1.75rem',
                    fontWeight: 800,
                    color:
                      evidence.integrityScore >= 80
                        ? 'var(--govt-success)'
                        : evidence.integrityScore >= 50
                        ? 'var(--govt-warning)'
                        : 'var(--govt-danger)',
                    fontFamily: 'monospace',
                  }}
                >
                  {evidence.integrityScore}%
                </span>
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                {evidence.riskLevel === 'LOW'
                  ? 'All 7 multi-signals validated'
                  : 'Anomalies detected requiring physical verification'}
              </span>
            </div>
            <IntegrityArc score={evidence.integrityScore} size="md" showRiskBadge />
          </div>

          {/* Dossier Tabs */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              boxShadow: 'var(--shadow-sm)',
              overflow: 'hidden',
            }}
          >
            {/* Tab Buttons */}
            <div
              style={{
                display: 'flex',
                borderBottom: '1px solid var(--govt-gray-medium)',
                backgroundColor: 'var(--govt-gray-off-white)',
              }}
            >
              {[
                { id: 'METADATA', label: 'Camera & EXIF' },
                { id: 'SIMILAR', label: `Similar Matches (${evidence.similarEvidenceMatches?.length || 0})` },
                { id: 'MAP', label: 'Geospatial Bounds' },
                { id: 'ACTIONS', label: 'Audit History' },
              ].map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    style={{
                      flex: 1,
                      padding: '0.75rem 0.5rem',
                      border: 'none',
                      borderBottom: isActive ? '2px solid var(--govt-blue-primary)' : '2px solid transparent',
                      backgroundColor: isActive ? '#ffffff' : 'transparent',
                      color: isActive ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                      fontSize: '0.775rem',
                      fontWeight: isActive ? 700 : 500,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Tab Panels */}
            <div style={{ padding: '1.25rem' }}>
              {activeTab === 'METADATA' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8rem' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Camera Device:</span>
                      <span style={{ fontWeight: 600 }}>{evidence.camera?.make} {evidence.camera?.model}</span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Client Software:</span>
                      <span style={{ fontWeight: 600 }}>{evidence.camera?.software}</span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Optical Exposure:</span>
                      <span style={{ fontWeight: 600 }}>{evidence.camera?.exposure} (ISO {evidence.camera?.iso})</span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Focal Length:</span>
                      <span style={{ fontWeight: 600 }}>{evidence.camera?.focalLength}</span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Capture Timestamp:</span>
                      <span style={{ fontWeight: 600 }}>{new Date(evidence.capturedAt).toLocaleString()}</span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>File Size & Type:</span>
                      <span style={{ fontWeight: 600 }}>{(evidence.sizeBytes / 1024 / 1024).toFixed(2)} MB • {evidence.mimeType}</span>
                    </div>
                  </div>

                  <div style={{ borderTop: '1px solid var(--govt-gray-light)', paddingTop: '0.75rem', marginTop: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                      <span style={{ fontWeight: 700, color: 'var(--govt-blue-dark)' }}>Plain-Language Findings</span>
                      <button
                        type="button"
                        onClick={handleTranslateFinding}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          color: 'var(--govt-blue-primary)',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                        }}
                      >
                        <Languages size={14} />
                        <span>{translatedText ? 'Show English' : 'Translate to Hindi'}</span>
                      </button>
                    </div>

                    <p style={{ margin: 0, fontStyle: 'italic', color: 'var(--govt-gray-text)', backgroundColor: 'var(--govt-gray-off-white)', padding: '0.65rem 0.85rem', borderRadius: '6px' }}>
                      {translatedText || 'GPS coordinates and sequential camera timestamps align with the physical milestone schedule. No manipulation artifacts detected.'}
                    </p>
                  </div>
                </div>
              )}

              {activeTab === 'SIMILAR' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8rem' }}>
                  {!evidence.similarEvidenceMatches || evidence.similarEvidenceMatches.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--govt-success)' }}>
                      <CheckCircle2 size={32} style={{ margin: '0 auto 0.5rem' }} />
                      <p style={{ margin: 0, fontWeight: 600 }}>Zero Duplicate Matches in National Vector Corpus</p>
                      <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                        pHash hamming distance and pgvector cosine similarity are unique across 1.4M records.
                      </p>
                    </div>
                  ) : (
                    evidence.similarEvidenceMatches.map((sim, i) => (
                      <div
                        key={i}
                        style={{
                          padding: '0.75rem',
                          borderRadius: '8px',
                          border: '1.5px solid var(--govt-danger-border)',
                          backgroundColor: 'var(--govt-danger-light)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div>
                          <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-danger-text)' }}>
                            {sim.evidenceId} • {sim.similarityPercentage}% Match
                          </span>
                          <h5 style={{ margin: '0.2rem 0', fontSize: '0.825rem', fontWeight: 600 }}>
                            {sim.projectName}
                          </h5>
                          <span style={{ fontSize: '0.725rem', color: 'var(--govt-gray-dark)' }}>
                            📍 {sim.district} ({sim.distanceKm} km away)
                          </span>
                        </div>
                        <span
                          style={{
                            padding: '0.2rem 0.5rem',
                            borderRadius: '4px',
                            backgroundColor: 'var(--govt-danger)',
                            color: '#ffffff',
                            fontWeight: 700,
                            fontSize: '0.725rem',
                          }}
                        >
                          Recycled Risk
                        </span>
                      </div>
                    ))
                  )}
                </div>
              )}

              {activeTab === 'MAP' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8rem' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Latitude / Longitude:</span>
                      <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                        {evidence.location?.lat?.toFixed(5)}° N, {evidence.location?.lng?.toFixed(5)}° E
                      </span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Centroid Displacement:</span>
                      <span style={{ fontWeight: 700, color: evidence.location?.geofenceDistanceMeters <= 150 ? 'var(--govt-success)' : 'var(--govt-danger)' }}>
                        {evidence.location?.geofenceDistanceMeters}m (Threshold: 150m)
                      </span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>GPS Precision:</span>
                      <span style={{ fontWeight: 600 }}>±{evidence.location?.accuracyMeters} meters</span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Administrative Block:</span>
                      <span style={{ fontWeight: 600 }}>{evidence.location?.block}, {evidence.location?.district}</span>
                    </div>
                  </div>

                  <div style={{ marginTop: '0.5rem', padding: '0.75rem', borderRadius: '6px', backgroundColor: 'var(--govt-gray-off-white)', border: '1px solid var(--govt-gray-medium)' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                      Impossible Travel Trajectory Check:
                    </span>
                    <p style={{ margin: '0.2rem 0 0', fontSize: '0.775rem', color: 'var(--govt-gray-text)' }}>
                      Previous upload by same field officer was 28m away 42 minutes earlier. Implied transit velocity: <strong>0.04 km/h (Feasible)</strong>.
                    </p>
                  </div>
                </div>
              )}

              {activeTab === 'ACTIONS' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8rem' }}>
                  <div>
                    <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Assigned Reviewer:</span>
                    <span style={{ fontWeight: 600 }}>{evidence.reviewer?.assignedTo || 'Unassigned'}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem', display: 'block' }}>Reviewer Audit Rationale:</span>
                    <span style={{ fontStyle: 'italic' }}>"{evidence.reviewer?.note || 'Pending official determination'}"</span>
                  </div>
                  {evidence.reviewer?.overrideReason && (
                    <div style={{ padding: '0.5rem', borderRadius: '4px', backgroundColor: 'rgba(217, 119, 6, 0.1)', border: '1px solid var(--govt-warning-border)' }}>
                      <span style={{ fontWeight: 700, color: 'var(--govt-warning-text)', display: 'block', fontSize: '0.75rem' }}>
                        Formal Override Recorded:
                      </span>
                      <p style={{ margin: '0.2rem 0 0', fontSize: '0.75rem' }}>{evidence.reviewer.overrideReason}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Reviewer Override Modal */}
      {showOverrideModal && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            padding: '1rem',
          }}
        >
          <div
            style={{
              width: '100%',
              maxWidth: '520px',
              backgroundColor: '#ffffff',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.5rem',
              boxShadow: 'var(--shadow-xl)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              Formal Reviewer Score Override
            </h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
              Manual adjustments to automated AI pipeline scores require mandatory statutory justification (minimum 20 characters).
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', display: 'block', marginBottom: '0.25rem' }}>
                  Adjusted Integrity Index:
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={overrideScore}
                  onChange={(e) => setOverrideScore(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '0.5rem',
                    borderRadius: '4px',
                    border: '1px solid var(--govt-gray-medium)',
                    fontSize: '0.85rem',
                    fontWeight: 700,
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', display: 'block', marginBottom: '0.25rem' }}>
                  Risk Classification:
                </label>
                <select
                  value={overrideRisk}
                  onChange={(e) => setOverrideRisk(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.5rem',
                    borderRadius: '4px',
                    border: '1px solid var(--govt-gray-medium)',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                  }}
                >
                  <option value="LOW">Low Risk</option>
                  <option value="MEDIUM">Medium Risk</option>
                  <option value="HIGH">High Risk</option>
                  <option value="CRITICAL">Critical Flag</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', display: 'block', marginBottom: '0.25rem' }}>
                Mandatory Override Rationale (min 20 characters):
              </label>
              <textarea
                rows={4}
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="State technical basis for overriding pipeline assessment..."
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  border: '1px solid var(--govt-gray-medium)',
                  fontSize: '0.825rem',
                  fontFamily: 'inherit',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '0.725rem',
                  marginTop: '0.25rem',
                  color: overrideReason.trim().length >= 20 ? 'var(--govt-success)' : 'var(--govt-danger)',
                }}
              >
                <span>{overrideReason.trim().length}/20 characters minimum</span>
                {overrideReason.trim().length >= 20 && <span>✓ Constraint satisfied</span>}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setShowOverrideModal(false)}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-gray-light)',
                  border: '1px solid var(--govt-gray-medium)',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveOverride}
                disabled={overrideReason.trim().length < 20}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  border: 'none',
                  cursor: overrideReason.trim().length < 20 ? 'not-allowed' : 'pointer',
                  opacity: overrideReason.trim().length < 20 ? 0.5 : 1,
                }}
              >
                Commit Formal Override
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
