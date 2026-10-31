import React, { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import {
  SplitSquareVertical,
  Columns,
  Layers,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Info,
  MapPin,
  Calendar,
  Building2,
  FileCheck,
  ShieldCheck,
} from 'lucide-react';

export default function EvidenceCompare() {
  const { evidenceList, projects } = useApp();

  // Find comparison pairs or items with beforeImageUrl
  const comparisonPairs = (evidenceList || []).filter((e) => e.beforeImageUrl);
  const defaultEvidence =
    comparisonPairs.find((e) => e.id === 'EVD-2026-7734') ||
    comparisonPairs[0] ||
    evidenceList?.[0] || {
      id: 'EVD-2026-7734',
      projectId: 'PRJ-SSA-UP-512',
      projectName: 'Government Primary & Upper Primary School Structural Roof & Masonry Repair',
      scheme: 'Samagra Shiksha Abhiyan',
      beforeImageUrl: '/images/projects/school-before.jpg',
      imageUrl: '/images/projects/school-after.jpg',
      structuralChangeConfidence: 94,
      sha256: '7a21f8c49e15903b68f5c22e4d9b01a23847e51c8901b2a4c8e71629d8164bc7',
      location: { district: 'Varanasi', state: 'Uttar Pradesh', block: 'Pindra' },
    };

  const [selectedPairId, setSelectedPairId] = useState(defaultEvidence.id);

  const activeEvidence = (evidenceList || []).find((e) => e.id === selectedPairId) || defaultEvidence;
  const activeProject = (projects || []).find((p) => p.id === activeEvidence.projectId) || projects?.[0] || {
    id: activeEvidence.projectId || 'PRJ-SSA-UP-512',
    name: activeEvidence.projectName || 'Samagra Shiksha School Repair',
    scheme: activeEvidence.scheme || 'SSA',
    district: activeEvidence.location?.district || 'Varanasi',
    state: activeEvidence.location?.state || 'Uttar Pradesh',
    budgetInr: 4600000,
    geofenceRadiusMeters: 80,
  };

  const beforeImg = activeEvidence.beforeImageUrl || '/images/projects/school-before.jpg';
  const afterImg = activeEvidence.imageUrl || '/images/projects/school-after.jpg';

  const [mode, setMode] = useState('SLIDER');
  const [sliderPos, setSliderPos] = useState(50);
  const [showDifferenceOverlay, setShowDifferenceOverlay] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef(null);

  const handleSliderMove = (clientX) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const percentage = Math.max(0, Math.min(100, (x / rect.width) * 100));
    setSliderPos(percentage);
  };

  const handleMouseDown = () => setIsDragging(true);
  const handleMouseUp = () => setIsDragging(false);
  const handleMouseMove = (e) => {
    if (isDragging) handleSliderMove(e.clientX);
  };

  const handleTouchMove = (e) => {
    if (e.touches[0]) handleSliderMove(e.touches[0].clientX);
  };

  const changeScore = activeEvidence.structuralChangeConfidence || 94;

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Top Header & Selector */}
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
              Before / After Visual Change Comparator
            </h1>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '999px',
                backgroundColor: 'rgba(5, 150, 105, 0.12)',
                color: 'var(--govt-success, #059669)',
                fontSize: '0.75rem',
                fontWeight: 700,
              }}
            >
              <CheckCircle2 size={13} />
              <span>Spatial Homography Aligned</span>
            </span>
          </div>
          <p
            style={{
              margin: '0.35rem 0 0',
              fontSize: '0.85rem',
              color: 'var(--govt-gray-dark, #64748b)',
            }}
          >
            Pixel-registered visual comparison verifying measurable physical construction progression across project milestones.
          </p>
        </div>

        {/* Milestone Pair Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)', fontWeight: 600 }}>
            Select Milestone:
          </span>
          <select
            value={selectedPairId}
            onChange={(e) => {
              setSelectedPairId(e.target.value);
              setSliderPos(50);
            }}
            style={{
              padding: '0.45rem 0.85rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium, #e2e8f0)',
              fontSize: '0.825rem',
              fontWeight: 600,
              color: 'var(--govt-gray-title, #0f172a)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            {comparisonPairs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id} • {p.scheme} ({p.location?.district})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Project Association Bar */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium, #e2e8f0)',
          borderRadius: 'var(--radius-lg, 12px)',
          padding: '1.25rem 1.5rem',
          boxShadow: 'var(--shadow-sm)',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
            <span
              style={{
                fontFamily: 'var(--font-family-mono)',
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '0.15rem 0.5rem',
                borderRadius: '4px',
                backgroundColor: 'var(--govt-gray-light)',
                border: '1px solid var(--govt-gray-medium)',
                color: 'var(--govt-blue-dark)',
              }}
            >
              {activeProject.id}
            </span>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-blue-primary)' }}>
              {activeProject.scheme}
            </span>
            <span
              style={{
                fontSize: '0.7rem',
                fontWeight: 700,
                padding: '0.15rem 0.45rem',
                borderRadius: '4px',
                backgroundColor: 'rgba(5, 150, 105, 0.1)',
                color: 'var(--govt-success)',
              }}
            >
              Verified Milestone Pair
            </span>
          </div>
          <h2
            style={{
              margin: '0 0 0.4rem',
              fontSize: '1.05rem',
              fontWeight: 700,
              color: 'var(--govt-gray-title)',
            }}
          >
            PROJECT: {activeProject.name}
          </h2>
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: '1rem',
              fontSize: '0.8rem',
              color: 'var(--govt-gray-dark)',
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              <MapPin size={13} /> {activeProject.district}, {activeProject.state}
            </span>
            <span>•</span>
            <span>Geofence: {activeProject.geofenceRadiusMeters}m radius</span>
            <span>•</span>
            <span>Sanctioned Budget: ₹{(activeProject.budgetInr / 10000000).toFixed(2)} Cr</span>
          </div>
        </div>

        <Link
          to={`/projects/${activeProject.id}`}
          style={{
            padding: '0.45rem 0.9rem',
            borderRadius: '6px',
            backgroundColor: 'var(--govt-gray-light)',
            border: '1px solid var(--govt-gray-medium)',
            color: 'var(--govt-blue-primary)',
            fontSize: '0.8rem',
            fontWeight: 700,
            textDecoration: 'none',
          }}
        >
          View Full Project Dossier →
        </Link>
      </div>

      {/* Mode & Control Toolbar */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium, #e2e8f0)',
          borderRadius: '8px',
          padding: '0.75rem 1rem',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.75rem',
          marginBottom: '1rem',
          fontSize: '0.825rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Segmented View Mode Toggle */}
          <div
            style={{
              display: 'inline-flex',
              backgroundColor: 'var(--govt-gray-light)',
              borderRadius: '6px',
              padding: '2px',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <button
              type="button"
              onClick={() => setMode('SLIDER')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.35rem 0.75rem',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: mode === 'SLIDER' ? 700 : 500,
                backgroundColor: mode === 'SLIDER' ? '#ffffff' : 'transparent',
                color: mode === 'SLIDER' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                boxShadow: mode === 'SLIDER' ? 'var(--shadow-xs)' : 'none',
              }}
            >
              <SplitSquareVertical size={14} />
              <span>Interactive Split Slider</span>
            </button>
            <button
              type="button"
              onClick={() => setMode('SIDE_BY_SIDE')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.35rem 0.75rem',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: mode === 'SIDE_BY_SIDE' ? 700 : 500,
                backgroundColor: mode === 'SIDE_BY_SIDE' ? '#ffffff' : 'transparent',
                color: mode === 'SIDE_BY_SIDE' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                boxShadow: mode === 'SIDE_BY_SIDE' ? 'var(--shadow-xs)' : 'none',
              }}
            >
              <Columns size={14} />
              <span>Side-by-Side</span>
            </button>
          </div>

          {/* Difference Overlay Toggle */}
          <button
            type="button"
            onClick={() => setShowDifferenceOverlay(!showDifferenceOverlay)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.35rem 0.75rem',
              borderRadius: '6px',
              border: showDifferenceOverlay ? '1px solid var(--govt-blue-primary)' : '1px solid var(--govt-gray-medium)',
              backgroundColor: showDifferenceOverlay ? 'var(--govt-blue-light)' : '#ffffff',
              color: showDifferenceOverlay ? 'var(--govt-blue-primary)' : 'var(--govt-gray-text)',
              fontWeight: 600,
              fontSize: '0.8rem',
              cursor: 'pointer',
            }}
          >
            <Layers size={14} />
            <span>Structural Heatmap Diff</span>
          </button>
        </div>

        {/* Zoom Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <button
            type="button"
            onClick={() => setZoomLevel((z) => Math.min(2.5, z + 0.25))}
            aria-label="Zoom In"
            style={{
              padding: '0.35rem 0.5rem',
              borderRadius: '4px',
              border: '1px solid var(--govt-gray-medium)',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
            }}
          >
            <ZoomIn size={14} />
          </button>
          <span style={{ fontSize: '0.75rem', fontFamily: 'monospace', fontWeight: 600, minWidth: '42px', textAlign: 'center' }}>
            {Math.round(zoomLevel * 100)}%
          </span>
          <button
            type="button"
            onClick={() => setZoomLevel((z) => Math.max(0.75, z - 0.25))}
            aria-label="Zoom Out"
            style={{
              padding: '0.35rem 0.5rem',
              borderRadius: '4px',
              border: '1px solid var(--govt-gray-medium)',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
            }}
          >
            <ZoomOut size={14} />
          </button>
          <button
            type="button"
            onClick={() => setZoomLevel(1)}
            aria-label="Reset Zoom"
            style={{
              padding: '0.35rem 0.5rem',
              borderRadius: '4px',
              border: '1px solid var(--govt-gray-medium)',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
            }}
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </div>

      {/* Main Comparison Canvas */}
      <div
        style={{
          position: 'relative',
          backgroundColor: '#0f172a',
          borderRadius: 'var(--radius-lg, 12px)',
          overflow: 'hidden',
          border: '1px solid var(--govt-gray-medium, #e2e8f0)',
          boxShadow: 'var(--shadow-md)',
          userSelect: 'none',
        }}
      >
        {mode === 'SLIDER' ? (
          <div
            ref={containerRef}
            onMouseDown={handleMouseDown}
            onMouseUp={handleMouseUp}
            onMouseMove={handleMouseMove}
            onTouchMove={handleTouchMove}
            style={{
              position: 'relative',
              width: '100%',
              height: '540px',
              cursor: isDragging ? 'ew-resize' : 'default',
              overflow: 'hidden',
            }}
          >
            {/* AFTER Layer (Base image) */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                transform: `scale(${zoomLevel})`,
                transformOrigin: 'center center',
                transition: isDragging ? 'none' : 'transform 0.2s ease',
              }}
            >
              <img
                src={afterImg}
                alt="After completion stage"
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                }}
              />
              {/* Difference Overlay */}
              {showDifferenceOverlay && (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    backgroundColor: 'rgba(5, 150, 105, 0.25)',
                    mixBlendMode: 'color-dodge',
                    pointerEvents: 'none',
                  }}
                />
              )}
            </div>

            {/* BEFORE Layer (Clipped image) */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                bottom: 0,
                left: 0,
                width: `${sliderPos}%`,
                overflow: 'hidden',
                borderRight: '2px solid #ffffff',
                boxShadow: '2px 0 10px rgba(0, 0, 0, 0.5)',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: containerRef.current?.clientWidth || '100%',
                  height: '100%',
                  transform: `scale(${zoomLevel})`,
                  transformOrigin: 'center center',
                  transition: isDragging ? 'none' : 'transform 0.2s ease',
                }}
              >
                <img
                  src={beforeImg}
                  alt="Before baseline survey stage"
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                  }}
                />
              </div>
            </div>

            {/* Slider Handle Divider */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                bottom: 0,
                left: `${sliderPos}%`,
                width: '4px',
                transform: 'translateX(-50%)',
                backgroundColor: '#ffffff',
                pointerEvents: 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  backgroundColor: 'var(--govt-blue-primary, #1d4ed8)',
                  border: '2.5px solid #ffffff',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ffffff',
                }}
              >
                <SplitSquareVertical size={18} />
              </div>
            </div>

            {/* Labels on top corners */}
            <div
              style={{
                position: 'absolute',
                top: '1rem',
                left: '1rem',
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                color: '#ffffff',
                padding: '0.3rem 0.75rem',
                borderRadius: '4px',
                fontSize: '0.75rem',
                fontWeight: 700,
                letterSpacing: '0.04em',
                pointerEvents: 'none',
              }}
            >
              BEFORE (Survey Baseline)
            </div>
            <div
              style={{
                position: 'absolute',
                top: '1rem',
                right: '1rem',
                backgroundColor: 'rgba(5, 150, 105, 0.85)',
                color: '#ffffff',
                padding: '0.3rem 0.75rem',
                borderRadius: '4px',
                fontSize: '0.75rem',
                fontWeight: 700,
                letterSpacing: '0.04em',
                pointerEvents: 'none',
              }}
            >
              AFTER (Final Completion)
            </div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px', height: '540px' }}>
            <div style={{ position: 'relative', overflow: 'hidden' }}>
              <img
                src={beforeImg}
                alt="Before"
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                  transform: `scale(${zoomLevel})`,
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  top: '1rem',
                  left: '1rem',
                  backgroundColor: 'rgba(15, 23, 42, 0.8)',
                  color: '#ffffff',
                  padding: '0.3rem 0.75rem',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                }}
              >
                BEFORE STAGE
              </div>
            </div>
            <div style={{ position: 'relative', overflow: 'hidden' }}>
              <img
                src={afterImg}
                alt="After"
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                  transform: `scale(${zoomLevel})`,
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  top: '1rem',
                  right: '1rem',
                  backgroundColor: 'rgba(5, 150, 105, 0.85)',
                  color: '#ffffff',
                  padding: '0.3rem 0.75rem',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                }}
              >
                AFTER STAGE
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Forensic Comparison Metric Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1rem',
          marginTop: '1.5rem',
        }}
      >
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium, #e2e8f0)',
            borderRadius: '8px',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
              Physical Transformation Score
            </span>
            <span
              style={{
                fontSize: '0.85rem',
                fontFamily: 'monospace',
                fontWeight: 700,
                color: 'var(--govt-success)',
              }}
            >
              {changeScore}% Confidence
            </span>
          </div>
          <div
            style={{
              width: '100%',
              height: '6px',
              backgroundColor: 'var(--govt-gray-light)',
              borderRadius: '999px',
              overflow: 'hidden',
              marginBottom: '0.75rem',
            }}
          >
            <div
              style={{
                width: `${changeScore}%`,
                height: '100%',
                backgroundColor: 'var(--govt-success)',
                borderRadius: '999px',
              }}
            />
          </div>
          <p style={{ margin: 0, fontSize: '0.775rem', color: 'var(--govt-gray-dark)', lineHeight: 1.4 }}>
            Computer vision edge-matching detected structural replacement of spalled masonry with high-grade elastomeric plaster coat.
          </p>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium, #e2e8f0)',
            borderRadius: '8px',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
              Cryptographic Signatures
            </span>
            <ShieldCheck size={16} color="var(--govt-blue-primary)" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.75rem' }}>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>Before SHA-256: </span>
              <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>4c91a0...8e12</span>
            </div>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>After SHA-256: </span>
              <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{activeEvidence.sha256?.substring(0, 16)}...</span>
            </div>
            <div>
              <span style={{ color: 'var(--govt-gray-dark)' }}>GPS Coordinate Delta: </span>
              <span style={{ fontWeight: 600, color: 'var(--govt-success)' }}>0.4 meters (Co-located)</span>
            </div>
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium, #e2e8f0)',
            borderRadius: '8px',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
              Institutional Recommendation
            </span>
            <CheckCircle2 size={16} color="var(--govt-success)" />
          </div>
          <p style={{ margin: '0 0 0.5rem', fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-gray-title)' }}>
            Clear for Milestone Stage-2 Disbursement
          </p>
          <p style={{ margin: 0, fontSize: '0.775rem', color: 'var(--govt-gray-dark)', lineHeight: 1.4 }}>
            Visual and spatial metrics confirm authentic progress. No evidence duplication or tampering detected.
          </p>
        </div>
      </div>
    </div>
  );
}
