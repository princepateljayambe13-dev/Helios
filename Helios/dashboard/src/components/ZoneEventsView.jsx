import { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../services/api';
import { TableRowSkeleton } from './SkeletonLoader';
import { BoltIcon, RefreshIcon, CheckIcon, AiSparklesIcon } from './Icons';

export function ZoneEventsView({
  events = [],
  onInvestigate,
  onSelectTab,
  onRefresh,
  loading = false,
  eventsCategory = 'zone',
  onSelectCategory,
  isZoneEvent,
}) {
  const [zones, setZones] = useState([]);
  const [dwellTracks, setDwellTracks] = useState([]);
  const [history, setHistory] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [cameraFilter, setCameraFilter] = useState('ALL');
  const [editingThresholds, setEditingThresholds] = useState({});
  const [savingZone, setSavingZone] = useState({});
  const [saveSuccessZone, setSaveSuccessZone] = useState({});

  // Fetch zone definitions, active dwell tracks, and loitering history
  const fetchZoneData = useCallback(async () => {
    try {
      const [zonesRes, dwellRes, historyRes] = await Promise.all([
        api.getZones().catch(() => ({ zones: [] })),
        api.getZoneDwell().catch(() => ({ dwell_tracks: [] })),
        api.getLoiteringHistory().catch(() => ({ history: [] })),
      ]);

      const zList = zonesRes.zones || (Array.isArray(zonesRes) ? zonesRes : []);
      setZones(zList);
      setDwellTracks(dwellRes.dwell_tracks || (Array.isArray(dwellRes) ? dwellRes : []));
      setHistory(historyRes.history || (Array.isArray(historyRes) ? historyRes : []));

      // Pre-fill editable thresholds for zones
      setEditingThresholds((prev) => {
        const next = { ...prev };
        zList.forEach((z) => {
          if (!next[z.zone_id]) {
            next[z.zone_id] = {
              dwell: z.dwell_threshold_seconds ?? 20.0,
              loiter: z.loitering_threshold_seconds ?? 50.0,
            };
          }
        });
        return next;
      });
    } catch (err) {
      console.error('Failed to fetch zone dwell data:', err);
    } finally {
      setLoadingData(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchZoneData();
    const interval = setInterval(() => {
      // Background poll active dwell tracks and history
      api.getZoneDwell()
        .then((res) => {
          setDwellTracks(res.dwell_tracks || (Array.isArray(res) ? res : []));
        })
        .catch(() => {});
    }, 2500);

    return () => clearInterval(interval);
  }, [fetchZoneData]);

  const handleManualRefresh = () => {
    setRefreshing(true);
    fetchZoneData();
    if (onRefresh) onRefresh();
  };

  const handleSaveThresholds = async (zoneId) => {
    const vals = editingThresholds[zoneId];
    if (!vals) return;
    setSavingZone((prev) => ({ ...prev, [zoneId]: true }));
    try {
      await api.updateZoneThresholds(zoneId, Number(vals.dwell), Number(vals.loiter));
      setSaveSuccessZone((prev) => ({ ...prev, [zoneId]: true }));
      setTimeout(() => {
        setSaveSuccessZone((prev) => ({ ...prev, [zoneId]: false }));
      }, 2500);
      // Refresh zones to reflect saved values
      const zonesRes = await api.getZones().catch(() => ({ zones: [] }));
      const zList = zonesRes.zones || (Array.isArray(zonesRes) ? zonesRes : []);
      setZones(zList);
    } catch (err) {
      alert(`Failed to save thresholds: ${err.message}`);
    } finally {
      setSavingZone((prev) => ({ ...prev, [zoneId]: false }));
    }
  };

  // Metrics summary
  const totalInZone = dwellTracks.length;
  const dwellingCount = dwellTracks.filter((t) => t.loitering_status === 'DWELLING').length;
  const loiteringCount = dwellTracks.filter((t) => t.loitering_status === 'LOITERING').length;
  const normalCount = dwellTracks.filter((t) => t.loitering_status === 'NORMAL').length;

  const checkIsZone = (e) => {
    if (typeof isZoneEvent === 'function') return isZoneEvent(e);
    return Boolean(
      e.zone_id ||
      e.attributes?.zone_id ||
      (e.event_type && (e.event_type.includes('ZONE') || e.event_type === 'INTRUSION' || e.event_type === 'LOITERING')) ||
      (e.description && (e.description.toLowerCase().includes('zone') || e.description.toLowerCase().includes('loitering')))
    );
  };

  const trackedCount = events.filter((e) => Boolean(e.track_id)).length;
  const zoneEventsCount = events.filter(checkIsZone).length;

  // Filtered loitering history + zone events
  const combinedHistory = useMemo(() => {
    const list = [];
    // From loitering_sessions table
    history.forEach((h) => {
      list.push({
        id: h.session_id,
        source: 'session',
        zone_id: h.zone_id,
        camera_id: h.camera_id,
        track_id: h.track_id,
        status: h.status,
        duration_seconds: h.duration_seconds,
        stationary_duration: h.duration_seconds,
        movement_state: h.status === 'LOITERING' ? 'STATIONARY' : 'DWELLING',
        timestamp: h.start_time,
        end_time: h.end_time,
        severity: h.status === 'LOITERING' ? 'HIGH' : 'MEDIUM',
        description: `${h.status} detected in ${h.zone_id} (${Math.round(h.duration_seconds || 0)}s duration)`,
      });
    });

    // From real-time events that are zone/loitering related
    events.filter(checkIsZone).forEach((e) => {
      if (!list.some((item) => item.id === e.event_id)) {
        list.push({
          id: e.event_id,
          source: 'event',
          zone_id: e.zone_id || e.attributes?.zone_id || 'ZONE',
          camera_id: e.camera_id,
          track_id: e.track_id,
          status: e.event_type === 'LOITERING' ? 'LOITERING' : e.event_type,
          duration_seconds: e.attributes?.duration_seconds || 0,
          stationary_duration: e.attributes?.stationary_duration || 0,
          movement_state: e.attributes?.movement_state || 'OBSERVED',
          timestamp: e.timestamp || e.created_at,
          severity: e.severity || 'MEDIUM',
          description: e.description || `${e.event_type} in zone`,
          raw_event: e,
        });
      }
    });

    return list.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }, [history, events]);

  const filteredHistory = useMemo(() => {
    return combinedHistory.filter((item) => {
      if (statusFilter !== 'ALL') {
        if (statusFilter === 'LOITERING' && item.status !== 'LOITERING') return false;
        if (statusFilter === 'DWELLING' && item.status !== 'DWELLING') return false;
      }
      if (cameraFilter !== 'ALL' && item.camera_id !== cameraFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        const mId = item.id?.toLowerCase().includes(q);
        const mCam = item.camera_id?.toLowerCase().includes(q);
        const mTrack = item.track_id?.toLowerCase().includes(q);
        const mZone = item.zone_id?.toLowerCase().includes(q);
        const mDesc = item.description?.toLowerCase().includes(q);
        if (!mId && !mCam && !mTrack && !mZone && !mDesc) return false;
      }
      return true;
    });
  }, [combinedHistory, statusFilter, cameraFilter, searchQuery]);

  // Extract unique cameras for filter dropdown
  const uniqueCameras = useMemo(() => {
    const cams = new Set();
    zones.forEach((z) => z.camera_id && cams.add(z.camera_id));
    combinedHistory.forEach((h) => h.camera_id && cams.add(h.camera_id));
    return Array.from(cams);
  }, [zones, combinedHistory]);

  const formatDuration = (seconds) => {
    if (!seconds || seconds <= 0) return '0s';
    const s = Math.round(seconds);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}m ${rem}s`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Category Navigation Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        {[
          { id: 'all', label: 'All events', count: events.length },
          { id: 'tracked', label: 'Tracked events', count: trackedCount },
          { id: 'zone', label: 'Zone events', count: zoneEventsCount },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            className="n-btn"
            style={{
              padding: '6px 14px',
              borderRadius: '8px',
              fontSize: '12.5px',
              background: eventsCategory === tab.id ? '#18181b' : 'var(--panel-hi)',
              color: eventsCategory === tab.id ? '#ffffff' : 'var(--text-mid)',
              borderColor: eventsCategory === tab.id ? 'rgba(255, 255, 255, 0.25)' : 'var(--hair)',
              fontWeight: eventsCategory === tab.id ? '500' : '400',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            onClick={() => onSelectCategory && onSelectCategory(tab.id)}
          >
            <span>{tab.label}</span>
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: '11px',
                color: eventsCategory === tab.id ? 'var(--text-hi)' : 'var(--text-low)',
                background: eventsCategory === tab.id ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.04)',
                padding: '1px 6px',
                borderRadius: '10px',
              }}
            >
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Section Head */}
      <div className="section-head" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2>Zone Intelligence & Loitering Operations</h2>
            <span
              style={{
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '10.5px',
                fontFamily: 'var(--mono)',
                background: 'var(--gold-dim)',
                color: 'var(--gold)',
                border: '1px solid rgba(201, 154, 91, 0.25)',
                fontWeight: '600',
                letterSpacing: '0.05em',
              }}
            >
              SPATIAL ENGINE
            </span>
          </div>
          <span className="section-sub">
            Real-time dwell tracking, loitering threat detection (Normal → Dwelling → Loitering), and perimeter occupancy matrix.
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            className="n-btn"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 12px' }}
            onClick={handleManualRefresh}
            disabled={refreshing}
          >
            <RefreshIcon size={13} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
            {refreshing ? 'Syncing...' : 'Refresh Matrix'}
          </button>

          <button
            className="n-btn primary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 14px' }}
            onClick={() => onSelectTab && onSelectTab('fencing')}
          >
            <BoltIcon size={13} />
            Configure Zones
          </button>
        </div>
      </div>

      {/* Executive Stat Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: '14px',
        }}
      >
        <div className="tile" style={{ padding: '16px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Active Occupants in Zones
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '26px', fontWeight: '700', color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
              {totalInZone}
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-mid)' }}>
              ({normalCount} Normal · {dwellingCount} Dwelling)
            </span>
          </div>
        </div>

        <div
          className="tile"
          style={{
            padding: '16px',
            borderColor: loiteringCount > 0 ? 'rgba(239, 82, 81, 0.4)' : 'var(--hair)',
            background: loiteringCount > 0 ? 'rgba(239, 82, 81, 0.05)' : 'var(--panel)',
          }}
        >
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Loitering Threats
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span
              style={{
                fontSize: '26px',
                fontWeight: '700',
                color: loiteringCount > 0 ? 'var(--red)' : 'var(--text-hi)',
                fontFamily: 'var(--mono)',
              }}
            >
              {loiteringCount}
            </span>
            {loiteringCount > 0 ? (
              <span
                style={{
                  fontSize: '10.5px',
                  fontWeight: '700',
                  color: 'var(--red)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: 'var(--red-dim)',
                  border: '1px solid rgba(239, 82, 81, 0.3)',
                  animation: 'pulse 1.5s infinite',
                }}
              >
                CRITICAL THREAT
              </span>
            ) : (
              <span style={{ fontSize: '11.5px', color: 'var(--green)' }}>Nominal Baseline</span>
            )}
          </div>
        </div>

        <div className="tile" style={{ padding: '16px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Active Perimeter Zones
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '26px', fontWeight: '700', color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
              {zones.length}
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-mid)' }}>
              across {uniqueCameras.length} cameras
            </span>
          </div>
        </div>

        <div className="tile" style={{ padding: '16px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Configured Limits
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '18px', fontWeight: '600', color: 'var(--gold)', fontFamily: 'var(--mono)' }}>
              20s <span style={{ fontSize: '11px', color: 'var(--text-mid)' }}>Dwell</span> · 50s{' '}
              <span style={{ fontSize: '11px', color: 'var(--text-mid)' }}>Loiter</span>
            </span>
          </div>
        </div>
      </div>

      {/* Live Zone Dwell & Loitering Matrix */}
      <div className="tile" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: '600', color: 'var(--text-hi)', margin: 0 }}>
              Live In-Zone Occupancy & Loitering Tracking
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-low)', marginTop: '4px' }}>
              Tracks inside defined boundaries. Movement-state classification ensures walking entities do not trigger loitering alarms.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: 'var(--text-mid)' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--green)' }} /> Normal (&lt;20s)
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: 'var(--text-mid)' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--gold)' }} /> Dwelling (≥20s)
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: 'var(--text-mid)' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--red)' }} /> Loitering (≥50s)
            </span>
          </div>
        </div>

        {zones.length === 0 ? (
          <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-low)', background: 'var(--panel-hi)', borderRadius: '8px' }}>
            <p style={{ fontSize: '13px', marginBottom: '10px' }}>No spatial zones configured yet.</p>
            <button className="n-btn primary" onClick={() => onSelectTab && onSelectTab('fencing')}>
              Create Perimeter Zones
            </button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: '16px' }}>
            {zones.map((zone) => {
              const zoneTracks = dwellTracks.filter((t) => t.zone_id === zone.zone_id);
              const th = editingThresholds[zone.zone_id] || {
                dwell: zone.dwell_threshold_seconds ?? 20.0,
                loiter: zone.loitering_threshold_seconds ?? 50.0,
              };
              const isSaving = savingZone[zone.zone_id];
              const isSaved = saveSuccessZone[zone.zone_id];

              return (
                <div
                  key={zone.zone_id}
                  className="zone-card-tile"
                  style={{
                    background: 'var(--panel-hi)',
                    border: '1px solid var(--hair)',
                    borderRadius: '10px',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                  }}
                >
                  {/* Zone Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-hi)' }}>
                          {zone.name || zone.zone_id}
                        </span>
                        <span
                          style={{
                            fontSize: '10px',
                            fontFamily: 'var(--mono)',
                            padding: '1px 6px',
                            borderRadius: '4px',
                            background: zone.zone_type === 'RESTRICTED' ? 'var(--red-dim)' : 'var(--blue-dim)',
                            color: zone.zone_type === 'RESTRICTED' ? 'var(--red)' : 'var(--gold)',
                            border: `1px solid ${zone.zone_type === 'RESTRICTED' ? 'rgba(239, 82, 81, 0.3)' : 'rgba(201, 154, 91, 0.3)'}`,
                            fontWeight: '600',
                          }}
                        >
                          {zone.zone_type || 'ZONE'}
                        </span>
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-low)', marginTop: '2px', fontFamily: 'var(--mono)' }}>
                        Camera: {zone.camera_id} · ID: {zone.zone_id}
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          fontFamily: 'var(--mono)',
                          padding: '2px 8px',
                          borderRadius: '12px',
                          background: zoneTracks.length > 0 ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.03)',
                          color: zoneTracks.length > 0 ? 'var(--text-hi)' : 'var(--text-low)',
                        }}
                      >
                        {zoneTracks.length} Active {zoneTracks.length === 1 ? 'Target' : 'Targets'}
                      </span>
                    </div>
                  </div>

                  {/* Configurable Thresholds Bar */}
                  <div
                    style={{
                      background: 'rgba(0,0,0,0.35)',
                      border: '1px solid var(--hair-soft)',
                      borderRadius: '6px',
                      padding: '8px 10px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '8px',
                      fontSize: '11.5px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--text-mid)' }}>
                        <span>Dwell:</span>
                        <input
                          type="number"
                          min="3"
                          max="300"
                          value={th.dwell}
                          onChange={(e) =>
                            setEditingThresholds((prev) => ({
                              ...prev,
                              [zone.zone_id]: { ...th, dwell: e.target.value },
                            }))
                          }
                          style={{
                            width: '46px',
                            background: '#111',
                            border: '1px solid var(--hair)',
                            color: 'var(--gold)',
                            borderRadius: '4px',
                            padding: '2px 4px',
                            fontFamily: 'var(--mono)',
                            fontSize: '11px',
                            textAlign: 'center',
                          }}
                        />
                        <span style={{ color: 'var(--text-low)' }}>s</span>
                      </label>

                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--text-mid)' }}>
                        <span>Loiter:</span>
                        <input
                          type="number"
                          min="5"
                          max="600"
                          value={th.loiter}
                          onChange={(e) =>
                            setEditingThresholds((prev) => ({
                              ...prev,
                              [zone.zone_id]: { ...th, loiter: e.target.value },
                            }))
                          }
                          style={{
                            width: '46px',
                            background: '#111',
                            border: '1px solid var(--hair)',
                            color: 'var(--red)',
                            borderRadius: '4px',
                            padding: '2px 4px',
                            fontFamily: 'var(--mono)',
                            fontSize: '11px',
                            textAlign: 'center',
                          }}
                        />
                        <span style={{ color: 'var(--text-low)' }}>s</span>
                      </label>
                    </div>

                    <button
                      className="n-btn"
                      style={{
                        padding: '2px 8px',
                        fontSize: '10.5px',
                        borderRadius: '4px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        background: isSaved ? 'var(--green-dim)' : 'rgba(255,255,255,0.06)',
                        color: isSaved ? 'var(--green)' : 'var(--text-hi)',
                        borderColor: isSaved ? 'var(--green)' : 'var(--hair)',
                      }}
                      disabled={isSaving}
                      onClick={() => handleSaveThresholds(zone.zone_id)}
                    >
                      {isSaved ? (
                        <>
                          <CheckIcon size={11} /> Saved
                        </>
                      ) : isSaving ? (
                        'Saving...'
                      ) : (
                        'Set Limits'
                      )}
                    </button>
                  </div>

                  {/* Active In-Zone Tracks */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minHeight: '60px' }}>
                    {zoneTracks.length === 0 ? (
                      <div
                        style={{
                          padding: '14px',
                          textAlign: 'center',
                          color: 'var(--text-low)',
                          fontSize: '11.5px',
                          fontStyle: 'italic',
                          background: 'rgba(255,255,255,0.01)',
                          borderRadius: '6px',
                          border: '1px dashed var(--hair-soft)',
                        }}
                      >
                        Sector clear · No active entities dwelling inside zone
                      </div>
                    ) : (
                      zoneTracks.map((trk) => {
                        const dwellLim = trk.dwell_threshold_seconds || 20.0;
                        const loiterLim = trk.loitering_threshold_seconds || 50.0;
                        const duration = trk.total_inside_duration || 0;
                        const statDuration = trk.stationary_duration || 0;
                        const pct = Math.min(100, Math.round((statDuration / loiterLim) * 100));

                        const isLoitering = trk.loitering_status === 'LOITERING';
                        const isDwelling = trk.loitering_status === 'DWELLING';

                        const statusColor = isLoitering
                          ? 'var(--red)'
                          : isDwelling
                          ? 'var(--gold)'
                          : 'var(--green)';

                        const statusBg = isLoitering
                          ? 'var(--red-dim)'
                          : isDwelling
                          ? 'var(--gold-dim)'
                          : 'var(--green-dim)';

                        return (
                          <div
                            key={trk.track_id}
                            className="occupant-item-tile"
                            style={{
                              background: isLoitering ? 'rgba(239, 82, 81, 0.08)' : 'rgba(0,0,0,0.4)',
                              border: `1px solid ${isLoitering ? 'rgba(239, 82, 81, 0.35)' : 'var(--hair)'}`,
                              borderRadius: '6px',
                              padding: '10px 12px',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '6px',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span
                                  style={{
                                    fontFamily: 'var(--mono)',
                                    fontWeight: '700',
                                    fontSize: '12px',
                                    color: 'var(--text-hi)',
                                  }}
                                >
                                  {trk.track_id}
                                </span>
                                <span
                                  style={{
                                    fontSize: '10px',
                                    padding: '1px 5px',
                                    borderRadius: '3px',
                                    background: 'rgba(255,255,255,0.06)',
                                    color: 'var(--text-mid)',
                                    textTransform: 'uppercase',
                                  }}
                                >
                                  {trk.object_type || 'TARGET'}
                                </span>
                                <span
                                  style={{
                                    fontSize: '10px',
                                    fontFamily: 'var(--mono)',
                                    padding: '1px 5px',
                                    borderRadius: '3px',
                                    background: trk.movement_state === 'STATIONARY' ? 'rgba(239, 82, 81, 0.15)' : 'rgba(47, 204, 139, 0.15)',
                                    color: trk.movement_state === 'STATIONARY' ? 'var(--red)' : 'var(--green)',
                                  }}
                                >
                                  {trk.movement_state || 'TRACKING'}
                                </span>
                              </div>

                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <span
                                  style={{
                                    fontSize: '10px',
                                    fontWeight: '700',
                                    fontFamily: 'var(--mono)',
                                    padding: '2px 7px',
                                    borderRadius: '4px',
                                    background: statusBg,
                                    color: statusColor,
                                    border: `1px solid ${statusColor}44`,
                                    animation: isLoitering ? 'pulse 1.5s infinite' : 'none',
                                  }}
                                >
                                  {trk.loitering_status || 'NORMAL'}
                                </span>

                                <button
                                  className="n-btn ai-investigate"
                                  style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px' }}
                                  onClick={() =>
                                    onInvestigate &&
                                    onInvestigate({
                                      event_id: `LOIT-${trk.track_id}`,
                                      track_id: trk.track_id,
                                      camera_id: trk.camera_id,
                                      zone_id: trk.zone_id,
                                      event_type: 'LOITERING',
                                      severity: isLoitering ? 'HIGH' : 'MEDIUM',
                                      description: `Live dwell investigation for ${trk.track_id} in ${trk.zone_name || trk.zone_id}. Status: ${trk.loitering_status}, duration: ${statDuration.toFixed(1)}s`,
                                    })
                                  }
                                >
                                  <AiSparklesIcon size={10} />
                                  <span>Investigate</span>
                                </button>
                              </div>
                            </div>

                            {/* Progress bar and timing detail */}
                            <div>
                              <div
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  fontSize: '10.5px',
                                  fontFamily: 'var(--mono)',
                                  color: 'var(--text-low)',
                                  marginBottom: '3px',
                                }}
                              >
                                <span>
                                  Stationary: <b style={{ color: statusColor }}>{formatDuration(statDuration)}</b>
                                  {' · '}Total: {formatDuration(duration)}
                                </span>
                                <span>
                                  Limit: {Math.round(loiterLim)}s ({pct}%)
                                </span>
                              </div>
                              <div
                                style={{
                                  width: '100%',
                                  height: '4px',
                                  background: 'rgba(255,255,255,0.06)',
                                  borderRadius: '2px',
                                  overflow: 'hidden',
                                }}
                              >
                                <div
                                  style={{
                                    height: '100%',
                                    width: `${pct}%`,
                                    background: statusColor,
                                    transition: 'width 0.3s ease, background 0.3s ease',
                                  }}
                                />
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Historical Zone & Loitering Audit Table */}
      <div className="tile" style={{ padding: '20px' }}>
        <div className="section-head" style={{ marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: '600', color: 'var(--text-hi)', margin: 0 }}>
              Loitering Threat & Zone Incident History
            </h3>
            <span className="section-sub">
              Audited dwell transitions and verified loitering occurrences saved across surveillance cameras.
            </span>
          </div>

          {/* Filters */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="text"
              placeholder="Search history, track, zone..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                background: '#0a0a0a',
                border: '1px solid var(--hair)',
                borderRadius: '6px',
                padding: '5px 10px',
                fontSize: '12px',
                color: 'var(--text-hi)',
                minWidth: '180px',
              }}
            />

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                background: '#0a0a0a',
                border: '1px solid var(--hair)',
                borderRadius: '6px',
                padding: '5px 10px',
                fontSize: '12px',
                color: 'var(--text-hi)',
              }}
            >
              <option value="ALL">All Statuses</option>
              <option value="LOITERING">Loitering Alerts</option>
              <option value="DWELLING">Dwelling Sessions</option>
            </select>

            <select
              value={cameraFilter}
              onChange={(e) => setCameraFilter(e.target.value)}
              style={{
                background: '#0a0a0a',
                border: '1px solid var(--hair)',
                borderRadius: '6px',
                padding: '5px 10px',
                fontSize: '12px',
                color: 'var(--text-hi)',
              }}
            >
              <option value="ALL">All Cameras</option>
              {uniqueCameras.map((cam) => (
                <option key={cam} value={cam}>
                  {cam}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Incident ID</th>
                <th>Camera & Zone</th>
                <th>Track ID</th>
                <th>Status</th>
                <th>Movement Dynamic</th>
                <th>Duration</th>
                <th>Timestamp</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loadingData ? (
                <TableRowSkeleton cols={8} rows={4} />
              ) : filteredHistory.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-low)' }}>
                    No zone incidents or loitering sessions match your criteria.
                  </td>
                </tr>
              ) : (
                filteredHistory.map((row) => {
                  const isLoit = row.status === 'LOITERING';
                  return (
                    <tr key={row.id}>
                      <td style={{ fontFamily: 'var(--mono)', fontSize: '11.5px', color: 'var(--text-mid)' }}>
                        {row.id}
                      </td>
                      <td>
                        <div style={{ fontWeight: '500', color: 'var(--text-hi)' }}>{row.zone_id}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                          {row.camera_id}
                        </div>
                      </td>
                      <td>
                        {row.track_id ? (
                          <span
                            style={{
                              fontFamily: 'var(--mono)',
                              fontSize: '11px',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              background: 'rgba(255,255,255,0.06)',
                              color: 'var(--text-hi)',
                            }}
                          >
                            {row.track_id}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-low)', fontSize: '11px' }}>—</span>
                        )}
                      </td>
                      <td>
                        <span
                          style={{
                            fontSize: '10.5px',
                            fontWeight: '700',
                            padding: '2px 7px',
                            borderRadius: '4px',
                            background: isLoit ? 'var(--red-dim)' : 'var(--gold-dim)',
                            color: isLoit ? 'var(--red)' : 'var(--gold)',
                            border: `1px solid ${isLoit ? 'rgba(239, 82, 81, 0.3)' : 'rgba(201, 154, 91, 0.3)'}`,
                          }}
                        >
                          {row.status}
                        </span>
                      </td>
                      <td>
                        <div style={{ fontSize: '12px', color: 'var(--text-mid)' }}>
                          {row.movement_state || 'Stationary'}
                        </div>
                        <div style={{ fontSize: '10.5px', color: 'var(--text-low)' }}>
                          {row.description}
                        </div>
                      </td>
                      <td style={{ fontFamily: 'var(--mono)', fontSize: '11.5px', color: 'var(--text-hi)' }}>
                        {formatDuration(row.duration_seconds)}
                      </td>
                      <td style={{ fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--text-low)' }}>
                        {row.timestamp ? new Date(row.timestamp).toLocaleString() : '—'}
                      </td>
                      <td>
                        <button
                          className="n-btn ai-investigate"
                          style={{ fontSize: '11px', padding: '3px 8px' }}
                          onClick={() =>
                            onInvestigate &&
                            onInvestigate(
                              row.rawEvent || {
                                event_id: row.event_id,
                                camera_id: row.camera_id,
                                zone_id: row.zone_id,
                                event_type: row.status,
                                severity: row.severity,
                                timestamp: row.timestamp,
                                description: row.description,
                              }
                            )
                          }
                        >
                          <AiSparklesIcon size={11} />
                          <span>Investigate AI</span>
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
