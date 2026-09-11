import React, { useState, useEffect } from 'react';

/**
 * Reusable animated skeleton box
 */
export function SkeletonBox({ width, height, borderRadius, style = {}, className = '' }) {
  return (
    <div
      className={`skeleton-box ${className}`}
      style={{
        width: width !== undefined ? width : '100%',
        height: height !== undefined ? height : '100%',
        borderRadius: borderRadius !== undefined ? borderRadius : undefined,
        ...style,
      }}
    />
  );
}

/**
 * Reusable animated skeleton text lines
 */
export function SkeletonText({ lines = 1, width = '100%', height = 12, gap = 8, style = {}, className = '' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: `${gap}px`, width: '100%', ...style }} className={className}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="skeleton-text"
          style={{
            height: `${height}px`,
            width: typeof width === 'function' ? width(i) : i === lines - 1 && lines > 1 ? '70%' : width,
          }}
        />
      ))}
    </div>
  );
}

/**
 * Progressive Image loader with Skeleton Placeholder Box.
 * Shows an animated shimmer placeholder box while the image or stream is loading.
 * Once loaded, smoothly transitions and stays loaded without flickering.
 */
export function SkeletonImage({
  src,
  alt = 'Image capture',
  style = {},
  containerStyle = {},
  className = '',
  imgClassName = '',
  placeholderText = 'CONNECTING FEED...',
  fallbackText = 'SIGNAL OFFLINE',
  objectFit = 'cover',
  onClick,
  onLoad,
  onError,
  children,
  ...rest
}) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);

  // Reset states if src genuinely changes
  useEffect(() => {
    setIsLoaded(false);
    setHasError(false);
  }, [src]);

  const handleLoad = (e) => {
    setIsLoaded(true);
    if (onLoad) onLoad(e);
  };

  const handleError = (e) => {
    setHasError(true);
    if (onError) onError(e);
  };

  return (
    <div
      className={`skeleton-image-wrapper ${className}`}
      style={{ ...containerStyle }}
      onClick={onClick}
    >
      {/* Skeleton Shimmer Placeholder Box */}
      {!isLoaded && !hasError && (
        <div className="skeleton-image-placeholder">
          <div className="skeleton-radar-pulse">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
              <path d="M12 3a9 9 0 0 1 9 9" />
              <circle cx="12" cy="12" r="3" fill="currentColor" opacity="0.6" />
            </svg>
          </div>
          {placeholderText && (
            <span style={{ fontSize: '10px', color: 'var(--text-low)', textTransform: 'uppercase' }}>
              {placeholderText}
            </span>
          )}
        </div>
      )}

      {/* Error Fallback Box */}
      {hasError ? (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#0c0a08',
            color: 'var(--text-low)',
            padding: '16px',
            textAlign: 'center',
            fontSize: '11px',
            gap: '6px',
          }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--red)" strokeWidth="1.5">
            <rect x="2" y="2" width="20" height="20" rx="5" />
            <path d="M8 8l8 8M16 8l-8 8" />
          </svg>
          <span style={{ color: 'var(--text-mid)', fontWeight: 600 }}>{fallbackText}</span>
          <span style={{ fontSize: '9.5px', fontFamily: 'var(--mono)', opacity: 0.6 }}>Feed unreachable or unavailable</span>
        </div>
      ) : (
        /* The Real Image */
        <img
          src={src}
          alt={alt}
          onLoad={handleLoad}
          onError={handleError}
          className={`skeleton-img ${isLoaded ? 'loaded' : ''} ${imgClassName}`}
          style={{
            objectFit,
            ...style,
          }}
          {...rest}
        />
      )}

      {/* Children overlays (e.g. bounding boxes or tags) */}
      {children}
    </div>
  );
}

/**
 * Skeleton for Hero Overview Section
 */
