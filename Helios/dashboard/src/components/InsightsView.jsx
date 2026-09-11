import { useState, useEffect, useCallback, useMemo } from 'react';
import { api, getApiBase } from '../services/api';
import {
  RefreshIcon,
  SearchIcon,
  CheckIcon,
  CloseIcon,
  AiSparklesIcon,
  CameraIcon,
  BoltIcon,
  ChartBarIcon,
  BrainIcon,
  WalkingIcon,
  PaletteIcon,
} from './Icons';

export function InsightsView({
  onSelectTab,
  onInvestigate,
}) {
  const [insights, setInsights] = useState([]);
  const [summary, setSummary] = useState(null);
  const [whatChanged, setWhatChanged] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeFilter, setActiveFilter] = useState('ALL'); // ALL, IMPORTANT, CRITICAL, RECENT
  const [selectedInsight, setSelectedInsight] = useState(null);

  // Natural Language Search State
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [investigationResult, setInvestigationResult] = useState(null);
  const [searchError, setSearchError] = useState(null);

  const fetchInsightsData = useCallback(async () => {
    try {
      const [insRes, sumRes, wcRes] = await Promise.all([
        api.getInsights({ limit: 50 }).catch(() => ({ insights: [] })),
        api.getInsightsSummary().catch(() => null),
        api.getWhatChanged().catch(() => ({ changes: [] })),
      ]);

      setInsights(insRes.insights || []);
      setSummary(sumRes);
      setWhatChanged(wcRes.changes || []);
    } catch (err) {
      console.error('Failed to fetch insights data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchInsightsData();
    const interval = setInterval(fetchInsightsData, 8000);
    return () => clearInterval(interval);
  }, [fetchInsightsData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchInsightsData();
  };

  const handleFeedback = async (insightId, feedbackType) => {
    try {
      await api.recordInsightFeedback(insightId, feedbackType);
      // Optimistic update
      setInsights((prev) =>
        prev.map((ins) =>
          ins.insight_id === insightId
            ? {
                ...ins,
                status: feedbackType === 'DISMISS' ? 'RESOLVED' : feedbackType === 'CONFIRM' ? 'ACKNOWLEDGED' : ins.status,
              }
            : ins
        )
      );
      if (selectedInsight && selectedInsight.insight_id === insightId) {
        setSelectedInsight((prev) => ({
          ...prev,
          status: feedbackType === 'DISMISS' ? 'RESOLVED' : feedbackType === 'CONFIRM' ? 'ACKNOWLEDGED' : prev.status,
        }));
      }
      // Refresh summary counts
      api.getInsightsSummary().then((s) => s && setSummary(s)).catch(() => {});
    } catch (err) {
      console.error('Failed to record feedback:', err);
    }
  };

  const handleNlSearch = async (queryText) => {
    const q = (queryText || searchQuery).trim();
    if (!q) return;
    setIsSearching(true);
    setSearchError(null);
    try {
      const res = await api.investigateEvidenceNL(q);
      setInvestigationResult(res);
    } catch (err) {
      setSearchError('Investigation failed: ' + (err.message || 'Check connection'));
    } finally {
      setIsSearching(false);
    }
  };

  // Filter insights
  const filteredInsights = useMemo(() => {
    if (activeFilter === 'IMPORTANT') {
      return insights.filter((i) => i.priority === 'IMPORTANT' || i.priority === 'CRITICAL');
    }
    if (activeFilter === 'CRITICAL') {
      return insights.filter((i) => i.priority === 'CRITICAL');
    }
    if (activeFilter === 'RECENT') {
      // Last 2 hours
      const cutoff = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
      return insights.filter((i) => i.created_at >= cutoff);
    }
    return insights;
  }, [insights, activeFilter]);

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'CRITICAL':
        return 'var(--red, #ef4444)';
      case 'IMPORTANT':
        return 'var(--amber, #f59e0b)';
      case 'NOTABLE':
        return 'var(--gold, #C99A5B)';
      default:
        return 'var(--text-muted, #94a3b8)';
    }
  };

  const sampleQueries = [
    'What happened near East Zone after midnight?',
    'Which zone had the highest activity?',
    'What were people wearing or doing?',
    'Were any vehicles detected in the last hour?',
    'How long did people remain in Zone 3?',
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '16px 20px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* TOP HEADER SECTION */}
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: '12px', borderBottom: '1px solid var(--hair)', paddingBottom: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h1 style={{ margin: 0, fontSize: '20px', fontWeight: '700', letterSpacing: '0.5px' }}>INSIGHTS</h1>
            <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', background: 'var(--gold-dim, #241B14)', color: 'var(--gold, #C99A5B)', border: '1px solid rgba(201, 154, 91, 0.3)', fontWeight: '600' }}>
              Intelligence Layer
            </span>
          </div>
          <div style={{ marginTop: '4px', fontSize: '12.5px', color: 'var(--text-low)' }}>
            Autonomous observation correlation & multi-signal telemetry synthesis
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* FILTER PILLS */}
          <div style={{ display: 'flex', background: 'var(--panel)', borderRadius: '8px', padding: '3px', border: '1px solid var(--hair)' }}>
            {['ALL', 'IMPORTANT', 'CRITICAL', 'RECENT'].map((f) => (
              <button
                key={f}
                onClick={() => setActiveFilter(f)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: 'none',
                  fontSize: '11px',
                  fontWeight: activeFilter === f ? '700' : '500',
                  background: activeFilter === f ? 'var(--gold, #C99A5B)' : 'transparent',
                  color: activeFilter === f ? '#101010' : 'var(--text-mid)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {f}
              </button>
            ))}
          </div>

          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="tile"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: '6px',
              background: 'var(--panel)',
              border: '1px solid var(--hair)',
              color: 'var(--text-hi)',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            <RefreshIcon size={13} className={refreshing ? 'spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* TOP SUMMARY STAT TILES */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '12px',
        }}
      >
        <div
          className="tile incident-stat-tile"
          style={{
            padding: '16px',
            background: 'var(--panel)',
            border: '1px solid var(--hair)',
          }}
        >
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Active Insights
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '26px', fontWeight: '700', color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
              {summary?.active ?? 0}
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-mid)' }}>
              active situations
            </span>
          </div>
        </div>

        <div
          className="tile incident-stat-tile"
          style={{
            padding: '16px',
            background: 'var(--panel)',
            border: (summary?.important ?? 0) > 0 ? '1px solid rgba(201, 154, 91, 0.35)' : '1px solid var(--hair)',
          }}
        >
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            High Priority
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '26px', fontWeight: '700', color: (summary?.important ?? 0) > 0 ? 'var(--gold, #C99A5B)' : 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
              {summary?.important ?? 0}
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-mid)' }}>
              important & critical
            </span>
          </div>
        </div>

        <div
          className="tile incident-stat-tile"
          style={{
            padding: '16px',
            background: 'var(--panel)',
            border: (summary?.new ?? 0) > 0 ? '1px solid rgba(201, 154, 91, 0.35)' : '1px solid var(--hair)',
          }}
        >
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            New Detections
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '26px', fontWeight: '700', color: (summary?.new ?? 0) > 0 ? 'var(--gold, #C99A5B)' : 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
              {summary?.new ?? 0}
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-mid)' }}>
              unreviewed
            </span>
          </div>
        </div>

        <div
          className="tile incident-stat-tile"
          style={{
            padding: '16px',
            background: 'var(--panel)',
            border: '1px solid var(--hair)',
          }}
        >
          <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-low)', letterSpacing: '0.06em' }}>
            Resolved
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
            <span style={{ fontSize: '26px', fontWeight: '700', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
              {summary?.resolved ?? 0}
            </span>
            <span style={{ fontSize: '11.5px', color: 'var(--text-low)' }}>
              archived / acknowledged
            </span>
          </div>
        </div>
      </div>

      {/* WHAT CHANGED? SECTION */}
      {whatChanged.length > 0 && (
        <div className="tile" style={{ padding: '18px 20px', background: 'var(--panel)', border: '1px solid var(--hair)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--gold, #C99A5B)' }} />
              <span style={{ fontSize: '13px', fontWeight: '700', letterSpacing: '0.5px', textTransform: 'uppercase', color: 'var(--text-hi)' }}>
                WHAT CHANGED?
              </span>
            </div>
            <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>Live facility baseline comparison</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
            {whatChanged.slice(0, 4).map((wc, idx) => {
              const sigColor =
                wc.significance === 'CRITICAL'
                  ? 'var(--red, #ef4444)'
                  : wc.significance === 'HIGH'
                  ? 'var(--amber, #f59e0b)'
                  : 'var(--gold, #C99A5B)';
              return (
                <div
                  key={idx}
                  className="tile"
                  style={{
                    background: 'var(--panel-hi)',
                    border: `1px solid ${wc.significance === 'CRITICAL' ? 'rgba(239, 68, 68, 0.35)' : 'var(--hair)'}`,
                    borderRadius: '10px',
                    padding: '14px 16px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontWeight: '700', fontSize: '13px', color: 'var(--text-hi)' }}>{wc.zone_name}</span>
                    <span
                      style={{
                        fontSize: '10px',
                        fontWeight: '700',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: `${sigColor}20`,
                        color: sigColor,
                        border: `1px solid ${sigColor}40`,
                      }}
                    >
                      {wc.significance}
                    </span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '11px', marginTop: '6px' }}>
                    <div>
                      <div style={{ color: 'var(--text-low)', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>NORMAL</div>
                      <div style={{ color: 'var(--text-mid)' }}>People: {wc.normal?.people ?? 3}</div>
                      <div style={{ color: 'var(--text-mid)' }}>Activity: {wc.normal?.activity ?? 30}</div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-low)', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>CURRENT</div>
                      <div style={{ color: 'var(--text-hi)', fontWeight: '600' }}>People: {wc.current?.people ?? 0}</div>
                      <div style={{ color: 'var(--text-hi)', fontWeight: '600' }}>Activity: {wc.current?.activity ?? 0}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ASK AI (QWEN) • HELIOS DATABASE INVESTIGATION */}
      <div className="tile" style={{ padding: '18px 20px', background: 'var(--panel)', border: '1px solid var(--hair)' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AiSparklesIcon size={15} style={{ color: 'var(--gold, #C99A5B)' }} />
            <span style={{ fontSize: '13px', fontWeight: '700', letterSpacing: '0.6px', textTransform: 'uppercase', color: 'var(--text-hi)' }}>
              ASK AI (QWEN)
            </span>
            <span style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '4px', background: 'var(--gold-dim, #241B14)', color: 'var(--gold, #C99A5B)', border: '1px solid rgba(201, 154, 91, 0.35)', fontWeight: '600' }}>
              HELIOS Database Grounded
            </span>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>
            Grounded queries across SQLite observations, events, tracks, dwell & evidence
          </span>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleNlSearch();
          }}
          style={{ display: 'flex', gap: '10px', alignItems: 'center' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', flex: 1, background: 'var(--panel-hi)', borderRadius: '8px', border: '1px solid var(--hair)', padding: '0 14px' }}>
            <AiSparklesIcon size={14} style={{ color: 'var(--gold, #C99A5B)', marginRight: '10px' }} />
            <input
              type="text"
              placeholder="Ask AI about HELIOS database evidence... (e.g. 'What happened near East Zone after midnight?', 'Any people walking or loitering?')"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '11px 0',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-hi)',
                fontSize: '13px',
                outline: 'none',
              }}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-low)', cursor: 'pointer' }}
              >
                <CloseIcon size={12} />
              </button>
            )}
          </div>

          <button
            type="submit"
            disabled={isSearching || !searchQuery.trim()}
            style={{
              padding: '11px 20px',
              borderRadius: '8px',
              background: 'var(--gold, #C99A5B)',
              color: '#101010',
              border: 'none',
              fontWeight: '700',
              fontSize: '12px',
              cursor: isSearching || !searchQuery.trim() ? 'not-allowed' : 'pointer',
              opacity: isSearching || !searchQuery.trim() ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            {isSearching ? <RefreshIcon size={13} className="spin" /> : <AiSparklesIcon size={13} />}
            Ask AI
          </button>
        </form>

        {/* Suggested Quick Queries */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '12px' }}>
          {sampleQueries.map((sq, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                setSearchQuery(sq);
                handleNlSearch(sq);
              }}
              style={{
                background: 'var(--panel-hi)',
                border: '1px solid var(--hair)',
                borderRadius: '14px',
                padding: '4px 12px',
                fontSize: '11px',
                color: 'var(--text-mid)',
                cursor: 'pointer',
              }}
            >
              {sq}
            </button>
          ))}
        </div>

        {/* Investigation Result Card with Evidence Snapshots */}
        {investigationResult && (
          <div className="tile" style={{ marginTop: '16px', background: 'var(--panel-hi)', borderRadius: '10px', border: '1px solid rgba(201, 154, 91, 0.3)', padding: '16px 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: '700', color: 'var(--gold, #C99A5B)' }}>
                  <AiSparklesIcon size={12} />
                  QWEN AI INVESTIGATION (HELIOS DATABASE)
                </span>
                <span style={{ fontSize: '9.5px', padding: '1px 6px', borderRadius: '4px', background: 'var(--gold-dim, #241B14)', color: 'var(--gold, #C99A5B)', border: '1px solid rgba(201, 154, 91, 0.3)', fontWeight: '600' }}>
                  {investigationResult.provider || 'ollama:qwen3:4b'}
                </span>
              </div>
              <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                Confidence {Math.round((investigationResult.confidence || 0.9) * 100)}%
              </span>
            </div>

            <p style={{ margin: '0 0 12px 0', fontSize: '13.5px', lineHeight: '1.5', color: 'var(--text-hi)' }}>
              {investigationResult.answer}
            </p>

            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--text-mid)', marginBottom: '4px' }}>
              <span style={{ padding: '2px 8px', borderRadius: '4px', background: 'var(--panel)', border: '1px solid var(--hair)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                <ChartBarIcon size={12} style={{ color: 'var(--gold, #C99A5B)' }} />
                <span><strong>{investigationResult.observation_ids?.length || 0}</strong> Observations</span>
              </span>
              <span style={{ padding: '2px 8px', borderRadius: '4px', background: 'var(--panel)', border: '1px solid var(--hair)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                <BoltIcon size={12} style={{ color: 'var(--gold, #C99A5B)' }} />
                <span><strong>{investigationResult.event_ids?.length || 0}</strong> Events</span>
              </span>
              {investigationResult.insight_ids && investigationResult.insight_ids.length > 0 && (
                <span style={{ padding: '2px 8px', borderRadius: '4px', background: 'var(--panel)', border: '1px solid var(--hair)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                  <BrainIcon size={12} style={{ color: 'var(--gold, #C99A5B)' }} />
                  <span><strong>{investigationResult.insight_ids.length}</strong> Insights</span>
                </span>
              )}
              <span style={{ padding: '2px 8px', borderRadius: '4px', background: 'var(--panel)', border: '1px solid var(--hair)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                <CameraIcon size={12} style={{ color: 'var(--gold, #C99A5B)' }} />
                <span><strong>{investigationResult.camera_ids?.length || 0}</strong> Cameras ({investigationResult.camera_ids?.join(', ') || 'N/A'})</span>
              </span>
            </div>

            {/* Evidence Snapshot Thumbnails for Respected Zone Events */}
            {investigationResult.evidence_snapshots && investigationResult.evidence_snapshots.length > 0 && (
              <div style={{ marginTop: '12px', borderTop: '1px solid var(--hair)', paddingTop: '10px' }}>
                <div style={{ fontSize: '11px', fontWeight: '600', color: 'var(--text-low)', marginBottom: '8px' }}>
                  EVIDENCE SNAPSHOTS (RESPECTED ZONE EVENTS)
                </div>
                <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '4px' }}>
                  {investigationResult.evidence_snapshots.map((snap, sIdx) => {
                    const imgUrl = api.getEvidenceFileUrl(snap.evidence_id);
                    const meta = snap.metadata || {};
                    const detectedCol = meta.detected_color || (meta.upper_color ? `${meta.upper_color}/${meta.lower_color || ''}` : null);
                    return (
                      <div
                        key={sIdx}
                        onClick={() => onSelectTab && onSelectTab('evidence')}
                        className="tile"
                        style={{
                          flex: '0 0 120px',
                          height: '80px',
                          borderRadius: '6px',
                          overflow: 'hidden',
                          background: 'var(--panel)',
                          border: '1px solid var(--hair)',
                          cursor: 'pointer',
                          position: 'relative',
                        }}
                      >
                        <img
                          src={imgUrl}
                          alt="Zone Snapshot"
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={(e) => {
                            e.target.style.display = 'none';
                          }}
                        />
                        <span style={{ position: 'absolute', bottom: '2px', left: '4px', fontSize: '9px', background: 'rgba(0,0,0,0.75)', padding: '1px 4px', borderRadius: '3px', color: '#fff' }}>
                          {snap.type || 'SNAPSHOT'}
                        </span>
                        {detectedCol && (
                          <span style={{ position: 'absolute', top: '2px', right: '4px', fontSize: '8.5px', background: 'var(--gold-dim, #241B14)', border: '1px solid rgba(201, 154, 91, 0.35)', color: 'var(--gold, #C99A5B)', padding: '1px 4px', borderRadius: '3px', fontWeight: '600', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                            <PaletteIcon size={9} />
                            <span>{detectedCol}</span>
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px', marginTop: '14px' }}>
              <button
                onClick={() => onSelectTab && onSelectTab('evidence')}
                className="tile"
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  background: 'var(--panel-hover)',
                  border: '1px solid var(--hair)',
                  color: 'var(--text-hi)',
                  fontSize: '11px',
                  fontWeight: '600',
                  cursor: 'pointer',
                }}
              >
                VIEW EVIDENCE
              </button>
              <button
                onClick={() => onSelectTab && onSelectTab('threads')}
                className="tile"
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  background: 'var(--panel-hover)',
                  border: '1px solid var(--hair)',
                  color: 'var(--text-hi)',
                  fontSize: '11px',
                  fontWeight: '600',
                  cursor: 'pointer',
                }}
              >
                VIEW TIMELINE
              </button>
            </div>
          </div>
        )}

        {searchError && (
          <div style={{ marginTop: '10px', fontSize: '12px', color: 'var(--red, #ef4444)' }}>
            {searchError}
          </div>
        )}
      </div>

      {/* COMPACT INSIGHT CARDS GRID */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: '700', letterSpacing: '0.5px', textTransform: 'uppercase', color: 'var(--text-low)' }}>
            ACTIONABLE OPERATOR FEED ({filteredInsights.length})
          </span>
        </div>

        {loading ? (
          <div className="tile" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-low)', background: 'var(--panel)', border: '1px solid var(--hair)' }}>
            Loading surveillance insights...
          </div>
        ) : filteredInsights.length === 0 ? (
          <div className="tile" style={{ padding: '40px', textAlign: 'center', background: 'var(--panel)', border: '1px solid var(--hair)' }}>
            <div style={{ fontSize: '14px', color: 'var(--text-mid)', marginBottom: '4px' }}>No insights recorded for the selected filter.</div>
            <div style={{ fontSize: '12px', color: 'var(--text-low)' }}>HELIOS continuous monitoring is active.</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '14px' }}>
            {filteredInsights.map((ins) => {
              const pColor = getPriorityColor(ins.priority);
              const sig = ins.signals || {};
              const cams = ins.camera_ids || [];
              const timeDisplay = ins.timestamp ? ins.timestamp.slice(11, 19) : 'recent';
              const trkId = ins.track_ids?.[0] || sig.track_id;
              const zoneId = ins.zone_ids?.[0] || sig.zone_id;
              const reasons = ins.reasoning_factors || sig.anomaly_reasons || [];

              return (
                <div
                  key={ins.insight_id}
                  className="tile"
                  style={{
                    background: 'var(--panel)',
                    borderRadius: '12px',
                    border: `1px solid ${ins.priority === 'CRITICAL' ? 'rgba(239,82,81,0.35)' : 'var(--hair)'}`,
                    padding: '16px 18px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    {/* CARD HEADER */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                        <span
                          style={{
                            fontSize: '10px',
                            fontWeight: '700',
                            padding: '2px 7px',
                            borderRadius: '4px',
                            background: `${pColor}20`,
                            color: pColor,
                            border: `1px solid ${pColor}40`,
                          }}
                        >
                          {ins.priority}
                        </span>
                        {ins.priority === 'CRITICAL' && (
                          <span
                            style={{
                              fontSize: '9.5px',
                              fontWeight: '700',
                              padding: '2px 7px',
                              borderRadius: '4px',
                              background: 'var(--gold-dim, #241B14)',
                              color: 'var(--gold, #C99A5B)',
                              border: '1px solid rgba(201, 154, 91, 0.45)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              letterSpacing: '0.3px',
                            }}
                          >
                            <AiSparklesIcon size={10} />
                            QWEN SYNTHESIS
                          </span>
                        )}
                        <span style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-low)', letterSpacing: '0.5px' }}>
                          {ins.type?.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>{timeDisplay}</span>
                    </div>

                    {/* SHORT SUMMARY */}
                    <p style={{ margin: '0 0 10px 0', fontSize: '13px', lineHeight: '1.45', color: 'var(--text-hi)', fontWeight: '500' }}>
                      {ins.summary}
                    </p>

                    {/* WALKING & COLOR TELEMETRY PILLS */}
                    {(sig.movement_summary || sig.color_summary || (sig.walking_count && sig.walking_count > 0) || sig.primary_color) && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px' }}>
                        {(sig.movement_summary || (sig.walking_count ? `${sig.walking_count} Walking` : null) || sig.primary_movement) && (
                          <span
                            style={{
                              fontSize: '10.5px',
                              fontWeight: '600',
                              padding: '2px 8px',
                              borderRadius: '6px',
                              background: 'var(--panel-hi)',
                              border: '1px solid var(--hair)',
                              color: 'var(--text-hi)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '5px',
                            }}
                          >
                            <WalkingIcon size={12} style={{ color: 'var(--gold, #C99A5B)' }} />
                            <span>{sig.movement_summary || `${sig.walking_count} Walking`}</span>
                          </span>
                        )}
                        {(sig.color_summary || sig.primary_color) && (
                          <span
                            style={{
                              fontSize: '10.5px',
                              fontWeight: '600',
                              padding: '2px 8px',
                              borderRadius: '6px',
                              background: 'var(--panel-hi)',
                              border: '1px solid rgba(201, 154, 91, 0.3)',
                              color: 'var(--gold, #C99A5B)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '5px',
                            }}
                          >
                            <PaletteIcon size={12} />
                            <span>{sig.color_summary || sig.primary_color}</span>
                          </span>
                        )}
                      </div>
                    )}

                    {/* EVIDENCE SNAPSHOTS MINI STRIP */}
                    {sig.evidence_snapshots && sig.evidence_snapshots.length > 0 && (
                      <div style={{ marginBottom: '10px' }}>
                        <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '2px' }}>
                          {sig.evidence_snapshots.slice(0, 3).map((snap, sIdx) => {
                            const imgUrl = api.getEvidenceFileUrl(snap.evidence_id);
                            const mov = snap.movement || {};
                            const col = snap.colors || {};
                            return (
                              <div
                                key={sIdx}
                                onClick={() => setSelectedInsight(ins)}
                                className="tile"
                                style={{
                                  flex: '0 0 92px',
                                  height: '58px',
                                  borderRadius: '6px',
                                  position: 'relative',
                                  overflow: 'hidden',
                                  background: 'var(--panel-hi)',
                                  border: '1px solid var(--hair)',
                                  cursor: 'pointer',
                                }}
                              >
                                <img
                                  src={imgUrl}
                                  alt="Snapshot"
                                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                  onError={(e) => { e.target.style.display = 'none'; }}
                                />
                                {mov.movement_state && (
                                  <span
                                    style={{
                                      position: 'absolute',
                                      top: '2px',
                                      left: '2px',
                                      fontSize: '8px',
                                      fontWeight: '700',
                                      background: 'rgba(0,0,0,0.8)',
                                      color: '#fff',
                                      padding: '1px 4px',
                                      borderRadius: '3px',
                                    }}
                                  >
                                    {mov.movement_state}
                                  </span>
                                )}
                                {col.primary_color && (
                                  <span
                                    style={{
                                      position: 'absolute',
                                      bottom: '2px',
                                      right: '2px',
                                      fontSize: '8px',
                                      fontWeight: '700',
                                      background: 'rgba(36, 27, 20, 0.9)',
                                      color: 'var(--gold, #C99A5B)',
                                      padding: '1px 4px',
                                      borderRadius: '3px',
                                      border: '1px solid rgba(201, 154, 91, 0.3)',
                                    }}
                                  >
                                    {col.primary_color}
                                  </span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* METRIC COMPARISONS */}
                    <div style={{ background: 'var(--panel-hi)', border: '1px solid var(--hair-soft)', borderRadius: '8px', padding: '10px 12px', marginBottom: '12px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {sig.people_delta && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-low)', textTransform: 'uppercase' }}>PEOPLE</span>
                          <span style={{ fontWeight: '600', color: 'var(--text-hi)' }}>{sig.people_delta}</span>
                        </div>
                      )}
                      {sig.dwell_delta && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-low)', textTransform: 'uppercase' }}>DURATION</span>
                          <span style={{ fontWeight: '600', color: 'var(--text-hi)' }}>{sig.dwell_delta}</span>
                        </div>
                      )}
                      {sig.duration_seconds && !sig.dwell_delta && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-low)', textTransform: 'uppercase' }}>DURATION</span>
                          <span style={{ fontWeight: '600', color: 'var(--text-hi)' }}>{Math.round(sig.duration_seconds)}s</span>
                        </div>
                      )}
                      {cams.length > 0 && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-low)', textTransform: 'uppercase' }}>CAMERAS</span>
                          <span style={{ fontWeight: '600', color: 'var(--text-hi)' }}>{cams.join(' → ')}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* CARD FOOTER WITH CONFIDENCE & ACTIONS */}
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                        Confidence {Math.round((ins.confidence || 0.9) * 100)}%
                      </span>

                      {/* OPERATOR FEEDBACK BUTTONS */}
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                          onClick={() => handleFeedback(ins.insight_id, 'CONFIRM')}
                          title="Confirm insight"
                          style={{
                            padding: '3px 8px',
                            borderRadius: '4px',
                            background: ins.status === 'ACKNOWLEDGED' ? 'rgba(47, 204, 139, 0.2)' : 'var(--panel-hi)',
                            color: ins.status === 'ACKNOWLEDGED' ? 'var(--green)' : 'var(--text-mid)',
                            border: '1px solid var(--hair)',
                            fontSize: '10px',
                            cursor: 'pointer',
                          }}
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => handleFeedback(ins.insight_id, 'DISMISS')}
                          title="Dismiss insight"
                          style={{
                            padding: '3px 8px',
                            borderRadius: '4px',
                            background: ins.status === 'RESOLVED' ? 'rgba(239, 82, 81, 0.2)' : 'var(--panel-hi)',
                            color: ins.status === 'RESOLVED' ? 'var(--red)' : 'var(--text-mid)',
                            border: '1px solid var(--hair)',
                            fontSize: '10px',
                            cursor: 'pointer',
                          }}
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '6px', borderTop: '1px solid var(--hair)', paddingTop: '10px' }}>
                      <button
                        onClick={() => setSelectedInsight(ins)}
                        className="tile"
                        style={{
                          flex: 1,
                          padding: '6px',
                          borderRadius: '6px',
                          background: 'var(--panel-hi)',
                          border: '1px solid var(--hair)',
                          color: 'var(--text-hi)',
                          fontSize: '11px',
                          fontWeight: '600',
                          cursor: 'pointer',
                        }}
                      >
                        View Details
                      </button>
                      <button
                        onClick={() => onSelectTab && onSelectTab('evidence')}
                        className="tile"
                        style={{
                          padding: '6px 10px',
                          borderRadius: '6px',
                          background: 'var(--panel-hi)',
                          border: '1px solid var(--hair)',
                          color: 'var(--text-mid)',
                          fontSize: '11px',
                          cursor: 'pointer',
                        }}
                      >
                        Evidence
                      </button>
                      <button
                        onClick={() => onSelectTab && onSelectTab('threads')}
                        className="tile"
                        style={{
                          padding: '6px 10px',
                          borderRadius: '6px',
                          background: 'var(--panel-hi)',
                          border: '1px solid var(--hair)',
                          color: 'var(--text-mid)',
                          fontSize: '11px',
                          cursor: 'pointer',
                        }}
                      >
                        Timeline
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* INSIGHT DETAILS MODAL */}
      {selectedInsight && (() => {
        const sig = selectedInsight.signals || {};
        const qwen = sig.qwen_analysis;
        const movIntel = sig.movement_intel || [];
        const colIntel = sig.color_intel || [];
        const snapshots = sig.evidence_snapshots || [];

        return (
          <div
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.82)',
              backdropFilter: 'blur(6px)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 999,
              padding: '20px',
            }}
            onClick={() => setSelectedInsight(null)}
          >
            <div
              className="tile helios-modal-card"
              style={{
                background: 'var(--panel-hi)',
                borderRadius: '14px',
                border: '1px solid var(--hair)',
                width: '100%',
                maxWidth: '620px',
                maxHeight: '90vh',
                overflowY: 'auto',
                padding: '24px',
                position: 'relative',
                boxShadow: '0 24px 60px rgba(0,0,0,0.85)',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', borderBottom: '1px solid var(--hair)', paddingBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: '700',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      background: `${getPriorityColor(selectedInsight.priority)}25`,
                      color: getPriorityColor(selectedInsight.priority),
                    }}
                  >
                    {selectedInsight.priority}
                  </span>
                  {selectedInsight.priority === 'CRITICAL' && (
                    <span
                      style={{
                        fontSize: '10px',
                        fontWeight: '700',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: 'var(--gold-dim, #241B14)',
                        color: 'var(--gold, #C99A5B)',
                        border: '1px solid rgba(201, 154, 91, 0.45)',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <AiSparklesIcon size={11} />
                      QWEN AI SYNTHESIS
                    </span>
                  )}
                  <span style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-hi)' }}>
                    {selectedInsight.type?.replace('_', ' ')}
                  </span>
                </div>
                <button
                  onClick={() => setSelectedInsight(null)}
                  style={{ background: 'transparent', border: 'none', color: 'var(--text-low)', cursor: 'pointer' }}
                >
                  <CloseIcon size={16} />
                </button>
              </div>

              {/* 1. WHAT HAPPENED? */}
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--gold, #C99A5B)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '4px' }}>
                  WHAT HAPPENED?
                </div>
                <p style={{ margin: 0, fontSize: '14px', lineHeight: '1.5', color: 'var(--text-hi)' }}>
                  {selectedInsight.summary}
                </p>
              </div>

              {/* INSIGHT 7-SIGNAL COMPOSITE PRIORITY SCORE BREAKDOWN */}
              {sig.score_breakdown && (() => {
                const bd = sig.score_breakdown || {};
                const compScore = selectedInsight.score || Math.round(bd.raw_score || 0);
                const factors = [
                  { label: 'Anomaly Deviation', weight: '25%', val: bd.anomaly ?? 0 },
                  { label: 'Temporal Persistence', weight: '20%', val: bd.persistence ?? 0 },
                  { label: 'Spatial Significance', weight: '15%', val: bd.spatial_significance ?? 0 },
                  { label: 'Cross-Camera Correlation', weight: '15%', val: bd.cross_camera_correlation ?? 0 },
                  { label: 'Density / Activity Shift', weight: '10%', val: bd.density_activity_change ?? 0 },
                  { label: 'Incident Relevance', weight: '10%', val: bd.incident_relevance ?? 0 },
                  { label: 'Camera Sensor Reliability', weight: '5%', val: bd.camera_reliability ?? 100 },
                ];

                return (
                  <div
                    className="tile"
                    style={{
                      marginBottom: '16px',
                      background: 'var(--panel)',
                      border: '1px solid rgba(201, 154, 91, 0.4)',
                      borderRadius: '10px',
                      padding: '16px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <ChartBarIcon size={16} style={{ color: 'var(--gold, #C99A5B)' }} />
                        <span style={{ fontSize: '13px', fontWeight: '800', color: 'var(--gold, #C99A5B)', letterSpacing: '0.5px' }}>
                          7-SIGNAL PRIORITY SCORE: {compScore} / 100
                        </span>
                      </div>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: '700',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          background: `${getPriorityColor(selectedInsight.priority)}25`,
                          color: getPriorityColor(selectedInsight.priority),
                        }}
                      >
                        {selectedInsight.priority}
                      </span>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '9px' }}>
                      {factors.map((f, fIdx) => (
                        <div key={fIdx} style={{ fontSize: '11px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '3px', color: 'var(--text-hi)' }}>
                            <span>
                              <strong>{f.label}</strong> <span style={{ color: 'var(--text-low)', fontSize: '10px' }}>({f.weight})</span>
                            </span>
                            <span style={{ fontWeight: '700', color: f.val >= 50 ? 'var(--red, #ef4444)' : f.val >= 25 ? 'var(--amber, #f59e0b)' : 'var(--gold, #C99A5B)' }}>
                              {Math.round(f.val)} / 100
                            </span>
                          </div>
                          <div style={{ width: '100%', height: '5px', background: 'var(--panel-hi)', borderRadius: '3px', overflow: 'hidden' }}>
                            <div
                              style={{
                                width: `${Math.max(2, Math.min(100, f.val))}%`,
                                height: '100%',
                                background: f.val >= 75 ? 'var(--red, #ef4444)' : f.val >= 40 ? 'var(--amber, #f59e0b)' : 'var(--gold, #C99A5B)',
                                borderRadius: '3px',
                                transition: 'width 0.3s ease',
                              }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* NORMAL VS CURRENT COMPARISON */}
              {(selectedInsight.baseline_comparison || sig.baseline_comparison || sig.people_delta || sig.dwell_delta) && (() => {
                const bcomp = selectedInsight.baseline_comparison || sig.baseline_comparison || {};
                const act = sig.activity_density || {};

                return (
                  <div style={{ marginBottom: '16px' }}>
                    <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--gold, #C99A5B)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '6px' }}>
                      NORMAL VS CURRENT COMPARISON
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '8px' }}>
                      <div className="tile" style={{ background: 'var(--panel)', border: '1px solid var(--hair)', borderRadius: '8px', padding: '10px', fontSize: '11px' }}>
                        <div style={{ color: 'var(--text-low)', textTransform: 'uppercase', fontSize: '10px', marginBottom: '4px' }}>Dwell Time</div>
                        <div style={{ color: 'var(--text-hi)', fontWeight: '600' }}>
                          {sig.dwell_delta || bcomp.dwell_delta || `${bcomp.normal_dwell_seconds || 25}s → ${Math.round(sig.dwell_seconds || sig.duration_seconds || 0)}s`}
                        </div>
                      </div>
                      <div className="tile" style={{ background: 'var(--panel)', border: '1px solid var(--hair)', borderRadius: '8px', padding: '10px', fontSize: '11px' }}>
                        <div style={{ color: 'var(--text-low)', textTransform: 'uppercase', fontSize: '10px', marginBottom: '4px' }}>People Density</div>
                        <div style={{ color: 'var(--text-hi)', fontWeight: '600' }}>
                          {sig.people_delta || bcomp.people_delta || `${bcomp.normal_people_count || 3} → ${act.people_count || sig.people_count || 1} people`}
                        </div>
                      </div>
                      <div className="tile" style={{ background: 'var(--panel)', border: '1px solid var(--hair)', borderRadius: '8px', padding: '10px', fontSize: '11px' }}>
                        <div style={{ color: 'var(--text-low)', textTransform: 'uppercase', fontSize: '10px', marginBottom: '4px' }}>Zone Capacity</div>
                        <div style={{ color: 'var(--text-hi)', fontWeight: '600' }}>
                          {sig.capacity ? `${sig.capacity} max (${act.status || 'NORMAL'})` : act.capacity ? `${act.capacity} max` : 'Within limits'}
                        </div>
                      </div>
                      <div className="tile" style={{ background: 'var(--panel)', border: '1px solid var(--hair)', borderRadius: '8px', padding: '10px', fontSize: '11px' }}>
                        <div style={{ color: 'var(--text-low)', textTransform: 'uppercase', fontSize: '10px', marginBottom: '4px' }}>Time Schedule</div>
                        <div style={{ color: bcomp.is_off_hours ? 'var(--amber, #f59e0b)' : 'var(--text-hi)', fontWeight: '600' }}>
                          {bcomp.is_off_hours ? 'Off-Hours Window' : 'Normal Operating Hours'}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* 2. CRITICAL AI SYNTHESIS (QWEN) */}
              {(selectedInsight.priority === 'CRITICAL' || qwen) && (
                <div
                  className="tile"
                  style={{
                    marginBottom: '16px',
                    background: 'var(--panel)',
                    border: '1px solid rgba(201, 154, 91, 0.35)',
                    borderRadius: '10px',
                    padding: '14px 16px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: '700', color: 'var(--gold, #C99A5B)' }}>
                      <AiSparklesIcon size={12} />
                      CRITICAL INTELLIGENCE SYNTHESIS (QWEN)
                    </div>
                    <span style={{ fontSize: '10px', color: 'var(--text-low)', textTransform: 'uppercase' }}>
                      {qwen?.provider || 'ollama:qwen3:4b'}
                    </span>
                  </div>

                  {qwen?.movement_summary && (
                    <div style={{ marginBottom: '8px', fontSize: '12px' }}>
                      <span style={{ color: 'var(--text-low)', fontWeight: '600', textTransform: 'uppercase', fontSize: '10px' }}>
                        Movement & Pacing:
                      </span>
                      <span style={{ color: 'var(--text-hi)', marginLeft: '6px' }}>
                        {qwen.movement_summary}
                      </span>
                    </div>
                  )}

                  {qwen?.color_summary && (
                    <div style={{ fontSize: '12px' }}>
                      <span style={{ color: 'var(--text-low)', fontWeight: '600', textTransform: 'uppercase', fontSize: '10px' }}>
                        Attire & Colors:
                      </span>
                      <span style={{ color: 'var(--gold, #C99A5B)', marginLeft: '6px' }}>
                        {qwen.color_summary}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* 3. WALKING & MOVEMENT TELEMETRY */}
              {(movIntel.length > 0 || sig.movement_summary) && (
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-low)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '6px' }}>
                    WALKING & MOVEMENT TELEMETRY
                  </div>
                  {movIntel.length > 0 ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '8px' }}>
                      {movIntel.map((m, mIdx) => (
                        <div
                          key={mIdx}
                          className="tile"
                          style={{
                            background: 'var(--panel)',
                            border: '1px solid var(--hair)',
                            borderRadius: '8px',
                            padding: '10px',
                            fontSize: '11px',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <span style={{ fontWeight: '700', color: 'var(--gold, #C99A5B)' }}>Track #{m.track_id}</span>
                            <span style={{ fontWeight: '600', color: 'var(--text-hi)' }}>{m.movement_state}</span>
                          </div>
                          <div style={{ color: 'var(--text-mid)', fontSize: '10.5px' }}>
                            Speed: <strong>{m.speed} m/s</strong>
                          </div>
                          <div style={{ color: 'var(--text-mid)', fontSize: '10.5px' }}>
                            Direction: <strong>{m.direction}</strong>
                          </div>
                          <div style={{ color: 'var(--text-mid)', fontSize: '10.5px' }}>
                            Dwell: <strong>{m.dwell_seconds}s</strong>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--hair)', padding: '10px 12px', fontSize: '12px', color: 'var(--text-hi)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <WalkingIcon size={14} style={{ color: 'var(--gold, #C99A5B)', flexShrink: 0 }} />
                      <span>{sig.movement_summary}</span>
                    </div>
                  )}
                </div>
              )}

              {/* 4. EVIDENCE APPEARANCE & COLORS */}
              {(colIntel.length > 0 || sig.color_summary) && (
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-low)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '6px' }}>
                    EVIDENCE APPEARANCE & COLORS
                  </div>
                  {colIntel.length > 0 ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px' }}>
                      {colIntel.map((c, cIdx) => (
                        <div
                          key={cIdx}
                          className="tile"
                          style={{
                            background: 'var(--panel)',
                            border: '1px solid var(--hair)',
                            borderRadius: '8px',
                            padding: '10px',
                            fontSize: '11px',
                          }}
                        >
                          <div style={{ fontWeight: '700', color: 'var(--text-hi)', marginBottom: '4px' }}>
                            {c.class_name || 'SUBJECT'}
                          </div>
                          {c.upper_color && (
                            <div style={{ color: 'var(--text-mid)', fontSize: '10.5px' }}>
                              Upper: <strong style={{ color: 'var(--text-hi)' }}>{c.upper_color}</strong>
                            </div>
                          )}
                          {c.lower_color && (
                            <div style={{ color: 'var(--text-mid)', fontSize: '10.5px' }}>
                              Lower: <strong style={{ color: 'var(--text-hi)' }}>{c.lower_color}</strong>
                            </div>
                          )}
                          <div style={{ color: 'var(--gold, #C99A5B)', fontSize: '10.5px', marginTop: '2px' }}>
                            Primary: {c.primary_color || 'Neutral'}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--hair)', padding: '10px 12px', fontSize: '12px', color: 'var(--gold, #C99A5B)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <PaletteIcon size={14} style={{ color: 'var(--gold, #C99A5B)', flexShrink: 0 }} />
                      <span>{sig.color_summary}</span>
                    </div>
                  )}
                </div>
              )}

              {/* 5. EVIDENCE SNAPSHOTS GALLERY */}
              {snapshots.length > 0 && (
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-low)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '6px' }}>
                    EVIDENCE SNAPSHOTS ({snapshots.length})
                  </div>
                  <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '4px' }}>
                    {snapshots.map((snap, sIdx) => {
                      const imgUrl = api.getEvidenceFileUrl(snap.evidence_id);
                      const mov = snap.movement || {};
                      const col = snap.colors || {};
                      return (
                        <div
                          key={sIdx}
                          className="tile"
                          style={{
                            flex: '0 0 130px',
                            height: '84px',
                            borderRadius: '8px',
                            position: 'relative',
                            overflow: 'hidden',
                            background: 'var(--panel)',
                            border: '1px solid var(--hair)',
                          }}
                        >
                          <img
                            src={imgUrl}
                            alt="Snapshot"
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            onError={(e) => { e.target.style.display = 'none'; }}
                          />
                          {mov.movement_state && (
                            <span
                              style={{
                                position: 'absolute',
                                top: '3px',
                                left: '3px',
                                fontSize: '8.5px',
                                fontWeight: '700',
                                background: 'rgba(0,0,0,0.85)',
                                color: '#fff',
                                padding: '1px 5px',
                                borderRadius: '3px',
                              }}
                            >
                              {mov.movement_state}
                            </span>
                          )}
                          {col.primary_color && (
                            <span
                              style={{
                                position: 'absolute',
                                bottom: '3px',
                                right: '3px',
                                fontSize: '8.5px',
                                fontWeight: '700',
                                background: 'rgba(36, 27, 20, 0.92)',
                                color: 'var(--gold, #C99A5B)',
                                padding: '1px 5px',
                                borderRadius: '3px',
                                border: '1px solid rgba(201, 154, 91, 0.35)',
                              }}
                            >
                              {col.primary_color}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* 6. WHY? */}
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--gold, #C99A5B)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '6px' }}>
                  WHY?
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {(selectedInsight.reasoning_factors && selectedInsight.reasoning_factors.length > 0
                    ? selectedInsight.reasoning_factors
                    : ['Telemetry deviation observed above site baseline.', 'Sustained presence recorded by surveillance engine.']
                  ).map((rf, idx) => (
                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text-mid)' }}>
                      <span style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--gold, #C99A5B)' }} />
                      {rf}
                    </div>
                  ))}
                </div>
              </div>

              {/* 7. WHERE / WHEN? */}
              <div style={{ marginBottom: '18px' }}>
                <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-low)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '6px' }}>
                  WHERE / WHEN?
                </div>
                <div style={{ background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--hair)', padding: '12px 14px', fontSize: '12px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                  <div>
                    <span style={{ color: 'var(--text-low)' }}>Zone: </span>
                    <span style={{ color: 'var(--text-hi)', fontWeight: '600' }}>{selectedInsight.zone_ids?.join(', ') || sig.zone_id || 'Facility Area'}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-low)' }}>Camera: </span>
                    <span style={{ color: 'var(--text-hi)', fontWeight: '600' }}>{selectedInsight.camera_ids?.join(', ') || sig.camera_id || 'N/A'}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-low)' }}>Track ID: </span>
                    <span style={{ color: 'var(--gold, #C99A5B)', fontWeight: '700' }}>
                      {selectedInsight.track_ids?.[0] ? `#${selectedInsight.track_ids[0]}` : sig.track_id ? `#${sig.track_id}` : 'N/A'}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-low)' }}>Timestamp: </span>
                    <span style={{ color: 'var(--text-hi)' }}>{selectedInsight.timestamp?.slice(11, 19) || 'N/A'}</span>
                  </div>
                  {sig.movement_state && (
                    <div>
                      <span style={{ color: 'var(--text-low)' }}>Movement: </span>
                      <span style={{ color: 'var(--text-hi)', fontWeight: '600' }}>{sig.movement_state}</span>
                    </div>
                  )}
                  {sig.speed !== undefined && (
                    <div>
                      <span style={{ color: 'var(--text-low)' }}>Speed & Direction: </span>
                      <span style={{ color: 'var(--text-hi)', fontWeight: '600' }}>{sig.speed} px/s ({sig.direction || 'STATIONARY'})</span>
                    </div>
                  )}
                  {(sig.dwell_seconds || sig.duration_seconds) && (
                    <div>
                      <span style={{ color: 'var(--text-low)' }}>Dwell Duration: </span>
                      <span style={{ color: 'var(--text-hi)', fontWeight: '600' }}>{Math.round(sig.dwell_seconds || sig.duration_seconds)}s</span>
                    </div>
                  )}
                  {sig.related_cameras && sig.related_cameras.length > 0 && (
                    <div>
                      <span style={{ color: 'var(--text-low)' }}>Related Cameras: </span>
                      <span style={{ color: 'var(--text-hi)', fontWeight: '600' }}>{sig.related_cameras.join(' → ')}</span>
                    </div>
                  )}
                  <div>
                    <span style={{ color: 'var(--text-low)' }}>Status: </span>
                    <span style={{ color: 'var(--text-hi)', fontWeight: '600' }}>{selectedInsight.status}</span>
                  </div>
                </div>
              </div>

              {/* 8. EVIDENCE BUTTONS */}
              <div>
                <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-low)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '8px' }}>
                  EVIDENCE & AUDIT CHAIN
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                  <button
                    onClick={() => {
                      setSelectedInsight(null);
                      onSelectTab && onSelectTab('evidence');
                    }}
                    style={{
                      padding: '9px',
                      borderRadius: '6px',
                      background: 'var(--gold, #C99A5B)',
                      color: '#101010',
                      border: 'none',
                      fontSize: '12px',
                      fontWeight: '700',
                      cursor: 'pointer',
                    }}
                  >
                    VIEW EVIDENCE
                  </button>
                  <button
                    onClick={() => {
                      setSelectedInsight(null);
                      onSelectTab && onSelectTab('threads');
                    }}
                    className="tile"
                    style={{
                      padding: '9px',
                      borderRadius: '6px',
                      background: 'var(--panel)',
                      color: 'var(--text-hi)',
                      border: '1px solid var(--hair)',
                      fontSize: '12px',
                      fontWeight: '600',
                      cursor: 'pointer',
                    }}
                  >
                    VIEW TIMELINE
                  </button>
                  <button
                    onClick={() => {
                      setSelectedInsight(null);
                      onSelectTab && onSelectTab('events');
                    }}
                    className="tile"
                    style={{
                      padding: '9px',
                      borderRadius: '6px',
                      background: 'var(--panel)',
                      color: 'var(--text-hi)',
                      border: '1px solid var(--hair)',
                      fontSize: '12px',
                      fontWeight: '600',
                      cursor: 'pointer',
                    }}
                  >
                    VIEW EVENTS
                  </button>
                  <button
                    onClick={() => {
                      setSelectedInsight(null);
                      onSelectTab && onSelectTab('feeds');
                    }}
                    className="tile"
                    style={{
                      padding: '9px',
                      borderRadius: '6px',
                      background: 'var(--panel)',
                      color: 'var(--text-hi)',
                      border: '1px solid var(--hair)',
                      fontSize: '12px',
                      fontWeight: '600',
                      cursor: 'pointer',
                    }}
                  >
                    VIEW CAMERAS
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
