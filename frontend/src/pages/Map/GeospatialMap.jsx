import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import { getProjectImage } from '../../data/mockDataset';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import {
  MapPin,
  Layers,
  Filter,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  ShieldAlert,
  ChevronRight,
  Info,
  Search,
  Building2,
  FileText,
} from 'lucide-react';

export default function GeospatialMap() {
  const { projects, evidenceList } = useApp();

  const [selectedScheme, setSelectedScheme] = useState('ALL');
  const [selectedProjectId, setSelectedProjectId] = useState(projects?.[0]?.id || 'PRJ-PMGSY-MH-401');
  const [showAnomaliesOnly, setShowAnomaliesOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [hoveredProjectId, setHoveredProjectId] = useState(null);

  const filteredProjects = (projects || []).filter((p) => {
    if (selectedScheme !== 'ALL' && !p.scheme?.includes(selectedScheme)) return false;
    if (showAnomaliesOnly && p.flaggedCount === 0) return false;
    if (
      searchQuery.trim() &&
      !p.name?.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !p.district?.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !p.id?.toLowerCase().includes(searchQuery.toLowerCase())
    ) {
      return false;
    }
    return true;
  });

  const activeProject = (projects || []).find((p) => p.id === selectedProjectId) || projects?.[0] || {
    id: 'PRJ-PMGSY-MH-401',
    name: 'Purandar Taluka Rural Bitumen Road Reconstruction',
    scheme: 'PMGSY (Rural Roads)',
    district: 'Pune',
    state: 'Maharashtra',
    budgetInr: 34500000,
    geofenceRadiusMeters: 150,
    evidenceHealthScore: 94,
    totalSubmissions: 12,
    flaggedCount: 0,
    requiredEvidenceList: [],
  };

  // SVG India Coordinate Projection Helper (Lat: 8 to 36 N, Lng: 68 to 97 E)
  const projectToSvg = (lat, lng) => {
    const minLat = 8.0;
    const maxLat = 35.5;
    const minLng = 68.0;
    const maxLng = 96.0;

    const x = ((lng - minLng) / (maxLng - minLng)) * 100;
    const y = ((maxLat - lat) / (maxLat - minLat)) * 100;
    return { x: Math.max(8, Math.min(92, x)), y: Math.max(8, Math.min(92, y)) };
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
              Geofence GIS & Multi-Scheme Spatial Map
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
                fontFamily: 'monospace',
              }}
            >
              WGS84 EPSG:4326
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
            Nationwide spatial distribution of public works project geofences, satellite boundaries, and verified evidence pins.
          </p>
        </div>

        {/* Filter Toolbar */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <Search size={14} color="var(--govt-gray-dark)" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search district or ID..."
              style={{
                border: 'none',
                outline: 'none',
                fontSize: '0.8rem',
                color: 'var(--govt-gray-title)',
                width: '140px',
              }}
            />
          </div>

          <select
            value={selectedScheme}
            onChange={(e) => setSelectedScheme(e.target.value)}
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
            <option value="ALL">All National Schemes</option>
            <option value="PMGSY">PMGSY (Rural Roads)</option>
            <option value="Jal Jeevan">Jal Jeevan Mission</option>
            <option value="Samagra">Samagra Shiksha (SSA)</option>
            <option value="KUSUM">PM-KUSUM (Solar)</option>
          </select>

          <button
            type="button"
            onClick={() => setShowAnomaliesOnly(!showAnomaliesOnly)}
            style={{
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: showAnomaliesOnly ? '1px solid var(--govt-danger)' : '1px solid var(--govt-gray-medium)',
              backgroundColor: showAnomaliesOnly ? 'var(--govt-danger-light)' : '#ffffff',
              color: showAnomaliesOnly ? 'var(--govt-danger)' : 'var(--govt-gray-text)',
            }}
          >
            {showAnomaliesOnly ? 'Showing Flagged Only' : 'Filter Anomalies'}
          </button>
        </div>
      </div>

      {/* Main Map Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.5rem' }}>
        {/* Left 8 Cols: GIS Map Canvas */}
        <div
          style={{
            gridColumn: 'span 8',
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            boxShadow: 'var(--shadow-sm)',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Map Top Status Bar */}
          <div
            style={{
              padding: '0.75rem 1rem',
              backgroundColor: 'var(--govt-gray-off-white)',
              borderBottom: '1px solid var(--govt-gray-medium)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '0.8rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <MapPin size={15} color="var(--govt-blue-primary)" />
              <span style={{ fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                National Evidence Distribution
              </span>
              <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.75rem' }}>
                (Geofence Boundary Representations)
              </span>
            </div>
            <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
              {filteredProjects.length} Active Nodes
            </span>
          </div>

          {/* SVG Map Container */}
          <div
            style={{
              position: 'relative',
              width: '100%',
              minHeight: '520px',
              backgroundColor: 'var(--govt-gray-light, #f1f5f9)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '1.5rem',
              userSelect: 'none',
              overflow: 'hidden',
            }}
          >
            {/* Coordinate Grid Background */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                backgroundImage: 'radial-gradient(circle at center, #cbd5e1 1px, transparent 1px)',
                backgroundSize: '24px 24px',
                opacity: 0.6,
              }}
            />

            <svg
              viewBox="0 0 100 100"
              style={{ width: '100%', height: '100%', maxHeight: '520px', overflow: 'visible' }}
              preserveAspectRatio="xMidYMid meet"
            >
              {/* India Boundary Polygon Silhouette */}
              <polygon
                points="30,10 40,8 55,12 70,18 85,22 92,30 88,38 78,45 68,48 62,58 55,75 50,88 45,78 38,62 30,52 20,42 22,30 28,18"
                fill="#ffffff"
                stroke="var(--govt-gray-medium, #cbd5e1)"
                strokeWidth="1.2"
                strokeDasharray="2 2"
                style={{ opacity: 0.85 }}
              />

              {/* Project Geofence Pins */}
              {filteredProjects.map((project) => {
                const { x, y } = projectToSvg(project.centroid?.lat || 20, project.centroid?.lng || 78);
                const isSelected = project.id === selectedProjectId;
                const isHovered = project.id === hoveredProjectId;
                const hasFlags = project.flaggedCount > 0;

                const pinColor = hasFlags
                  ? 'var(--govt-danger, #dc2626)'
                  : project.evidenceHealthScore > 80
                  ? 'var(--govt-success, #059669)'
                  : 'var(--govt-warning, #d97706)';

                return (
                  <g
                    key={project.id}
                    onClick={() => setSelectedProjectId(project.id)}
                    onMouseEnter={() => setHoveredProjectId(project.id)}
                    onMouseLeave={() => setHoveredProjectId(null)}
                    style={{ cursor: 'pointer' }}
                  >
                    {/* Geofence Radius Boundary Ring */}
                    <circle
                      cx={x}
                      cy={y}
                      r={isSelected ? 9 : isHovered ? 7.5 : 5.5}
                      fill={hasFlags ? 'rgba(220, 38, 38, 0.08)' : 'rgba(5, 150, 105, 0.06)'}
                      stroke={pinColor}
                      strokeWidth={isSelected ? 1.5 : 0.8}
                      strokeDasharray={isSelected ? 'none' : '1.5 1.5'}
                    />

                    {/* Center Core Marker Pin */}
                    <circle
                      cx={x}
                      cy={y}
                      r={isSelected ? 4 : isHovered ? 3.5 : 2.8}
                      fill={pinColor}
                      stroke="#ffffff"
                      strokeWidth="1"
                    />

                    {/* Marker Label */}
                    {(isSelected || isHovered) && (
                      <text
                        x={x + 4.5}
                        y={y + 1.2}
                        fill="var(--govt-gray-title, #0f172a)"
                        fontSize="3.2"
                        fontFamily="var(--font-family-primary, sans-serif)"
                        fontWeight="bold"
                        style={{ pointerEvents: 'none' }}
                      >
                        {project.district} • {project.scheme?.split(' ')[0]}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>

            {/* Map Legend */}
            <div
              style={{
                position: 'absolute',
                bottom: '1rem',
                left: '1rem',
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                backdropFilter: 'blur(4px)',
                border: '1px solid var(--govt-gray-medium)',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                fontSize: '0.75rem',
                boxShadow: 'var(--shadow-sm)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.4rem',
              }}
            >
              <span style={{ fontWeight: 700, color: 'var(--govt-blue-dark)', textTransform: 'uppercase', fontSize: '0.7rem' }}>
                Geofence Health Legend
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--govt-success)' }} />
                <span style={{ color: 'var(--govt-gray-dark)' }}>Consistent (Score &gt; 80)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--govt-warning)' }} />
                <span style={{ color: 'var(--govt-gray-dark)' }}>Minor Deviation / Reviewing</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--govt-danger)' }} />
                <span style={{ color: 'var(--govt-danger)', fontWeight: 600 }}>Flagged Anomaly / Mismatch</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right 4 Cols: Project Inspection Drawer */}
        <div style={{ gridColumn: 'span 4' }}>
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.5rem',
              boxShadow: 'var(--shadow-sm)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'space-between',
                gap: '0.75rem',
                borderBottom: '1px solid var(--govt-gray-medium)',
                paddingBottom: '0.85rem',
              }}
            >
              <div>
                <span
                  style={{
                    fontFamily: 'monospace',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: 'var(--govt-gray-dark)',
                    display: 'block',
                  }}
                >
                  {activeProject.id}
                </span>
                <h3
                  style={{
                    margin: '0.2rem 0 0',
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    color: 'var(--govt-gray-title)',
                    lineHeight: 1.35,
                  }}
                >
                  {activeProject.name}
                </h3>
              </div>
              <IntegrityArc score={activeProject.evidenceHealthScore} size="sm" showLabel />
            </div>

            <div
              style={{
                aspectRatio: '16/9',
                width: '100%',
                borderRadius: '8px',
                overflow: 'hidden',
                backgroundColor: '#0f172a',
                border: '1px solid var(--govt-gray-medium)',
              }}
            >
              <img
                src={activeProject.imageUrl || getProjectImage(activeProject.id)}
                alt={activeProject.name}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.8rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Scheme Track:</span>
                <span style={{ fontWeight: 600, color: 'var(--govt-blue-primary)' }}>{activeProject.scheme}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Jurisdiction:</span>
                <span style={{ fontWeight: 500, color: 'var(--govt-gray-title)' }}>
                  {activeProject.district}, {activeProject.state}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Sanctioned Budget:</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                  ₹{(activeProject.budgetInr / 10000000).toFixed(2)} Cr
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Geofence Radius:</span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--govt-gray-title)' }}>
                  {activeProject.geofenceRadiusMeters}m
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Total Submissions:</span>
                <span style={{ fontWeight: 600 }}>{activeProject.totalSubmissions} records</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Flagged Anomalies:</span>
                <span
                  style={{
                    fontWeight: 700,
                    color: activeProject.flaggedCount > 0 ? 'var(--govt-danger)' : 'var(--govt-success)',
                  }}
                >
                  {activeProject.flaggedCount > 0 ? `${activeProject.flaggedCount} issues detected` : '0 issues'}
                </span>
              </div>
            </div>

            {/* Mandatory Evidence Checklist */}
            <div style={{ borderTop: '1px solid var(--govt-gray-medium)', paddingTop: '0.85rem' }}>
              <h4
                style={{
                  margin: '0 0 0.5rem',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: 'var(--govt-gray-dark)',
                }}
              >
                Mandatory Evidence Checklist
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.75rem' }}>
                {(activeProject.requiredEvidenceList || []).map((req) => (
                  <div
                    key={req.key}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.45rem 0.65rem',
                      backgroundColor: 'var(--govt-gray-off-white)',
                      borderRadius: '4px',
                      border: '1px solid var(--govt-gray-light)',
                    }}
                  >
                    <span style={{ color: 'var(--govt-gray-title)', fontWeight: 500 }}>{req.label}</span>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        padding: '0.1rem 0.4rem',
                        borderRadius: '3px',
                        backgroundColor:
                          req.status === 'FULFILLED'
                            ? 'rgba(5, 150, 105, 0.12)'
                            : req.status === 'PARTIAL'
                            ? 'rgba(217, 119, 6, 0.12)'
                            : 'rgba(220, 38, 38, 0.12)',
                        color:
                          req.status === 'FULFILLED'
                            ? 'var(--govt-success)'
                            : req.status === 'PARTIAL'
                            ? 'var(--govt-warning)'
                            : 'var(--govt-danger)',
                      }}
                    >
                      {req.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <Link
              to={`/projects/${activeProject.id}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                padding: '0.65rem 1rem',
                borderRadius: '6px',
                backgroundColor: 'var(--govt-blue-primary)',
                color: '#ffffff',
                fontSize: '0.825rem',
                fontWeight: 700,
                textDecoration: 'none',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <span>Inspect Full Project Dossier</span>
              <ExternalLink size={14} />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