export function HeroSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginBottom: '24px' }}>
      {/* Top Banner Skeleton */}
      <div
        className="skeleton-card"
        style={{
          height: '110px',
          display: 'flex',
          justifyContent: 'space-between',
          flexDirection: 'row',
          alignItems: 'center',
          padding: '24px 28px',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1 }}>
          <SkeletonBox width="140px" height="18px" />
          <SkeletonBox width="60%" height="28px" />
          <SkeletonBox width="40%" height="14px" />
        </div>
        <SkeletonBox width="130px" height="42px" borderRadius="20px" />
      </div>

      {/* Metrics Row Skeleton */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px' }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton-card" style={{ height: '94px', padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <SkeletonBox width="90px" height="12px" />
              <SkeletonBox width="18px" height="18px" borderRadius="4px" />
            </div>
            <SkeletonBox width="65px" height="28px" style={{ marginTop: '6px' }} />
          </div>
        ))}
      </div>

      {/* Chart & Spatial Radar Skeleton */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))', gap: '16px' }}>
        <div className="skeleton-card" style={{ height: '260px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
            <SkeletonBox width="160px" height="16px" />
            <SkeletonBox width="80px" height="24px" borderRadius="12px" />
          </div>
          <SkeletonBox width="100%" height="180px" />
        </div>
        <div className="skeleton-card" style={{ height: '260px' }}>
          <SkeletonBox width="140px" height="16px" style={{ marginBottom: '16px' }} />
          <div style={{ flex: 1, display: 'grid', placeItems: 'center' }}>
            <SkeletonBox width="160px" height="160px" borderRadius="50%" />
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Skeleton for Camera Feed Cards
 */
export function CameraCardSkeleton() {
  return (
    <div className="skeleton-camera-card">
      <div
        style={{
          position: 'absolute',
          top: '12px',
          left: '12px',
          right: '12px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          zIndex: 3,
        }}
      >
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <SkeletonBox width="90px" height="14px" />
          <SkeletonBox width="60px" height="10px" />
        </div>
        <SkeletonBox width="55px" height="18px" borderRadius="10px" />
      </div>
      <div className="skeleton-image-placeholder">
        <div className="skeleton-radar-pulse">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
        </div>
        <span style={{ fontSize: '10px', color: 'var(--text-low)', textTransform: 'uppercase' }}>
          INITIALIZING STREAM...
        </span>
      </div>
    </div>
  );
}

/**
 * Skeleton for Tables (Events, Alerts, Logs)
 */
export function TableRowSkeleton({ columns = 5, rows = 6 }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rIdx) => (
        <tr key={rIdx} style={{ height: '48px', borderBottom: '1px solid var(--hair-soft)' }}>
          {Array.from({ length: columns }).map((_, cIdx) => (
            <td key={cIdx} style={{ padding: '12px 16px' }}>
              <SkeletonBox
                width={cIdx === 0 ? '70px' : cIdx === 1 ? '50%' : cIdx === columns - 1 ? '60px' : '85%'}
                height="14px"
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

/**
 * Skeleton for Evidence Cards
 */
export function EvidenceCardSkeleton() {
  return (
    <div
      className="skeleton-card"
      style={{
        padding: '12px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      <SkeletonBox width="100%" height="150px" borderRadius="6px" />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <SkeletonBox width="75px" height="14px" />
        <SkeletonBox width="50px" height="12px" />
      </div>
      <SkeletonBox width="90%" height="11px" />
      <SkeletonBox width="60%" height="11px" />
    </div>
  );
}

/**
 * Skeleton for Narrative Grid Cards
 */
export function NarrativeCardSkeleton() {
  return (
    <div className="skeleton-card" style={{ minHeight: '180px', padding: '18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <SkeletonBox width="110px" height="16px" />
        <SkeletonBox width="70px" height="20px" borderRadius="10px" />
      </div>
      <SkeletonBox width="85%" height="20px" style={{ margin: '8px 0 4px' }} />
      <SkeletonText lines={3} height={12} gap={8} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px' }}>
        <SkeletonBox width="90px" height="12px" />
        <SkeletonBox width="80px" height="26px" borderRadius="4px" />
      </div>
    </div>
  );
}
