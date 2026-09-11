import { useState, useEffect, useRef, useMemo } from 'react';
import { api } from '../services/api';
import { SkeletonImage } from './SkeletonLoader';
import { CloseIcon, RefreshIcon, BoltIcon, AiSparklesIcon } from './Icons';

const SVG_WIDTH = 1000;
const SVG_HEIGHT = 562.5; // 16:9 aspect ratio

const OBJECT_TYPES = ['HUMAN', 'VEHICLE', 'UAV', 'ANIMAL'];

// Fast camera-space point-in-polygon algorithm matching backend geometry
function pointInPolygon(point, vs) {
  const x = point[0], y = point[1];
  let inside = false;
  for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
    const xi = vs[i][0], yi = vs[i][1];
    const xj = vs[j][0], yj = vs[j][1];
    const intersect = ((yi > y) !== (yj > y)) && (x < ((xj - xi) * (y - yi)) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

export function FencingView({
  cameras = [],
  tracks = [],
  events = [],
  alerts = [],
  zoneDensity = [],
  onSelectTab,
  onInvestigate,
}) {
  const [selectedCameraId, setSelectedCameraId] = useState(() => {
    return cameras[0]?.camera_id || 'CAM-01';
  });

  const [zones, setZones] = useState([]);
  const [loadingZones, setLoadingZones] = useState(false);
  const [selectedZoneId, setSelectedZoneId] = useState(null);
  const [backendDensity, setBackendDensity] = useState([]);

  // Drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawingPoints, setDrawingPoints] = useState([]);
  const [mousePos, setMousePos] = useState(null);
  const [draggingVertexIndex, setDraggingVertexIndex] = useState(null);

  // Inspector form state
  const [zoneName, setZoneName] = useState('');
  const [zoneType, setZoneType] = useState('RESTRICTED');
  const [zoneCapacity, setZoneCapacity] = useState(10);
  const [zoneEnabled, setZoneEnabled] = useState(true);
  const [selectedObjTypes, setSelectedObjTypes] = useState(['HUMAN', 'VEHICLE']);
  const [actionFeedback, setActionFeedback] = useState(null);

  const svgRef = useRef(null);

  // Load zones for current camera
  const loadCameraZones = async (camId) => {
    setLoadingZones(true);
    try {
      const res = await api.getZones(camId);
      setZones(Array.isArray(res) ? res : []);
    } catch (err) {
      console.error('Failed to load zones:', err);
    } finally {
      setLoadingZones(false);
    }
  };

  // Load density data from API
  const loadDensityData = async (camId) => {
    try {
      const res = await api.getZoneDensity(camId);
      if (Array.isArray(res)) {
        setBackendDensity(res);
      }
    } catch (err) {
      console.error('Failed to load zone density:', err);
    }
  };

  // Auto-select valid camera when cameras load or change
  useEffect(() => {
    if (cameras.length > 0 && !cameras.some((c) => c.camera_id === selectedCameraId)) {
      setSelectedCameraId(cameras[0].camera_id);
    }
  }, [cameras, selectedCameraId]);

  useEffect(() => {
    if (selectedCameraId) {
      loadCameraZones(selectedCameraId);
      loadDensityData(selectedCameraId);
      setSelectedZoneId(null);
      setIsDrawing(false);
      setDrawingPoints([]);
    }
  }, [selectedCameraId]);

  // Periodic density sync with backend
  useEffect(() => {
    if (!selectedCameraId) return;
    const interval = setInterval(() => {
      loadDensityData(selectedCameraId);
    }, 4000);
    return () => clearInterval(interval);
  }, [selectedCameraId]);

  // When selectedZoneId changes, populate inspector form
  useEffect(() => {
    if (selectedZoneId) {
      const z = zones.find((item) => item.zone_id === selectedZoneId);
      if (z) {
        setZoneName(z.name || '');
        setZoneType(z.zone_type || 'RESTRICTED');
        setZoneCapacity(z.capacity != null ? z.capacity : 10);
        setZoneEnabled(z.enabled !== false);
        setSelectedObjTypes(Array.isArray(z.object_types) ? z.object_types : ['HUMAN', 'VEHICLE']);
        setIsDrawing(false);
        setDrawingPoints([]);
      }
    }
  }, [selectedZoneId, zones]);

  const selectedCamera = useMemo(() => {
    return cameras.find((c) => c.camera_id === selectedCameraId) || cameras[0] || { camera_id: selectedCameraId, name: selectedCameraId };
  }, [cameras, selectedCameraId]);

  // Active tracks on this camera
  const cameraTracks = useMemo(() => {
    return tracks.filter((t) => t.status === 'ACTIVE' && t.camera_id === selectedCameraId && Array.isArray(t.current_position || (typeof t.current_position === 'string' && JSON.parse(t.current_position))));
  }, [tracks, selectedCameraId]);

  // Active human tracks on this camera (for People Density & Count)
  const cameraHumanTracks = useMemo(() => {
    return cameraTracks.filter((t) => (t.object_type || '').toUpperCase() === 'HUMAN');
  }, [cameraTracks]);

  // Monitored zones on this camera
  const cameraMonitoredZones = useMemo(() => {
    return zones.filter((z) => (z.zone_type || '').toUpperCase() === 'MONITORED');
  }, [zones]);

  // Continuously evaluate unique tracked people inside each monitored zone using existing YOLO + ByteTrack
  const liveMonitoredMetrics = useMemo(() => {
    return cameraMonitoredZones.map((z) => {
      let geom = z.geometry;
      if (typeof geom === 'string') {
        try {
          geom = JSON.parse(geom);
        } catch {
          geom = [];
        }
      }
      if (!Array.isArray(geom)) geom = [];

      const insideTrackIds = [];
      if (geom.length >= 3) {
        for (const t of cameraHumanTracks) {
          let pos = t.current_position;
          if (typeof pos === 'string') {
            try {
              pos = JSON.parse(pos);
            } catch {
              pos = null;
            }
          }
          if (pos && pos.length >= 4) {
            const [bx, by, bw, bh] = pos;
            const bc = [bx + bw / 2, by + bh];
            if (pointInPolygon(bc, geom)) {
              insideTrackIds.push(t.track_id);
            }
          }
        }
      }

      const count = insideTrackIds.length;
      const maxCap = Math.max(1, parseInt(z.capacity != null ? z.capacity : 10, 10));
      const anomalyThresh = maxCap;
      let status = 'CLEAR';
      if (count === 0) status = 'CLEAR';
      else if (count <= Math.ceil(maxCap * 0.35)) status = 'LOW';
      else if (count <= Math.ceil(maxCap * 0.75)) status = 'NORMAL';
      else if (count <= maxCap) status = 'HIGH';
      else status = 'OVERCROWDED';

      const isAnomaly = count > maxCap;

      // Also correlate with backend density record if available
      const beMatch = (backendDensity || []).find((bd) => bd.zone_id === z.zone_id) || (zoneDensity || []).find((zd) => zd.zone_id === z.zone_id);

      return {
        zone_id: z.zone_id,
        name: z.name || z.zone_id,
        camera_id: z.camera_id || selectedCameraId,
        camera_name: selectedCamera.name || selectedCameraId,
        enabled: z.enabled !== false,
        people_count: count,
        tracked_people: insideTrackIds,
        density_status: status,
        density_ratio: Math.min(1.0, count / maxCap),
        max_capacity: maxCap,
        anomaly_threshold: anomalyThresh,
        is_anomaly: isAnomaly,
        geometry: geom,
        backend_synced: !!beMatch,
      };
    });
  }, [cameraMonitoredZones, cameraHumanTracks, selectedCameraId, selectedCamera, backendDensity, zoneDensity]);

  // Total people in monitored zones for this camera
  const totalPeopleInMonitored = useMemo(() => {
    const allTrackIds = new Set();
    liveMonitoredMetrics.forEach((m) => {
      m.tracked_people.forEach((tid) => allTrackIds.add(tid));
    });
    return allTrackIds.size;
  }, [liveMonitoredMetrics]);

  const hasAnyAnomaly = useMemo(() => {
    return liveMonitoredMetrics.some((m) => m.is_anomaly);
  }, [liveMonitoredMetrics]);

  // Recent intrusion events on this camera
  const cameraIntrusions = useMemo(() => {
    return events.filter(
      (e) =>
        (e.camera_id === selectedCameraId || !e.camera_id) &&
        (e.event_type === 'INTRUSION' || e.event_type === 'RESTRICTED_ZONE_ENTRY' || e.description?.toLowerCase().includes('intrusion'))
    ).slice(0, 15);
  }, [events, selectedCameraId]);

  // Convert normalized point [0..1, 0..1] to SVG coordinates
  const toSvgCoords = (normPt) => {
    return [normPt[0] * SVG_WIDTH, normPt[1] * SVG_HEIGHT];
  };

  // Convert SVG coordinates to normalized [0..1, 0..1]
  const toNormCoords = (e) => {
    if (!svgRef.current) return [0, 0];
    const rect = svgRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    return [parseFloat(x.toFixed(4)), parseFloat(y.toFixed(4))];
  };

  // Canvas click handler
  const handleSvgClick = (e) => {
    if (draggingVertexIndex !== null) return;

    if (isDrawing) {
      const pt = toNormCoords(e);
      // If clicking near first point and we have at least 3 points, close polygon
      if (drawingPoints.length >= 3) {
        const [firstX, firstY] = drawingPoints[0];
        const dist = Math.hypot(pt[0] - firstX, pt[1] - firstY);
        if (dist < 0.04) {
          handleFinishDrawing();
          return;
        }
      }
      setDrawingPoints((prev) => [...prev, pt]);
    }
  };

  const handleSvgMouseMove = (e) => {
    if (!svgRef.current) return;
    const pt = toNormCoords(e);
    setMousePos(pt);

    // If dragging an existing vertex of selected zone
    if (draggingVertexIndex !== null && selectedZoneId) {
      setZones((prev) =>
        prev.map((z) => {
          if (z.zone_id !== selectedZoneId) return z;
          const newGeom = [...z.geometry];
          newGeom[draggingVertexIndex] = pt;
          return { ...z, geometry: newGeom };
        })
      );
    }
  };

  const handleMouseUp = () => {
    if (draggingVertexIndex !== null) {
      setDraggingVertexIndex(null);
    }
  };

  // Start new zone drawing
  const handleStartDrawing = (type = 'RESTRICTED', defaultName = '') => {
    setSelectedZoneId(null);
    setIsDrawing(true);
    setDrawingPoints([]);
    setZoneName(defaultName || `Zone ${zones.length + 1}`);
    setZoneType(type);
    setZoneCapacity(10);
    setZoneEnabled(true);
    setSelectedObjTypes(type === 'MONITORED' ? ['HUMAN'] : ['HUMAN', 'VEHICLE']);
  };

  const handleCancelDrawing = () => {
    setIsDrawing(false);
    setDrawingPoints([]);
  };

  const handleFinishDrawing = () => {
    if (drawingPoints.length < 3) {
      alert('A restricted zone requires at least 3 points to form a polygon.');
      return;
    }
    setIsDrawing(false);
  };

  // Save (Create or Update) Zone
  const handleSaveZone = async () => {
    const isNew = !selectedZoneId;
    const geom = isNew ? drawingPoints : zones.find((z) => z.zone_id === selectedZoneId)?.geometry;

    if (!geom || geom.length < 3) {
      alert('Zone polygon must contain at least 3 points.');
      return;
    }

    if (!zoneName.trim()) {
      alert('Please enter a zone name.');
      return;
    }

    const parsedCapacity = Math.max(1, parseInt(zoneCapacity, 10) || 10);

    try {
      if (isNew) {
        const payload = {
          camera_id: selectedCameraId,
          name: zoneName.trim(),
          zone_type: zoneType,
          geometry: geom,
          enabled: zoneEnabled,
          object_types: selectedObjTypes,
          capacity: parsedCapacity,
        };
        const created = await api.createZone(payload);
        setZones((prev) => [created, ...prev]);
        setSelectedZoneId(created.zone_id);
        setDrawingPoints([]);
        setActionFeedback('Zone created successfully!');
      } else {
        const payload = {
          name: zoneName.trim(),
          zone_type: zoneType,
          geometry: geom,
          enabled: zoneEnabled,
          object_types: selectedObjTypes,
          capacity: parsedCapacity,
        };
        const updated = await api.updateZone(selectedZoneId, payload);
        setZones((prev) => prev.map((z) => (z.zone_id === selectedZoneId ? updated : z)));
        setActionFeedback('Zone updated successfully!');
      }
    } catch (err) {
      alert(`Failed to save zone: ${err.message}`);
    } finally {
      setTimeout(() => setActionFeedback(null), 3000);
    }
  };

  // Delete Zone
  const handleDeleteZone = async (idToDelete) => {
    const id = idToDelete || selectedZoneId;
    if (!id) return;
    if (!window.confirm(`Are you sure you want to delete zone ${id}?`)) return;

    try {
      await api.deleteZone(id);
      setZones((prev) => prev.filter((z) => z.zone_id !== id));
      if (selectedZoneId === id) {
        setSelectedZoneId(null);
      }
      setActionFeedback(`Zone ${id} deleted.`);
    } catch (err) {
      alert(`Failed to delete zone: ${err.message}`);
    } finally {
      setTimeout(() => setActionFeedback(null), 3000);
    }
  };

  // Quick toggle enabled status
  const handleToggleZoneEnabled = async (e, z) => {
    e.stopPropagation();
    try {
      const nextEnabled = !z.enabled;
      const updated = await api.updateZone(z.zone_id, { enabled: nextEnabled });
      setZones((prev) => prev.map((item) => (item.zone_id === z.zone_id ? updated : item)));
      if (selectedZoneId === z.zone_id) {
        setZoneEnabled(nextEnabled);
      }
    } catch (err) {
      alert(`Failed to update status: ${err.message}`);
    }
  };

  // Toggle object type filter tag
  const handleToggleObjType = (type) => {
    setSelectedObjTypes((prev) => {
      if (prev.includes(type)) {
        if (prev.length === 1) return prev; // keep at least 1
        return prev.filter((t) => t !== type);
      } else {
        return [...prev, type];
      }
    });
  };

  const selectedZone = zones.find((z) => z.zone_id === selectedZoneId);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }} onMouseUp={handleMouseUp}>
      {/* PROFESSIONAL TACTICAL SENSOR & FEED CONTROL TILE */}
      <div className="fencing-top-tile">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span className="brand-mark" style={{ width: '28px', height: '28px' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <polygon points="12 2 2 7 12 12 22 7 12 2" />
                <polyline points="2 17 12 22 22 17" />
                <polyline points="2 12 12 17 22 12" />
              </svg>
            </span>
            <div>
              <div style={{ fontSize: '15px', fontWeight: '700', color: 'var(--text-hi)', letterSpacing: '0.3px' }}>
                Perimeter Fencing & Restricted Zones
              </div>
              <span className="section-sub" style={{ fontSize: '11.5px', color: 'var(--text-low)' }}>
                Spatial intrusion detection · Bottom-center bounding-box tracking · Camera-space geometry
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span className="nav-badge" style={{ background: 'var(--panel-hi)', color: 'var(--text-mid)', border: '1px solid var(--hair)', fontSize: '11px', padding: '4px 10px' }}>
              ZONES: <b style={{ color: 'var(--text-hi)', marginLeft: '4px' }}>{zones.filter((z) => z.enabled).length} ACTIVE / {zones.length} TOTAL</b>
            </span>
            <span className="nav-badge" style={{ background: cameraIntrusions.length > 0 ? 'var(--red-dim)' : 'var(--panel-hi)', color: cameraIntrusions.length > 0 ? 'var(--red)' : 'var(--text-mid)', border: '1px solid var(--hair)', fontSize: '11px', padding: '4px 10px' }}>
              BREACHES: <b style={{ marginLeft: '4px' }}>{cameraIntrusions.length}</b>
            </span>
            <span className="nav-badge" style={{ background: 'rgba(47, 204, 139, 0.12)', color: 'var(--green)', border: '1px solid rgba(47, 204, 139, 0.25)', fontSize: '11px', padding: '4px 10px' }}>
              ACTIVE MONITORING
            </span>
          </div>
        </div>

        {/* CAMERA SELECTOR STRIP */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px', paddingTop: '10px', borderTop: '1px solid var(--hair)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '10px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
              PRIMARY CAMERA:
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            {cameras.map((c) => {
              const isSelected = c.camera_id === selectedCameraId;
              const isOnline = c.status === 'ONLINE';
              return (
                <button
                  key={c.camera_id}
                  onClick={() => setSelectedCameraId(c.camera_id)}
                  className={`n-btn ${isSelected ? 'active' : ''}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    borderColor: isSelected ? 'var(--green)' : undefined,
                    background: isSelected ? 'var(--panel-hover)' : undefined,
                    fontSize: '11.5px',
                    padding: '5px 12px',
                  }}
                >
                  <span
                    style={{
                      width: '7px',
                      height: '7px',
                      borderRadius: '50%',
                      background: isOnline ? 'var(--green)' : 'var(--red)',
                      boxShadow: isOnline && isSelected ? '0 0 6px var(--green)' : 'none',
                    }}
                  />
                  <b>{c.name || c.camera_id}</b>
                  <span style={{ fontSize: '10px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>({c.camera_id})</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* FEEDBACK BANNER */}
      {actionFeedback && (
        <div
          style={{
            padding: '10px 14px',
            borderRadius: '6px',
            background: 'rgba(47, 204, 139, 0.12)',
            border: '1px solid var(--green)',
            color: 'var(--text-hi)',
            fontSize: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>{actionFeedback}</span>
          <button onClick={() => setActionFeedback(null)} style={{ color: 'var(--text-low)', background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}>
            <CloseIcon size={12} />
          </button>
        </div>
      )}

      {/* MAIN TWO-COLUMN FENCING LAYOUT */}
      <div className="fencing-layout">
        {/* LEFT COLUMN: INTERACTIVE STREAM & CANVAS + LIVE PEOPLE DENSITY TILE */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', minWidth: 0 }}>
          <div className="fencing-viewport-card">
            <div className="fencing-viewport-head">
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className="brand-mark" style={{ width: '22px', height: '22px' }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polygon points="12 2 2 7 12 12 22 7 12 2" />
                    <polyline points="2 17 12 22 22 17" />
                    <polyline points="2 12 12 17 22 12" />
                  </svg>
                </span>
                <span style={{ fontWeight: '700', fontSize: '13px' }}>
                  {selectedCamera.name} ({selectedCamera.camera_id})
                </span>
                <span className="nav-badge neutral" style={{ fontSize: '10px' }}>
                  {zones.length} {zones.length === 1 ? 'ZONE' : 'ZONES'}
                </span>
              </div>

              {/* ACTION TOOLBAR */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {!isDrawing ? (
                  <button
                    className="n-btn primary"
                    onClick={() => handleStartDrawing('RESTRICTED')}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 12px' }}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="12" y1="5" x2="12" y2="19" />
                      <line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    Draw Restricted Zone
                  </button>
                ) : (
                <>
                  <span style={{ fontSize: '11px', color: 'var(--gold)', fontFamily: 'var(--mono)' }}>
                    Points: {drawingPoints.length} (Click feed to place, close at start)
                  </span>
                  <button
                    className="n-btn primary"
                    onClick={handleFinishDrawing}
                    disabled={drawingPoints.length < 3}
                    style={{ fontSize: '11px', padding: '4px 10px' }}
                  >
                    Finish Zone
                  </button>
                  <button
                    className="n-btn"
                    onClick={handleCancelDrawing}
                    style={{ fontSize: '11px', padding: '4px 8px' }}
                  >
                    Cancel
                  </button>
                </>
              )}
            </div>
          </div>

          {/* CANVAS VIEWPORT CONTAINER */}
          <div className="fencing-canvas-wrap">
            {/* Background Camera Feed */}
            {selectedCamera.stream_configured !== false ? (
              <img
                src={api.getStreamUrl(selectedCameraId)}
                alt={`${selectedCamera.name} stream`}
                className="fencing-stream-img"
                onError={(e) => {
                  e.target.style.display = 'none';
                }}
              />
            ) : (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--text-low)',
                  fontFamily: 'var(--mono)',
                  fontSize: '12px',
                }}
              >
                STANDBY · STREAM OFFLINE
              </div>
            )}

            {/* INTERACTIVE SVG OVERLAY */}
            <svg
              ref={svgRef}
              viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
              className="fencing-canvas-svg"
              onClick={handleSvgClick}
              onMouseMove={handleSvgMouseMove}
              style={{ cursor: isDrawing ? 'crosshair' : 'default' }}
            >
              {/* 1. Render Configured Zones */}
              {zones.map((z) => {
                if (!z.geometry || z.geometry.length < 3) return null;
                const isSelected = z.zone_id === selectedZoneId;
                const pointsStr = z.geometry.map((pt) => toSvgCoords(pt).join(',')).join(' ');

                // Calculate centroid for zone label
                const avgX = (z.geometry.reduce((acc, p) => acc + p[0], 0) / z.geometry.length) * SVG_WIDTH;
                const avgY = (z.geometry.reduce((acc, p) => acc + p[1], 0) / z.geometry.length) * SVG_HEIGHT;

                let polyClass = 'fencing-polygon';
                if (!z.enabled) polyClass += ' disabled';
                else if (z.zone_type === 'RESTRICTED') polyClass += ' restricted';
                else polyClass += ' monitored';

                if (isSelected) polyClass += ' selected';

                const isMonitored = (z.zone_type || '').toUpperCase() === 'MONITORED';
                const zoneMetric = liveMonitoredMetrics.find((m) => m.zone_id === z.zone_id);

                return (
                  <g key={z.zone_id}>
                    {/* Zone Polygon Fill & Stroke */}
                    <polygon
                      points={pointsStr}
                      className={polyClass}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isDrawing) setSelectedZoneId(z.zone_id);
                      }}
                    />

                    {/* Zone Label */}
                    <g transform={`translate(${avgX}, ${avgY})`} pointerEvents="none">
                      <rect
                        x={isMonitored ? "-95" : "-65"}
                        y="-14"
                        width={isMonitored ? "190" : "130"}
                        height="26"
                        rx="4"
                        fill="rgba(5, 5, 5, 0.88)"
                        stroke={isSelected ? (isMonitored ? 'var(--green)' : '#ff7875') : isMonitored ? 'var(--green)' : z.enabled ? 'var(--red)' : 'var(--hair)'}
                        strokeWidth={isSelected ? "1.5" : "1"}
                      />
                      <text
                        x="0"
                        y="3"
                        fill={isMonitored ? 'var(--green)' : z.enabled ? '#ffffff' : 'var(--text-low)'}
                        fontSize="11"
                        fontWeight="700"
                        fontFamily="var(--sans)"
                        textAnchor="middle"
                      >
                        {isMonitored && zoneMetric
                          ? `${z.name || z.zone_id} · ${zoneMetric.people_count} · ${zoneMetric.density_status}`
                          : (z.name || z.zone_id)}
                      </text>
                    </g>

                    {/* Draggable Vertex Handles for Selected Zone */}
                    {isSelected &&
                      z.geometry.map((pt, idx) => {
                        const [px, py] = toSvgCoords(pt);
                        return (
                          <circle
                            key={idx}
                            cx={px}
                            cy={py}
                            r="5"
                            className="fencing-vertex-handle"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              setDraggingVertexIndex(idx);
                            }}
                          />
                        );
                      })}
                  </g>
                );
              })}

              {/* 2. Render In-Progress Drawing Points & Lines */}
              {isDrawing && drawingPoints.length > 0 && (
                <g>
                  {/* Closed preview if >= 3 points */}
                  {drawingPoints.length >= 3 && (
                    <polygon
                      points={drawingPoints.map((pt) => toSvgCoords(pt).join(',')).join(' ')}
                      fill="rgba(239, 82, 81, 0.15)"
                      stroke="var(--red)"
                      strokeWidth="1.5"
                      strokeDasharray="4 4"
                    />
                  )}

                  {/* Connected line segments */}
                  {drawingPoints.map((pt, idx) => {
                    if (idx === 0) return null;
                    const [p1x, p1y] = toSvgCoords(drawingPoints[idx - 1]);
                    const [p2x, p2y] = toSvgCoords(pt);
                    return (
                      <line
                        key={`seg-${idx}`}
                        x1={p1x}
                        y1={p1y}
                        x2={p2x}
                        y2={p2y}
                        stroke="var(--red)"
                        strokeWidth="2"
                      />
                    );
                  })}

                  {/* Live guideline from last placed vertex to mouse cursor */}
                  {mousePos && drawingPoints.length > 0 && (
                    <line
                      x1={toSvgCoords(drawingPoints[drawingPoints.length - 1])[0]}
                      y1={toSvgCoords(drawingPoints[drawingPoints.length - 1])[1]}
                      x2={toSvgCoords(mousePos)[0]}
                      y2={toSvgCoords(mousePos)[1]}
                      stroke="#ff7875"
                      strokeWidth="1.5"
                      strokeDasharray="3 3"
                    />
                  )}

                  {/* Vertex circles */}
                  {drawingPoints.map((pt, idx) => {
                    const [px, py] = toSvgCoords(pt);
                    const isFirst = idx === 0;
                    return (
                      <circle
                        key={`pt-${idx}`}
                        cx={px}
                        cy={py}
                        r={isFirst ? '6' : '4'}
                        fill={isFirst ? 'var(--gold)' : '#ffffff'}
                        stroke="var(--red)"
                        strokeWidth="2"
                      />
                    );
                  })}
                </g>
              )}

              {/* 3. Live Tracks Overlay with Bottom-Center Evaluation Indicator */}
              {cameraTracks.map((t) => {
                let pos = t.current_position;
                if (typeof pos === 'string') {
                  try {
                    pos = JSON.parse(pos);
                  } catch {
                    pos = null;
                  }
                }
                if (!pos || pos.length < 4) return null;

                const [bx, by, bw, bh] = pos;
                const svgBx = bx * SVG_WIDTH;
                const svgBy = by * SVG_HEIGHT;
                const svgBw = bw * SVG_WIDTH;
                const svgBh = bh * SVG_HEIGHT;

                // Bottom-center point
                const bcX = (bx + bw / 2) * SVG_WIDTH;
                const bcY = (by + bh) * SVG_HEIGHT;

                const objType = (t.object_type || 'OBJECT').toUpperCase();

                return (
                  <g key={t.track_id}>
                    {/* Bounding box outline */}
                    <rect
                      x={svgBx}
                      y={svgBy}
                      width={svgBw}
                      height={svgBh}
                      fill="rgba(47, 204, 139, 0.08)"
                      stroke="var(--green)"
                      strokeWidth="1.5"
                      rx="2"
                    />

                    {/* Track tag label */}
                    <g transform={`translate(${svgBx}, ${svgBy - 6})`}>
                      <rect
                        x="0"
                        y="-12"
                        width={Math.max(60, t.track_id.length * 7 + 10)}
                        height="16"
                        rx="3"
                        fill="rgba(10, 15, 20, 0.9)"
                        stroke="var(--green)"
                        strokeWidth="1"
                      />
                      <text x="4" y="0" fill="#2FCC8B" fontSize="9" fontWeight="700" fontFamily="var(--mono)">
                        {objType} {t.track_id}
                      </text>
                    </g>

                    {/* Bottom-Center Tracking Point Marker */}
                    <circle cx={bcX} cy={bcY} r="4" fill="var(--green)" stroke="#ffffff" strokeWidth="1.5" />
                    <circle cx={bcX} cy={bcY} r="8" fill="none" stroke="var(--green)" strokeWidth="1" opacity="0.6" className="fencing-bc-marker" />
                  </g>
                );
              })}
            </svg>
          </div>

          {/* HELPER HINT FOOTER */}
          <div
            style={{
              padding: '8px 14px',
              borderTop: '1px solid var(--hair)',
              background: 'var(--panel-hi)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '11px',
              color: 'var(--text-mid)',
              fontFamily: 'var(--mono)',
            }}
          >
            <span>
              {isDrawing
                ? 'Click points to build polygon. Double-click or click initial point to close.'
                : selectedZoneId
                ? 'Drag white vertex points to adjust boundary. Edit settings in right inspector.'
                : 'Click any zone polygon to select & edit. Click "Draw Restricted Zone" to create new perimeter.'}
            </span>
            {mousePos && (
              <span style={{ color: 'var(--text-low)' }}>
                X: {(mousePos[0] * 100).toFixed(1)}% · Y: {(mousePos[1] * 100).toFixed(1)}%
              </span>
            )}
          </div>
        </div>

        {/* PEOPLE DENSITY & ANOMALY TILE ITEM */}
        <div className="fencing-density-tile">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span className="brand-mark" style={{ width: '28px', height: '28px', background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-hi)', border: '1px solid var(--hair)' }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
              </span>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '15px', fontWeight: '700', color: 'var(--text-hi)', letterSpacing: '0.3px' }}>
                    People Density/Anomaly
                  </span>
                  <span className="nav-badge" style={{ background: 'var(--panel-hi)', color: 'var(--text-mid)', border: '1px solid var(--hair)', fontSize: '10px', padding: '2px 8px' }}>
                    MONITORED ZONES ONLY
                  </span>
                </div>
                <span className="section-sub" style={{ fontSize: '11.5px', color: 'var(--text-low)' }}>
                  Live people count & density anomalies · Continuous ByteTrack unique tracking · Camera-space geometry
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span className="nav-badge" style={{ background: 'var(--panel-hi)', color: 'var(--text-mid)', border: '1px solid var(--hair)', fontSize: '11px', padding: '4px 10px' }}>
                ZONES: <b style={{ color: 'var(--text-hi)', marginLeft: '4px' }}>{liveMonitoredMetrics.length} MONITORED</b>
              </span>
              <span className="nav-badge" style={{ background: 'var(--panel-hi)', color: 'var(--text-mid)', border: '1px solid var(--hair)', fontSize: '11px', padding: '4px 10px' }}>
                LIVE COUNT: <b style={{ color: 'var(--green)', marginLeft: '4px' }}>{totalPeopleInMonitored} PEOPLE PRESENT</b>
              </span>
              <span
                className="nav-badge"
                style={{
                  background: hasAnyAnomaly ? 'rgba(239, 82, 81, 0.16)' : 'rgba(47, 204, 139, 0.12)',
                  color: hasAnyAnomaly ? 'var(--red)' : 'var(--green)',
                  border: hasAnyAnomaly ? '1px solid rgba(239, 82, 81, 0.45)' : '1px solid rgba(47, 204, 139, 0.25)',
                  fontSize: '11px',
                  padding: '4px 10px',
                }}
              >
                {hasAnyAnomaly ? 'ANOMALY: OVERCROWDED' : 'STATUS: NOMINAL'}
              </span>
            </div>
          </div>

          {/* CONFIGURED MONITORED ZONES DISPLAY */}
          {liveMonitoredMetrics.length > 0 ? (
            <div className="fencing-density-grid">
              {liveMonitoredMetrics.map((md) => {
                const isSelected = md.zone_id === selectedZoneId;
                const fillPct = Math.min(100, Math.round((md.people_count / md.max_capacity) * 100));
                let badgeClass = 'density-badge-normal';
                let fillColor = 'var(--green)';
                if (md.density_status === 'CLEAR') {
                  badgeClass = 'density-badge-clear';
                  fillColor = 'rgba(255,255,255,0.2)';
                } else if (md.density_status === 'LOW') {
                  badgeClass = 'density-badge-low';
                  fillColor = 'var(--green)';
                } else if (md.density_status === 'NORMAL') {
                  badgeClass = 'density-badge-normal';
                  fillColor = 'var(--green)';
                } else if (md.density_status === 'HIGH') {
                  badgeClass = 'density-badge-high';
                  fillColor = 'var(--gold)';
                } else if (md.density_status === 'OVERCROWDED') {
                  badgeClass = 'density-badge-anomaly';
                  fillColor = 'var(--red)';
                }

                return (
                  <div
                    key={md.zone_id}
                    className={`fencing-density-card ${md.is_anomaly ? 'anomaly' : ''} ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedZoneId(md.zone_id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: md.is_anomaly ? 'var(--red)' : md.people_count > 0 ? 'var(--green)' : 'var(--text-low)',
                            boxShadow: md.people_count > 0 ? (md.is_anomaly ? '0 0 8px var(--red)' : '0 0 8px rgba(47, 204, 139, 0.4)') : 'none',
                          }}
                        />
                        <div>
                          <div style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-hi)' }}>
                            {md.name}
                          </div>
                          <span style={{ fontSize: '10.5px', color: 'var(--text-low)' }}>
                            {md.camera_name} · {md.zone_id}
                          </span>
                        </div>
                      </div>

                      <span className={`nav-badge ${badgeClass}`} style={{ fontSize: '10px', padding: '3px 8px', textTransform: 'uppercase', fontWeight: '700' }}>
                        {md.density_status}
                      </span>
                    </div>

                    {/* LIVE PEOPLE COUNT HERO DISPLAY */}
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '6px 0' }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                        <span style={{ fontSize: '28px', fontWeight: '800', color: md.people_count > 0 ? (md.is_anomaly ? 'var(--red)' : 'var(--text-hi)') : 'var(--text-mid)', lineHeight: '1' }}>
                          {md.people_count}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--text-low)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          {md.people_count === 1 ? 'Person Present (Live)' : 'People Present (Live)'}
                        </span>
                      </div>
                      <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                        Capacity: {md.people_count}/{md.max_capacity}
                      </span>
                    </div>

                    {/* CAPACITY METER GAUGE */}
                    <div className="density-gauge-track" title={`${fillPct}% capacity`}>
                      <div
                        className="density-gauge-fill"
                        style={{
                          width: `${Math.max(4, fillPct)}%`,
                          background: fillColor,
                        }}
                      />
                    </div>

                    {/* ACTIVE UNIQUE TRACKED PEOPLE CHIPS */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px', fontSize: '10.5px', paddingTop: '4px' }}>
                      <span style={{ color: 'var(--text-low)', fontSize: '10px' }}>Active Track IDs:</span>
                      {md.tracked_people.length > 0 ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                          {md.tracked_people.slice(0, 4).map((tid) => (
                            <span
                              key={tid}
                              className="density-track-chip"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (onSelectTab) onSelectTab('threads', tid);
                              }}
                              title="Click to view target thread"
                              style={{ cursor: 'pointer' }}
                            >
                              {tid}
                            </span>
                          ))}
                          {md.tracked_people.length > 4 && (
                            <span style={{ fontSize: '10px', color: 'var(--text-low)' }}>
                              +{md.tracked_people.length - 4} more
                            </span>
                          )}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--text-low)', fontSize: '10px' }}>
                          —
                        </span>
                      )}
                    </div>

                    {md.is_anomaly && (
                      <div style={{ padding: '6px 10px', borderRadius: '5px', background: 'rgba(239, 82, 81, 0.12)', border: '1px solid rgba(239, 82, 81, 0.3)', color: 'var(--red)', fontSize: '10.5px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <BoltIcon size={12} />
                        <span>Capacity threshold ({md.max_capacity}) exceeded!</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="density-empty-box">
              <div style={{ color: 'var(--text-mid)', fontSize: '12.5px', maxWidth: '540px' }}>
                No monitored zones defined for <b>{selectedCamera.name}</b>. Create a zone with classification <b>"MONITORED"</b> to track live people counts and detect density anomalies.
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <button
                  className="n-btn primary"
                  onClick={() => handleStartDrawing('MONITORED', 'Monitored Zone')}
                  style={{ fontSize: '11.5px', padding: '6px 14px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  + Create Monitored Zone
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* RIGHT COLUMN: ZONE CONFIGURATION INSPECTOR & CAMERA ZONES LIST */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* INSPECTOR PANEL */}
          <div className="fencing-panel">
            <div className="fencing-panel-head">
              <span style={{ fontWeight: '700', fontSize: '13px', letterSpacing: '0.5px' }}>
                {isDrawing ? 'NEW ZONE SPECIFICATION' : selectedZoneId ? 'ZONE INSPECTOR' : 'ZONE CONFIGURATION'}
              </span>
              {selectedZoneId && (
                <span className="nav-badge" style={{ background: zoneEnabled ? 'var(--red-dim)' : 'var(--panel-hover)', color: zoneEnabled ? 'var(--red)' : 'var(--text-low)' }}>
                  {selectedZoneId}
                </span>
              )}
            </div>

            {isDrawing || selectedZoneId ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {/* Name field */}
                <div className="fencing-form-group">
                  <label className="fencing-label">Zone Name</label>
                  <input
                    type="text"
                    value={zoneName}
                    onChange={(e) => setZoneName(e.target.value)}
                    placeholder="Zone Name"
                    className="fencing-input"
                  />
                </div>

                {/* Zone Type */}
                <div className="fencing-form-group">
                  <label className="fencing-label">Zone Classification</label>
                  <select
                    value={zoneType}
                    onChange={(e) => setZoneType(e.target.value)}
                    className="fencing-select"
                  >
                    <option value="RESTRICTED">RESTRICTED (Perimeter breach alert)</option>
                    <option value="VIRTUAL_FENCE">VIRTUAL FENCE (Crossing boundary)</option>
                    <option value="MONITORED">MONITORED (People density & anomaly tracking)</option>
                  </select>
                </div>

                {/* Zone Capacity field */}
                <div className="fencing-form-group">
                  <label className="fencing-label">Zone Capacity</label>
                  <input
                    type="number"
                    min="1"
                    max="500"
                    value={zoneCapacity}
                    onChange={(e) => setZoneCapacity(Math.max(1, parseInt(e.target.value, 10) || 1))}
                    className="fencing-input"
                  />
                  <span style={{ fontSize: '10px', color: 'var(--text-low)' }}>
                    Threshold used for live people density and anomaly detection
                  </span>
                </div>

                {/* Enabled status toggle */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid var(--hair)', borderBottom: '1px solid var(--hair)' }}>
                  <div>
                    <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-hi)' }}>Active Monitoring</span>
                    <p style={{ fontSize: '10px', color: 'var(--text-low)' }}>Enable intrusion alarms for this zone</p>
                  </div>
                  <button
                    onClick={() => setZoneEnabled((prev) => !prev)}
                    className="n-btn"
                    style={{
                      background: zoneEnabled ? 'var(--green-dim)' : 'var(--panel-hover)',
                      borderColor: zoneEnabled ? 'var(--green)' : 'var(--hair)',
                      color: zoneEnabled ? 'var(--green)' : 'var(--text-low)',
                      fontSize: '11px',
                      padding: '4px 10px',
                    }}
                  >
                    {zoneEnabled ? 'ENABLED' : 'DISABLED'}
                  </button>
                </div>

                {/* Object-type filter tags */}
                <div className="fencing-form-group">
                  <label className="fencing-label">Target Object Filter</label>
                  <span style={{ fontSize: '10px', color: 'var(--text-low)' }}>
                    Only trigger intrusions when filtered object types enter
                  </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
                    {OBJECT_TYPES.map((type) => {
                      const active = selectedObjTypes.includes(type);
                      return (
                        <span
                          key={type}
                          onClick={() => handleToggleObjType(type)}
                          className={`fencing-tag-pill ${active ? 'active' : ''}`}
                        >
                          {type}
                        </span>
                      );
                    })}
                  </div>
                </div>

                {/* Save & Delete Action Buttons */}
                <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                  <button
                    onClick={handleSaveZone}
                    className="n-btn primary"
                    style={{ flex: 1, padding: '8px', fontSize: '12px' }}
                  >
                    {isDrawing ? 'Save Zone' : 'Update Zone'}
                  </button>
                  {selectedZoneId && (
                    <button
                      onClick={() => handleDeleteZone(selectedZoneId)}
                      className="n-btn"
                      style={{ padding: '8px 12px', borderColor: 'var(--red)', color: 'var(--red)' }}
                      title="Delete Zone"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--text-low)', fontSize: '12px' }}>
                <p>Select an existing zone from below or click "Draw Restricted Zone" to begin.</p>
              </div>
            )}
          </div>

          {/* ALL CONFIGURED ZONES LIST */}
          <div className="fencing-panel">
            <div className="fencing-panel-head">
              <span style={{ fontWeight: '700', fontSize: '13px', letterSpacing: '0.5px' }}>
                CONFIGURED ZONES ({zones.length})
              </span>
              <button
                onClick={() => loadCameraZones(selectedCameraId)}
                className="n-btn"
                style={{ fontSize: '11px', padding: '2px 8px', display: 'inline-flex', alignItems: 'center' }}
                title="Refresh zones"
              >
                <RefreshIcon size={11} />
              </button>
            </div>

            <div className="fencing-scroll-list">
              {zones.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-low)', fontSize: '12px' }}>
                  No zones configured for {selectedCamera.name}.
                </div>
              ) : (
                zones.map((z) => {
                  const isSelected = z.zone_id === selectedZoneId;
                  const isMon = (z.zone_type || '').toUpperCase() === 'MONITORED';
                  const monMetric = liveMonitoredMetrics.find((m) => m.zone_id === z.zone_id);

                  return (
                    <div
                      key={z.zone_id}
                      className={`fencing-zone-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedZoneId(z.zone_id)}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span
                            style={{
                              width: '6px',
                              height: '6px',
                              borderRadius: '50%',
                              background: !z.enabled ? 'var(--text-low)' : isMon ? 'var(--green)' : 'var(--red)',
                            }}
                          />
                          <b style={{ fontSize: '12px', color: 'var(--text-hi)' }}>{z.name}</b>
                          {isMon && (
                            <span
                              className="nav-badge"
                              style={{
                                fontSize: '9px',
                                padding: '1px 6px',
                                background: 'rgba(47, 204, 139, 0.12)',
                                color: 'var(--green)',
                                border: '1px solid rgba(47, 204, 139, 0.25)',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '3px',
                              }}
                            >
                              {monMetric ? (
                                <>
                                  <span>{monMetric.people_count}</span>
                                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" style={{ display: 'inline-block' }}>
                                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                                    <circle cx="12" cy="7" r="4" />
                                  </svg>
                                  <span>· {monMetric.density_status}</span>
                                </>
                              ) : (
                                'MONITORED'
                              )}
                            </span>
                          )}
                        </div>
                        <span style={{ fontSize: '10px', color: 'var(--text-low)', fontFamily: 'var(--mono)', marginLeft: '12px' }}>
                           {z.zone_id} · {z.zone_type} · {(z.object_types || []).join(', ')}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <button
                          onClick={(e) => handleToggleZoneEnabled(e, z)}
                          className="n-btn"
                          style={{
                            padding: '2px 6px',
                            fontSize: '10px',
                            color: z.enabled ? 'var(--green)' : 'var(--text-low)',
                          }}
                          title={z.enabled ? 'Click to disable' : 'Click to enable'}
                        >
                          {z.enabled ? 'ON' : 'OFF'}
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteZone(z.zone_id);
                          }}
                          className="n-btn"
                          style={{ padding: '2px 6px', fontSize: '10px', color: 'var(--text-low)', display: 'inline-flex', alignItems: 'center' }}
                          title="Delete zone"
                        >
                          <CloseIcon size={10} />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* LIVE INTRUSION & BREACH LOG (SHIFTED TO RIGHT COLUMN) */}
          <div className="fencing-panel">
            <div className="fencing-panel-head">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="brand-mark" style={{ width: '22px', height: '22px', background: 'var(--red-dim)', color: 'var(--red)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                  <BoltIcon size={12} />
                </span>
                <span style={{ fontWeight: '700', fontSize: '13px', letterSpacing: '0.5px' }}>
                  LIVE INTRUSION LOG
                </span>
              </div>
              <span className="nav-badge" style={{ background: cameraIntrusions.length > 0 ? 'var(--red-dim)' : 'var(--panel-hi)', color: cameraIntrusions.length > 0 ? 'var(--red)' : 'var(--text-low)' }}>
                {cameraIntrusions.length} {cameraIntrusions.length === 1 ? 'BREACH' : 'BREACHES'}
              </span>
            </div>

            <div className="fencing-scroll-list" style={{ maxHeight: '310px' }}>
              {cameraIntrusions.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '24px 12px', color: 'var(--text-low)', fontSize: '11.5px' }}>
                  Perimeter nominal. No intrusion breaches recorded on {selectedCamera.name}.
                </div>
              ) : (
                cameraIntrusions.map((ev) => {
                  const timeStr = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : 'N/A';
                  return (
                    <div key={ev.event_id} className="fencing-intrusion-item">
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="nav-badge" style={{ background: 'rgba(239, 82, 81, 0.15)', color: 'var(--red)', border: '1px solid rgba(239, 82, 81, 0.3)', fontSize: '9.5px', padding: '1px 5px' }}>
                            {ev.event_type}
                          </span>
                          <span style={{ fontFamily: 'var(--mono)', fontSize: '10.5px', color: 'var(--text-low)' }}>
                            {timeStr}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="nav-badge" style={{ background: 'var(--red-dim)', color: 'var(--red)', fontSize: '9.5px', padding: '1px 5px' }}>
                            {ev.severity || 'HIGH'}
                          </span>
                          {onInvestigate && (
                            <button
                              className="n-btn ai-investigate"
                              style={{ padding: '2px 7px', fontSize: '10px' }}
                              onClick={() => onInvestigate(ev)}
                              title="Investigate this intrusion with AI"
                            >
                              <AiSparklesIcon size={10} />
                              <span>Investigate</span>
                            </button>
                          )}
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ color: 'var(--text-low)' }}>Target:</span>
                          {ev.track_id ? (
                            <button
                              className="n-chip"
                              style={{ cursor: 'pointer', color: 'var(--green)', padding: '1px 5px', fontSize: '10px', display: 'inline-flex', alignItems: 'center' }}
                              onClick={() => onSelectTab && onSelectTab('threads', ev.track_id)}
                              title="Click to view target thread"
                            >
                              {ev.track_id}
                            </button>
                          ) : (
                            <span style={{ fontFamily: 'var(--mono)', color: 'var(--text-low)' }}>N/A</span>
                          )}
                        </div>
                        <span style={{ fontFamily: 'var(--mono)', fontSize: '10.5px', color: 'var(--text-hi)' }}>
                          {ev.zone_id || 'RESTRICTED-AREA'}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10.5px', paddingTop: '4px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ color: 'var(--text-low)', fontSize: '10px' }}>Vector:</span>
                        <span style={{ color: 'var(--gold)', fontFamily: 'var(--mono)', fontWeight: '600' }}>
                          {ev.direction || 'OUTSIDE → INSIDE'}
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
