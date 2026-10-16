import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

const INDIAN_LANGUAGES = [
  { name: 'PRISM', lang: 'English', code: 'EN', subtitle: 'Evidence Integrity & Intelligence' },
  { name: 'प्रिज़्म', lang: 'हिन्दी', code: 'HI', subtitle: 'साक्ष्य सत्यनिष्ठा एवं विश्लेषण प्रणाली' },
  { name: 'প্রিজম', lang: 'বাংলা', code: 'BN', subtitle: 'প্রমাণ অখণ্ডতা ও যাচাইকরণ স্তর' },
  { name: 'ప్రిజమ్', lang: 'తెలుగు', code: 'TE', subtitle: 'సాక్ష్య సమగ్రత & నిఘా వ్యవస్థ' },
  { name: 'பிரிசம்', lang: 'தமிழ்', code: 'TA', subtitle: 'சான்று ஒருமைப்பாடு மற்றும் சரிபார்ப்பு' },
  { name: 'प्रिझम', lang: 'मराठी', code: 'MR', subtitle: 'पुरावा सत्यता आणि पडताळणी प्रणाली' },
  { name: 'પ્રિઝમ', lang: 'ગુજરાતી', code: 'GU', subtitle: 'પુરાવા અખંડિતતા અને વિશ્લેષણ સ્તર' },
  { name: 'ಪ್ರಿಸಂ', lang: 'ಕನ್ನಡ', code: 'KN', subtitle: 'ಸಾಕ್ಷ್ಯ ಸಮಗ್ರತೆ ಮತ್ತು ದೃಢೀಕರಣ ವ್ಯವಸ್ಥೆ' },
  { name: 'പ്രിസം', lang: 'മലയാളം', code: 'ML', subtitle: 'തെളിവ് സമഗ്രതയും ബുദ്ധിപരമായ പരിശോധനയും' },
  { name: 'ਪ੍ਰਿਜ਼ਮ', lang: 'ਪੰਜਾਬੀ', code: 'PA', subtitle: 'ਸਬੂਤ ਅਖੰਡਤਾ ਅਤੇ ਪੜਤਾਲ ਪ੍ਰਣਾਲੀ' },
  { name: 'ପ୍ରିଜିମ୍', lang: 'ଓଡ଼ିଆ', code: 'OD', subtitle: 'ପ୍ରମାଣ ଅଖଣ୍ଡତା ଏବଂ ଯାଞ୍ଚ ପ୍ରଣାଳୀ' },
];

function PrismLogo({ size = 'md', showSubtitle = true, linkTo = '/dashboard' }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [animating, setAnimating] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setAnimating(true);
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % INDIAN_LANGUAGES.length);
        setAnimating(false);
      }, 300);
    }, 2800);

    return () => clearInterval(interval);
  }, []);

  const current = INDIAN_LANGUAGES[currentIndex];
  const emblemDim = size === 'lg' ? 52 : size === 'sm' ? 34 : 44;
  const iconDim = size === 'lg' ? 38 : size === 'sm' ? 24 : 32;

  const content = (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: size === 'sm' ? '0.6rem' : '0.85rem',
        textDecoration: 'none',
        color: '#ffffff',
        outline: 'none',
      }}
      aria-label={`PRISM - ${current.name} (${current.lang})`}
    >
      {/* Authentic Glowing Prism Emblem */}
      <div
        style={{
          position: 'relative',
          width: `${emblemDim}px`,
          height: `${emblemDim}px`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: size === 'sm' ? '8px' : '12px',
          background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 58, 138, 0.5) 100%)',
          border: '1.5px solid rgba(168, 85, 247, 0.45)',
          boxShadow: '0 0 18px rgba(168, 85, 247, 0.35)',
          overflow: 'hidden',
          flexShrink: 0,
        }}
      >
        {/* Subtle background refraction glow */}
        <div
          style={{
            position: 'absolute',
            inset: '-50%',
            background: 'conic-gradient(from 180deg at 50% 50%, rgba(6, 182, 212, 0.2) 0deg, rgba(168, 85, 247, 0.3) 120deg, rgba(236, 72, 153, 0.3) 240deg, rgba(6, 182, 212, 0.2) 360deg)',
            animation: 'spin 14s linear infinite',
            pointerEvents: 'none',
          }}
        />

        {/* User's authentic PRISM crystal emblem */}
        <img
          src="/prism-symbol-transparent.png"
          alt="PRISM"
          style={{
            width: `${iconDim}px`,
            height: `${iconDim}px`,
            objectFit: 'contain',
            position: 'relative',
            zIndex: 2,
            filter: 'drop-shadow(0 0 8px rgba(168, 85, 247, 0.7))',
            animation: 'prism-pulse 3s ease-in-out infinite',
          }}
        />
      </div>

      {/* Multilingual Text & Subtitle */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span
            style={{
              fontSize: '1.45rem',
              fontWeight: '800',
              letterSpacing: current.code === 'EN' ? '2.5px' : '0.5px',
              color: '#ffffff',
              fontFamily: 'var(--font-family-primary)',
              textShadow: '0 2px 10px rgba(56, 189, 248, 0.4)',
              transition: 'all 0.28s cubic-bezier(0.4, 0, 0.2, 1)',
              opacity: animating ? 0 : 1,
              transform: animating ? 'translateY(4px)' : 'translateY(0)',
              display: 'inline-block',
            }}
          >
            {current.name}
          </span>

          {/* Subtle Language Indicator */}
          <span
            style={{
              fontSize: '0.72rem',
              fontWeight: '500',
              color: '#94a3b8',
              letterSpacing: '0.02em',
              transition: 'opacity 0.25s ease',
              opacity: animating ? 0.3 : 1,
            }}
          >
            · {current.lang}
          </span>
        </div>

        {/* Subtitle */}
        {showSubtitle && (
          <span
            style={{
              fontSize: size === 'sm' ? '0.65rem' : '0.72rem',
              color: '#94a3b8',
              fontWeight: '500',
              letterSpacing: '0.3px',
              whiteSpace: 'nowrap',
              transition: 'opacity 0.28s ease',
              opacity: animating ? 0 : 1,
            }}
          >
            {current.subtitle}
          </span>
        )}
      </div>
    </div>
  );

  if (linkTo) {
    return (
      <Link to={linkTo} style={{ textDecoration: 'none', display: 'inline-flex', outline: 'none' }}>
        {content}
      </Link>
    );
  }

  return content;
}

export default PrismLogo;
