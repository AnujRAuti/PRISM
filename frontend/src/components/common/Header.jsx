import { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { UserIcon, SearchIcon, GlobeIcon } from './Icon';
import PrismLogo from './PrismLogo';
import { useApp } from '../../context/AppContext';
import { useAuth } from '../../context/AuthContext';
import { useI18n } from '../../i18n/I18nContext';

function Header({ onToggleSidebar }) {
  const [user, setUser] = useState(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [showLangDropdown, setShowLangDropdown] = useState(false);

  const userDropdownRef = useRef(null);
  const langDropdownRef = useRef(null);

  const navigate = useNavigate();
  const location = useLocation();
  const { logout, user: authUser } = useAuth();
  const { setIsCommandPaletteOpen, role, currentUser, loginUser, logoutUser } = useApp();
  const { language, currentLanguage, supportedLanguages, setLanguage, t } = useI18n();

  const activeUser = authUser || currentUser || user;

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

  // Close dropdowns on click outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (userDropdownRef.current && !userDropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
      if (langDropdownRef.current && !langDropdownRef.current.contains(event.target)) {
        setShowLangDropdown(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleLogout = async () => {
    try {
      if (logout) {
        await logout();
      }
    } catch (err) {
      console.error('Logout error:', err);
    }
    if (logoutUser) {
      logoutUser();
    }
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    localStorage.removeItem('eiil_current_user');
    setUser(null);
    setShowDropdown(false);
    navigate('/login', { replace: true });
  };

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
        {/* Left: Mobile Drawer Trigger + Multilingual PRISM Brand */}
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

        {/* Right Section: Language Selector, Search & User */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
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
            <span style={{ fontSize: '0.8rem' }}>{t('btn_search_placeholder', 'Search').split(' ')[0] || 'Search'}</span>
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

          {/* Multilingual Indian Language Selector */}
          <div style={{ position: 'relative' }} ref={langDropdownRef}>
            <button
              type="button"
              onClick={() => {
                setShowLangDropdown(!showLangDropdown);
                setShowDropdown(false);
              }}
              aria-expanded={showLangDropdown}
              aria-haspopup="listbox"
              aria-label="Select website language"
              title="Change language / भाषा बदलें"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.4rem 0.8rem',
                backgroundColor: showLangDropdown ? 'rgba(255, 255, 255, 0.2)' : 'rgba(255, 255, 255, 0.08)',
                border: '1px solid rgba(255, 255, 255, 0.18)',
                borderRadius: 'var(--radius-md)',
                color: '#ffffff',
                fontSize: '0.825rem',
                fontWeight: '600',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <GlobeIcon />
              <span style={{ fontSize: '0.825rem', fontWeight: 600 }}>
                {currentLanguage?.nativeName || 'English'}
              </span>
              <span
                style={{
                  fontSize: '0.62rem',
                  textTransform: 'uppercase',
                  backgroundColor: 'rgba(255, 255, 255, 0.2)',
                  padding: '0.1rem 0.35rem',
                  borderRadius: '3px',
                  color: '#f1f5f9',
                  fontFamily: 'var(--font-family-mono)',
                }}
              >
                {currentLanguage?.code || 'en'}
              </span>
              <span style={{ fontSize: '0.62rem', color: '#cbd5e1' }}>
                {showLangDropdown ? '▲' : '▼'}
              </span>
            </button>

            {showLangDropdown && (
              <div
                role="listbox"
                aria-label="Supported Indian Languages"
                style={{
                  position: 'absolute',
                  top: 'calc(100% + 0.5rem)',
                  right: 0,
                  backgroundColor: 'var(--govt-white)',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.2)',
                  width: '320px',
                  maxHeight: '460px',
                  overflowY: 'auto',
                  zIndex: 'var(--z-dropdown)',
                }}
              >
                <div
                  style={{
                    padding: '0.75rem 1rem',
                    borderBottom: '1px solid var(--govt-gray-medium)',
                    backgroundColor: 'var(--govt-gray-off-white)',
                  }}
                >
                  <div style={{ fontWeight: '700', color: 'var(--govt-gray-title)', fontSize: '0.85rem' }}>
                    {t('language_select', 'भाषा चुनें / Select Language')}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)', marginTop: '0.15rem' }}>
                    12 Official & Regional Indian Languages
                  </div>
                </div>

                <div style={{ padding: '0.4rem', display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                  {(supportedLanguages || []).map((lang) => {
                    const isSelected = lang.code === language;
                    return (
                      <button
                        key={lang.code}
                        role="option"
                        aria-selected={isSelected}
                        type="button"
                        onClick={() => {
                          setLanguage(lang.code);
                          setShowLangDropdown(false);
                        }}
                        style={{
                          width: '100%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '0.55rem 0.75rem',
                          borderRadius: 'var(--radius-sm)',
                          border: isSelected ? '1px solid var(--govt-blue-primary)' : '1px solid transparent',
                          backgroundColor: isSelected ? 'var(--govt-blue-light)' : 'transparent',
                          color: isSelected ? 'var(--govt-blue-primary)' : 'var(--govt-gray-title)',
                          cursor: 'pointer',
                          textAlign: 'left',
                          transition: 'all 0.15s ease',
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--govt-gray-off-white)';
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                          <span style={{ fontSize: '0.95rem', fontWeight: isSelected ? '700' : '600' }}>
                            {lang.nativeName}
                          </span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                            ({lang.name})
                          </span>
                          {lang.isRtl && (
                            <span
                              style={{
                                fontSize: '0.6rem',
                                padding: '0.05rem 0.35rem',
                                backgroundColor: '#ede9fe',
                                color: '#6d28d9',
                                borderRadius: '3px',
                                fontWeight: 600,
                              }}
                            >
                              RTL
                            </span>
                          )}
                        </div>
                        {isSelected && (
                          <span style={{ color: 'var(--govt-blue-primary)', fontWeight: 'bold', fontSize: '0.9rem' }}>
                            ✓
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* User Account / Role Menu */}
          <div style={{ position: 'relative' }} ref={userDropdownRef}>
            {activeUser ? (
              <>
                <button
                  onClick={() => {
                    setShowDropdown(!showDropdown);
                    setShowLangDropdown(false);
                  }}
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
                    {(activeUser?.name || 'O').charAt(0).toUpperCase()}
                  </div>
                  <div style={{ textAlign: 'left', lineHeight: 1.2 }}>
                    <div style={{ fontWeight: '600', fontSize: '0.85rem' }}>
                      {activeUser?.name || 'Operator'}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'capitalize' }}>
                      {role || activeUser?.role || 'Reviewer'}
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
                        {activeUser?.name || 'Demo Operator'}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                        {activeUser?.email || 'operator@poa.gov.in'}
                      </div>
                      <div style={{ marginTop: '0.4rem' }}>
                        <span
                          style={{
                            fontSize: '0.675rem',
                            fontWeight: 800,
                            padding: '0.15rem 0.5rem',
                            borderRadius: '999px',
                            backgroundColor:
                              (role || 'REVIEWER') === 'CITIZEN'
                                ? 'rgba(22, 101, 52, 0.15)'
                                : (role || 'REVIEWER') === 'AUDITOR'
                                ? 'rgba(126, 34, 206, 0.15)'
                                : (role || 'REVIEWER') === 'ADMIN'
                                ? 'rgba(180, 83, 9, 0.15)'
                                : 'rgba(29, 78, 216, 0.15)',
                            color:
                              (role || 'REVIEWER') === 'CITIZEN'
                                ? 'var(--govt-success)'
                                : (role || 'REVIEWER') === 'AUDITOR'
                                ? '#7e22ce'
                                : (role || 'REVIEWER') === 'ADMIN'
                                ? '#b45309'
                                : 'var(--govt-blue-primary)',
                            textTransform: 'uppercase',
                          }}
                        >
                          Role: {role || 'REVIEWER'}
                        </span>
                      </div>
                    </div>

                    {/* Quick Role Switcher */}
                    <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--govt-gray-medium)', backgroundColor: '#fff' }}>
                      <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--govt-gray-dark)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
                        Switch Operational Role
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.35rem' }}>
                        {[
                          { key: 'REVIEWER', label: '🛡️ Reviewer', path: '/dashboard' },
                          { key: 'AUDITOR', label: '⚖️ Auditor', path: '/auditor' },
                          { key: 'CITIZEN', label: '👥 Citizen', path: '/citizen' },
                          { key: 'ADMIN', label: '⚙️ Admin', path: '/admin' },
                        ].map((r) => (
                          <button
                            key={r.key}
                            type="button"
                            onClick={() => {
                              loginUser(r.key);
                              setShowDropdown(false);
                              navigate(r.path);
                            }}
                            style={{
                              padding: '0.4rem 0.5rem',
                              borderRadius: '4px',
                              border: '1px solid',
                              borderColor: (role || 'REVIEWER') === r.key ? 'var(--govt-blue-primary)' : 'var(--govt-gray-medium)',
                              backgroundColor: (role || 'REVIEWER') === r.key ? 'var(--govt-blue-light)' : 'transparent',
                              color: (role || 'REVIEWER') === r.key ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                              fontSize: '0.725rem',
                              fontWeight: (role || 'REVIEWER') === r.key ? 700 : 500,
                              cursor: 'pointer',
                              textAlign: 'left',
                            }}
                          >
                            {r.label}
                          </button>
                        ))}
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
