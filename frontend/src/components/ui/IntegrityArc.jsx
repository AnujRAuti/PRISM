import React, { useEffect, useState } from 'react';

export function IntegrityArc({
  score,
  size = 'md',
  showLabel = true,
  showRiskBadge = false,
  className = '',
  animate = true,
}) {
  const [displayScore, setDisplayScore] = useState(animate ? 0 : score);

  useEffect(() => {
    if (!animate) {
      setDisplayScore(score);
      return;
    }
    const duration = 400;
    const startTime = performance.now();
    const startVal = 0;
    const endVal = score;

    let frameId;
    const update = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      setDisplayScore(Math.round(startVal + (endVal - startVal) * ease));

      if (progress < 1) {
        frameId = requestAnimationFrame(update);
      }
    };
    frameId = requestAnimationFrame(update);
    return () => cancelAnimationFrame(frameId);
  }, [score, animate]);

  const sizeMap = {
    sm: { width: 44, height: 44, strokeWidth: 3.5, fontSize: '0.75rem', radius: 18 },
    md: { width: 68, height: 68, strokeWidth: 4.5, fontSize: '0.9rem', radius: 28 },
    lg: { width: 104, height: 104, strokeWidth: 6, fontSize: '1.5rem', radius: 44 },
    xl: { width: 152, height: 152, strokeWidth: 8, fontSize: '2.25rem', radius: 64 },
  };

  const config = sizeMap[size] || sizeMap.md;
  const center = config.width / 2;
  const circumference = 2 * Math.PI * config.radius;
  const strokeDashoffset = circumference - (circumference * displayScore) / 100;

  // Determine institutional color
  const getColor = (s) => {
    if (s >= 80) return 'var(--govt-success, #059669)';
    if (s >= 50) return 'var(--govt-warning, #d97706)';
    return 'var(--govt-danger, #dc2626)';
  };

  const color = getColor(score);

  return (
    <div
      className={`integrity-arc-wrapper ${className}`}
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.25rem',
      }}
    >
      <div style={{ position: 'relative', width: config.width, height: config.height }}>
        <svg
          width={config.width}
          height={config.height}
          viewBox={`0 0 ${config.width} ${config.height}`}
          style={{ transform: 'rotate(-90deg)', overflow: 'visible' }}
        >
          {/* Background track circle */}
          <circle
            cx={center}
            cy={center}
            r={config.radius}
            fill="transparent"
            stroke="var(--govt-gray-medium, #e2e8f0)"
            strokeWidth={config.strokeWidth}
          />
          {/* Animated score arc */}
          <circle
            cx={center}
            cy={center}
            r={config.radius}
            fill="transparent"
            stroke={color}
            strokeWidth={config.strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            style={{
              transition: animate ? 'stroke-dashoffset 0.4s ease-out' : 'none',
            }}
          />
        </svg>

        {showLabel && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'var(--font-family-mono, monospace)',
              fontWeight: 700,
              fontSize: config.fontSize,
              color: 'var(--govt-gray-title, #0f172a)',
            }}
          >
            {displayScore}
          </div>
        )}
      </div>

      {showRiskBadge && (
        <span
          style={{
            fontSize: '0.7rem',
            fontWeight: 700,
            padding: '0.15rem 0.5rem',
            borderRadius: '999px',
            backgroundColor: score >= 80 ? 'rgba(5, 150, 105, 0.12)' : score >= 50 ? 'rgba(217, 119, 6, 0.12)' : 'rgba(220, 38, 38, 0.12)',
            color: color,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
          }}
        >
          {score >= 80 ? 'Low Risk' : score >= 50 ? 'Medium Risk' : 'Critical Flag'}
        </span>
      )}
    </div>
  );
}

export default IntegrityArc;
