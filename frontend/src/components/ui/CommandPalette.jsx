import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import {
  Search,
  FolderGit2,
  FileText,
  ArrowRight,
  ShieldCheck,
  MapPin,
  X,
  SplitSquareVertical,
  BarChart3,
  Cpu,
  Smartphone
} from 'lucide-react';

export function CommandPalette() {
  const navigate = useNavigate();
  const { isCommandPaletteOpen, setIsCommandPaletteOpen, evidenceList, projects } = useApp();
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (isCommandPaletteOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isCommandPaletteOpen]);

  if (!isCommandPaletteOpen) return null;

  const quickActions = [
    { title: 'Open Review Queue', icon: FileText, href: '/reviews', badge: 'Queue' },
    { title: 'Open Before / After Comparison Tool', icon: SplitSquareVertical, href: '/compare', badge: 'Forensics' },
    { title: 'Open Geofence & Anomaly Map', icon: MapPin, href: '/map', badge: 'GIS' },
    { title: 'Open Live Ingestion Sandbox', icon: Cpu, href: '/ingest', badge: 'Sandbox' },
    { title: 'Open Immutable Event Ledger', icon: ShieldCheck, href: '/audit', badge: 'Audit' },
    { title: 'Open Program Analytics & Certificates', icon: BarChart3, href: '/analytics', badge: 'Reports' },
    { title: 'Open Field Operations (Mobile View)', icon: Smartphone, href: '/field', badge: 'Field' },
  ].filter((a) => a.title.toLowerCase().includes(query.toLowerCase()));

  const filteredEvidence = (evidenceList || []).filter(
    (e) =>
      e.id.toLowerCase().includes(query.toLowerCase()) ||
      e.title.toLowerCase().includes(query.toLowerCase()) ||
      e.sha256.toLowerCase().includes(query.toLowerCase()) ||
      e.location?.district?.toLowerCase().includes(query.toLowerCase()) ||
      e.scheme?.toLowerCase().includes(query.toLowerCase())
  ).slice(0, 5);

  const filteredProjects = (projects || []).filter(
    (p) =>
      p.id.toLowerCase().includes(query.toLowerCase()) ||
      p.name.toLowerCase().includes(query.toLowerCase()) ||
      p.state.toLowerCase().includes(query.toLowerCase()) ||
      p.scheme.toLowerCase().includes(query.toLowerCase())
  ).slice(0, 4);

  const allResults = [
    ...quickActions.map((a) => ({
      type: 'action',
      id: a.href,
      title: a.title,
      subtitle: a.badge,
      href: a.href,
      icon: a.icon,
    })),
    ...filteredEvidence.map((e) => ({
      type: 'evidence',
      id: e.id,
      title: `${e.id} • ${e.title}`,
      subtitle: `${e.scheme} • ${e.location?.district}, ${e.location?.state} • Score: ${e.integrityScore}%`,
      href: `/evidence/${e.id}`,
      icon: FileText,
    })),
    ...filteredProjects.map((p) => ({
      type: 'project',
      id: p.id,
      title: `${p.id} • ${p.name}`,
      subtitle: `${p.scheme} • ${p.district}, ${p.state} • Budget: ₹${(p.budgetInr / 10000000).toFixed(2)} Cr`,
      href: `/projects/${p.id}`,
      icon: FolderGit2,
    })),
  ];

  const handleSelect = (item) => {
    setIsCommandPaletteOpen(false);
    navigate(item.href);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % (allResults.length || 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + (allResults.length || 1)) % (allResults.length || 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (allResults[selectedIndex]) {
        handleSelect(allResults[selectedIndex]);
      }
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Global Search and Command Palette"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        padding: '5rem 1rem 1rem',
        backgroundColor: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(4px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setIsCommandPaletteOpen(false);
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '640px',
          backgroundColor: '#ffffff',
          borderRadius: 'var(--radius-lg, 12px)',
          border: '1px solid var(--govt-gray-medium, #e2e8f0)',
          boxShadow: 'var(--shadow-xl, 0 25px 50px -12px rgba(0, 0, 0, 0.25))',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Search Input Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '1rem 1.25rem',
            borderBottom: '1px solid var(--govt-gray-medium, #e2e8f0)',
            backgroundColor: 'var(--govt-gray-off-white, #f8fafc)',
          }}
        >
          <Search size={20} color="var(--govt-blue-primary, #1d4ed8)" style={{ flexShrink: 0 }} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Type a command, project, evidence ID, or SHA-256 hash..."
            style={{
              flex: 1,
              border: 'none',
              backgroundColor: 'transparent',
              fontSize: '0.95rem',
              color: 'var(--govt-gray-title, #0f172a)',
              outline: 'none',
              fontFamily: 'inherit',
            }}
          />
          <kbd
            style={{
              padding: '0.15rem 0.4rem',
              borderRadius: '4px',
              backgroundColor: 'var(--govt-gray-light, #f1f5f9)',
              border: '1px solid var(--govt-gray-medium, #e2e8f0)',
              fontSize: '0.7rem',
              fontWeight: 600,
              color: 'var(--govt-gray-dark, #64748b)',
            }}
          >
            ESC
          </kbd>
        </div>

        {/* Results List */}
        <div style={{ maxHeight: '380px', overflowY: 'auto', padding: '0.5rem' }}>
          {allResults.length === 0 ? (
            <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--govt-gray-dark)' }}>
              No matches found for "{query}".
            </div>
          ) : (
            allResults.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              const Icon = item.icon || FileText;

              return (
                <div
                  key={`${item.type}-${item.id}`}
                  onClick={() => handleSelect(item)}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    backgroundColor: isSelected ? 'var(--govt-blue-light, #eff6ff)' : 'transparent',
                    border: isSelected ? '1px solid var(--govt-blue-accent, #2563eb)' : '1px solid transparent',
                    transition: 'background-color 0.1s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
                    <div
                      style={{
                        padding: '0.35rem',
                        borderRadius: '6px',
                        backgroundColor: isSelected ? '#ffffff' : 'var(--govt-gray-light, #f1f5f9)',
                        color: isSelected ? 'var(--govt-blue-primary, #1d4ed8)' : 'var(--govt-gray-dark, #64748b)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <Icon size={16} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: '0.85rem',
                          fontWeight: 600,
                          color: isSelected ? 'var(--govt-blue-primary, #1d4ed8)' : 'var(--govt-gray-title, #0f172a)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {item.title}
                      </div>
                      <div
                        style={{
                          fontSize: '0.75rem',
                          color: 'var(--govt-gray-dark, #64748b)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {item.subtitle}
                      </div>
                    </div>
                  </div>
                  <ArrowRight
                    size={14}
                    color={isSelected ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)'}
                    style={{ flexShrink: 0, marginLeft: '0.5rem' }}
                  />
                </div>
              );
            })
          )}
        </div>

        {/* Footer Shortcut Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.5rem 1.25rem',
            borderTop: '1px solid var(--govt-gray-medium, #e2e8f0)',
            backgroundColor: 'var(--govt-gray-off-white, #f8fafc)',
            fontSize: '0.75rem',
            color: 'var(--govt-gray-dark, #64748b)',
          }}
        >
          <span>Use ↑ ↓ to navigate</span>
          <span>Press ↵ to select</span>
        </div>
      </div>
    </div>
  );
}

export default CommandPalette;
