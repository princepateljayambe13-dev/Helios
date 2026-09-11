import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { api, V1, resolveMediaUrl } from '../services/api';
import { SkeletonImage, SkeletonBox, SkeletonText } from './SkeletonLoader';
import {
  RefreshIcon,
  PinIcon,
  ClapperIcon,
  CameraIcon,
  VideoIcon,
  MicIcon,
  BoltIcon,
  SearchIcon,
  CloseIcon,
  AiSparklesIcon,
  FaceIcon,
  PersonIcon,
} from './Icons';

export function ActivityThreadsView({ tracks = [], selectedTrackId, onInvestigate, onSelectTab }) {
  const [threads, setThreads] = useState([]);
  const [selectedThread, setSelectedThread] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [clearingEnded, setClearingEnded] = useState(false);
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [movementFilter, setMovementFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [showCoordinates, setShowCoordinates] = useState(false);
  const [previewEvidence, setPreviewEvidence] = useState(null);

  const tracksRef = useRef(tracks);
  tracksRef.current = tracks;

  const fetchThreads = useCallback(async (targetTrackId = null, isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const params = { limit: 50, status: 'ACTIVE' };
      if (['SUV', 'SEDAN', 'TRUCK', 'VAN'].includes(typeFilter)) {
        params.objectType = 'VEHICLE';
        params.vehicleType = typeFilter === 'TRUCK' ? 'heavy truck' : typeFilter.toLowerCase();
      } else if (typeFilter !== 'ALL') {
        params.objectType = typeFilter === 'MOTION' ? 'UNCLASSIFIED' : typeFilter;
      }
      if (movementFilter !== 'ALL') {
        params.movement_state = movementFilter;
      }

      let loadedThreads = [];
      try {
        const data = await api.getThreads(params);
        if (Array.isArray(data)) loadedThreads = data;
      } catch (e) {
        console.warn('API getThreads error, checking fallback tracks:', e);
      }

      // If backend returned no threads, fall back to realtime tracks prop
      const fallbackTracks = tracksRef.current;
      if (loadedThreads.length === 0 && fallbackTracks && fallbackTracks.length > 0) {
        loadedThreads = fallbackTracks.map((t) => ({
          track_id: t.track_id,
          object_type: t.object_type || 'UNKNOWN',
          camera_id: t.camera_id || 'CAM-01',
          status: t.status || 'ACTIVE',
          created_at: t.created_at || new Date().toISOString(),
          last_seen_at: t.last_seen_at || new Date().toISOString(),
          positions_count: 1,
          detections_count: 1,
          timeline: [
            {
              node_type: 'CAMERA_DETECTION',
              title: `Initial ${t.object_type || 'Target'} Detection`,
              camera_id: t.camera_id || 'CAM-01',
              timestamp: t.created_at || new Date().toISOString(),
              detail: `Real-time detected on ${t.camera_id || 'CAM-01'}.`,
            },
          ],
          evidence: [],
          positions: [],
        }));
      }

      const lookForId = targetTrackId || selectedTrackId;
      if (lookForId) {
        const found = loadedThreads.find((t) => t.track_id === lookForId);
        if (!found) {
          try {
            const singleThread = await api.getTrackThread(lookForId);
            if (singleThread && singleThread.track_id) {
              loadedThreads = [singleThread, ...loadedThreads];
            }
          } catch (err) {
            console.warn(`Could not fetch thread for ${lookForId}:`, err);
          }
        }
      }

      setThreads(loadedThreads);

      let chosen = null;
      if (lookForId) {
        chosen = loadedThreads.find((t) => t.track_id === lookForId) || loadedThreads[0] || null;
      } else {
        chosen = loadedThreads.find((t) => t.track_id === selectedThread?.track_id) || loadedThreads[0] || null;
      }
      setSelectedThread(chosen);

      // Asynchronously fetch positions for chosen thread if missing
      if (chosen && (!chosen.positions || chosen.positions.length === 0)) {
        api.getTrackThread(chosen.track_id).then((full) => {
          if (full && full.track_id === chosen.track_id) {
            setSelectedThread(full);
            setThreads((prev) => prev.map((item) => (item.track_id === full.track_id ? full : item)));
          }
        }).catch(() => {});
      }
    } catch (err) {
      console.error('Failed to load activity threads from backend:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [typeFilter, movementFilter, selectedTrackId]);

  const handleSelectThread = async (th) => {
    setSelectedThread(th);
    if (!th.positions || th.positions.length === 0) {
      try {
        const full = await api.getTrackThread(th.track_id);
        if (full && full.track_id === th.track_id) {
          setSelectedThread(full);
          setThreads((prev) => prev.map((item) => (item.track_id === full.track_id ? full : item)));
        }
      } catch (err) {
        console.warn('Could not load detailed thread positions:', err);
      }
    }
  };

  useEffect(() => {
    fetchThreads(selectedTrackId, true);
  }, [fetchThreads, selectedTrackId]);

  const handleManualRefresh = () => {
    setRefreshing(true);
    fetchThreads(selectedThread?.track_id || selectedTrackId, false);
  };

  const handleClearEnded = async () => {
    if (!window.confirm('Clear and permanently remove all ended stories and inactive tracks?')) return;
    setClearingEnded(true);
    try {
      await api.clearEndedThreads();
      setThreads((prev) => {
        const remaining = prev.filter((t) => t.status !== 'ENDED');
        if (selectedThread && selectedThread.status === 'ENDED') {
          setSelectedThread(remaining[0] || null);
        }
        return remaining;
      });
      await fetchThreads(null, false);
    } catch (err) {
      alert(`Failed to clear ended stories: ${err.message}`);
    } finally {
      setClearingEnded(false);
    }
  };

  const filteredThreads = useMemo(() => {
    let list = threads.filter((t) => t.status !== 'ENDED');
    if (movementFilter !== 'ALL') {
      list = list.filter((t) => {
        const st = t.movement_state || t.attributes?.movement?.movement_state;
        return st === movementFilter;
      });
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter(
        (t) =>
          t.track_id?.toLowerCase().includes(q) ||
          t.camera_id?.toLowerCase().includes(q) ||
          t.object_type?.toLowerCase().includes(q) ||
          t.movement_state?.toLowerCase().includes(q) ||
          t.direction?.toLowerCase().includes(q) ||
          t.person_name?.toLowerCase().includes(q) ||
          t.face_intel?.person_name?.toLowerCase().includes(q) ||
          t.face_intel?.person_id?.toLowerCase().includes(q) ||
          t.face_intel?.role?.toLowerCase().includes(q) ||
          t.vehicle_intelligence?.type?.toLowerCase().includes(q) ||
          t.vehicle_intelligence?.color?.toLowerCase().includes(q) ||
          t.vehicle_intelligence?.vehicle_id?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [threads, movementFilter, searchQuery]);

  const formatTimestamp = (ts) => {
    if (!ts) return '--:--:--';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return ts;
    }
  };

  const formatDate = (ts) => {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  return (
    <div>
      {/* HEADER BAR */}
      <div className="section-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2>Activity Threads & Story Reconstructions</h2>
          <span className="section-sub">
            Track movement lifecycles, zone observations, camera handoffs, breach alerts, and evidence
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="n-btn"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11.5px',
              background: 'var(--red-dim)',
              color: 'var(--red)',
              borderColor: 'rgba(239,82,81,0.35)',
            }}
            onClick={handleClearEnded}
            disabled={clearingEnded}
            title="Clear and permanently remove all ended stories and inactive tracks"
          >
            {clearingEnded ? 'Clearing...' : 'Clear Ended Stories'}
          </button>
          <button
            className="n-btn"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11.5px' }}
            onClick={handleManualRefresh}
            disabled={refreshing}
            title="Refresh threads from backend"
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', transform: refreshing ? 'rotate(180deg)' : 'none', transition: 'transform 0.4s ease' }}>
              <RefreshIcon size={12} />
            </span>
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* FILTER CONTROLS */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '10px',
          alignItems: 'center',
          background: 'var(--panel-hi)',
          padding: '10px 14px',
          borderRadius: '8px',
          border: '1px solid var(--hair)',
          marginTop: '10px',
        }}
      >
        {/* Type Filters */}
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-low)', marginRight: '4px', textTransform: 'uppercase' }}>
            Type:
          </span>
          {['ALL', 'HUMAN', 'VEHICLE', 'SUV', 'SEDAN', 'TRUCK', 'VAN', 'UAV', 'MOTION'].map((t) => (
            <button
              key={t}
              className="n-btn"
              style={{
                padding: '3px 8px',
                fontSize: '11px',
                background: typeFilter === t ? 'var(--panel-hover)' : 'transparent',
                color: typeFilter === t ? 'var(--text-hi)' : 'var(--text-mid)',
                borderColor: typeFilter === t ? 'var(--gold)' : 'var(--hair-soft)',
              }}
              onClick={() => setTypeFilter(t)}
            >
              {t}
            </button>
          ))}
        </div>

        <div style={{ width: '1px', height: '18px', background: 'var(--hair)' }} />

        {/* Movement Filters */}
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-low)', marginRight: '4px', textTransform: 'uppercase' }}>
            Movement:
          </span>
          {['ALL', 'RUNNING', 'WALKING', 'STATIONARY', 'CRUISING', 'FAST'].map((m) => (
            <button
              key={m}
              className="n-btn"
              style={{
                padding: '3px 8px',
                fontSize: '11px',
                background: movementFilter === m ? 'var(--panel-hover)' : 'transparent',
                color: movementFilter === m ? 'var(--text-hi)' : 'var(--text-mid)',
                borderColor: movementFilter === m ? 'var(--gold)' : 'var(--hair-soft)',
              }}
              onClick={() => setMovementFilter(m)}
            >
              {m}
            </button>
          ))}
        </div>

        <div style={{ width: '1px', height: '18px', background: 'var(--hair)' }} />

        {/* Search */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px', flex: '1 1 200px', minWidth: '160px' }}>
          <input
            type="text"
            placeholder="Search story ID, camera, notes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              background: '#0a0a0a',
              border: '1px solid var(--hair)',
              borderRadius: '6px',
              padding: '5px 10px',
              color: 'var(--text-hi)',
              fontSize: '11.5px',
              outline: 'none',
              width: '100%',
            }}
          />
        </div>
      </div>

      {/* MAIN TWO-COLUMN VIEW */}
      <div className="threads-layout">
        {/* LEFT RAIL: THREADS LIST */}
        <div className="tile threads-list-pane">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
            <span className="n-col-label" style={{ fontSize: '11px', color: 'var(--text-low)', textTransform: 'uppercase' }}>
              Stories ({filteredThreads.length})
            </span>
            {loading && <span style={{ fontSize: '10.5px', color: 'var(--gold)' }}>Loading...</span>}
          </div>

          {loading && filteredThreads.length === 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="skeleton-card" style={{ padding: '12px', height: '72px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <SkeletonBox width="80px" height="12px" />
                    <SkeletonBox width="50px" height="12px" borderRadius="6px" />
                  </div>
                  <SkeletonBox width="60%" height="10px" />
                </div>
              ))}
            </div>
          )}

          {filteredThreads.length === 0 && !loading && (
            <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--text-low)', fontSize: '12px' }}>
              No activity threads match the current criteria.
              <div style={{ marginTop: '8px' }}>
                <button
                  className="n-btn"
                  style={{ fontSize: '10.5px', padding: '3px 8px' }}
                  onClick={() => {
                    setTypeFilter('ALL');
                    setSearchQuery('');
                  }}
                >
                  Reset Filters
                </button>
              </div>
            </div>
          )}

          {filteredThreads.map((t) => {
            const isSelected = selectedThread?.track_id === t.track_id;
            const isCritical = t.timeline?.some((n) => n.severity === 'CRITICAL' || n.severity === 'HIGH' || n.node_type === 'EVENT_BREACH');

            return (
              <div
                key={t.track_id}
                className="thread-item-tile"
                style={{
                  padding: '10px 12px',
                  borderRadius: '8px',
                  background: isSelected ? 'var(--panel-hover)' : 'var(--panel-hi)',
                  border: `1px solid ${isSelected ? 'var(--gold)' : 'var(--hair)'}`,
                  cursor: 'pointer',
                  transition: 'all .15s ease',
                }}
                onClick={() => handleSelectThread(t)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <b style={{ fontSize: '12.5px', color: 'var(--text-hi)' }}>{t.track_id}</b>
                  <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                    {t.threat_level && t.threat_level !== 'LOW' && (
                      <span
                        className="nav-badge"
                        style={{
                          background: t.threat_level === 'CRITICAL' ? 'var(--red-dim)' : t.threat_level === 'HIGH' ? 'var(--orange-dim)' : 'var(--gold-dim)',
                          color: t.threat_level === 'CRITICAL' ? 'var(--red)' : t.threat_level === 'HIGH' ? 'var(--orange)' : 'var(--gold)',
                          fontSize: '8.5px',
                          padding: '1px 5px',
                        }}
                      >
                        {t.threat_level}
                      </span>
                    )}
                    <span
                      className={`nav-badge ${t.status === 'ACTIVE' ? '' : 'neutral'}`}
                      style={{
                        background: isCritical ? 'var(--red-dim)' : t.status === 'ACTIVE' ? 'var(--green-dim)' : 'var(--panel-hi)',
                        color: isCritical ? 'var(--red)' : t.status === 'ACTIVE' ? 'var(--green)' : 'var(--text-mid)',
                        fontSize: '9.5px',
                        padding: '1px 6px',
                      }}
                    >
                      {isCritical ? 'BREACH' : t.status}
                    </span>
                  </div>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-low)', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: t.vehicle_label ? 'var(--gold)' : 'inherit', fontWeight: t.vehicle_label ? 600 : 400 }}>
                    {t.vehicle_label || (t.vehicle_intelligence?.color && t.vehicle_intelligence?.type
                      ? `${t.vehicle_intelligence.color.toUpperCase()} ${t.vehicle_intelligence.type.toUpperCase()}`
                      : t.vehicle_intelligence?.color
                      ? `${t.vehicle_intelligence.color.toUpperCase()} VEHICLE`
                      : t.vehicle_intelligence?.type
                      ? t.vehicle_intelligence.type.toUpperCase()
                      : t.object_type)} · {t.camera_id}
                  </span>
                  <span style={{ fontSize: '10px' }}>
                    {formatTimestamp(t.last_seen_at)}
                  </span>
                </div>
                {t.activity_story && (
                  <div style={{ fontSize: '10.5px', color: 'var(--text-mid)', marginTop: '3px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {t.activity_story}
                  </div>
                )}
                {(t.person_name || t.face_intel?.person_name) && (
                  <div style={{ marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span
                      className="n-chip"
                      style={{
                        fontSize: '9.5px',
                        padding: '1px 6px',
                        background: 'rgba(213, 177, 138, 0.15)',
                        color: 'var(--gold)',
                        borderColor: 'rgba(213, 177, 138, 0.35)',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <FaceIcon size={10} />
                      <span>{t.person_name || t.face_intel?.person_name}</span>
                      {t.face_intel?.similarity ? (
                        <span style={{ opacity: 0.8 }}>({Math.round(t.face_intel.similarity * 100)}%)</span>
                      ) : null}
                    </span>
                  </div>
                )}
                <div style={{ fontSize: '10px', color: 'var(--text-low)', marginTop: '4px', display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}><PinIcon size={10} /> {t.positions_count || 1} pts</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}><ClapperIcon size={10} /> {t.timeline?.length || 1} nodes</span>
                  {t.movement_state && (
                    <span
                      className="n-chip"
                      style={{
                        fontSize: '8.5px',
                        padding: '0 5px',
                        background: t.movement_state === 'RUNNING' || t.movement_state === 'FAST'
                          ? 'rgba(239, 68, 68, 0.15)'
                          : t.movement_state === 'WALKING' || t.movement_state === 'CRUISING'
                          ? 'rgba(201, 154, 91, 0.15)'
                          : 'rgba(255, 255, 255, 0.05)',
                        color: t.movement_state === 'RUNNING' || t.movement_state === 'FAST'
                          ? '#ef4444'
                          : t.movement_state === 'WALKING' || t.movement_state === 'CRUISING'
                          ? '#C99A5B'
                          : 'var(--text-mid)',
                        fontWeight: 600,
                      }}
                    >
                      {t.movement_state}
                      {t.speed !== undefined && t.speed !== null ? ` · ${Math.round(t.speed)} ${t.speed_unit || 'px/s'}` : ''}
                      {t.direction && t.direction !== 'STATIONARY' ? ` · ${t.direction}` : ''}
                    </span>
                  )}
                  {t.movement_dynamic && <span className="n-chip" style={{ fontSize: '8.5px', padding: '0 4px' }}>{t.movement_dynamic.replace('_', ' ')}</span>}
                  {t.loitering_detected && <span className="n-chip attention" style={{ fontSize: '8.5px', padding: '0 4px' }}>LOITERING</span>}
                  {t.evidence?.length > 0 && <span style={{ color: 'var(--gold)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}><CameraIcon size={10} /> {t.evidence.length} clip{t.evidence.length > 1 ? 's' : ''}</span>}
                </div>
              </div>
            );
          })}
        </div>

        {/* RIGHT CANVAS: STORY RECONSTRUCTION HUD */}
        {selectedThread ? (
          <div className="tile" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* THREAD HEADER */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                borderBottom: '1px solid var(--hair-soft)',
                paddingBottom: '14px',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <b style={{ fontSize: '18px', color: 'var(--text-hi)' }}>
                    TRACK {selectedThread.track_id}
                  </b>
                  <span className="n-chip info" style={{ textTransform: 'uppercase' }}>
                    {selectedThread.object_type}
                  </span>
                  {selectedThread.vehicle_intelligence && (
                    <>
                      {selectedThread.vehicle_intelligence.color && (
                        <span
                          className="n-chip"
                          style={{
                            padding: '2px 8px',
                            background: 'rgba(201, 154, 91, 0.12)',
                            color: '#C99A5B',
                            borderColor: 'rgba(201, 154, 91, 0.3)',
                            fontWeight: 600,
                          }}
                        >
                          COLOR: {selectedThread.vehicle_intelligence.color.toUpperCase()}
                          {selectedThread.vehicle_intelligence.color_confidence ? ` (${Math.round(selectedThread.vehicle_intelligence.color_confidence * 100)}%)` : ''}
                        </span>
                      )}
                      {selectedThread.vehicle_intelligence.type && (
                        <span
                          className="n-chip"
                          style={{
                            padding: '2px 8px',
                            background: 'rgba(160, 125, 90, 0.12)',
                            color: '#D5B18A',
                            borderColor: 'rgba(160, 125, 90, 0.3)',
                            fontWeight: 600,
                          }}
                        >
                          TYPE: {selectedThread.vehicle_intelligence.type.toUpperCase()}
                          {selectedThread.vehicle_intelligence.type_confidence ? ` (${Math.round(selectedThread.vehicle_intelligence.type_confidence * 100)}%)` : ''}
                        </span>
                      )}
                      {selectedThread.vehicle_intelligence.vehicle_id && (
                        <span className="n-chip" style={{ fontFamily: 'var(--mono)', fontSize: '11px' }}>
                          VID: {selectedThread.vehicle_intelligence.vehicle_id}
                        </span>
                      )}
                    </>
                  )}
                  {(selectedThread.face_intel?.person_name || selectedThread.person_name) && (
                    <span
                      className="n-chip"
                      style={{
                        padding: '2px 8px',
                        background: 'rgba(213, 177, 138, 0.15)',
                        color: 'var(--gold)',
                        borderColor: 'rgba(213, 177, 138, 0.4)',
                        fontWeight: 600,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <FaceIcon size={12} />
                      <span>
                        RECOGNIZED: {selectedThread.face_intel?.person_name || selectedThread.person_name}
                        {selectedThread.face_intel?.similarity ? ` (${Math.round(selectedThread.face_intel.similarity * 100)}%)` : ''}
                      </span>
                    </span>
                  )}
                  {(selectedThread.face_intel?.has_face || selectedThread.associated_face_id) && (
                    <span
                      className="n-chip"
                      style={{
                        padding: '2px 8px',
                        background: 'rgba(236, 72, 153, 0.15)',
                        color: '#ec4899',
                        borderColor: 'rgba(236, 72, 153, 0.4)',
                        fontWeight: 600,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <FaceIcon size={12} />
                      <span>
                        FACE LINKED: {selectedThread.associated_face_id || selectedThread.face_intel?.face_track_id}
                        {selectedThread.face_intel?.face_match_score ? ` (${Math.round(selectedThread.face_intel.face_match_score * 100)}% match)` : ''}
                      </span>
                    </span>
                  )}
                  {selectedThread.associated_human_id && (
                    <span
                      className="n-chip"
                      style={{
                        padding: '2px 8px',
                        background: 'rgba(59, 130, 246, 0.15)',
                        color: '#60a5fa',
                        borderColor: 'rgba(59, 130, 246, 0.4)',
                        fontWeight: 600,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <PersonIcon size={12} />
                      <span>LINKED TO HUMAN: {selectedThread.associated_human_id}</span>
                    </span>
                  )}
                  <span
                    className="n-chip"
                    style={{
                      background: selectedThread.status === 'ACTIVE' ? 'var(--green-dim)' : 'var(--panel-hi)',
                      color: selectedThread.status === 'ACTIVE' ? 'var(--green)' : 'var(--text-mid)',
                    }}
                  >
                    {selectedThread.status}
                  </span>
                  {selectedThread.threat_level && selectedThread.threat_level !== 'LOW' && (
                    <span
                      className="n-chip"
                      style={{
                        background: selectedThread.threat_level === 'CRITICAL' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(201, 154, 91, 0.18)',
                        color: selectedThread.threat_level === 'CRITICAL' ? '#ef4444' : 'var(--gold)',
                        borderColor: selectedThread.threat_level === 'CRITICAL' ? 'rgba(239, 68, 68, 0.4)' : 'rgba(201, 154, 91, 0.35)',
                        fontWeight: 700,
                        letterSpacing: '0.04em',
                      }}
                    >
                      THREAT: {selectedThread.threat_level}
                    </span>
                  )}
                  {selectedThread.movement_dynamic && (
                    <span
                      className="n-chip"
                      style={{
                        background: 'rgba(181, 115, 46, 0.15)',
                        color: '#D5B18A',
                        borderColor: 'rgba(181, 115, 46, 0.3)',
                        fontWeight: 600,
                      }}
                    >
                      {selectedThread.movement_dynamic.replace('_', ' ')}
                      {selectedThread.avg_speed_px_per_sec ? ` (${Math.round(selectedThread.avg_speed_px_per_sec)} px/s)` : ''}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '11.5px', color: 'var(--text-low)', marginTop: '6px' }}>
                  Primary Camera: <b>{selectedThread.camera_id}</b> · Recorded {selectedThread.positions_count || 1} coordinates · Created {formatDate(selectedThread.created_at)} {formatTimestamp(selectedThread.created_at)} · Last Seen {formatTimestamp(selectedThread.last_seen_at)}
                  {selectedThread.duration_seconds > 0 && ` · Duration: ${Math.round(selectedThread.duration_seconds)}s`}
                </div>

                {(selectedThread.movement_state || selectedThread.speed !== undefined) && (
                  <div
                    className="thread-item-tile"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      flexWrap: 'wrap',
                      marginTop: '8px',
                      padding: '6px 12px',
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--hair-soft)',
                      borderRadius: '6px',
                      fontSize: '11px',
                    }}
                  >
                    <span style={{ color: 'var(--gold)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Movement Intel:
                    </span>
                    <span
                      className="nav-badge"
                      style={{
                        background: selectedThread.movement_state === 'RUNNING' || selectedThread.movement_state === 'FAST'
                          ? 'var(--red-dim)'
                          : 'var(--gold-dim)',
                        color: selectedThread.movement_state === 'RUNNING' || selectedThread.movement_state === 'FAST'
                          ? 'var(--red)'
                          : 'var(--gold)',
                        fontWeight: 700,
                        fontSize: '9.5px',
                        padding: '1px 6px',
                      }}
                    >
                      {selectedThread.movement_state || 'STATIONARY'}
                    </span>
                    <span>
                      Speed: <b>{selectedThread.speed !== undefined && selectedThread.speed !== null ? Number(selectedThread.speed).toFixed(1) : '0.0'} {selectedThread.speed_unit || 'px/s'}</b>
                      {selectedThread.speed_kmh !== undefined && selectedThread.speed_kmh !== null && (
                        <span style={{ color: 'var(--text-mid)', marginLeft: '4px' }}>
                          ({Number(selectedThread.speed_kmh).toFixed(1)} km/h)
                        </span>
                      )}
                    </span>
                    <span>·</span>
                    <span>
                      Heading: <b>{selectedThread.direction || 'STATIONARY'}</b>
                      {selectedThread.heading_deg !== undefined && selectedThread.heading_deg !== null && ` (${Math.round(selectedThread.heading_deg)}°)`}
                    </span>
                    <span>·</span>
                    <span>
                      Distance Travelled: <b>{Math.round(selectedThread.distance_travelled || 0)} px</b>
                    </span>
                    {selectedThread.movements_count > 0 && (
                      <>
                        <span>·</span>
                        <span style={{ color: 'var(--text-low)' }}>
                          {selectedThread.movements_count} time-series snapshot{selectedThread.movements_count > 1 ? 's' : ''}
                        </span>
                      </>
                    )}
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  className="n-btn ai-investigate"
                  style={{ padding: '5px 12px' }}
                  onClick={() => {
                    if (!onInvestigate) return;
                    const linkedEvt = selectedThread.timeline?.find((n) => n.event_id)?.event_id || selectedThread.event_id;
                    onInvestigate({
                      track_id: selectedThread.track_id,
                      event_id: linkedEvt || undefined,
                      headline: `Investigation into track ${selectedThread.track_id}`,
                      summary: `AI deep investigation into ${selectedThread.object_type} ${selectedThread.track_id} on camera ${selectedThread.camera_id}. Current status: ${selectedThread.status}.`,
                      camera_id: selectedThread.camera_id,
                    });
                  }}
                  title="Direct AI deep investigation into this track and all its evidence"
                >
                  <AiSparklesIcon size={12} />
                  <span>Investigate AI</span>
                </button>
                <button
                  className="n-btn"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                  onClick={() => onSelectTab && onSelectTab('feeds')}
                  title="Switch to live feed camera stream"
                >
                  <VideoIcon size={12} /> Live Stream ({selectedThread.camera_id})
                </button>
              </div>
            </div>

            {/* BIOMETRIC FACIAL INTELLIGENCE TILE */}
            {selectedThread.face_intel && (
              <div
                className="thread-item-tile"
                style={{
                  background: 'rgba(213, 177, 138, 0.05)',
                  border: '1px solid rgba(213, 177, 138, 0.3)',
                  borderRadius: '10px',
                  padding: '14px 18px',
                  marginBottom: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '14px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  {selectedThread.face_intel.snapshot_path && (
                    <img
                      src={resolveMediaUrl(selectedThread.face_intel.snapshot_path)}
                      alt={selectedThread.face_intel.person_name || 'Face Snapshot'}
                      style={{
                        width: '52px',
                        height: '52px',
                        borderRadius: '6px',
                        objectFit: 'cover',
                        border: '1px solid rgba(213, 177, 138, 0.4)',
                        background: '#000',
                      }}
                      onError={(e) => { e.currentTarget.style.display = 'none'; }}
                    />
                  )}
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '10px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--gold)' }}>
                        Biometric Identity
                      </span>
                      <span
                        className="n-chip"
                        style={{
                          fontSize: '9px',
                          padding: '1px 6px',
                          background: selectedThread.face_intel.status === 'RECOGNIZED' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(236, 72, 153, 0.15)',
                          color: selectedThread.face_intel.status === 'RECOGNIZED' ? 'var(--green)' : '#ec4899',
                          borderColor: selectedThread.face_intel.status === 'RECOGNIZED' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(236, 72, 153, 0.3)',
                        }}
                      >
                        {selectedThread.face_intel.status || 'UNCLASSIFIED'}
                      </span>
                    </div>
                    <div style={{ fontSize: '14px', fontWeight: '700', color: 'var(--text-hi)', marginTop: '2px' }}>
                      {selectedThread.face_intel.person_name || 'Unclassified Subject'}
                      {selectedThread.face_intel.role && (
                        <span style={{ fontSize: '11.5px', fontWeight: '400', color: 'var(--text-mid)', marginLeft: '6px' }}>
                          · {selectedThread.face_intel.role}
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)', marginTop: '2px' }}>
                      {selectedThread.face_intel.person_id ? `ID: ${selectedThread.face_intel.person_id} · ` : ''}
                      {selectedThread.face_intel.similarity ? `Match: ${Math.round(selectedThread.face_intel.similarity * 100)}% · ` : ''}
                      Detections: {selectedThread.face_intel.detection_count || 1}x
                    </div>
                  </div>
                </div>
                {onSelectTab && (
                  <button
                    className="n-btn"
                    style={{
                      fontSize: '11px',
                      padding: '5px 12px',
                      background: 'rgba(213, 177, 138, 0.15)',
                      color: 'var(--gold)',
                      borderColor: 'rgba(213, 177, 138, 0.3)',
                      flexShrink: 0,
                    }}
                    onClick={() => onSelectTab('face-recognition')}
                  >
                    View in Directory →
                  </button>
                )}
              </div>
            )}

            {/* STORY RECONSTRUCTION HUD */}
            <div
              className="thread-item-tile"
              style={{
                background: '#090909',
                border: '1px solid #222',
                borderRadius: '10px',
                padding: '18px 22px',
                fontSize: '12.5px',
                lineHeight: '1.7',
                color: 'var(--text-mid)',
              }}
            >
              <div style={{ color: 'var(--gold)', fontWeight: '700', fontSize: '14px', marginBottom: '8px' }}>
                TRACK {selectedThread.track_id} · STORY RECONSTRUCTION
              </div>
              
              {selectedThread.activity_story && (
                <div
                  className="thread-item-tile"
                  style={{
                    background: 'rgba(201, 154, 91, 0.08)',
                    border: '1px solid rgba(201, 154, 91, 0.25)',
                    borderRadius: '6px',
                    padding: '10px 14px',
                    marginBottom: '12px',
                    color: '#F3ECE2',
                    fontSize: '12px',
                    lineHeight: '1.5',
                  }}
                >
                  <div style={{ fontSize: '10px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--gold)', marginBottom: '3px' }}>
                    AI Activity Synthesis
                  </div>
                  {selectedThread.activity_story}
                </div>
              )}

              <div style={{ color: '#444' }}>│</div>

              {selectedThread.timeline?.map((node, i) => {
                const isLast = i === selectedThread.timeline.length - 1 && (!selectedThread.evidence || selectedThread.evidence.length === 0) && !selectedThread.positions;
                const isCritical = node.severity === 'CRITICAL' || node.severity === 'HIGH' || node.node_type === 'EVENT_BREACH';
                const isHandoff = node.node_type === 'CAMERA_HANDOFF';
                const isLoitering = node.node_type === 'ZONE_LOITERING';
                const isMovementChange = node.node_type === 'MOVEMENT_CHANGE';
                const isFaceAssoc = node.node_type === 'FACE_ASSOCIATION';
                const isFaceRec = node.node_type === 'FACE_RECOGNITION';
                const isHumanAssoc = node.node_type === 'HUMAN_ASSOCIATION';
                const isConcluded = node.node_type === 'TRACK_CONCLUDED';
                const nodeColor = isCritical ? 'var(--red)' : isFaceRec ? '#ec4899' : isLoitering ? 'var(--gold)' : isHandoff ? 'var(--gold)' : isMovementChange ? '#60a5fa' : (isFaceAssoc || isHumanAssoc) ? '#ec4899' : isConcluded ? 'var(--green)' : 'var(--text-hi)';

                return (
                  <div key={i} style={{ position: 'relative' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ color: '#444' }}>{isLast ? '└─' : '├─'}</span>
                      <span
                        style={{
                          color: nodeColor,
                          fontWeight: '700',
                        }}
                      >
                        {node.camera_id || node.zone_id || 'SENSOR'}
                      </span>
                      <span style={{ color: 'var(--text-low)', fontSize: '11px' }}>
                        {formatTimestamp(node.timestamp)}
                      </span>
                      {isCritical && (
                        <span className="n-chip critical" style={{ fontSize: '9px', padding: '1px 5px' }}>
                           CRITICAL BREACH
                        </span>
                      )}
                      {isLoitering && (
                        <span className="n-chip" style={{ fontSize: '9px', padding: '1px 5px', background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(201, 154, 91, 0.4)' }}>
                          LOITERING ALERT
                        </span>
                      )}
                      {isFaceRec && (
                        <span className="n-chip" style={{ fontSize: '9px', padding: '1px 5px', background: 'rgba(236, 72, 153, 0.15)', color: '#ec4899', borderColor: 'rgba(236, 72, 153, 0.35)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                          <FaceIcon size={10} /> {node.person_name ? 'BIOMETRIC MATCH' : 'FACE DETECTED'}
                        </span>
                      )}
                      {isFaceAssoc && (
                        <span className="n-chip" style={{ fontSize: '9px', padding: '1px 5px', background: 'rgba(236, 72, 153, 0.15)', color: '#ec4899', borderColor: 'rgba(236, 72, 153, 0.35)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                          <FaceIcon size={10} /> FACE LINKED
                        </span>
                      )}
                      {isHumanAssoc && (
                        <span className="n-chip" style={{ fontSize: '9px', padding: '1px 5px', background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', borderColor: 'rgba(59, 130, 246, 0.35)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                          <PersonIcon size={10} /> HUMAN TARGET
                        </span>
                      )}
                      {isMovementChange && (
                        <span className="n-chip" style={{ fontSize: '9px', padding: '1px 5px', background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', borderColor: 'rgba(59, 130, 246, 0.35)' }}>
                          {node.change_type || 'MOVEMENT CHANGE'}
                        </span>
                      )}
                      {isHandoff && (
                        <span className="n-chip attention" style={{ fontSize: '9px', padding: '1px 5px' }}>
                          CAMERA HANDOFF
                        </span>
                      )}
                      {isConcluded && (
                        <span className="n-chip" style={{ fontSize: '9px', padding: '1px 5px', background: 'var(--green-dim)', color: 'var(--green)' }}>
                          TRACK CONCLUDED
                        </span>
                      )}
                    </div>

                    <div style={{ paddingLeft: '24px', color: 'var(--text-mid)', marginBottom: '8px' }}>
                      <div style={{ color: nodeColor, fontWeight: '600' }}>
                        {node.title}
                      </div>
                      <div style={{ fontSize: '11.5px', color: 'var(--text-low)' }}>{node.detail}</div>

                      {isFaceRec && node.thumbnail && (
                        <div style={{ marginTop: '6px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <img
                            src={resolveMediaUrl(node.thumbnail)}
                            alt={node.person_name || 'Face Crop'}
                            style={{ width: '42px', height: '42px', borderRadius: '4px', objectFit: 'cover', border: '1px solid rgba(236, 72, 153, 0.4)', background: '#000' }}
                            onError={(e) => { e.currentTarget.style.display = 'none'; }}
                          />
                          <div>
                            {node.person_name && (
                              <div style={{ fontSize: '11.5px', fontWeight: 600, color: 'var(--text-hi)' }}>
                                {node.person_name}
                                {node.role && <span style={{ fontSize: '10px', color: 'var(--text-mid)', marginLeft: '4px' }}>· {node.role}</span>}
                              </div>
                            )}
                            {node.similarity ? (
                              <span className="n-chip" style={{ fontSize: '8.5px', padding: '0 4px', background: 'rgba(213, 177, 138, 0.15)', color: 'var(--gold)' }}>
                                {Math.round(node.similarity * 100)}% ArcFace
                              </span>
                            ) : null}
                          </div>
                        </div>
                      )}

                      {node.event_id && (
                        <div style={{ marginTop: '4px', display: 'flex', gap: '6px' }}>
                          <button
                            className="n-btn ai-investigate"
                            style={{ padding: '2px 8px', fontSize: '10px' }}
                            onClick={() => onInvestigate && onInvestigate({ event_id: node.event_id })}
                          >
                            <AiSparklesIcon size={10} />
                            <span>Investigate Event {node.event_id}</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* EVIDENCE VAULT BRANCH */}
              {selectedThread.evidence && selectedThread.evidence.length > 0 && (
                <div>
                  <div style={{ color: '#444' }}>│</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--gold)', fontWeight: '700' }}>
                    <span style={{ color: '#444' }}>├─</span>
                    <span>EVIDENCE VAULT ({selectedThread.evidence.length} Capture{selectedThread.evidence.length > 1 ? 's' : ''})</span>
                  </div>

                  <div style={{ paddingLeft: '24px', display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
                    {selectedThread.evidence.map((ev, idx) => {
                      const isEnd = idx === selectedThread.evidence.length - 1;
                      const isImage = ev.type === 'SNAPSHOT' || ev.storage_reference?.endsWith('.jpg') || ev.storage_reference?.includes('/file');

                      return (
                        <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11.5px' }}>
                          <span style={{ color: '#444' }}>{isEnd ? '└─' : '├─'}</span>
                          <span style={{ color: 'var(--text-hi)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                            {ev.type === 'SNAPSHOT' ? (
                              <><CameraIcon size={11} /> Snapshot</>
                            ) : ev.type === 'VIDEO_CLIP' ? (
                              <><VideoIcon size={11} /> Stream Clip</>
                            ) : (
                              <><MicIcon size={11} /> Audio Clip</>
                            )}{' '}
                            <span style={{ color: 'var(--gold)', marginLeft: '3px' }}>{ev.evidence_id}</span>
                          </span>
                          <span style={{ fontSize: '10px', color: 'var(--text-low)' }}>
                            {formatTimestamp(ev.timestamp || ev.created_at)}
                          </span>
                          {isImage && (
                            <button
                              className="n-btn"
                              style={{ padding: '1px 6px', fontSize: '9.5px', background: 'var(--panel-hover)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}
                              onClick={() => {
                                const refUrl = ev.evidence_id
                                  ? api.getEvidenceFileUrl(ev.evidence_id)
                                  : (ev.storage_reference?.startsWith('http')
                                      ? ev.storage_reference
                                      : `${V1}${ev.storage_reference?.startsWith('/') ? '' : '/'}${ev.storage_reference || ''}`);
                                setPreviewEvidence({ ...ev, fullUrl: refUrl });
                              }}
                            >
                              <SearchIcon size={10} /> View Capture
                            </button>
                          )}
                          <button
                            className="n-btn"
                            style={{ padding: '1px 6px', fontSize: '9.5px', background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.3)' }}
                            onClick={() => onSelectTab && onSelectTab('evidence')}
                          >
                            Vault
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* COORDINATES HISTORY BRANCH */}
              <div>
                <div style={{ color: '#444' }}>│</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-mid)', fontWeight: '600' }}>
                  <span style={{ color: '#444' }}>└─</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                    <PinIcon size={11} /> Track Path History ({selectedThread.positions_count || 1} coordinates recorded)
                  </span>
                  {selectedThread.positions && selectedThread.positions.length > 0 && (
                    <button
                      className="n-btn"
                      style={{ padding: '1px 6px', fontSize: '9.5px', background: 'transparent', borderColor: 'var(--hair)' }}
                      onClick={() => setShowCoordinates((prev) => !prev)}
                    >
                      {showCoordinates ? 'Hide Trail' : 'Show Trail'}
                    </button>
                  )}
                </div>

                {showCoordinates && selectedThread.positions && (
                  <div
                    style={{
                      paddingLeft: '24px',
                      marginTop: '6px',
                      maxHeight: '160px',
                      overflowY: 'auto',
                      fontSize: '11px',
                      color: 'var(--text-low)',
                    }}
                  >
                    {selectedThread.positions.map((pos, pidx) => (
                      <div key={pidx} style={{ display: 'flex', gap: '8px', padding: '1px 0' }}>
                        <span style={{ color: 'var(--gold)' }}>{formatTimestamp(pos.timestamp)}:</span>
                        <span>
                          bbox: [
                          {Array.isArray(pos.bounding_box)
                            ? pos.bounding_box.map((v) => (typeof v === 'number' ? v.toFixed(3) : v)).join(', ')
                            : typeof pos.bounding_box === 'string'
                            ? pos.bounding_box
                            : 'N/A'}
                          ]
                        </span>
                        <span>conf: {Math.round((pos.confidence || 0.9) * 100)}%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="tile" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-low)' }}>
            Select an Activity Story from the list on the left to inspect target movement reconstruction.
          </div>
        )}
      </div>

      {/* EVIDENCE PREVIEW MODAL */}
      {previewEvidence && (
        <div
          className="modal-overlay"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.85)',
            display: 'grid',
            placeItems: 'center',
            zIndex: 9999,
          }}
          onClick={() => setPreviewEvidence(null)}
        >
          <div
            className="tile"
            style={{
              maxWidth: '650px',
              width: '90%',
              padding: '16px',
              background: '#111',
              border: '1px solid var(--hair)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div>
                <b style={{ color: 'var(--text-hi)' }}>{previewEvidence.evidence_id}</b>
                <span style={{ color: 'var(--text-low)', fontSize: '11px', marginLeft: '8px' }}>
                  {formatTimestamp(previewEvidence.timestamp || previewEvidence.created_at)}
                </span>
              </div>
              <button className="n-btn" onClick={() => setPreviewEvidence(null)} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                <CloseIcon size={12} /> Close
              </button>
            </div>
            <div style={{ background: '#000', borderRadius: '6px', overflow: 'hidden', textAlign: 'center', minHeight: '260px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <SkeletonImage
                src={previewEvidence.fullUrl}
                alt={previewEvidence.evidence_id}
                placeholderText="RETRIEVING SNAPSHOT PREVIEW..."
                fallbackText="SNAPSHOT ARCHIVE VERIFIED"
                containerStyle={{ width: '100%', minHeight: '260px', maxHeight: '420px' }}
                style={{ width: '100%', maxHeight: '420px' }}
                objectFit="contain"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
