import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { UserIcon, SearchIcon } from './Icon';
import PrismLogo from './PrismLogo';
import { useApp } from '../../context/AppContext';

function Header({ onToggleSidebar }) {
  const [user, setUser] = useState(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { setIsCommandPaletteOpen } = useApp();

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        setUser(null);
      }
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const navLinks = [
    { path: '/dashboard', label: 'Dashboard' },
    { path: '/projects', label: 'Projects' },
    { path: '/evidence', label: 'Evidence' },
    { path: '/graph', label: 'Evidence Graph' },
    { path: '/reviews', label: 'Reviews' },
    { path: '/search', label: 'Advanced Search' },
    { path: '/admin', label: 'Admin Portal' },
  ];

  return (
    <header
      role="banner"
      aria-label="Government of India - PRISM Evidence Intelligence Portal"
      style={{
        backgroundColor: 'var(--govt-blue-dark)',
        color: '#ffffff',
        padding: '0',
        borderBottom: '1px solid rgba(226, 232, 240, 0.15)',
        position: 'sticky',
        top: 0,
        zIndex: 'var(--z-sticky)',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: '64px',
          padding: '0 1.25rem',
          width: '100%',
          boxSizing: 'border-box',
        }}
      >
        {/* Left: Mobile Drawer Trigger + Animated Multilingual PRISM Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {onToggleSidebar && (
            <button
              type="button"
              onClick={onToggleSidebar}
              className="mobile-menu-btn"
              aria-label="Open portal navigation menu"
              style={{
                display: 'none',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: 'rgba(255, 255, 255, 0.12)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                color: '#ffffff',
                borderRadius: 'var(--radius-sm)',
                padding: '0.4rem 0.6rem',
                fontSize: '1.1rem',
                cursor: 'pointer',
              }}
            >
              ☰
            </button>
          )}
          <PrismLogo />
        </div>

        {/* Right Section: Search & User */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {/* Quick Search Button Shortcut */}
          <button
            type="button"
            onClick={() => setIsCommandPaletteOpen(true)}
            aria-label="Quick Search"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.4rem 0.9rem',
              backgroundColor: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: 'var(--radius-md)',
              color: '#cbd5e1',
              fontSize: '0.825rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <SearchIcon />
            <span style={{ fontSize: '0.8rem' }}>Search</span>
            <kbd
              style={{
                fontSize: '0.65rem',
                backgroundColor: 'rgba(255, 255, 255, 0.12)',
                padding: '0.1rem 0.35rem',
                borderRadius: '3px',
                color: '#94a3b8',
                fontFamily: 'var(--font-family-mono)',
              }}
            >
              /
            </kbd>
          </button>
          <div style={{ position: 'relative' }}>
            {user ? (
              <>
                <button
                  onClick={() => setShowDropdown(!showDropdown)}
                  aria-expanded={showDropdown}
                  aria-haspopup="true"
                  aria-label="User account menu"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    padding: '0.4rem 0.85rem',
                    backgroundColor: 'rgba(255, 255, 255, 0.08)',
                    border: '1px solid rgba(255, 255, 255, 0.18)',
                    borderRadius: 'var(--radius-full)',
                    color: '#ffffff',
                    cursor: 'pointer',
                    fontSize: '0.875rem',
                    transition: 'background 0.2s ease',
                  }}
                >
                  <div
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      backgroundColor: 'var(--govt-blue-primary)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#ffffff',
                      fontWeight: '700',
                      fontSize: '0.8rem',
                    }}
                  >
                    {(user.name || user.username || 'U').charAt(0).toUpperCase()}
                  </div>
                  <div style={{ textAlign: 'left', lineHeight: 1.2 }}>
                    <div style={{ fontWeight: '600', fontSize: '0.85rem' }}>
                      {user.name || user.username || 'Operator'}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'capitalize' }}>
                      {user.role || 'Reviewer'}
                    </div>
                  </div>
                  <span style={{ fontSize: '0.65rem', color: '#94a3b8', marginLeft: '0.2rem' }}>▼</span>
                </button>

                {showDropdown && (
                  <div
                    style={{
                      position: 'absolute',
                      top: 'calc(100% + 0.5rem)',
                      right: 0,
                      backgroundColor: 'var(--govt-white)',
                      border: '1px solid var(--govt-gray-medium)',
                      borderRadius: 'var(--radius-md)',
                      boxShadow: 'var(--shadow-lg)',
                      minWidth: '200px',
                      zIndex: 'var(--z-dropdown)',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        padding: '0.85rem 1rem',
                        borderBottom: '1px solid var(--govt-gray-medium)',
                        backgroundColor: 'var(--govt-gray-off-white)',
                      }}
                    >
                      <div style={{ fontWeight: '700', color: 'var(--govt-gray-title)', fontSize: '0.875rem' }}>
                        {user.name || 'Demo Operator'}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                        {user.email || 'operator@poa.gov.in'}
                      </div>
                    </div>

                    <Link
                      to="/profile"
                      onClick={() => setShowDropdown(false)}
                      style={{
                        display: 'block',
                        padding: '0.75rem 1rem',
                        color: 'var(--govt-gray-text)',
                        textDecoration: 'none',
                        fontSize: '0.85rem',
                        fontWeight: '500',
                        borderBottom: '1px solid var(--govt-gray-light)',
                      }}
                    >
                      Operator Profile & Credentials
                    </Link>
                    <Link
                      to="/settings"
                      onClick={() => setShowDropdown(false)}
                      style={{
                        display: 'block',
                        padding: '0.75rem 1rem',
                        color: 'var(--govt-gray-text)',
                        textDecoration: 'none',
                        fontSize: '0.85rem',
                        fontWeight: '500',
                        borderBottom: '1px solid var(--govt-gray-light)',
                      }}
                    >
                      System Settings & Integration APIs
                    </Link>
                    <button
                      onClick={handleLogout}
                      style={{
                        display: 'block',
                        width: '100%',
                        padding: '0.75rem 1rem',
                        backgroundColor: 'transparent',
                        border: 'none',
                        color: 'var(--govt-danger)',
                        cursor: 'pointer',
                        textAlign: 'left',
                        fontSize: '0.85rem',
                        fontWeight: '600',
                      }}
                    >
                      Sign Out
                    </button>
                  </div>
                )}
              </>
            ) : (
              <Link
                to="/login"
                style={{
                  padding: '0.5rem 1.25rem',
                  backgroundColor: 'var(--govt-blue-primary)',
                  borderRadius: 'var(--radius-sm)',
                  color: '#ffffff',
                  textDecoration: 'none',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                }}
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

export default Header;
