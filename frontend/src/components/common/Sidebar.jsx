import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
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
      { path: '/projects', label: 'Projects', icon: ProjectIcon },
      { path: '/evidence', label: 'Evidence', icon: EvidenceIcon },
    ]
  },
  {
    category: 'INTELLIGENCE & AUDIT',
    items: [
      { path: '/graph', label: 'Evidence Graph', icon: GraphIcon },
      { path: '/review', label: 'Review Queue', icon: ReviewIcon, badge: '24' },
      { path: '/search', label: 'Advanced Search', icon: SearchIcon },
    ]
  },
  {
    category: 'GOVERNANCE',
    items: [
      { path: '/admin', label: 'Admin Portal', icon: AdminIcon },
      { path: '/profile', label: 'Operator Profile', icon: UserIcon },
    ]
  }
];

function Sidebar({ isOpen = false, onClose }) {
  const [activeItem, setActiveItem] = useState('');
  const location = useLocation();

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
        {navSections.map((sec, secIdx) => (
          <div key={secIdx} style={{ marginBottom: '1.25rem' }}>
            <div
              style={{
                padding: '0 1.25rem 0.5rem 1.25rem',
                fontSize: '0.68rem',
                fontWeight: '700',
                color: 'var(--govt-gray-dark)',
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}
            >
              {sec.category}
            </div>

            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {sec.items.map((item) => {
                const Icon = item.icon;
                const isActive = activeItem === item.path || (item.path !== '/' && activeItem.startsWith(item.path + '/'));

                return (
                  <li key={item.path} style={{ margin: '0.15rem 0.75rem' }}>
                    <Link
                      to={item.path}
                      onClick={() => {
                        if (onClose) onClose();
                      }}
                      aria-current={isActive ? 'page' : undefined}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.625rem 0.85rem',
                        color: isActive ? 'var(--govt-blue-primary)' : 'var(--govt-gray-text)',
                        backgroundColor: isActive ? 'var(--govt-blue-light)' : 'transparent',
                        textDecoration: 'none',
                        borderRadius: 'var(--radius-md)',
                        transition: 'all 0.18s ease',
                        fontSize: '0.875rem',
                        fontWeight: isActive ? '700' : '500',
                        borderLeft: isActive ? '3px solid var(--govt-blue-primary)' : '3px solid transparent',
                      }}
                      onMouseEnter={(e) => {
                        if (!isActive) {
                          e.currentTarget.style.backgroundColor = 'var(--govt-gray-light)';
                          e.currentTarget.style.color = 'var(--govt-blue-dark)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isActive) {
                          e.currentTarget.style.backgroundColor = 'transparent';
                          e.currentTarget.style.color = 'var(--govt-gray-text)';
                        }
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <span style={{
                          flexShrink: 0,
                          color: isActive ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                          display: 'flex',
                          alignItems: 'center',
                        }}>
                          <Icon />
                        </span>
                        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {item.label}
                        </span>
                      </div>

                      {item.badge && (
                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: '600',
                            padding: '0.1rem 0.45rem',
                            borderRadius: '9999px',
                            backgroundColor: 'var(--govt-gray-light)',
                            color: 'var(--govt-gray-dark)',
                            border: '1px solid var(--govt-gray-medium)',
                          }}
                        >
                          {item.badge}
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

      {/* Sidebar System Footer */}
      <div
        style={{
          padding: '1rem 1.25rem',
          borderTop: '1px solid var(--govt-gray-medium)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>PRISM Engine</span>
        <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)', fontWeight: 500 }}>v1.0.0</span>
      </div>
    </aside>
  );
}

export default Sidebar;
