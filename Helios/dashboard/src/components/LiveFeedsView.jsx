import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { api } from '../services/api';
import {
  RefreshIcon,
  ExpandIcon,
  CloseIcon,
  CameraIcon,
  AiSparklesIcon,
  UserIcon,
  VehicleIcon,
  TargetIcon,
  BoltIcon,
  WalkingIcon,
  RunningIcon,
  StationaryIcon,
  ThreadIcon,
  FullscreenIcon,
  FullscreenExitIcon,
} from './Icons';

/**
 * High-accuracy, interactive bounding boxes overlay.
 * Supports click-through to object activity threads, object-specific icons,
 * and human movement status indicators (Stationary, Walking, Running).
 */
function TrackBoxesOverlay({
  tracks = [],
  showBoxes = true,
  onSelectTab,
}) {
  if (!showBoxes || tracks.length === 0) return null;

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 10,
      }}
    >
      {tracks.map((t) => {
        if (!Array.isArray(t.current_position) || t.current_position.length < 4) return null;
        const [rawX, rawY, rawW, rawH] = t.current_position;
        const x = Number(rawX) || 0;
        const y = Number(rawY) || 0;
        const w = Number(rawW) || 0;
        const h = Number(rawH) || 0;

        // Accurate normalized coordinates clamped strictly within [0, 1]
        const leftPct = Math.max(0, Math.min(0.99, x)) * 100;
        const topPct = Math.max(0, Math.min(0.99, y)) * 100;
        const widthPct = Math.max(0.5, Math.min(100 - leftPct, w * 100));
        const heightPct = Math.max(0.5, Math.min(100 - topPct, h * 100));

        const objType = (t.object_type || 'OBJECT').toLowerCase();
        const isHuman = t.object_type === 'HUMAN' || t.attributes?.person_name || t.source_class === 'person';
        const isVehicle = t.object_type === 'VEHICLE' || t.attributes?.vehicle_type || t.source_class === 'car';
        const isUnclassified = t.object_type === 'UNCLASSIFIED';
        const personName = t.attributes?.person_name;
        const vehicleType = t.attributes?.vehicle_type;

        // Human movement classification: STATIONARY, WALKING, RUNNING
        const rawMState = (t.movement_state || t.attributes?.movement_state || '').toUpperCase();
        let humanState = 'STATIONARY';
        if (rawMState === 'RUNNING' || rawMState === 'FAST' || (typeof t.speed === 'number' && t.speed > 80)) {
          humanState = 'RUNNING';
        } else if (rawMState === 'WALKING' || rawMState === 'MOVING' || (typeof t.speed === 'number' && t.speed > 8)) {
          humanState = 'WALKING';
        } else {
          humanState = 'STATIONARY';
        }

        return (
          <div
            key={t.track_id}
            className={`track-box ${objType}`}
            style={{
              left: `${leftPct}%`,
              top: `${topPct}%`,
              width: `${widthPct}%`,
              height: `${heightPct}%`,
              pointerEvents: 'auto',
              cursor: 'pointer',
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (onSelectTab) {
                onSelectTab('threads', t.track_id);
              }
            }}
            title={`Click to view Activity Thread for ${t.track_id} (${t.object_type})`}
          >
            {/* Top Label: Object class + ID + click-to-thread cue */}
            <label>
              {isHuman ? (
                <UserIcon size={10} style={{ display: 'inline-block', flexShrink: 0 }} />
              ) : isVehicle ? (
                <VehicleIcon size={10} style={{ display: 'inline-block', flexShrink: 0 }} />
              ) : (
                <TargetIcon size={10} style={{ display: 'inline-block', flexShrink: 0 }} />
              )}
              <span>
                {personName
                  ? `${personName} · ${t.track_id}`
                  : vehicleType
                  ? `${vehicleType.toUpperCase()} · ${t.track_id}`
                  : isUnclassified
                  ? `MOTION ${t.track_id}`
                  : `${t.object_type} ${t.track_id}`}
              </span>
              <ThreadIcon size={9} style={{ opacity: 0.75, marginLeft: 2 }} />
            </label>

            {/* Bottom Movement Status Pill: For human show STATIONARY / WALKING / RUNNING */}
            {isHuman && (
              <div className="track-box-tags">
                <span className={`track-state-pill ${humanState.toLowerCase()}`}>
                  {humanState === 'RUNNING' && <RunningIcon size={9} />}
                  {humanState === 'WALKING' && <WalkingIcon size={9} />}
                  {humanState === 'STATIONARY' && <StationaryIcon size={9} />}
                  <span>{humanState}</span>
                  {typeof t.speed === 'number' && t.speed > 0 && (
                    <span style={{ opacity: 0.8, marginLeft: 2 }}>{Math.round(t.speed)}px/s</span>
                  )}
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function LiveFeedsView({
  cameras = [],
  tracks = [],
  events = [],
  alerts = [],
  loading = false,
  connected = true,
  onSelectTab,
  onRefresh,
  onInvestigate,
}) {
  // Layout & filter states
  const [layoutMode, setLayoutMode] = useState('grid'); // 'grid' | 'quad' | 'focus'
  const [selectedCameraFilter, setSelectedCameraFilter] = useState('ALL'); // 'ALL' | camera_id
  const [focusCamera, setFocusCamera] = useState(null); // Camera object for expanded view
  const [isFullscreen, setIsFullscreen] = useState(false);
  const focusContentRef = useRef(null);

  // Overlay layer toggles
  const [showBoxes, setShowBoxes] = useState(true);
  const [showZones, setShowZones] = useState(true);

  // Per-camera stream state tracking
  const [streamErrors, setStreamErrors] = useState({});
  const [streamRetryKeys, setStreamRetryKeys] = useState({});
  const [zonesByCamera, setZonesByCamera] = useState({});

  // Real-time ticking HUD timestamp
  const [currentTime, setCurrentTime] = useState(() =>
    new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
  );

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC');
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fullscreen state listener
  useEffect(() => {
    const onFsChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      if (focusContentRef.current?.requestFullscreen) {
        focusContentRef.current.requestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
  }, []);

  // Fetch configured zones for each camera from backend API
  const loadZones = useCallback(async () => {
    try {
      const res = await api.getZones();
      if (Array.isArray(res)) {
        const grouped = {};
        res.forEach((z) => {
          if (z.camera_id) {
            if (!grouped[z.camera_id]) grouped[z.camera_id] = [];
            grouped[z.camera_id].push(z);
          }
        });
        setZonesByCamera(grouped);
      }
    } catch (err) {
      console.warn('Could not load camera zones:', err);
    }
  }, []);

  useEffect(() => {
    loadZones();
  }, [loadZones]);

  // Handle stream image error
  const handleImageError = useCallback((cameraId) => {
    setStreamErrors((prev) => ({ ...prev, [cameraId]: true }));
  }, []);

  // Handle stream image successfully loaded
  const handleImageLoad = useCallback((cameraId) => {
    setStreamErrors((prev) => {
      if (!prev[cameraId]) return prev;
      const next = { ...prev };
      delete next[cameraId];
      return next;
    });
  }, []);

  // Retry individual camera stream connection
  const handleRetryStream = useCallback(async (cameraId, e) => {
    if (e) e.stopPropagation();
    try {
      await api.reloadCameras();
    } catch (err) {
      console.warn('Reload cameras request failed:', err);
    }
    setStreamErrors((prev) => {
      const next = { ...prev };
      delete next[cameraId];
      return next;
    });
    setStreamRetryKeys((prev) => ({
      ...prev,
      [cameraId]: Date.now(),
    }));
    if (onRefresh) onRefresh();
  }, [onRefresh]);

  // Full manual refresh
  const handleGlobalRefresh = useCallback(async () => {
    try {
      await api.reloadCameras();
    } catch (err) {
      console.warn('Reload cameras request failed:', err);
    }
    setStreamErrors({});
    const now = Date.now();
    const newKeys = {};
    cameras.forEach((c) => {
      newKeys[c.camera_id] = now;
    });
    setStreamRetryKeys(newKeys);
    if (onRefresh) onRefresh();
    loadZones();
  }, [cameras, onRefresh, loadZones]);

  // Active targets calculation mapped per camera
  const activeTracksByCam = useMemo(() => {
    const map = {};
    cameras.forEach((c) => {
      map[c.camera_id] = tracks.filter(
        (t) =>
          (t.status === 'ACTIVE' || t.status === 'TRACKED') &&
          t.camera_id === c.camera_id &&
          Array.isArray(t.current_position)
      );
    });
    return map;
  }, [cameras, tracks]);

  // Filtered cameras list based on channel selector
  const filteredCameras = useMemo(() => {
    if (selectedCameraFilter === 'ALL') return cameras;
    return cameras.filter((c) => c.camera_id === selectedCameraFilter);
  }, [cameras, selectedCameraFilter]);

  // Metrics summary
  const onlineCount = cameras.filter((c) => c.status === 'ONLINE' && !streamErrors[c.camera_id]).length;
  const totalActiveTracks = tracks.filter((t) => t.status === 'ACTIVE' || t.status === 'TRACKED').length;

  // Render SVG zones for a camera
  const renderZonesSvg = (camId) => {
    const cameraZones = zonesByCamera[camId] || [];
    if (!showZones || cameraZones.length === 0) return null;
    return (
      <svg
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
          zIndex: 4,
        }}
        viewBox="0 0 1000 562.5"
        preserveAspectRatio="none"
      >
        {cameraZones.map((z) => {
          if (!z.geometry || z.geometry.length < 3) return null;
          const pointsStr = z.geometry
            .map((p) => `${p[0] * 1000},${p[1] * 562.5}`)
            .join(' ');
          const isRestricted = (z.zone_type || 'RESTRICTED').toUpperCase() === 'RESTRICTED';
          const cx =
            (z.geometry.reduce((acc, pt) => acc + pt[0], 0) / z.geometry.length) * 1000;
          const cy =
            (z.geometry.reduce((acc, pt) => acc + pt[1], 0) / z.geometry.length) * 562.5;

          return (
            <g key={z.zone_id}>
              <polygon
                points={pointsStr}
                fill={isRestricted ? 'rgba(239, 82, 81, 0.08)' : 'rgba(47, 204, 139, 0.06)'}
                stroke={isRestricted ? 'rgba(239, 82, 81, 0.65)' : 'rgba(47, 204, 139, 0.5)'}
                strokeWidth="1.5"
                strokeDasharray="4 2"
              />
              <text
                x={cx}
                y={cy}
                fill={isRestricted ? '#ef5251' : '#2fcc8b'}
                fontSize="10.5"
                fontFamily="var(--mono)"
                fontWeight="600"
                textAnchor="middle"
              >
                {z.name || z.zone_id}
              </text>
            </g>
          );
        })}
      </svg>
    );
  };

  return (
    <div>
      {/* 1. BACKEND DISCONNECTED WARNING BANNER */}
      {!connected && (
        <div
          style={{
            background: 'var(--red-dim)',
            border: '1px solid rgba(239, 82, 81, 0.4)',
            padding: '10px 16px',
            marginBottom: '16px',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span className="live-dot pulse" style={{ background: 'var(--red)' }} />
            <div>
              <b style={{ color: 'var(--text-hi)', fontSize: '13px' }}>BACKEND DISCONNECTED</b>
              <span style={{ color: 'var(--text-mid)', marginLeft: '8px', fontSize: '12px' }}>
                Lost connection to HELIOS Core API & WebSocket. Reconnecting automatically...
              </span>
            </div>
          </div>
          <button
            type="button"
            className="n-btn primary"
            onClick={handleGlobalRefresh}
            style={{ padding: '4px 12px', fontSize: '11.5px' }}
          >
            <RefreshIcon size={11} />
            Retry Connection
          </button>
        </div>
      )}

      {/* 2. SECTION HEAD */}
      <div className="section-head">
        <div>
          <h2>Live Surveillance Feeds</h2>
          <span className="section-sub">
            {cameras.length} camera streams configured · {onlineCount} online · real-time proxy
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span className="nav-badge neutral">
            {onlineCount} / {cameras.length} ONLINE
          </span>

          {totalActiveTracks > 0 && (
            <span
              className="nav-badge"
              style={{
                background: 'var(--green-dim)',
                color: 'var(--green)',
                border: '1px solid rgba(47, 204, 139, 0.3)',
              }}
            >
              {totalActiveTracks} TARGETS ACTIVE
            </span>
          )}

          <button
            type="button"
            className="n-btn"
            onClick={handleGlobalRefresh}
            title="Refresh All Feeds"
            style={{ padding: '5px 12px', fontSize: '12px' }}
          >
            <RefreshIcon size={12} />
            Refresh
          </button>
        </div>
      </div>

      {/* 3. CHANNEL TABS & VIEW CONTROLS */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          marginBottom: '16px',
          flexWrap: 'wrap',
        }}
      >
        {/* Channel filter pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <button
            type="button"
            className={`n-btn ${selectedCameraFilter === 'ALL' ? 'active' : ''}`}
            onClick={() => setSelectedCameraFilter('ALL')}
          >
            All Cameras ({cameras.length})
          </button>
          {cameras.map((c) => {
            const isOnline = c.status === 'ONLINE' && !streamErrors[c.camera_id];
            const isSel = selectedCameraFilter === c.camera_id;
            const trkCount = (activeTracksByCam[c.camera_id] || []).length;
            return (
              <button
                key={c.camera_id}
                type="button"
                className={`n-btn ${isSel ? 'active' : ''}`}
                onClick={() => setSelectedCameraFilter(c.camera_id)}
              >
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: isOnline ? 'var(--green)' : 'var(--red)',
                  }}
                />
                {c.name || c.camera_id}
                {trkCount > 0 && <span style={{ color: 'var(--gold)', fontWeight: 600 }}>({trkCount})</span>}
              </button>
            );
          })}
        </div>

        {/* Layout & Overlays */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="list-toggle" style={{ display: 'inline-flex' }}>
            <span className={layoutMode === 'grid' ? 'active' : ''} onClick={() => setLayoutMode('grid')}>
              Grid
            </span>
            <span className={layoutMode === 'quad' ? 'active' : ''} onClick={() => setLayoutMode('quad')}>
              2x2
            </span>
            <span className={layoutMode === 'focus' ? 'active' : ''} onClick={() => setLayoutMode('focus')}>
              1x1
            </span>
          </div>

          <button
            type="button"
            className={`n-btn ${showBoxes ? 'active' : ''}`}
            onClick={() => setShowBoxes((v) => !v)}
          >
            Boxes: {showBoxes ? 'ON' : 'OFF'}
          </button>

          <button
            type="button"
            className={`n-btn ${showZones ? 'active' : ''}`}
            onClick={() => setShowZones((v) => !v)}
          >
            Zones: {showZones ? 'ON' : 'OFF'}
          </button>
        </div>
      </div>

      {/* 4. CAMERA GRID */}
      {filteredCameras.length === 0 ? (
        <div className="panel" style={{ padding: '48px', textAlign: 'center', color: 'var(--text-low)' }}>
          <CameraIcon size={32} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-hi)' }}>No camera feeds match filter</div>
          <button
            type="button"
            className="n-btn primary"
            onClick={() => setSelectedCameraFilter('ALL')}
            style={{ marginTop: '16px' }}
          >
            Reset Filter
          </button>
        </div>
      ) : (
        <div
          className={`camera-grid ${
            layoutMode === 'quad'
              ? 'quad-matrix'
              : layoutMode === 'focus'
              ? 'single-focus'
              : ''
          }`}
        >
          {filteredCameras.map((c) => {
            const camId = c.camera_id;
            const hasStreamConfigured = c.stream_configured !== false && Boolean(c.source_type);
            const isStreamErrored = Boolean(streamErrors[camId]);
            const isOnline = c.status === 'ONLINE' && !isStreamErrored;
            const isConnecting = c.status === 'CONNECTING';
            const cameraTracks = activeTracksByCam[camId] || [];
            const hasMotion = cameraTracks.some(
              (t) => t.object_type === 'UNCLASSIFIED' || t.attributes?.motion_type
            );
            const retryKey = streamRetryKeys[camId] || 0;
            const streamUrl = `${api.getStreamUrl(camId)}${retryKey ? `?_r=${retryKey}` : ''}`;

            // Reliability & Condition
            const condition = c.condition || 'CLEAR';
            const isOccluded = condition !== 'CLEAR';
            const reliabilityScore = c.reliability_score ?? 100;

            return (
              <div key={camId} className="camera-card">
                {/* HEADER HUD */}
                <div className="camera-head">
                  <div>
                    <b style={{ color: 'var(--text-hi)', fontSize: '13px' }}>{c.name || camId}</b>
                    <span style={{ color: 'var(--text-low)', marginLeft: '8px', fontSize: '11px' }}>
                      {c.location} ({camId})
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {hasMotion && (
                      <span
                        className="nav-badge"
                        style={{
                          background: 'rgba(168, 85, 247, 0.15)',
                          color: '#c084fc',
                          border: '1px solid rgba(168, 85, 247, 0.3)',
                          fontSize: '10.5px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                        }}
                      >
                        <BoltIcon size={10} />
                        MOTION
                      </span>
                    )}

                    {isOccluded && (
                      <span
                        className="nav-badge"
                        style={{
                          background: 'var(--gold-dim)',
                          color: 'var(--gold)',
                          border: '1px solid rgba(201, 154, 91, 0.3)',
                          fontSize: '10.5px',
                        }}
                      >
                        {condition} ({reliabilityScore}%)
                      </span>
                    )}

                    <span
                      className={`nav-badge ${isOnline ? 'neutral' : ''}`}
                      style={{
                        background: isOnline ? 'var(--green-dim)' : isConnecting ? 'var(--gold-dim)' : 'var(--red-dim)',
                        color: isOnline ? 'var(--green)' : isConnecting ? 'var(--gold)' : 'var(--red)',
                        border: `1px solid ${
                          isOnline ? 'rgba(47, 204, 139, 0.3)' : isConnecting ? 'rgba(201, 154, 91, 0.3)' : 'rgba(239, 82, 81, 0.3)'
                        }`,
                        fontSize: '10.5px',
                      }}
                    >
                      {c.status}
                    </span>
                  </div>
                </div>

                {/* VIEWPORT: REAL STREAM OR CAMERA OFFLINE */}
                {isStreamErrored || !hasStreamConfigured || c.status === 'OFFLINE' ? (
                  <div className="camera-empty">
                    <div style={{ textAlign: 'center' }}>
                      <CameraIcon size={24} style={{ margin: '0 auto 8px', display: 'block', opacity: 0.5 }} />
                      <b style={{ color: 'var(--text-mid)', fontSize: '12px', display: 'block', letterSpacing: '0.5px' }}>
                        CAMERA OFFLINE
                      </b>
                      <span style={{ color: 'var(--text-low)', fontSize: '11px', display: 'block', marginTop: '2px' }}>
                        {c.location ? `${c.location} · ` : ''}
                        {!hasStreamConfigured
                          ? 'Stream not configured'
                          : 'Feed signal offline or unreachable'}
                      </span>
                      <button
                        type="button"
                        className="n-btn"
                        style={{ marginTop: '10px', padding: '4px 10px', fontSize: '11px' }}
                        onClick={(e) => handleRetryStream(camId, e)}
                      >
                        <RefreshIcon size={10} />
                        Reconnect
                      </button>
                    </div>
                  </div>
                ) : (
                  <img
                    src={streamUrl}
                    alt={`${c.name} live stream`}
                    style={{ width: '100%', height: '100%', objectFit: 'fill', display: 'block' }}
                    onLoad={() => handleImageLoad(camId)}
                    onError={() => handleImageError(camId)}
                  />
                )}

                {/* SPATIAL ZONE BOUNDARIES OVERLAY */}
                {renderZonesSvg(camId)}

                {/* HIGH-ACCURACY CLICKABLE BOUNDING BOXES OVERLAY */}
                <TrackBoxesOverlay
                  tracks={cameraTracks}
                  showBoxes={showBoxes}
                  onSelectTab={onSelectTab}
                />

                {/* FOOTER BAR */}
                <div
                  style={{
                    position: 'absolute',
                    inset: 'auto 10px 10px 10px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    background: 'rgba(0, 0, 0, 0.55)',
                    backdropFilter: 'blur(6px)',
                    padding: '5px 10px',
                    borderRadius: '6px',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    zIndex: 10,
                    fontSize: '11px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        color: cameraTracks.length > 0 ? 'var(--green)' : 'var(--text-low)',
                        fontFamily: 'var(--mono)',
                        fontWeight: 600,
                      }}
                    >
                      {cameraTracks.length > 0
                        ? `${cameraTracks.length} TARGET${cameraTracks.length > 1 ? 'S' : ''} ACTIVE`
                        : 'STANDBY'}
                    </span>
                    <span style={{ color: 'var(--text-low)', fontFamily: 'var(--mono)', fontSize: '10px' }}>
                      {currentTime}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {onInvestigate && (
                      <button
                        type="button"
                        className="n-btn ai-investigate"
                        style={{ padding: '2px 8px', fontSize: '10.5px' }}
                        onClick={() =>
                          onInvestigate({
                            event_id: `feed-${camId}-${Date.now()}`,
                            camera_id: camId,
                            event_type: 'SURVEILLANCE_INSPECTION',
                            description: `Tactical review for camera ${camId} (${c.name}). Active targets: ${cameraTracks.length}.`,
                          })
                        }
                        title="Investigate with AI"
                      >
                        <AiSparklesIcon size={10} />
                        Investigate
                      </button>
                    )}

                    <button
                      type="button"
                      className="n-btn primary"
                      style={{ padding: '2px 8px', fontSize: '10.5px' }}
                      onClick={() => setFocusCamera(c)}
                      title="Spotlight Focus View"
                    >
                      <ExpandIcon size={10} />
                      Focus
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 5. SPOTLIGHT FOCUS MODAL WITH FULLSCREEN SUPPORT */}
      {focusCamera && (
        <div className="camera-focus-modal" onClick={() => setFocusCamera(null)}>
          <div
            ref={focusContentRef}
            className="camera-focus-content"
            style={isFullscreen ? { width: '100vw', height: '100vh', maxWidth: 'none', borderRadius: 0 } : {}}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 20px',
                borderBottom: '1px solid var(--hair)',
                background: 'var(--panel-hi)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className="live-dot pulse" />
                <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-hi)' }}>
                  {focusCamera.name} · SPOTLIGHT INSPECTION
                </span>
                <span className="nav-badge neutral">{focusCamera.camera_id}</span>
                <span
                  className="nav-badge"
                  style={{
                    background: focusCamera.status === 'ONLINE' ? 'var(--green-dim)' : 'var(--red-dim)',
                    color: focusCamera.status === 'ONLINE' ? 'var(--green)' : 'var(--red)',
                  }}
                >
                  {focusCamera.status}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {onInvestigate && (
                  <button
                    type="button"
                    className="n-btn ai-investigate"
                    onClick={() => {
                      onInvestigate({
                        event_id: `focus-${focusCamera.camera_id}`,
                        camera_id: focusCamera.camera_id,
                        event_type: 'CAMERA_INSPECTION',
                        description: `Deep situational analysis of ${focusCamera.name} (${focusCamera.camera_id})`,
                      });
                    }}
                  >
                    <AiSparklesIcon size={12} />
                    AI Investigate Feed
                  </button>
                )}

                <button
                  type="button"
                  className="n-btn"
                  onClick={toggleFullscreen}
                  title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen View'}
                >
                  {isFullscreen ? <FullscreenExitIcon size={13} /> : <FullscreenIcon size={13} />}
                </button>

                <button type="button" className="n-btn" onClick={() => setFocusCamera(null)} title="Close Modal">
                  <CloseIcon size={14} />
                </button>
              </div>
            </div>

            {/* Modal Body: Feed + Detailed Telemetry Sidebar */}
            <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
              {/* Primary Expanded Feed with Aspect-Preserving Overlay Container */}
              <div
                style={{
                  flex: 1,
                  position: 'relative',
                  background: '#000000',
                  overflow: 'hidden',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <div
                  style={{
                    position: 'relative',
                    width: '100%',
                    aspectRatio: '16 / 9',
                    maxHeight: '100%',
                    maxWidth: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: '#040609',
                  }}
                >
                  <img
                    src={`${api.getStreamUrl(focusCamera.camera_id)}?_f=${streamRetryKeys[focusCamera.camera_id] || 0}`}
                    alt={`${focusCamera.name} focused feed`}
                    style={{ width: '100%', height: '100%', objectFit: 'fill', display: 'block' }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                      if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex';
                    }}
                  />
                  <div className="camera-empty" style={{ display: 'none', position: 'absolute', inset: 0 }}>
                    <div style={{ textAlign: 'center' }}>
                      <CameraIcon size={24} style={{ margin: '0 auto 8px', display: 'block', opacity: 0.5 }} />
                      <b style={{ color: 'var(--text-mid)', fontSize: '13px' }}>CAMERA OFFLINE</b>
                      <span style={{ color: 'var(--text-low)', fontSize: '11px', display: 'block', marginTop: '4px' }}>
                        No video stream received from {focusCamera.camera_id}
                      </span>
                    </div>
                  </div>

                  {/* SPATIAL ZONE BOUNDARIES OVERLAY IN FOCUS MODE */}
                  {renderZonesSvg(focusCamera.camera_id)}

                  {/* HIGH-ACCURACY CLICKABLE BOUNDING BOXES IN FOCUS MODE */}
                  <TrackBoxesOverlay
                    tracks={activeTracksByCam[focusCamera.camera_id] || []}
                    showBoxes={showBoxes}
                    onSelectTab={(tab, trackId) => {
                      setFocusCamera(null);
                      if (onSelectTab) onSelectTab(tab, trackId);
                    }}
                  />
                </div>
              </div>

              {/* Side Telemetry Drawer */}
              <div
                style={{
                  width: '320px',
                  borderLeft: '1px solid var(--hair)',
                  background: 'var(--panel)',
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '16px',
                  overflowY: 'auto',
                }}
              >
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-low)', textTransform: 'uppercase', marginBottom: '6px' }}>
                    Feed Telemetry
                  </div>
                  <div style={{ background: 'var(--panel-hi)', border: '1px solid var(--hair)', borderRadius: '6px', padding: '10px', fontSize: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ color: 'var(--text-low)' }}>Camera ID:</span>
                      <b>{focusCamera.camera_id}</b>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ color: 'var(--text-low)' }}>Location:</span>
                      <span>{focusCamera.location || 'N/A'}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ color: 'var(--text-low)' }}>Source Type:</span>
                      <span>{focusCamera.source_type || 'RTSP'}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ color: 'var(--text-low)' }}>Condition:</span>
                      <span style={{ color: focusCamera.condition === 'CLEAR' ? 'var(--green)' : 'var(--gold)' }}>
                        {focusCamera.condition || 'CLEAR'} ({focusCamera.reliability_score ?? 100}%)
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--text-low)' }}>Active Targets:</span>
                      <b style={{ color: 'var(--gold)' }}>
                        {(activeTracksByCam[focusCamera.camera_id] || []).length}
                      </b>
                    </div>
                  </div>
                </div>

                {/* Active Targets List (Clickable to Activity Thread) */}
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-low)', textTransform: 'uppercase', marginBottom: '6px' }}>
                    Active Tracked Objects ({(activeTracksByCam[focusCamera.camera_id] || []).length})
                  </div>
                  {(activeTracksByCam[focusCamera.camera_id] || []).length === 0 ? (
                    <div style={{ fontSize: '12px', color: 'var(--text-low)', fontStyle: 'italic' }}>
                      No active targets in camera field.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {(activeTracksByCam[focusCamera.camera_id] || []).map((t) => {
                        const isHuman = t.object_type === 'HUMAN';
                        const rawMState = (t.movement_state || t.attributes?.movement_state || '').toUpperCase();
                        let humanState = 'STATIONARY';
                        if (rawMState === 'RUNNING' || rawMState === 'FAST' || (typeof t.speed === 'number' && t.speed > 80)) {
                          humanState = 'RUNNING';
                        } else if (rawMState === 'WALKING' || rawMState === 'MOVING' || (typeof t.speed === 'number' && t.speed > 8)) {
                          humanState = 'WALKING';
                        }
                        return (
                          <div
                            key={t.track_id}
                            style={{
                              background: 'var(--panel-hi)',
                              border: '1px solid var(--hair)',
                              padding: '8px 10px',
                              borderRadius: '4px',
                              fontSize: '11.5px',
                              cursor: 'pointer',
                              transition: 'all 0.15s ease',
                            }}
                            onClick={() => {
                              setFocusCamera(null);
                              if (onSelectTab) onSelectTab('threads', t.track_id);
                            }}
                            title={`Click to open Activity Thread for ${t.track_id}`}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: 600 }}>
                              <span style={{ color: isHuman ? 'var(--green)' : 'var(--gold)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                {isHuman ? <UserIcon size={11} /> : <VehicleIcon size={11} />}
                                {t.object_type}
                              </span>
                              <span style={{ fontFamily: 'var(--mono)', color: 'var(--text-hi)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                {t.track_id}
                                <ThreadIcon size={10} style={{ opacity: 0.6 }} />
                              </span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-low)', marginTop: '4px', fontSize: '10.5px' }}>
                              <span>State: {isHuman ? humanState : (t.movement_state || 'STATIONARY')}</span>
                              <span>Speed: {Math.round(t.speed || 0)} px/s</span>
                            </div>
                            {t.attributes?.person_name && (
                              <div style={{ color: '#f472b6', marginTop: '4px', fontSize: '10.5px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                <UserIcon size={11} />
                                Identified: {t.attributes.person_name}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Spatial Zones List */}
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-low)', textTransform: 'uppercase', marginBottom: '6px' }}>
                    Configured Zones ({(zonesByCamera[focusCamera.camera_id] || []).length})
                  </div>
                  {(zonesByCamera[focusCamera.camera_id] || []).length === 0 ? (
                    <div style={{ fontSize: '12px', color: 'var(--text-low)', fontStyle: 'italic' }}>
                      No zones configured on this feed.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {(zonesByCamera[focusCamera.camera_id] || []).map((z) => (
                        <div
                          key={z.zone_id}
                          style={{
                            background: 'var(--panel-hi)',
                            border: '1px solid var(--hair)',
                            padding: '6px 10px',
                            borderRadius: '4px',
                            fontSize: '11px',
                            display: 'flex',
                            justifyContent: 'space-between',
                          }}
                        >
                          <span>{z.name || z.zone_id}</span>
                          <span
                            style={{
                              color: z.zone_type === 'RESTRICTED' ? 'var(--red)' : 'var(--green)',
                              fontWeight: 600,
                            }}
                          >
                            {z.zone_type || 'RESTRICTED'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div style={{ marginTop: 'auto', paddingTop: '12px', borderTop: '1px solid var(--hair)' }}>
                  <button
                    type="button"
                    className="n-btn"
                    style={{ width: '100%', justifyContent: 'center' }}
                    onClick={() => setFocusCamera(null)}
                  >
                    Return to Grid View
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

