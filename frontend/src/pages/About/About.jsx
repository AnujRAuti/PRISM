import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import {
  ShieldCheck,
  ShieldAlert,
  Layers,
  MapPin,
  Clock,
  Camera,
  FileCheck2,
  ArrowRight,
  Sparkles,
  Info,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

export default function About() {
  const [demoScore, setDemoScore] = useState(88);

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Editorial Hero Section */}
      <div style={{ maxWidth: '800px', marginBottom: '2.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <span
            style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--govt-blue-primary)',
            }}
          >
            DIGITAL PUBLIC INFRASTRUCTURE (DPI) • STATUTORY PROVENANCE
          </span>
        </div>

        <h1
          style={{
            margin: '0 0 1rem',
            fontSize: '2.25rem',
            fontWeight: 800,
            color: 'var(--govt-blue-dark)',
            letterSpacing: '-0.02em',
            lineHeight: 1.2,
          }}
        >
          We don't collect more evidence; we make existing evidence trustworthy.
        </h1>

        <p
          style={{
            margin: 0,
            fontSize: '1rem',
            color: 'var(--govt-gray-text)',
            lineHeight: 1.6,
          }}
        >
          <strong>PRISM / Proof-of-Action (PoA)</strong> is an Indian government-grade evidence intelligence layer that audits evidence already submitted for public-works projects (roads, piped water, school repairs, solar installations) to detect whether it is spatially, temporally, visually, and cross-project consistent.
        </p>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginTop: '1.5rem' }}>
          <Link
            to="/reviews"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.65rem 1.25rem',
              borderRadius: '6px',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              fontSize: '0.85rem',
              fontWeight: 700,
              textDecoration: 'none',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <span>Open Reviewer Queue</span>
            <ArrowRight size={16} />
          </Link>
          <Link
            to="/ingest"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.65rem 1.25rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              color: 'var(--govt-blue-dark)',
              fontSize: '0.85rem',
              fontWeight: 600,
              textDecoration: 'none',
            }}
          >
            <Sparkles size={16} color="var(--govt-blue-primary)" />
            <span>Try Live Pipeline Sandbox</span>
          </Link>
        </div>
      </div>

      {/* 7-Signal Fusion Pipeline Cards */}
      <div style={{ marginBottom: '2.5rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '1rem' }}>
          The 7-Signal Evidence Intelligence Pipeline
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
          {[
            {
              title: '1. Cryptographic Binary Seal',
              desc: 'Every file is immediately hashed with SHA-256 before upload. Tampering with even 1 pixel alters the hash completely.',
              icon: ShieldCheck,
            },
            {
              title: '2. Sub-Decameter Geofence Boundary',
              desc: 'Haversine distance comparison between EXIF camera GPS and sanctioned project centroid polygon bounds.',
              icon: MapPin,
            },
            {
              title: '3. Sensor & Timestamp Chronology',
              desc: 'Validates capture timestamps against upload times, solar elevation, and sequential milestones.',
              icon: Clock,
            },
            {
              title: '4. Cross-Project Embedding Corpus',
              desc: 'Vector similarity search over nationwide public works corpus to intercept recycled photographs across districts.',
              icon: Layers,
            },
            {
              title: '5. Impossible Travel Trajectory',
              desc: 'Detects physically impossible transit velocity (>120 km/h) between successive uploads by the same field officer.',
              icon: Camera,
            },
            {
              title: '6. Structural Computer Vision Transformation',
              desc: 'Verifies pixel-registered change between before and after milestone submissions (e.g. asphalt carpet vs raw gravel).',
              icon: FileCheck2,
            },
          ].map((signal) => {
            const Icon = signal.icon;
            return (
              <div
                key={signal.title}
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: '8px',
                  padding: '1.25rem',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <Icon size={18} color="var(--govt-blue-primary)" />
                  <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                    {signal.title}
                  </h3>
                </div>
                <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)', lineHeight: 1.45 }}>
                  {signal.desc}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Interactive Integrity Score Demonstration */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium)',
          borderRadius: 'var(--radius-lg, 12px)',
          padding: '2rem',
          boxShadow: 'var(--shadow-sm)',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '2rem',
        }}
      >
        <div style={{ maxWidth: '540px' }}>
          <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.15rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            Interactive Integrity Arc Scoring
          </h3>
          <p style={{ margin: '0 0 1rem', fontSize: '0.85rem', color: 'var(--govt-gray-dark)', lineHeight: 1.5 }}>
            Adjust the slider to see how PRISM dynamically classifies statutory risk levels and issues disbursement recommendations:
          </p>

          <input
            type="range"
            min="0"
            max="100"
            value={demoScore}
            onChange={(e) => setDemoScore(Number(e.target.value))}
            style={{ width: '100%', cursor: 'pointer' }}
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--govt-gray-dark)', marginTop: '0.35rem' }}>
            <span>0% (Critical Anomaly)</span>
            <span>50% (Under Review)</span>
            <span>100% (Fully Verified)</span>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
          <IntegrityArc score={demoScore} size="lg" showRiskBadge />
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-gray-title)' }}>
            {demoScore >= 80 ? '✓ Ready for Disbursal' : demoScore >= 50 ? '⚠ Requires Field Inspection' : '✕ Immediate Audit Hold'}
          </span>
        </div>
      </div>
    </div>
  );
}
