import { useState, useEffect, useMemo } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { GraphIcon, FilterIcon, ClockIcon, AlertIcon, CheckIcon } from '../../components/common/Icon';
import { formatDate } from '../../utils/helpers';

function EvidenceGraph() {
  const routerLocation = useLocation();
  const queryParams = new URLSearchParams(routerLocation.search);
  const initialHighlight = queryParams.get('highlight') || '';

  const [activeView, setActiveView] = useState('graph'); // 'graph' or 'timeline'
  const [selectedNodeId, setSelectedNodeId] = useState(initialHighlight || 'EVD-003');
  const [projectFilter, setProjectFilter] = useState('all');
  const [showCrossProjectOnly, setShowCrossProjectOnly] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  // Graph Nodes Definition
  const initialNodes = [
    // Projects
    { id: 'PRJ-001', type: 'project', label: 'Rural Road Construction', sub: 'PMGSY (Maharashtra)', x: 180, y: 120, status: 'active' },
    { id: 'PRJ-002', type: 'project', label: 'Solar Street Lights', sub: 'Solar Energy (Gujarat)', x: 580, y: 120, status: 'active' },
    { id: 'PRJ-003', type: 'project', label: 'Water Tank Project', sub: 'Jal Jeevan (Rajasthan)', x: 920, y: 120, status: 'completed' },

    // Activities
    { id: 'ACT-001', type: 'activity', label: 'Road Base Layer', sub: 'PRJ-001 Milestone 2', x: 180, y: 240, status: 'completed' },
    { id: 'ACT-002', type: 'activity', label: 'PV Panel Mounting', sub: 'PRJ-002 Milestone 1', x: 580, y: 240, status: 'active' },
    { id: 'ACT-003', type: 'activity', label: 'Curing & Sealing', sub: 'PRJ-003 Milestone 3', x: 920, y: 240, status: 'completed' },

    // Evidence
    { id: 'EVD-001', type: 'evidence', label: 'EVD-001 (Road Base Photo)', sub: 'Integrity: 92% | Risk: 15%', x: 110, y: 390, status: 'approved', integrity: 92, risk: 15, date: '2024-02-15T10:30:00Z', project: 'PRJ-001' },
    { id: 'EVD-002', type: 'evidence', label: 'EVD-002 (Compaction Audit)', sub: 'Integrity: 88% | Risk: 22%', x: 280, y: 390, status: 'approved', integrity: 88, risk: 22, date: '2024-02-18T14:20:00Z', project: 'PRJ-001' },
    { id: 'EVD-003', type: 'evidence', label: 'EVD-003 (Pole Photo)', sub: 'Integrity: 45% | Risk: 78%', x: 580, y: 390, status: 'flagged', integrity: 45, risk: 78, date: '2024-02-20T09:45:00Z', project: 'PRJ-002', anomaly: 'Cross-Project Duplicate of EVD-001 & Geofence violation' },
    { id: 'EVD-004', type: 'evidence', label: 'EVD-004 (Structure Completion)', sub: 'Integrity: 75% | Risk: 30%', x: 920, y: 390, status: 'pending', integrity: 75, risk: 30, date: '2024-02-22T16:10:00Z', project: 'PRJ-003' },

    // Locations
    { id: 'LOC-PUN', type: 'location', label: 'Pune Geofence', sub: '18.5204 N, 73.8567 E', x: 180, y: 510 },
    { id: 'LOC-SUR', type: 'location', label: 'Surat Geofence', sub: '21.1702 N, 72.8311 E', x: 580, y: 510 },
    { id: 'LOC-RAJ', type: 'location', label: 'Jaipur Geofence', sub: '26.9124 N, 75.7873 E', x: 920, y: 510 },
  ];

  // Graph Edges / Relationships
  const initialEdges = [
    // Project -> Activity
    { source: 'PRJ-001', target: 'ACT-001', rel: 'CONTAINS', isCross: false },
    { source: 'PRJ-002', target: 'ACT-002', rel: 'CONTAINS', isCross: false },
    { source: 'PRJ-003', target: 'ACT-003', rel: 'CONTAINS', isCross: false },

    // Activity -> Evidence
    { source: 'ACT-001', target: 'EVD-001', rel: 'SUPPORTS', isCross: false },
    { source: 'ACT-001', target: 'EVD-002', rel: 'SUPPORTS', isCross: false },
    { source: 'ACT-002', target: 'EVD-003', rel: 'SUPPORTS', isCross: false },
    { source: 'ACT-003', target: 'EVD-004', rel: 'SUPPORTS', isCross: false },

    // Evidence -> Location
    { source: 'EVD-001', target: 'LOC-PUN', rel: 'CAPTURED_AT', isCross: false },
    { source: 'EVD-002', target: 'LOC-PUN', rel: 'CAPTURED_AT', isCross: false },
    { source: 'EVD-003', target: 'LOC-SUR', rel: 'OUT_OF_BOUNDS', isCross: false, isAnomaly: true },
    { source: 'EVD-004', target: 'LOC-RAJ', rel: 'CAPTURED_AT', isCross: false },

    // Cross-Evidence Relationships
    { source: 'EVD-001', target: 'EVD-002', rel: 'CORROBORATES', isCross: false },
    { source: 'EVD-003', target: 'EVD-001', rel: 'DUPLICATE_OF', isCross: true, isAnomaly: true }, // The major cross-project finding!
  ];

  // Filtered nodes and edges
  const filteredData = useMemo(() => {
    let nodes = initialNodes;
    let edges = initialEdges;

    if (showCrossProjectOnly) {
      edges = edges.filter(e => e.isCross);
      const connectedIds = new Set();
      edges.forEach(e => {
        connectedIds.add(e.source);
        connectedIds.add(e.target);
      });
      nodes = nodes.filter(n => connectedIds.has(n.id));
      return { nodes, edges };
    }

    if (projectFilter !== 'all') {
      const allowed = new Set([projectFilter]);
      if (projectFilter === 'PRJ-001') {
        allowed.add('ACT-001'); allowed.add('EVD-001'); allowed.add('EVD-002'); allowed.add('LOC-PUN');
      } else if (projectFilter === 'PRJ-002') {
        allowed.add('ACT-002'); allowed.add('EVD-003'); allowed.add('LOC-SUR'); allowed.add('EVD-001'); // Show duplicate link
      } else if (projectFilter === 'PRJ-003') {
        allowed.add('ACT-003'); allowed.add('EVD-004'); allowed.add('LOC-RAJ');
      }
      nodes = nodes.filter(n => allowed.has(n.id));
      edges = edges.filter(e => allowed.has(e.source) && allowed.has(e.target));
    }

    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      nodes = nodes.filter(n => n.id.toLowerCase().includes(term) || n.label.toLowerCase().includes(term));
      const nIds = new Set(nodes.map(n => n.id));
      edges = edges.filter(e => nIds.has(e.source) && nIds.has(e.target));
    }

    return { nodes, edges };
  }, [projectFilter, showCrossProjectOnly, searchTerm]);

  const selectedNode = useMemo(() => {
    return initialNodes.find(n => n.id === selectedNodeId) || null;
  }, [selectedNodeId]);

  const getNodeColor = (type, status) => {
    if (type === 'project') return { bg: '#003375', border: '#0056b3', text: '#ffffff' };
    if (type === 'activity') return { bg: '#4a154b', border: '#611f69', text: '#ffffff' };
    if (type === 'location') return { bg: '#0b7285', border: '#15aabf', text: '#ffffff' };
    if (status === 'flagged') return { bg: '#dc3545', border: '#bd2130', text: '#ffffff' };
    if (status === 'approved') return { bg: '#28a745', border: '#1e7e34', text: '#ffffff' };
    return { bg: '#ffc107', border: '#d39e00', text: '#212529' };
  };

  const getEdgeStyle = (edge) => {
    if (edge.rel === 'DUPLICATE_OF') return { stroke: '#dc3545', dash: '5,5', width: 3, labelColor: '#dc3545' };
    if (edge.rel === 'CORROBORATES') return { stroke: '#28a745', dash: '3,3', width: 2, labelColor: '#28a745' };
    if (edge.rel === 'OUT_OF_BOUNDS') return { stroke: '#dc3545', dash: '4,4', width: 2, labelColor: '#dc3545' };
    return { stroke: '#0056b3', dash: 'none', width: 2, labelColor: '#003375' };
  };

  // Timeline Events List
  const timelineEvents = [
    {
      id: 'EVD-001',
      date: '2024-02-15 10:30 IST',
      project: 'PRJ-001 (Maharashtra)',
      activity: 'Road Base Layer Inspection',
      location: 'Pune District (18.5204 N, 73.8567 E)',
      status: 'approved',
      integrity: 92,
      risk: 15,
      note: 'Normal sequential baseline evidence.'
    },
    {
      id: 'EVD-002',
      date: '2024-02-18 14:20 IST',
      project: 'PRJ-001 (Maharashtra)',
      activity: 'Road Compaction Validation',
      location: 'Pune District (18.5204 N, 73.8567 E)',
      status: 'approved',
      integrity: 88,
      risk: 22,
      note: 'Corroborates EVD-001 progress.'
    },
    {
      id: 'EVD-003',
      date: '2024-02-20 09:45 IST',
      project: 'PRJ-002 (Gujarat)',
      activity: 'Solar Panel Installation',
      location: 'Surat District (21.1702 N, 72.8311 E)',
      status: 'flagged',
      integrity: 45,
      risk: 78,
      anomaly: 'CRITICAL: Image perceptual hash duplicate with EVD-001 in PRJ-001. Location is 12.4 km outside project geofence polygon.'
    },
    {
      id: 'EVD-004',
      date: '2024-02-22 16:10 IST',
      project: 'PRJ-003 (Rajasthan)',
      activity: 'Water Tank Construction',
      location: 'Jaipur District (26.9124 N, 75.7873 E)',
      status: 'pending',
      integrity: 75,
      risk: 30,
      note: 'Scheduled for supervisory review.'
    }
  ];

  return (
    <div style={{ padding: '1.75rem 2rem', width: '100%', boxSizing: 'border-box', backgroundColor: 'var(--govt-gray-off-white)' }}>
      {/* Header and Controls */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        flexWrap: 'wrap',
        gap: '1rem',
        marginBottom: '1.25rem',
        paddingBottom: '1rem',
        borderBottom: '2px solid var(--govt-gray-medium)'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.75rem' }}>
              Evidence Graph & Cross-Project Intelligence
            </h2>
            <span style={{
              backgroundColor: 'var(--govt-blue-light)',
              color: 'var(--govt-blue-primary)',
              fontSize: '0.75rem',
              fontWeight: '700',
              padding: '0.2rem 0.5rem',
              borderRadius: '2px'
            }}>
              GRAPH ENGINE V1
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.925rem' }}>
            Relational ontology mapping dependencies, duplicate linkages, and corroborations across infrastructure projects.
          </p>
        </div>

        {/* View Switch Buttons */}
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => setActiveView('graph')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.5rem 1rem',
              borderRadius: 'var(--radius-sm)',
              border: activeView === 'graph' ? 'none' : '1px solid var(--govt-gray-medium)',
              backgroundColor: activeView === 'graph' ? 'var(--govt-blue-primary)' : 'var(--govt-white)',
              color: activeView === 'graph' ? '#ffffff' : 'var(--govt-gray-text)',
              fontWeight: '600',
              fontSize: '0.875rem',
              cursor: 'pointer'
            }}
          >
            <GraphIcon />
            Interactive Graph View
          </button>
          <button
            onClick={() => setActiveView('timeline')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.5rem 1rem',
              borderRadius: 'var(--radius-sm)',
              border: activeView === 'timeline' ? 'none' : '1px solid var(--govt-gray-medium)',
              backgroundColor: activeView === 'timeline' ? 'var(--govt-blue-primary)' : 'var(--govt-white)',
              color: activeView === 'timeline' ? '#ffffff' : 'var(--govt-gray-text)',
              fontWeight: '600',
              fontSize: '0.875rem',
              cursor: 'pointer'
            }}
          >
            <ClockIcon />
            Timeline & Travel Chronology
          </button>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        padding: '1rem 1.25rem',
        marginBottom: '1.25rem',
        border: '1px solid var(--govt-gray-medium)',
        boxShadow: 'var(--shadow-sm)',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '1rem',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: '700', color: 'var(--govt-gray-dark)', marginBottom: '0.2rem' }}>
              Filter by Project
            </label>
            <select
              value={projectFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
              style={{
                padding: '0.4rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--govt-gray-medium)',
                fontSize: '0.85rem'
              }}
            >
              <option value="all">All Projects</option>
              <option value="PRJ-001">PRJ-001: Rural Road Construction (MH)</option>
              <option value="PRJ-002">PRJ-002: Solar Street Lights (GJ)</option>
              <option value="PRJ-003">PRJ-003: Water Tank Project (RJ)</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: '700', color: 'var(--govt-gray-dark)', marginBottom: '0.2rem' }}>
              Quick Search Node
            </label>
            <input
              type="text"
              placeholder="e.g. EVD-003 or Solar..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                padding: '0.4rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--govt-gray-medium)',
                fontSize: '0.85rem',
                width: '180px'
              }}
            />
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.85rem', fontWeight: '600', color: 'var(--govt-danger)', marginTop: '1rem' }}>
            <input
              type="checkbox"
              checked={showCrossProjectOnly}
              onChange={(e) => setShowCrossProjectOnly(e.target.checked)}
            />
            Highlight Cross-Project Conflicts Only
          </label>
        </div>

        {/* Legend */}
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', fontSize: '0.75rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <span style={{ width: '12px', height: '12px', backgroundColor: '#003375', borderRadius: '2px', display: 'inline-block' }}></span>
            <span>Project</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <span style={{ width: '12px', height: '12px', backgroundColor: '#4a154b', borderRadius: '2px', display: 'inline-block' }}></span>
            <span>Activity</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <span style={{ width: '12px', height: '12px', backgroundColor: '#28a745', borderRadius: '50%', display: 'inline-block' }}></span>
            <span>Evidence (Pass)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <span style={{ width: '12px', height: '12px', backgroundColor: '#dc3545', borderRadius: '50%', display: 'inline-block' }}></span>
            <span>Evidence (Flagged)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <span style={{ width: '12px', height: '12px', backgroundColor: '#0b7285', borderRadius: '2px', display: 'inline-block' }}></span>
            <span>Geofence</span>
          </div>
        </div>
      </div>

      {activeView === 'graph' ? (
        /* Graph Visualizer and Node Inspector Drawer */
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(600px, 1fr) 340px', gap: '1.25rem' }}>
          {/* SVG Canvas Area */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--govt-gray-medium)',
            boxShadow: 'var(--shadow-sm)',
            overflow: 'hidden',
            position: 'relative'
          }}>
            <div style={{
              position: 'absolute',
              top: '12px',
              left: '12px',
              backgroundColor: 'rgba(255, 255, 255, 0.9)',
              padding: '0.4rem 0.8rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.75rem',
              border: '1px solid var(--govt-gray-medium)',
              zIndex: 10
            }}>
              💡 <em>Click any node to inspect relationships, integrity signals, and cross-project ties.</em>
            </div>

            <svg width="100%" height="600" viewBox="0 0 1100 600" style={{ backgroundColor: '#fafbfc' }}>
              <defs>
                {/* Arrow Markers */}
                <marker id="arrow-blue" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#0056b3" />
                </marker>
                <marker id="arrow-red" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#dc3545" />
                </marker>
                <marker id="arrow-green" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#28a745" />
                </marker>
              </defs>

              {/* Edge Connections */}
              {filteredData.edges.map((edge, idx) => {
                const src = initialNodes.find(n => n.id === edge.source);
                const tgt = initialNodes.find(n => n.id === edge.target);
                if (!src || !tgt) return null;

                const style = getEdgeStyle(edge);
                const marker = edge.rel === 'DUPLICATE_OF' || edge.rel === 'OUT_OF_BOUNDS' ? 'url(#arrow-red)' : edge.rel === 'CORROBORATES' ? 'url(#arrow-green)' : 'url(#arrow-blue)';
                const midX = (src.x + tgt.x) / 2;
                const midY = (src.y + tgt.y) / 2;

                return (
                  <g key={idx}>
                    <line
                      x1={src.x}
                      y1={src.y}
                      x2={tgt.x}
                      y2={tgt.y}
                      stroke={style.stroke}
                      strokeWidth={style.width}
                      strokeDasharray={style.dash}
                      markerEnd={marker}
                    />
                    <rect
                      x={midX - 35}
                      y={midY - 9}
                      width="70"
                      height="16"
                      fill="#ffffff"
                      rx="2"
                      stroke={style.stroke}
                      strokeWidth="0.5"
                    />
                    <text
                      x={midX}
                      y={midY + 3}
                      fill={style.labelColor}
                      fontSize="9"
                      fontWeight="bold"
                      textAnchor="middle"
                      fontFamily="var(--font-family-mono)"
                    >
                      {edge.rel}
                    </text>
                  </g>
                );
              })}

              {/* Node Circles and Cards */}
              {filteredData.nodes.map((node) => {
                const isSelected = selectedNodeId === node.id;
                const colors = getNodeColor(node.type, node.status);
                const isEvidence = node.type === 'evidence';

                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x}, ${node.y})`}
                    onClick={() => setSelectedNodeId(node.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    {/* Pulsing ring for selected node or anomaly */}
                    {isSelected && (
                      <circle r={isEvidence ? 32 : 48} fill="none" stroke="#0056b3" strokeWidth="3" strokeDasharray="4,4" />
                    )}

                    {isEvidence ? (
                      <circle
                        r="24"
                        fill={colors.bg}
                        stroke={isSelected ? '#003375' : colors.border}
                        strokeWidth={isSelected ? '3' : '2'}
                      />
                    ) : (
                      <rect
                        x="-65"
                        y="-22"
                        width="130"
                        height="44"
                        rx="4"
                        fill={colors.bg}
                        stroke={isSelected ? '#000000' : colors.border}
                        strokeWidth={isSelected ? '2.5' : '1.5'}
                      />
                    )}

                    <text
                      textAnchor="middle"
                      y={isEvidence ? 4 : -4}
                      fill={colors.text}
                      fontSize={isEvidence ? '10' : '11'}
                      fontWeight="bold"
                    >
                      {node.id}
                    </text>

                    {!isEvidence && (
                      <text
                        textAnchor="middle"
                        y="12"
                        fill="#e9ecef"
                        fontSize="9"
                      >
                        {node.type.toUpperCase()}
                      </text>
                    )}

                    {/* Node Label Below */}
                    <text
                      textAnchor="middle"
                      y={isEvidence ? 36 : 34}
                      fill="var(--govt-gray-text)"
                      fontSize="10"
                      fontWeight="600"
                    >
                      {node.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Node Inspector Drawer */}
          <div style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--govt-gray-medium)',
            boxShadow: 'var(--shadow-sm)',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between'
          }}>
            {selectedNode ? (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <span style={{
                    fontSize: '0.7rem',
                    fontWeight: '700',
                    textTransform: 'uppercase',
                    color: 'var(--govt-gray-dark)',
                    backgroundColor: 'var(--govt-gray-off-white)',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '2px',
                    border: '1px solid var(--govt-gray-medium)'
                  }}>
                    {selectedNode.type} Node
                  </span>
                  {selectedNode.status && (
                    <span style={{
                      fontSize: '0.7rem',
                      fontWeight: '700',
                      textTransform: 'uppercase',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '2px',
                      backgroundColor: selectedNode.status === 'flagged' ? 'var(--govt-danger-light)' : 'var(--govt-success-light)',
                      color: selectedNode.status === 'flagged' ? 'var(--govt-danger)' : 'var(--govt-success)'
                    }}>
                      {selectedNode.status}
                    </span>
                  )}
                </div>

                <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--govt-blue-dark)', fontSize: '1.25rem' }}>
                  {selectedNode.id}
                </h3>
                <p style={{ margin: '0 0 1rem 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
                  {selectedNode.label}
                </p>

                {selectedNode.type === 'evidence' && (
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.75rem' }}>
                      <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '0.6rem', borderRadius: 'var(--radius-sm)' }}>
                        <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', display: 'block' }}>Integrity</span>
                        <strong style={{ fontSize: '1.1rem', color: 'var(--govt-blue-primary)' }}>{selectedNode.integrity}%</strong>
                      </div>
                      <div style={{ backgroundColor: 'var(--govt-gray-off-white)', padding: '0.6rem', borderRadius: 'var(--radius-sm)' }}>
                        <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', display: 'block' }}>Risk</span>
                        <strong style={{ fontSize: '1.1rem', color: selectedNode.risk > 50 ? 'var(--govt-danger)' : 'var(--govt-success)' }}>{selectedNode.risk}%</strong>
                      </div>
                    </div>

                    {selectedNode.anomaly && (
                      <div style={{
                        backgroundColor: 'var(--govt-danger-light)',
                        border: '1px solid var(--govt-danger)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '0.75rem',
                        fontSize: '0.8rem',
                        color: 'var(--govt-danger)',
                        marginBottom: '1rem'
                      }}>
                        <strong>Cross-Project Anomaly:</strong>
                        <p style={{ margin: '0.25rem 0 0 0', lineHeight: 1.35 }}>
                          {selectedNode.anomaly}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Relationships of this node */}
                <h5 style={{ margin: '0 0 0.5rem 0', fontSize: '0.85rem', color: 'var(--govt-blue-dark)', textTransform: 'uppercase' }}>
                  Connected Relationships
                </h5>
                <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 1rem 0', fontSize: '0.825rem' }}>
                  {initialEdges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).map((edge, i) => (
                    <li key={i} style={{
                      padding: '0.4rem 0.6rem',
                      backgroundColor: 'var(--govt-gray-off-white)',
                      borderRadius: 'var(--radius-sm)',
                      marginBottom: '0.35rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <span>
                        {edge.source === selectedNode.id ? `➡️ ${edge.target}` : `⬅️ ${edge.source}`}
                      </span>
                      <strong style={{
                        fontSize: '0.7rem',
                        color: edge.isCross ? 'var(--govt-danger)' : 'var(--govt-blue-primary)'
                      }}>
                        {edge.rel}
                      </strong>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p style={{ color: 'var(--govt-gray-dark)', fontSize: '0.9rem' }}>Select a node on the canvas to view details.</p>
            )}

            {selectedNode && (
              <div>
                {selectedNode.type === 'evidence' ? (
                  <Link
                    to={`/evidence/${selectedNode.id}`}
                    style={{
                      display: 'block',
                      textAlign: 'center',
                      backgroundColor: 'var(--govt-blue-primary)',
                      color: '#ffffff',
                      padding: '0.6rem',
                      borderRadius: 'var(--radius-sm)',
                      textDecoration: 'none',
                      fontWeight: '600',
                      fontSize: '0.875rem'
                    }}
                  >
                    Open Full Dossier
                  </Link>
                ) : selectedNode.type === 'project' ? (
                  <Link
                    to={`/projects/${selectedNode.id}`}
                    style={{
                      display: 'block',
                      textAlign: 'center',
                      backgroundColor: 'var(--govt-blue-primary)',
                      color: '#ffffff',
                      padding: '0.6rem',
                      borderRadius: 'var(--radius-sm)',
                      textDecoration: 'none',
                      fontWeight: '600',
                      fontSize: '0.875rem'
                    }}
                  >
                    Open Project Page
                  </Link>
                ) : null}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Timeline View with Impossible Travel Diagnostics */
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-md)',
          padding: '1.5rem',
          border: '1px solid var(--govt-gray-medium)',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <h4 style={{ margin: '0 0 1rem 0', color: 'var(--govt-blue-dark)', fontSize: '1.15rem' }}>
            Multi-Project Temporal Chronology & Impossible Travel Verification
          </h4>
          <p style={{ margin: '0 0 1.5rem 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
            Telemetry sequencing comparing capture timestamps across projects to detect timeline inversions, repeated timestamps, and physically implausible velocity between submissions.
          </p>

          <div style={{ position: 'relative', borderLeft: '3px solid var(--govt-blue-primary)', marginLeft: '1rem', paddingLeft: '1.5rem' }}>
            {timelineEvents.map((ev, idx) => (
              <div key={idx} style={{ marginBottom: '2rem', position: 'relative' }}>
                {/* Node Bullet */}
                <div style={{
                  position: 'absolute',
                  left: '-31px',
                  top: '0',
                  width: '16px',
                  height: '16px',
                  borderRadius: '50%',
                  backgroundColor: ev.status === 'flagged' ? 'var(--govt-danger)' : 'var(--govt-success)',
                  border: '3px solid #ffffff',
                  boxShadow: '0 0 0 2px var(--govt-blue-primary)'
                }} />

                <div style={{
                  backgroundColor: 'var(--govt-gray-off-white)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '1rem 1.25rem',
                  border: ev.status === 'flagged' ? '1px solid var(--govt-danger)' : '1px solid var(--govt-gray-medium)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <div>
                      <Link to={`/evidence/${ev.id}`} style={{ fontWeight: '700', fontSize: '1rem', color: 'var(--govt-blue-primary)', textDecoration: 'none' }}>
                        {ev.id} — {ev.activity}
                      </Link>
                      <span style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)', marginLeft: '0.5rem' }}>
                        ({ev.project})
                      </span>
                    </div>
                    <span style={{
                      backgroundColor: 'var(--govt-blue-dark)',
                      color: '#ffffff',
                      fontSize: '0.75rem',
                      fontFamily: 'var(--font-family-mono)',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '2px'
                    }}>
                      {ev.date}
                    </span>
                  </div>

                  <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.85rem', color: 'var(--govt-gray-text)' }}>
                    📍 <strong>Recorded Location:</strong> {ev.location}
                  </p>

                  {ev.anomaly ? (
                    <div style={{
                      backgroundColor: 'var(--govt-danger-light)',
                      color: 'var(--govt-danger)',
                      padding: '0.6rem 0.8rem',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.85rem',
                      fontWeight: '600'
                    }}>
                      ⚠️ {ev.anomaly}
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.825rem', color: 'var(--govt-success)' }}>
                      ✅ {ev.note}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default EvidenceGraph;
