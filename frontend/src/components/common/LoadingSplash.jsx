import { useState, useEffect, useRef } from 'react';

// Character sets from official Indian languages mapped to each letter of "PRISM"
const SCRIPT_POOLS = [
  // P
  { target: 'P', glyphs: ['प', 'প্র', 'ప', 'ப', 'ਪ', 'ପ', 'પ', 'ಪ್', 'പ'] },
  // R
  { target: 'R', glyphs: ['र', 'র', 'ర', 'ர', 'ਰ', 'ର', 'ર', 'ರ್', 'ര'] },
  // I
  { target: 'I', glyphs: ['इ', 'ই', 'ఇ', 'இ', 'ਇ', 'ଇ', 'ઇ', 'ಇ', 'ഇ'] },
  // S
  { target: 'S', glyphs: ['स', 'স', 'స', 'ஸ', 'ਸ', 'ସ', 'સ', 'స్', 'സ'] },
  // M
  { target: 'M', glyphs: ['म', 'ম', 'మ', 'ம', 'ਮ', 'ମ', 'મ', 'ಮ್', 'മ'] },
];

function LoadingSplash({ onComplete }) {
  // Current visible glyph for each of the 5 positions
  const [displayChars, setDisplayChars] = useState(['प', 'র', 'इ', 'స', 'ம']);
  // Which letters have locked into their English target
  const [locked, setLocked] = useState([false, false, false, false, false]);
  // When all 5 letters are completed in English
  const [isCompleted, setIsCompleted] = useState(false);
  // Fade-out trigger before unmounting
  const [isFadingOut, setIsFadingOut] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);

  const lockedRef = useRef(locked);
  lockedRef.current = locked;

  // Rapid scramble of unlocked letters through different Indian scripts
  useEffect(() => {
    const scrambleInterval = setInterval(() => {
      setDisplayChars((prev) =>
        prev.map((char, index) => {
          if (lockedRef.current[index]) {
            return SCRIPT_POOLS[index].target;
          }
          const pool = SCRIPT_POOLS[index].glyphs;
          const randomGlyph = pool[Math.floor(Math.random() * pool.length)];
          return randomGlyph;
        })
      );
    }, 70);

    return () => clearInterval(scrambleInterval);
  }, []);

  // Sequential letter resolution timeline: Indian Script -> English Letter
  useEffect(() => {
    // Letter 1: P
    const t0 = setTimeout(() => {
      setLocked((prev) => [true, prev[1], prev[2], prev[3], prev[4]]);
    }, 550);

    // Letter 2: R
    const t1 = setTimeout(() => {
      setLocked((prev) => [true, true, prev[2], prev[3], prev[4]]);
    }, 850);

    // Letter 3: I
    const t2 = setTimeout(() => {
      setLocked((prev) => [true, true, true, prev[3], prev[4]]);
    }, 1150);

    // Letter 4: S
    const t3 = setTimeout(() => {
      setLocked((prev) => [true, true, true, true, prev[4]]);
    }, 1450);

    // Letter 5: M -> Full PRISM Complete in English!
    const t4 = setTimeout(() => {
      setLocked([true, true, true, true, true]);
      setIsCompleted(true);
    }, 1750);

    // Automatic smooth fade-out and transition into website
    const t5 = setTimeout(() => {
      setIsFadingOut(true);
    }, 2550);

    const t6 = setTimeout(() => {
      setIsDismissed(true);
      if (onComplete) onComplete();
    }, 3050);

    return () => {
      clearTimeout(t0);
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
      clearTimeout(t5);
      clearTimeout(t6);
    };
  }, [onComplete]);

  if (isDismissed) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Loading PRISM"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 999999,
        // Website theme: clean off-white canvas with subtle ambient GovTech glows
        backgroundColor: '#f8fafc',
        backgroundImage: `
          radial-gradient(circle at 50% 40%, rgba(29, 78, 216, 0.08) 0%, transparent 60%),
          radial-gradient(circle at 45% 60%, rgba(168, 85, 247, 0.07) 0%, transparent 50%),
          radial-gradient(circle at 55% 55%, rgba(6, 182, 212, 0.06) 0%, transparent 50%)
        `,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem',
        opacity: isFadingOut ? 0 : 1,
        transform: isFadingOut ? 'scale(1.03)' : 'scale(1)',
        transition: 'opacity 0.5s cubic-bezier(0.4, 0, 0.2, 1), transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)',
        pointerEvents: 'none',
        userSelect: 'none',
      }}
    >
      {/* Centered Minimal Container: Authentic Logo + Animated PRISM Wordmark */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '1.75rem',
        }}
      >
        {/* Authentic PRISM Crystal Emblem */}
        <div
          style={{
            position: 'relative',
            width: '108px',
            height: '108px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {/* Subtle Ambient Refractive Halo */}
          <div
            style={{
              position: 'absolute',
              inset: '-12px',
              borderRadius: '28px',
              background: isCompleted
                ? 'radial-gradient(circle, rgba(168, 85, 247, 0.45) 0%, rgba(6, 182, 212, 0.35) 50%, transparent 75%)'
                : 'radial-gradient(circle, rgba(29, 78, 216, 0.3) 0%, rgba(168, 85, 247, 0.25) 50%, transparent 70%)',
              filter: 'blur(16px)',
              transition: 'background 0.5s ease',
              animation: 'prism-pulse 2.4s ease-in-out infinite',
            }}
          />

          {/* Deep Slate Glass Container */}
          <div
            style={{
              position: 'relative',
              width: '100%',
              height: '100%',
              borderRadius: '26px',
              backgroundColor: '#0f172a',
              border: isCompleted
                ? '1.5px solid rgba(168, 85, 247, 0.6)'
                : '1.5px solid rgba(255, 255, 255, 0.12)',
              boxShadow: isCompleted
                ? '0 16px 36px -8px rgba(15, 23, 42, 0.25), 0 0 24px rgba(168, 85, 247, 0.35)'
                : '0 14px 32px -8px rgba(15, 23, 42, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.4s ease',
            }}
          >
            <img
              src="/prism-symbol-transparent.png"
              alt="PRISM Emblem"
              style={{
                width: '74px',
                height: '74px',
                objectFit: 'contain',
                filter: isCompleted
                  ? 'drop-shadow(0 0 14px rgba(168, 85, 247, 0.85)) drop-shadow(0 0 24px rgba(6, 182, 212, 0.5))'
                  : 'drop-shadow(0 0 8px rgba(168, 85, 247, 0.6))',
                animation: 'prism-pulse 2.4s ease-in-out infinite',
                transition: 'filter 0.4s ease',
              }}
            />
          </div>
        </div>

        {/* Modern Animated Typography: Indian Script Glyphs Morphing into English PRISM */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.45rem',
            minHeight: '72px',
          }}
        >
          {SCRIPT_POOLS.map((letterDef, index) => {
            const isLetterLocked = locked[index];
            const currentChar = isLetterLocked ? letterDef.target : displayChars[index];

            return (
              <span
                key={index}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '56px',
                  height: '68px',
                  fontSize: '3.6rem',
                  fontWeight: '900',
                  fontFamily: 'var(--font-family-primary)',
                  letterSpacing: '1px',
                  lineHeight: 1,
                  // When locked and word complete: full prismatic spectral gradient sheen
                  // When locked individually: crisp slate 900
                  // While scrambling: vibrant cobalt / purple glow
                  color: isLetterLocked ? '#0f172a' : '#2563eb',
                  textShadow: isLetterLocked
                    ? 'none'
                    : '0 0 16px rgba(37, 99, 235, 0.45)',
                  animation: isLetterLocked ? 'letter-pop 0.35s ease-out' : 'none',
                  transition: 'color 0.2s ease, text-shadow 0.2s ease',
                  ...(isCompleted
                    ? {
                        background: 'linear-gradient(110deg, #0f172a 10%, #1d4ed8 35%, #7c3aed 60%, #db2777 85%, #0f172a 100%)',
                        backgroundSize: '250% 100%',
                        WebkitBackgroundClip: 'text',
                        WebkitTextFillColor: 'transparent',
                        animation: 'prism-sweep 2s ease-in-out infinite',
                      }
                    : {}),
                }}
              >
                {currentChar}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default LoadingSplash;
