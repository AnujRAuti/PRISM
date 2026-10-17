import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import {
  DashboardIcon,
  ProjectIcon,
  EvidenceIcon,
  ReviewIcon,
  SearchIcon,
  UserIcon,
  GraphIcon,
  AdminIcon,
} from './Icon';

const navSections = [
  {
    category: 'OPERATIONS',
    items: [
      { path: '/dashboard', label: 'Dashboard', icon: DashboardIcon },
      { path: '/reviews', label: 'Review Queue', icon: ReviewIcon, badgeKey: 'pending' },
      { path: '/projects', label: 'Projects', icon: ProjectIcon },
      { path: '/ingest', label: 'Live Sandbox', icon: EvidenceIcon },
      { path: '/field', label: 'Field Companion', icon: UserIcon },
    ]
  },
  {
    category: 'INTELLIGENCE & AUDIT',
    items: [
      { path: '/compare', label: 'Visual Comparator', icon: GraphIcon },
      { path: '/map', label: 'Geospatial Map', icon: ProjectIcon },
      { path: '/audit', label: 'Audit Ledger', icon: SearchIcon },
      { path: '/analytics', label: 'Analytics & Certs', icon: AdminIcon },
    ]
  },
  {
    category: 'GOVERNANCE',
    items: [
      { path: '/settings', label: 'System Settings', icon: AdminIcon },
      { path: '/about', label: 'About Platform', icon: EvidenceIcon },
      { path: '/profile', label: 'Operator Profile', icon: UserIcon },
    ]
  }
];

function Sidebar({ isOpen = false, onClose }) {
  const [activeItem, setActiveItem] = useState('');
  const location = useLocation();
  const { evidenceList } = useApp();

  const pendingCount = (evidenceList || []).filter(
    (e) => e.auditStatus === 'PENDING' || e.auditStatus === 'FLAGGED'
  ).length;

  useEffect(() => {
    setActiveItem(location.pathname);
  }, [location]);

  return (
    <aside
      aria-label="Portal Navigation"
      className={`app-sidebar ${isOpen ? 'sidebar-open' : ''}`}
      style={{
        width: '240px',
        backgroundColor: 'var(--govt-white)',
        borderRight: '1px solid var(--govt-gray-medium)',
        minHeight: 'calc(100vh - 68px)',
        padding: '1.25rem 0',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        boxShadow: 'var(--shadow-xs)',
      }}
    >
      {/* Mobile Drawer Header with Close Button */}
      <div
        className="mobile-sidebar-header"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 1.25rem 1rem 1.25rem',
          borderBottom: '1px solid var(--govt-gray-medium)',
          marginBottom: '1rem',
        }}
      >
        <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)', letterSpacing: '0.5px' }}>
          NAVIGATION
        </span>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation menu"
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.25rem',
              color: 'var(--govt-gray-dark)',
              cursor: 'pointer',
              padding: '0.2rem 0.4rem',
              borderRadius: '4px',
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        )}
      </div>

      <nav aria-label="Main Sections" style={{ flex: 1 }}>
        {navSections.map((section, idx) => (
          <div key={section.category} style={{ marginBottom: '1.25rem' }}>
            <div
              style={{
                fontSize: '0.675rem',
                fontWeight: 700,
                color: 'var(--govt-gray-dark)',
                padding: '0 1.25rem 0.4rem 1.25rem',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
              }}
            >
              {section.category}
            </div>

            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive = activeItem === item.path || (item.path !== '/dashboard' && activeItem.startsWith(item.path));
                const badgeValue = item.badgeKey === 'pending' ? pendingCount : item.badge;

                return (
                  <li key={item.path} style={{ margin: '1px 0' }}>
                    <Link
                      to={item.path}
                      onClick={() => {
                        if (onClose) onClose();
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.55rem 1.25rem',
                        fontSize: '0.825rem',
                        fontWeight: isActive ? '700' : '500',
                        color: isActive ? 'var(--govt-blue-primary)' : 'var(--govt-gray-text)',
                        backgroundColor: isActive ? 'var(--govt-blue-light)' : 'transparent',
                        borderLeft: isActive ? '3.5px solid var(--govt-blue-primary)' : '3.5px solid transparent',
                        textDecoration: 'none',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <Icon active={isActive} />
                        <span>{item.label}</span>
                      </div>

                      {badgeValue && (
                        <span
                          style={{
                            fontSize: '0.675rem',
                            fontWeight: 700,
                            padding: '0.1rem 0.45rem',
                            borderRadius: '999px',
                            backgroundColor: isActive ? 'var(--govt-blue-primary)' : 'var(--govt-gray-light)',
                            color: isActive ? '#ffffff' : 'var(--govt-gray-title)',
                            fontFamily: 'var(--font-family-mono)',
                          }}
                        >
                          {badgeValue}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Trust & Cryptographic Integrity Strip at Bottom */}
      <div
        style={{
          padding: '0.85rem 1.25rem',
          borderTop: '1px solid var(--govt-gray-medium)',
          backgroundColor: 'var(--govt-gray-off-white)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.2rem' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--govt-success)' }} />
          <span style={{ fontSize: '0.725rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            EIIL Node Verified
          </span>
        </div>
        <p style={{ margin: 0, fontSize: '0.675rem', color: 'var(--govt-gray-dark)', lineHeight: 1.3 }}>
          Statutory Public Works Provenance pursuant to Section 86
        </p>
      </div>
    </aside>
  );
}

export default Sidebar;
