import React from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { IntegrityArc } from '../components/ui/IntegrityArc';
import {
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ArrowRight,
  TrendingUp,
  MapPin,
  FileText,
  ExternalLink,
  Layers,
  ChevronRight,
  Sparkles,
  SplitSquareVertical,
  Cpu,
} from 'lucide-react';

export default function Dashboard() {
  const { evidenceList, projects, currentUser } = useApp();

  const totalAudited = 1428;
  const flaggedItems = (evidenceList || []).filter(
    (e) => e.riskLevel === 'CRITICAL' || e.riskLevel === 'HIGH'
  );
  const pendingItems = (evidenceList || []).filter(
    (e) => e.auditStatus === 'PENDING' || e.auditStatus === 'FLAGGED'
  );

  const avgIntegrity =
    evidenceList && evidenceList.length > 0
      ? Math.round(evidenceList.reduce((acc, curr) => acc + curr.integrityScore, 0) / evidenceList.length)
      : 78;

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Top Welcome & Institutional Status Strip */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          paddingBottom: '1.25rem',
          borderBottom: '1px solid var(--govt-gray-medium, #e2e8f0)',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1
              style={{
                margin: 0,
                fontSize: '1.65rem',
                fontWeight: 800,
                color: 'var(--govt-blue-dark, #0f172a)',
                letterSpacing: '-0.02em',
              }}
            >
              Reviewer Operations Hub
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
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: 'var(--govt-success)',
                  display: 'inline-block',
                }}
              />
              Live Audit Engine
            </span>
          </div>
          <p
            style={{
              margin: '0.35rem 0 0',
              fontSize: '0.85rem',
              color: 'var(--govt-gray-dark, #64748b)',
            }}
          >
            Multi-signal consistency audit for public-works evidence across geospatial, temporal, visual, and cross-project vector corpora. Operator: <strong>{currentUser?.name || 'Lead Reviewer'}</strong>
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Link
            to="/reviews"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.55rem 1.15rem',
              borderRadius: '6px',
              backgroundColor: 'var(--govt-blue-primary, #1d4ed8)',
              color: '#ffffff',
              fontSize: '0.825rem',
              fontWeight: 700,
              textDecoration: 'none',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <span>Open Review Queue</span>
            <span
              style={{
                padding: '0.1rem 0.45rem',
                borderRadius: '999px',
                backgroundColor: 'rgba(255, 255, 255, 0.25)',
                fontSize: '0.7rem',
                fontFamily: 'monospace',
              }}
            >
              {pendingItems.length}
            </span>
            <ArrowRight size={14} />
          </Link>
          <Link
            to="/ingest"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.55rem 1rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium, #e2e8f0)',
              color: 'var(--govt-blue-dark)',
              fontSize: '0.825rem',
              fontWeight: 600,
              textDecoration: 'none',
            }}
          >
            <Sparkles size={15} color="var(--govt-blue-primary)" />
            <span>Live Pipeline Sandbox</span>
          </Link>
        </div>
      </div>

      {/* 4 Core Metric Tiles */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1rem',
          marginBottom: '1.75rem',
        }}
      >
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-md, 8px)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
              Total Audited Submissions
            </span>
            <FileText size={16} color="var(--govt-blue-primary)" />
          </div>
          <div style={{ margin: '0.5rem 0 0.25rem' }}>
            <span style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--govt-blue-dark)', fontFamily: 'monospace' }}>
              {totalAudited}
            </span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--govt-success)', fontWeight: 600 }}>
            +142 this week across 6 state projects
          </span>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-md, 8px)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
              Flagged Anomaly Rate
            </span>
            <ShieldAlert size={16} color="var(--govt-danger)" />
          </div>
          <div style={{ margin: '0.5rem 0 0.25rem' }}>
            <span style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--govt-danger)', fontFamily: 'monospace' }}>
              18.4%
            </span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--govt-danger)', fontWeight: 600 }}>
            {flaggedItems.length} active critical holds requiring inspection
          </span>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-md, 8px)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
              Pending Review Queue
            </span>
            <Clock size={16} color="var(--govt-warning)" />
          </div>
          <div style={{ margin: '0.5rem 0 0.25rem' }}>
            <span style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--govt-warning)', fontFamily: 'monospace' }}>
              {pendingItems.length}
            </span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
            Average turnaround time 4.2 hours
          </span>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-md, 8px)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', display: 'block' }}>
              Mean Evidence Health Index
            </span>
            <div style={{ margin: '0.35rem 0 0.15rem' }}>
              <span style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--govt-blue-dark)', fontFamily: 'monospace' }}>
                {avgIntegrity}%
              </span>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--govt-success)', fontWeight: 600 }}>
              National Baseline Met
            </span>
          </div>
          <IntegrityArc score={avgIntegrity} size="md" />
        </div>
      </div>

      {/* Main Content Grid: Schemes Health Overview + Critical Flagged Stream */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Left 7 Cols: Urgent Flagged Queue Stream */}
        <div style={{ gridColumn: 'span 7' }}>
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              boxShadow: 'var(--shadow-sm)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '1rem 1.25rem',
                backgroundColor: 'var(--govt-gray-off-white)',
                borderBottom: '1px solid var(--govt-gray-medium)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <AlertTriangle size={16} color="var(--govt-danger)" />
                <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                  Urgent Anomalies & Multi-Signal Flags
                </h3>
              </div>
              <Link
                to="/reviews"
                style={{
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  color: 'var(--govt-blue-primary)',
                  textDecoration: 'none',
                }}
              >
                View Complete Queue ({pendingItems.length}) →
              </Link>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {flaggedItems.slice(0, 4).map((item) => (
                <div
                  key={item.id}
                  style={{
                    padding: '1rem 1.25rem',
                    borderBottom: '1px solid var(--govt-gray-light)',
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: '1rem',
                  }}
                >
                  <div style={{ display: 'flex', gap: '0.85rem' }}>
                    <div
                      style={{
                        width: '56px',
                        height: '56px',
                        borderRadius: '6px',
                        overflow: 'hidden',
                        backgroundColor: '#0f172a',
                        flexShrink: 0,
                      }}
                    >
                      <img
                        src={item.imageUrl}
                        alt={item.title}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    </div>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.2rem' }}>
                        <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                          {item.id}
                        </span>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: 700,
                            padding: '0.1rem 0.4rem',
                            borderRadius: '3px',
                            backgroundColor: 'rgba(220, 38, 38, 0.1)',
                            color: 'var(--govt-danger)',
                          }}
                        >
                          {item.riskLevel}
                        </span>
                      </div>
                      <h4
                        style={{
                          margin: '0 0 0.25rem',
                          fontSize: '0.875rem',
                          fontWeight: 600,
                          color: 'var(--govt-gray-title)',
                        }}
                      >
                        {item.title}
                      </h4>
                      <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                        {item.scheme} • {item.location?.district}, {item.location?.state}
                      </div>

                      {item.detectedAnomalies?.[0] && (
                        <div
                          style={{
                            marginTop: '0.4rem',
                            padding: '0.35rem 0.6rem',
                            borderRadius: '4px',
                            backgroundColor: 'var(--govt-danger-light)',
                            border: '1px solid var(--govt-danger-border)',
                            fontSize: '0.725rem',
                            color: 'var(--govt-danger-text)',
                            fontWeight: 600,
                          }}
                        >
                          ⚠ {item.detectedAnomalies[0].title}
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem', flexShrink: 0 }}>
                    <IntegrityArc score={item.integrityScore} size="sm" showLabel />
                    <Link
                      to={`/evidence/${item.id}`}
                      style={{
                        padding: '0.35rem 0.75rem',
                        borderRadius: '4px',
                        backgroundColor: 'var(--govt-gray-light)',
                        border: '1px solid var(--govt-gray-medium)',
                        color: 'var(--govt-blue-primary)',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        textDecoration: 'none',
                      }}
                    >
                      Inspect →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right 5 Cols: Schemes Health Index & Quick Tools */}
        <div style={{ gridColumn: 'span 5', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Schemes Health Distribution */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.25rem',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <h3 style={{ margin: '0 0 0.85rem', fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              Scheme-wise Evidence Integrity
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {(projects || []).slice(0, 4).map((p) => {
                const color =
                  p.evidenceHealthScore >= 80
                    ? 'var(--govt-success)'
                    : p.evidenceHealthScore >= 50
                    ? 'var(--govt-warning)'
                    : 'var(--govt-danger)';

                return (
                  <div key={p.id}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
                      <span style={{ fontWeight: 600, color: 'var(--govt-gray-title)' }}>
                        {p.scheme}
                      </span>
                      <span style={{ fontFamily: 'monospace', fontWeight: 700, color }}>
                        {p.evidenceHealthScore}%
                      </span>
                    </div>
                    <div
                      style={{
                        width: '100%',
                        height: '6px',
                        backgroundColor: 'var(--govt-gray-light)',
                        borderRadius: '999px',
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          width: `${p.evidenceHealthScore}%`,
                          height: '100%',
                          backgroundColor: color,
                          borderRadius: '999px',
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Forensic Quick Actions Card */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.25rem',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <h3 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              Evidence Intelligence Modules
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <Link
                to="/compare"
                style={{
                  padding: '0.75rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  border: '1px solid var(--govt-gray-medium)',
                  textDecoration: 'none',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem',
                }}
              >
                <SplitSquareVertical size={18} color="var(--govt-blue-primary)" />
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                  Before / After
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>
                  Pixel-registered diff slider
                </span>
              </Link>

              <Link
                to="/map"
                style={{
                  padding: '0.75rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  border: '1px solid var(--govt-gray-medium)',
                  textDecoration: 'none',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem',
                }}
              >
                <MapPin size={18} color="var(--govt-success)" />
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                  Geospatial GIS
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>
                  Nationwide boundary map
                </span>
              </Link>

              <Link
                to="/audit"
                style={{
                  padding: '0.75rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  border: '1px solid var(--govt-gray-medium)',
                  textDecoration: 'none',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem',
                }}
              >
                <FileText size={18} color="var(--govt-warning)" />
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                  Audit Ledger
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>
                  Immutable SHA-256 trail
                </span>
              </Link>

              <Link
                to="/field"
                style={{
                  padding: '0.75rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  border: '1px solid var(--govt-gray-medium)',
                  textDecoration: 'none',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem',
                }}
              >
                <Cpu size={18} color="var(--govt-blue-primary)" />
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                  Field Companion
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>
                  Offline capture wizard
                </span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
