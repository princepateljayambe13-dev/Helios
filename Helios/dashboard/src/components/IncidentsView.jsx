import { useState, useEffect, useCallback, useMemo } from 'react';
import { api, getApiBase } from '../services/api';
import { TableRowSkeleton } from './SkeletonLoader';
import { BoltIcon, RefreshIcon, CheckIcon, CloseIcon, AiSparklesIcon } from './Icons';

const getSnapshotUrl = (ev) => {
  if (!ev) return '';
  if (ev.url) return ev.url;
  if (ev.evidence_id) {
    return api.getEvidenceFileUrl(ev.evidence_id);
  }
  if (ev.storage_reference) {
    if (ev.storage_reference.startsWith('http://') || ev.storage_reference.startsWith('https://')) {
      return ev.storage_reference;
    }
    const base = getApiBase();
    const cleanRef = ev.storage_reference.startsWith('/') ? ev.storage_reference : `/${ev.storage_reference}`;
    return `${base}${cleanRef}`;
  }
  return '';
};

export function IncidentsView({
  onInvestigate,
  onSelectTab,
  onRefresh,
}) {
  const [incidents, setIncidents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [selectedIncidentDetail, setSelectedIncidentDetail] = useState(null);
  const [previewEvidence, setPreviewEvidence] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [actionInProgress, setActionInProgress] = useState(false);

  // Evidence list and navigation for modal
  const evidenceList = selectedIncidentDetail?.evidence || [];
  const currentEvidenceIndex = previewEvidence
    ? evidenceList.findIndex((ev) => ev.evidence_id === previewEvidence.evidence_id)
    : -1;

  const handlePrevEvidence = useCallback(() => {
    if (currentEvidenceIndex > 0) {
      setPreviewEvidence(evidenceList[currentEvidenceIndex - 1]);
    }
  }, [currentEvidenceIndex, evidenceList]);

  const handleNextEvidence = useCallback(() => {
    if (currentEvidenceIndex >= 0 && currentEvidenceIndex < evidenceList.length - 1) {
      setPreviewEvidence(evidenceList[currentEvidenceIndex + 1]);
    }
  }, [currentEvidenceIndex, evidenceList]);

  useEffect(() => {
    if (!previewEvidence) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setPreviewEvidence(null);
      if (e.key === 'ArrowLeft') handlePrevEvidence();
      if (e.key === 'ArrowRight') handleNextEvidence();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [previewEvidence, handlePrevEvidence, handleNextEvidence]);

  // Fetch incidents list & summary
  const fetchIncidentsData = useCallback(async () => {
    try {
      const [listRes, sumRes] = await Promise.all([
        api.getIncidents({ limit: 100 }).catch(() => ({ incidents: [] })),
        api.getIncidentsSummary().catch(() => null),
      ]);

      const incs = listRes.incidents || [];
      setIncidents(incs);
      setSummary(sumRes);

      // Auto-select first incident if none selected
      setSelectedIncidentId((prev) => {
        if (prev && incs.some((i) => i.incident_id === prev)) return prev;
        return incs.length > 0 ? incs[0].incident_id : null;
      });
    } catch (err) {
      console.error('Failed to fetch incidents:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Fetch selected incident full details
  const fetchDetail = useCallback(async (id) => {
    if (!id) return;
    setLoadingDetail(true);
    try {
      const detail = await api.getIncident(id);
      setSelectedIncidentDetail(detail);
    } catch (err) {
      console.error('Failed to fetch incident detail:', err);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    fetchIncidentsData();
    const interval = setInterval(() => {
      fetchIncidentsData();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchIncidentsData]);

  useEffect(() => {
    if (selectedIncidentId) {
      fetchDetail(selectedIncidentId);
    } else {
      setSelectedIncidentDetail(null);
    }
  }, [selectedIncidentId, fetchDetail]);

  const handleManualRefresh = () => {
    setRefreshing(true);
    fetchIncidentsData();
    if (selectedIncidentId) fetchDetail(selectedIncidentId);
    if (onRefresh) onRefresh();
  };

  const handleAcknowledge = async (id) => {
    setActionInProgress(true);
    try {
      await api.acknowledgeIncident(id, 'Operator');
      await fetchIncidentsData();
      await fetchDetail(id);
    } catch (err) {
      alert(`Failed to acknowledge incident: ${err.message}`);
    } finally {
      setActionInProgress(false);
    }
  };

  const handleResolve = async (id) => {
    setActionInProgress(true);
    try {
      await api.resolveIncident(id, 'Operator');
      await fetchIncidentsData();
      await fetchDetail(id);
    } catch (err) {
      alert(`Failed to resolve incident: ${err.message}`);
    } finally {
      setActionInProgress(false);
    }
  };

  const filteredIncidents = useMemo(() => {
    return incidents.filter((inc) => {
      if (statusFilter !== 'ALL' && inc.status !== statusFilter) return false;
      if (severityFilter !== 'ALL' && inc.severity !== severityFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        const mId = inc.incident_id?.toLowerCase().includes(q);
        const mTitle = inc.title?.toLowerCase().includes(q);
        const mType = inc.incident_type?.toLowerCase().includes(q);
        const mCam = inc.primary_camera_id?.toLowerCase().includes(q);
        const mZone = inc.primary_zone_id?.toLowerCase().includes(q);
        const mTrack = inc.primary_track_id?.toLowerCase().includes(q);
        if (!mId && !mTitle && !mType && !mCam && !mZone && !mTrack) return false;
      }
      return true;
    });
  }, [incidents, statusFilter, severityFilter, searchQuery]);

  const formatDuration = (seconds) => {
    if (!seconds || seconds <= 0) return '0s';
    const s = Math.round(seconds);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}m ${rem}s`;
  };

  const getSeverityStyle = (sev) => {
    switch (sev) {
      case 'CRITICAL':
        return { color: 'var(--red)', bg: 'var(--red-dim)', border: 'rgba(239, 82, 81, 0.4)' };
      case 'HIGH':
        return { color: 'var(--red)', bg: 'rgba(239, 82, 81, 0.12)', border: 'rgba(239, 82, 81, 0.25)' };
      case 'ELEVATED':
      case 'MEDIUM':
        return { color: 'var(--gold)', bg: 'var(--gold-dim)', border: 'rgba(201, 154, 91, 0.3)' };
      default:
        return { color: 'var(--green)', bg: 'var(--green-dim)', border: 'rgba(47, 204, 139, 0.3)' };
    }
  };

  const getStatusStyle = (st) => {
    switch (st) {
      case 'ACTIVE':
        return { color: 'var(--red)', bg: 'var(--red-dim)', label: 'ACTIVE THREAT' };
      case 'CONFIRMED':
        return { color: 'var(--gold)', bg: 'var(--gold-dim)', label: 'CONFIRMED' };
      case 'DETECTED':
        return { color: 'var(--text-mid)', bg: 'rgba(255,255,255,0.06)', label: 'DETECTED' };
      case 'ACKNOWLEDGED':
        return { color: '#60a5fa', bg: 'rgba(96, 165, 250, 0.12)', label: 'ACKNOWLEDGED' };
      case 'RESOLVED':
        return { color: 'var(--green)', bg: 'var(--green-dim)', label: 'RESOLVED' };
      default:
        return { color: 'var(--text-mid)', bg: 'rgba(255,255,255,0.06)', label: st };
    }
  };

  const activeCount = summary?.active_incidents ?? incidents.filter((i) => ['DETECTED', 'CONFIRMED', 'ACTIVE'].includes(i.status)).length;
  const criticalCount = summary?.critical_incidents ?? incidents.filter((i) => i.severity === 'CRITICAL' && i.status !== 'RESOLVED').length;
  const totalCorrelated = summary?.correlated_events ?? incidents.reduce((acc, i) => acc + (i.event_count || 1), 0);
  const dedupRatio = summary?.deduplication_ratio_pct ?? 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Section Head */}
      <div className="section-head" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <h2>Incident Correlation & Developing Situations</h2>
            <span className="beta-pill">Beta</span>
            <span
              style={{
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '10.5px',
                fontFamily: 'var(--mono)',
                background: 'rgba(239, 82, 81, 0.15)',
                color: 'var(--red)',
                border: '1px solid rgba(239, 82, 81, 0.3)',
                fontWeight: '600',
                letterSpacing: '0.05em',
              }}
            >
              CORRELATION ENGINE
            </span>
          </div>
          <span className="section-sub">
            Continuous probabilistic correlation unifying multi-camera detections, zone breaches, and movement dynamics into verified incidents.
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
        <div
          className="tile incident-stat-tile"
          style={{
            padding: '16px',
            borderColor: activeCount > 0 ? 'rgba(239, 82, 81, 0.35)' : 'var(--hair)',
            background: activeCount > 0 ? 'rgba(239, 82, 81, 0.04)' : 'var(--panel)',
          }}
        >
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Active Developing Situations
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span
              style={{
                fontSize: '26px',
                fontWeight: '700',
                color: activeCount > 0 ? 'var(--red)' : 'var(--text-hi)',
                fontFamily: 'var(--mono)',
              }}
            >
              {activeCount}
            </span>
            {activeCount > 0 && (
              <span
                style={{
                  fontSize: '10.5px',
                  fontWeight: '700',
                  color: 'var(--red)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: 'var(--red-dim)',
                  animation: 'pulse 1.5s infinite',
                }}
              >
                LIVE
              </span>
            )}
          </div>
        </div>

        <div className="tile incident-stat-tile" style={{ padding: '16px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Critical / Escalated Threats
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span
              style={{
                fontSize: '26px',
                fontWeight: '700',
                color: criticalCount > 0 ? 'var(--red)' : 'var(--text-hi)',
                fontFamily: 'var(--mono)',
              }}
            >
              {criticalCount}
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-mid)' }}>
              compound multi-zone breaches
            </span>
          </div>
        </div>

        <div className="tile incident-stat-tile" style={{ padding: '16px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Correlated Observations
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '26px', fontWeight: '700', color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
              {totalCorrelated}
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-mid)' }}>
              across {incidents.length} total incidents
            </span>
          </div>
        </div>

        <div className="tile incident-stat-tile" style={{ padding: '16px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Alert Storm Reduction
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '26px', fontWeight: '700', color: 'var(--green)', fontFamily: 'var(--mono)' }}>
              {dedupRatio}%
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-mid)' }}>
              deduplication efficiency
            </span>
          </div>
        </div>
      </div>

      {/* Master-Detail Command Center Layout */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(320px, 390px) 1fr',
          gap: '16px',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Incidents Feed & Evidence Snapshots */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Tile 1: Incidents Feed */}
          <div className="tile" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-hi)', margin: 0 }}>
                Incidents Feed ({filteredIncidents.length})
              </h3>
            </div>

            {/* Filter Bar */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <input
                type="text"
                placeholder="Search incidents, track, zone..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  background: '#0a0a0a',
                  border: '1px solid var(--hair)',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  fontSize: '12px',
                  color: 'var(--text-hi)',
                }}
              />

              <div style={{ display: 'flex', gap: '6px' }}>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  style={{
                    flex: 1,
                    background: '#0a0a0a',
                    border: '1px solid var(--hair)',
                    borderRadius: '6px',
                    padding: '5px 8px',
                    fontSize: '11.5px',
                    color: 'var(--text-hi)',
                  }}
                >
                  <option value="ALL">All Statuses</option>
                  <option value="ACTIVE">Active Threats</option>
                  <option value="CONFIRMED">Confirmed</option>
                  <option value="DETECTED">Detected</option>
                  <option value="ACKNOWLEDGED">Acknowledged</option>
                  <option value="RESOLVED">Resolved</option>
                </select>

                <select
                  value={severityFilter}
                  onChange={(e) => setSeverityFilter(e.target.value)}
                  style={{
                    flex: 1,
                    background: '#0a0a0a',
                    border: '1px solid var(--hair)',
                    borderRadius: '6px',
                    padding: '5px 8px',
                    fontSize: '11.5px',
                    color: 'var(--text-hi)',
                  }}
                >
                  <option value="ALL">All Severities</option>
                  <option value="CRITICAL">Critical</option>
                  <option value="HIGH">High</option>
                  <option value="ELEVATED">Elevated</option>
                  <option value="MEDIUM">Medium</option>
                </select>
              </div>
            </div>

            {/* Incidents List with In-Box Scroll */}
            <div className="in-box-scroll" style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '420px', overflowY: 'auto', paddingRight: '4px' }}>
              {loading ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-low)' }}>
                  Loading incidents correlation matrix...
                </div>
              ) : filteredIncidents.length === 0 ? (
                <div
                  style={{
                    padding: '24px',
                    textAlign: 'center',
                    color: 'var(--text-low)',
                    fontSize: '12px',
                    background: 'rgba(255,255,255,0.02)',
                    borderRadius: '6px',
                  }}
                >
                  No correlated incidents match your filter.
                </div>
              ) : (
                filteredIncidents.map((inc) => {
                  const isSelected = selectedIncidentId === inc.incident_id;
                  const sevStyle = getSeverityStyle(inc.severity);
                  const stStyle = getStatusStyle(inc.status);
                  const confPct = Math.round((inc.confidence || 0) * 100);

                  return (
                    <div
                      key={inc.incident_id}
                      onClick={() => setSelectedIncidentId(inc.incident_id)}
                      className={`incident-card-tile ${isSelected ? 'selected' : ''} ${isSelected && inc.severity === 'CRITICAL' ? 'critical' : ''}`}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span
                          style={{
                            fontFamily: 'var(--mono)',
                            fontSize: '11px',
                            fontWeight: '700',
                            color: isSelected ? 'var(--gold)' : 'var(--text-hi)',
                          }}
                        >
                          {inc.incident_id}
                        </span>

                        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                          <span
                            style={{
                              fontSize: '9.5px',
                              fontWeight: '700',
                              padding: '1px 5px',
                              borderRadius: '3px',
                              background: stStyle.bg,
                              color: stStyle.color,
                              border: `1px solid ${stStyle.color}33`,
                            }}
                          >
                            {stStyle.label}
                          </span>

                          <span
                            style={{
                              fontSize: '9.5px',
                              fontWeight: '700',
                              padding: '1px 5px',
                              borderRadius: '3px',
                              background: sevStyle.bg,
                              color: sevStyle.color,
                              border: `1px solid ${sevStyle.border}`,
                            }}
                          >
                            {inc.severity}
                          </span>
                        </div>
                      </div>

                      <div style={{ fontSize: '12.5px', fontWeight: '600', color: 'var(--text-hi)', lineHeight: '1.3' }}>
                        {inc.title}
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                        <span>{inc.primary_zone_id || inc.primary_camera_id || 'System'}</span>
                        <span>{inc.event_count} events · {formatDuration(inc.duration_seconds)}</span>
                      </div>

                      {/* Confidence Meter */}
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', fontFamily: 'var(--mono)', color: 'var(--text-low)', marginBottom: '2px' }}>
                          <span>Confidence</span>
                          <span>{confPct}%</span>
                        </div>
                        <div style={{ width: '100%', height: '3px', background: 'rgba(255,255,255,0.06)', borderRadius: '2px', overflow: 'hidden' }}>
                          <div
                            style={{
                              height: '100%',
                              width: `${confPct}%`,
                              background: confPct > 80 ? 'var(--green)' : confPct > 55 ? 'var(--gold)' : 'var(--red)',
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

          {/* Tile 2: Evidence Snapshot Box (Full Picture with In-Box Scroll) */}
          <div className="tile" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-hi)', margin: 0 }}>
                  Evidence Snapshots
                </h3>
                {selectedIncidentDetail?.evidence && (
                  <span
                    style={{
                      fontFamily: 'var(--mono)',
                      fontSize: '10.5px',
                      color: 'var(--gold)',
                      background: 'rgba(201, 154, 91, 0.12)',
                      border: '1px solid rgba(201, 154, 91, 0.3)',
                      padding: '1px 6px',
                      borderRadius: '10px',
                    }}
                  >
                    {selectedIncidentDetail.evidence.length}
                  </span>
                )}
              </div>
              {selectedIncidentDetail?.evidence && selectedIncidentDetail.evidence.length > 0 && (
                <span style={{ fontSize: '10px', fontFamily: 'var(--mono)', color: 'var(--text-low)', letterSpacing: '0.5px' }}>
                  SCROLL TO VIEW ({selectedIncidentDetail.evidence.length})
                </span>
              )}
            </div>

            {selectedIncidentDetail ? (
              selectedIncidentDetail.evidence && selectedIncidentDetail.evidence.length > 0 ? (
                <div
                  className="in-box-scroll"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    maxHeight: '380px',
                    overflowY: 'auto',
                    paddingRight: '6px',
                  }}
                >
                  {selectedIncidentDetail.evidence.map((ev, idx) => (
                    <div
                      key={ev.evidence_id || idx}
                      className="tile"
                      style={{
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: '1px solid var(--hair)',
                        background: '#070707',
                        display: 'flex',
                        flexDirection: 'column',
                        transition: 'border-color 0.15s ease, transform 0.15s ease',
                      }}
                    >
                      {/* Picture Container - Kept in Its Own Natural Size */}
                      <div
                        style={{
                          width: '100%',
                          minHeight: '140px',
                          maxHeight: '260px',
                          background: '#040404',
                          position: 'relative',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          overflow: 'hidden',
                          cursor: 'pointer',
                          padding: '8px',
                        }}
                        onClick={() => setPreviewEvidence(ev)}
                        title="Click to view picture in inspection window"
                      >
                        <img
                          src={getSnapshotUrl(ev)}
                          alt={ev.evidence_id}
                          style={{
                            width: 'auto',
                            height: 'auto',
                            maxWidth: '100%',
                            maxHeight: '244px',
                            display: 'block',
                            margin: '0 auto',
                            borderRadius: '4px',
                          }}
                          onError={(e) => {
                            if (!e.target.dataset.retried && ev.evidence_id) {
                              e.target.dataset.retried = 'true';
                              e.target.src = `/api/v1/evidence/${encodeURIComponent(ev.evidence_id)}/file`;
                            }
                          }}
                        />

                        {/* Full Picture badge overlay */}
                        <div
                          style={{
                            position: 'absolute',
                            bottom: '8px',
                            right: '8px',
                            background: 'rgba(0, 0, 0, 0.75)',
                            backdropFilter: 'blur(6px)',
                            border: '1px solid var(--hair)',
                            borderRadius: '4px',
                            padding: '3px 8px',
                            fontSize: '10px',
                            fontFamily: 'var(--mono)',
                            color: 'var(--text-mid)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '5px',
                            pointerEvents: 'none',
                          }}
                        >
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                          </svg>
                          <span>Full Picture</span>
                        </div>
                      </div>

                      {/* Snapshot Meta Header */}
                      <div
                        style={{
                          padding: '10px 12px',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          borderTop: '1px solid var(--hair-soft)',
                          background: '#0a0a0a',
                        }}
                      >
                        <div style={{ overflow: 'hidden', paddingRight: '8px' }}>
                          <div
                            style={{
                              color: 'var(--text-hi)',
                              fontWeight: '600',
                              fontSize: '11px',
                              fontFamily: 'var(--mono)',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}
                            title={ev.evidence_id}
                          >
                            {ev.evidence_id}
                          </div>
                          <div style={{ color: 'var(--gold)', fontSize: '10px', fontFamily: 'var(--mono)', marginTop: '2px' }}>
                            {ev.type || 'SNAPSHOT'} {ev.timestamp ? `· ${new Date(ev.timestamp).toLocaleTimeString()}` : ''}
                          </div>
                        </div>

                        <button
                          className="n-btn"
                          style={{
                            fontSize: '11px',
                            padding: '4px 9px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            whiteSpace: 'nowrap',
                          }}
                          onClick={() => setPreviewEvidence(ev)}
                          title="Open full view inspection dialog"
                        >
                          <span>Inspect</span>
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                            <path d="M7 17L17 7M7 7h10v10" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  style={{
                    padding: '24px 16px',
                    textAlign: 'center',
                    color: 'var(--text-low)',
                    fontSize: '12px',
                    background: 'rgba(255,255,255,0.02)',
                    borderRadius: '6px',
                    border: '1px dashed var(--hair)',
                  }}
                >
                  No sensor snapshots linked to this incident.
                </div>
              )
            ) : (
              <div
                style={{
                  padding: '28px 16px',
                  textAlign: 'center',
                  color: 'var(--text-low)',
                  fontSize: '12px',
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: '6px',
                  border: '1px dashed var(--hair)',
                }}
              >
                Select an incident from the feed to review correlated forensic snapshots.
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Selected Incident Command Center */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {selectedIncidentDetail ? (
            <>
              {/* Incident Header Tile */}
              <div className="tile" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: '14px', fontWeight: '700', color: 'var(--gold)' }}>
                        {selectedIncidentDetail.incident_id}
                      </span>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: '700',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          ...getSeverityStyle(selectedIncidentDetail.severity),
                        }}
                      >
                        {selectedIncidentDetail.severity}
                      </span>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: '700',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          ...getStatusStyle(selectedIncidentDetail.status),
                        }}
                      >
                        {getStatusStyle(selectedIncidentDetail.status).label}
                      </span>
                    </div>

                    <h2 style={{ fontSize: '18px', fontWeight: '700', color: 'var(--text-hi)', marginTop: '6px' }}>
                      {selectedIncidentDetail.title}
                    </h2>

                    <div style={{ display: 'flex', gap: '14px', marginTop: '6px', fontSize: '11.5px', color: 'var(--text-mid)', fontFamily: 'var(--mono)', flexWrap: 'wrap' }}>
                      <span>Started: {new Date(selectedIncidentDetail.start_time).toLocaleTimeString()}</span>
                      <span>Last Activity: {new Date(selectedIncidentDetail.last_seen_at).toLocaleTimeString()}</span>
                      <span>Duration: {formatDuration(selectedIncidentDetail.duration_seconds)}</span>
                      <span>Confidence: {Math.round(selectedIncidentDetail.confidence * 100)}%</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    {selectedIncidentDetail.status !== 'ACKNOWLEDGED' && selectedIncidentDetail.status !== 'RESOLVED' && (
                      <button
                        className="n-btn"
                        style={{ fontSize: '12px', padding: '6px 12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                        disabled={actionInProgress}
                        onClick={() => handleAcknowledge(selectedIncidentDetail.incident_id)}
                      >
                        <CheckIcon size={13} /> Acknowledge
                      </button>
                    )}

                    {selectedIncidentDetail.status !== 'RESOLVED' && (
                      <button
                        className="n-btn"
                        style={{ fontSize: '12px', padding: '6px 12px' }}
                        disabled={actionInProgress}
                        onClick={() => handleResolve(selectedIncidentDetail.incident_id)}
                      >
                        Resolve Incident
                      </button>
                    )}

                    <button
                      className="n-btn ai-investigate"
                      style={{ fontSize: '12px', padding: '6px 14px' }}
                      onClick={() =>
                        onInvestigate &&
                        onInvestigate({
                          event_id: selectedIncidentDetail.incident_id,
                          incident_id: selectedIncidentDetail.incident_id,
                          event_type: selectedIncidentDetail.incident_type,
                          severity: selectedIncidentDetail.severity,
                          camera_id: selectedIncidentDetail.primary_camera_id,
                          zone_id: selectedIncidentDetail.primary_zone_id,
                          track_id: selectedIncidentDetail.primary_track_id,
                          description: selectedIncidentDetail.summary,
                        })
                      }
                    >
                      <AiSparklesIcon size={13} />
                      <span>Investigate AI</span>
                    </button>
                  </div>
                </div>

                {/* Summary narrative */}
                <div
                  style={{
                    background: 'rgba(0,0,0,0.4)',
                    border: '1px solid var(--hair-soft)',
                    borderRadius: '8px',
                    padding: '12px 14px',
                    fontSize: '12.5px',
                    lineHeight: '1.5',
                    color: 'var(--text-hi)',
                  }}
                >
                  {selectedIncidentDetail.summary || 'No narrative synthesis available.'}
                </div>
              </div>

              {/* "Why Correlated" Rationale Breakdown */}
              <div className="tile" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-hi)', margin: 0 }}>
                    Why This Incident Was Correlated
                  </h3>
                  <span
                    style={{
                      fontSize: '10px',
                      fontFamily: 'var(--mono)',
                      background: 'rgba(255,255,255,0.06)',
                      padding: '1px 6px',
                      borderRadius: '4px',
                      color: 'var(--gold)',
                    }}
                  >
                    PROBABILISTIC RATIONALE
                  </span>
                </div>

                {/* Correlation Score Meters */}
                {selectedIncidentDetail.score_breakdown && (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                      gap: '10px',
                      marginBottom: '16px',
                    }}
                  >
                    {[
                      { key: 'time', label: 'Temporal Proximity' },
                      { key: 'track', label: 'Track Continuity' },
                      { key: 'spatial', label: 'Spatial / Zone' },
                      { key: 'attribute', label: 'Entity Category' },
                      { key: 'sequence', label: 'Threat Sequence' },
                    ].map(({ key, label }) => {
                      const score = selectedIncidentDetail.score_breakdown[key] ?? 0.8;
                      const pct = Math.round(score * 100);
                      return (
                        <div
                          key={key}
                          className="incident-mini-tile"
                        >
                          <div style={{ fontSize: '10.5px', color: 'var(--text-low)', marginBottom: '4px' }}>
                            {label}
                          </div>
                          <div style={{ fontSize: '14px', fontWeight: '700', fontFamily: 'var(--mono)', color: 'var(--text-hi)' }}>
                            {pct}%
                          </div>
                          <div style={{ width: '100%', height: '3px', background: 'rgba(255,255,255,0.06)', borderRadius: '2px', marginTop: '6px' }}>
                            <div style={{ height: '100%', width: `${pct}%`, background: 'var(--gold)' }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Rationale Bullet Factors */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {(selectedIncidentDetail.correlation_reasons || []).map((reason, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        alignItems: 'baseline',
                        gap: '8px',
                        fontSize: '12px',
                        color: 'var(--text-mid)',
                      }}
                    >
                      <span style={{ color: 'var(--gold)', fontSize: '11px' }}>▸</span>
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Chronological Situation Timeline */}
              <div className="tile" style={{ padding: '20px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-hi)', marginBottom: '14px' }}>
                  Developing Situation Timeline ({selectedIncidentDetail.timeline?.length || 0} stages)
                </h3>

                <div className="in-box-scroll" style={{ maxHeight: '380px', overflowY: 'auto', paddingRight: '8px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', position: 'relative', paddingLeft: '16px' }}>
                    {/* Vertical rule line */}
                    <div
                      style={{
                        position: 'absolute',
                        left: '6px',
                        top: '8px',
                        bottom: '8px',
                        width: '2px',
                        background: 'var(--hair)',
                      }}
                    />

                    {(selectedIncidentDetail.timeline || []).map((step, idx) => {
                      const isAlertNode = ['INTRUSION', 'LOITERING', 'RESTRICTED_BREACH'].includes(step.node_type);
                      return (
                        <div key={idx} style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          {/* Bullet node */}
                          <div
                            style={{
                              position: 'absolute',
                              left: '-14px',
                              top: '4px',
                              width: '8px',
                              height: '8px',
                              borderRadius: '50%',
                              background: isAlertNode ? 'var(--red)' : 'var(--gold)',
                              boxShadow: isAlertNode ? '0 0 6px var(--red)' : 'none',
                            }}
                          />

                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: '12.5px', fontWeight: '600', color: 'var(--text-hi)' }}>
                              {step.title}
                            </span>
                            <span style={{ fontSize: '11px', fontFamily: 'var(--mono)', color: 'var(--text-low)' }}>
                              {new Date(step.timestamp).toLocaleTimeString()}
                            </span>
                          </div>

                          <div style={{ fontSize: '11.5px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                            Camera: {step.camera_id} · Zone: {step.zone_id} · Track: {step.track_id}
                          </div>

                          <div style={{ fontSize: '12px', color: 'var(--text-mid)', marginTop: '2px' }}>
                            {step.detail}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div
              className="tile"
              style={{
                padding: '48px',
                textAlign: 'center',
                color: 'var(--text-low)',
                fontSize: '13px',
              }}
            >
              Select an incident from the feed to inspect correlation rationale, timeline, and sensor evidence.
            </div>
          )}
        </div>
      </div>

      {/* High-Resolution Full Picture Inspection Modal */}
      {previewEvidence && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.88)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
          onClick={() => setPreviewEvidence(null)}
        >
          <div
            className="tile"
            style={{
              maxWidth: '960px',
              width: '100%',
              maxHeight: '92vh',
              overflowY: 'auto',
              padding: '22px',
              borderRadius: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
              border: '1px solid #2a2a2a',
              background: '#0d0d0f',
              boxShadow: '0 24px 60px rgba(0,0,0,0.95)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span
                    style={{
                      fontFamily: 'var(--mono)',
                      fontSize: '11px',
                      color: 'var(--gold)',
                      background: 'rgba(201, 154, 91, 0.14)',
                      padding: '2px 7px',
                      borderRadius: '4px',
                      fontWeight: '600',
                    }}
                  >
                    {previewEvidence.type || 'FORENSIC SNAPSHOT'}
                  </span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: '13px', fontWeight: '700', color: 'var(--text-hi)' }}>
                    {previewEvidence.evidence_id}
                  </span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)', marginTop: '4px' }}>
                  Incident: {selectedIncidentDetail?.incident_id} {previewEvidence.timestamp ? `· ${new Date(previewEvidence.timestamp).toLocaleString()}` : ''}
                  {evidenceList.length > 1 && ` (Snapshot ${currentEvidenceIndex + 1} of ${evidenceList.length})`}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {evidenceList.length > 1 && (
                  <div style={{ display: 'flex', gap: '4px', marginRight: '6px' }}>
                    <button
                      className="n-btn"
                      disabled={currentEvidenceIndex <= 0}
                      onClick={handlePrevEvidence}
                      title="Previous snapshot (Left Arrow)"
                      style={{ padding: '5px 10px', fontSize: '12px' }}
                    >
                      ‹ Prev
                    </button>
                    <button
                      className="n-btn"
                      disabled={currentEvidenceIndex >= evidenceList.length - 1}
                      onClick={handleNextEvidence}
                      title="Next snapshot (Right Arrow)"
                      style={{ padding: '5px 10px', fontSize: '12px' }}
                    >
                      Next ›
                    </button>
                  </div>
                )}
                <button
                  className="n-btn"
                  onClick={() => setPreviewEvidence(null)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <CloseIcon size={13} />
                  <span>Close</span>
                </button>
              </div>
            </div>

            {/* Modal Image Frame - Kept in Its Own Natural Size */}
            <div
              style={{
                width: '100%',
                background: '#040404',
                borderRadius: '8px',
                border: '1px solid var(--hair)',
                minHeight: '260px',
                maxHeight: '68vh',
                overflow: 'auto',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                position: 'relative',
                padding: '16px',
              }}
            >
              <img
                src={getSnapshotUrl(previewEvidence)}
                alt={previewEvidence.evidence_id}
                style={{
                  width: 'auto',
                  height: 'auto',
                  maxWidth: '100%',
                  maxHeight: '64vh',
                  display: 'block',
                  margin: 'auto',
                  borderRadius: '4px',
                  boxShadow: '0 8px 30px rgba(0, 0, 0, 0.8)',
                }}
                onError={(e) => {
                  if (!e.target.dataset.retried && previewEvidence.evidence_id) {
                    e.target.dataset.retried = 'true';
                    e.target.src = `/api/v1/evidence/${encodeURIComponent(previewEvidence.evidence_id)}/file`;
                  }
                }}
              />
            </div>

            {/* Modal Footer / Actions */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                {previewEvidence.integrity_hash && (
                  <div>SHA256: <span style={{ color: 'var(--green)' }}>{previewEvidence.integrity_hash}</span></div>
                )}
                <div>Full resolution forensic capture · Complete sensor frame</div>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <a
                  href={api.getEvidenceFileUrl(previewEvidence.evidence_id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  download={previewEvidence.evidence_id}
                  className="n-btn"
                  style={{ fontSize: '11.5px', padding: '5px 12px', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <span>Open High-Res</span>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                  </svg>
                </a>

                {onInvestigate && (
                  <button
                    className="n-btn ai-investigate"
                    style={{ fontSize: '11.5px', padding: '5px 14px' }}
                    onClick={() => {
                      const ev = previewEvidence;
                      setPreviewEvidence(null);
                      onInvestigate({
                        event_id: selectedIncidentDetail?.incident_id,
                        evidence_id: ev.evidence_id,
                        type: ev.type,
                      });
                    }}
                  >
                    <AiSparklesIcon size={12} />
                    <span>Investigate AI</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
