import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import { getProjectImage } from '../../data/mockDataset';
import {
  FolderGit2,
  MapPin,
  Calendar,
  Building2,
  ExternalLink,
  Search,
  Filter,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';

export default function ProjectsList() {
  const { projects } = useApp();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedScheme, setSelectedScheme] = useState('ALL');

  const filteredProjects = (projects || []).filter((p) => {
    if (selectedScheme !== 'ALL' && !p.scheme?.includes(selectedScheme)) return false;
    if (searchTerm.trim() !== '') {
      const q = searchTerm.toLowerCase();
      const match =
        p.id?.toLowerCase().includes(q) ||
        p.name?.toLowerCase().includes(q) ||
        p.district?.toLowerCase().includes(q) ||
        p.state?.toLowerCase().includes(q) ||
        p.contractor?.toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });

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
                fontWeight: 800,
                color: 'var(--govt-blue-dark, #0f172a)',
                letterSpacing: '-0.02em',
              }}
            >
              Public Works Projects Directory
            </h1>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '4px',
                backgroundColor: 'var(--govt-gray-light)',
                border: '1px solid var(--govt-gray-medium)',
                color: 'var(--govt-gray-title)',
                fontWeight: 700,
                fontFamily: 'monospace',
              }}
            >
              {filteredProjects.length} Schemes Monitored
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
            Centralized registry of state infrastructure schemes, geofence polygons, and cumulative evidence health scores.
          </p>
        </div>

        {/* Search & Filter Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.45rem 0.75rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <Search size={14} color="var(--govt-gray-dark)" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search scheme, district, ID..."
              style={{
                border: 'none',
                outline: 'none',
                fontSize: '0.8rem',
                width: '180px',
              }}
            />
          </div>

          <select
            value={selectedScheme}
            onChange={(e) => setSelectedScheme(e.target.value)}
            style={{
              padding: '0.45rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--govt-gray-medium)',
              backgroundColor: '#ffffff',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <option value="ALL">All Schemes</option>
            <option value="PMGSY">PMGSY (Rural Roads)</option>
            <option value="Jal Jeevan">Jal Jeevan Mission</option>
            <option value="Samagra">Samagra Shiksha</option>
            <option value="KUSUM">PM-KUSUM</option>
          </select>
        </div>
      </div>

      {/* Projects Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.25rem' }}>
        {filteredProjects.map((p) => (
          <div
            key={p.id}
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              boxShadow: 'var(--shadow-sm)',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
            }}
          >
            <div>
              {/* Card Image Banner */}
              <div style={{ aspectRatio: '16/9', backgroundColor: '#0f172a', position: 'relative', overflow: 'hidden' }}>
                <img
                  src={p.imageUrl || getProjectImage(p.id)}
                  alt={p.name}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
                <div
                  style={{
                    position: 'absolute',
                    top: '0.75rem',
                    left: '0.75rem',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: 'rgba(15, 23, 42, 0.85)',
                    color: '#ffffff',
                    fontFamily: 'monospace',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                  }}
                >
                  {p.id}
                </div>
                <div
                  style={{
                    position: 'absolute',
                    top: '0.75rem',
                    right: '0.75rem',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: p.flaggedCount > 0 ? 'var(--govt-danger)' : 'var(--govt-success)',
                    color: '#ffffff',
                    fontSize: '0.7rem',
                    fontWeight: 700,
                  }}
                >
                  {p.flaggedCount > 0 ? `${p.flaggedCount} Flags` : 'Verified Clean'}
                </div>
              </div>

              {/* Card Body */}
              <div style={{ padding: '1.25rem' }}>
                <span
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: 'var(--govt-blue-primary)',
                    display: 'block',
                    marginBottom: '0.25rem',
                  }}
                >
                  {p.scheme}
                </span>
                <h3
                  style={{
                    margin: '0 0 0.5rem',
                    fontSize: '1rem',
                    fontWeight: 700,
                    color: 'var(--govt-gray-title)',
                    lineHeight: 1.35,
                  }}
                >
                  {p.name}
                </h3>

                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.35rem',
                    fontSize: '0.775rem',
                    color: 'var(--govt-gray-dark)',
                    marginTop: '0.75rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    <MapPin size={13} /> {p.district}, {p.state} ({p.block} Block)
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    <Building2 size={13} /> Contractor: {p.contractor}
                  </div>
                  <div>
                    Sanctioned Budget:{' '}
                    <strong style={{ color: 'var(--govt-gray-title)' }}>
                      ₹{(p.budgetInr / 10000000).toFixed(2)} Cr
                    </strong>{' '}
                    • Geofence: {p.geofenceRadiusMeters}m
                  </div>
                </div>
              </div>
            </div>

            {/* Card Footer */}
            <div
              style={{
                padding: '0.85rem 1.25rem',
                backgroundColor: 'var(--govt-gray-off-white)',
                borderTop: '1px solid var(--govt-gray-medium)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <IntegrityArc score={p.evidenceHealthScore} size="sm" showLabel />
                <div>
                  <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', display: 'block' }}>Health Index</span>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-gray-title)' }}>
                    {p.totalSubmissions} records
                  </span>
                </div>
              </div>

              <Link
                to={`/projects/${p.id}`}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  padding: '0.4rem 0.85rem',
                  borderRadius: '4px',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textDecoration: 'none',
                }}
              >
                <span>Dossier</span>
                <ArrowRight size={13} />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
