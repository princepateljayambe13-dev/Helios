import { useState } from 'react';
import { api } from '../services/api';
import { TableRowSkeleton } from './SkeletonLoader';
import { AiSparklesIcon } from './Icons';

export function EventsView({
  events = [],
  onInvestigate,
  onSelectTab,
  onRefresh,
  loading = false,
  eventsCategory = 'all',
  onSelectCategory,
  isZoneEvent,
}) {
  const [filterSeverity, setFilterSeverity] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [clearing, setClearing] = useState(false);

  const checkIsZone = (e) => {
    if (typeof isZoneEvent === 'function') return isZoneEvent(e);
    return Boolean(
      e.zone_id ||
      e.attributes?.zone_id ||
      (e.event_type && (e.event_type.includes('ZONE') || e.event_type === 'INTRUSION')) ||
      (e.description && (e.description.toLowerCase().includes('zone') || e.description.toLowerCase().includes('perimeter')))
    );
  };

  const trackedCount = events.filter((e) => Boolean(e.track_id)).length;
  const zoneCount = events.filter(checkIsZone).length;

  const categoryEvents = events.filter((e) => {
    if (eventsCategory === 'tracked') return Boolean(e.track_id);
    if (eventsCategory === 'zone') return checkIsZone(e);
    return true;
  });

  const handleClearHistory = async () => {
    if (!window.confirm('Clear all event history and linked alerts?')) return;
    setClearing(true);
    try {
      await api.clearEventsHistory(true);
      if (onRefresh) onRefresh();
    } catch (err) {
      alert(`Failed to clear event history: ${err.message}`);
    } finally {
      setClearing(false);
    }
  };

  const filteredEvents = categoryEvents.filter((e) => {
    if (filterSeverity !== 'ALL' && e.severity !== filterSeverity) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      const matchId = e.event_id?.toLowerCase().includes(q);
      const matchDesc = (e.description || e.event_type || '')?.toLowerCase().includes(q);
      const matchCam = e.camera_id?.toLowerCase().includes(q);
      const matchTrack = e.track_id?.toLowerCase().includes(q);
      const matchZone = (e.zone_id || e.attributes?.zone_id || '')?.toLowerCase().includes(q);
      const vi = e.attributes?.vehicle_intelligence;
      const matchVi = vi
        ? (vi.type?.toLowerCase().includes(q) ||
           vi.color?.toLowerCase().includes(q) ||
           vi.vehicle_id?.toLowerCase().includes(q))
        : false;
      if (!matchId && !matchDesc && !matchCam && !matchTrack && !matchZone && !matchVi) return false;
    }
    return true;
  });

  const getSubTitle = () => {
    if (eventsCategory === 'tracked') {
      return `Target track trajectory events (${filteredEvents.length} / ${trackedCount} logged)`;
    }
    if (eventsCategory === 'zone') {
      return `Perimeter and polygon zone boundary events (${filteredEvents.length} / ${zoneCount} logged)`;
    }
    return `Operational surveillance events and detected threats (${filteredEvents.length} / ${events.length} logged)`;
  };

  return (
    <div>
      {/* Event Category Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        {[
          { id: 'all', label: 'All events', count: events.length },
          { id: 'tracked', label: 'Tracked events', count: trackedCount },
          { id: 'zone', label: 'Zone events', count: zoneCount },
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

      <div className="section-head" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2>
            {eventsCategory === 'tracked'
              ? 'Tracked Events'
              : eventsCategory === 'zone'
              ? 'Zone Events'
              : 'Security Events'}
          </h2>
          <span className="section-sub">
            {getSubTitle()}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="Filter events, camera, track..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              background: '#0a0a0a',
              border: '1px solid var(--hair)',
              borderRadius: '6px',
              padding: '4px 10px',
              color: 'var(--text-hi)',
              fontSize: '11.5px',
              outline: 'none',
              minWidth: '150px',
              flex: '1 1 180px',
            }}
          />
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'INFO'].map((sev) => (
            <button
              key={sev}
              className="n-btn"
              style={{
                background: filterSeverity === sev ? 'var(--panel-hover)' : 'var(--panel-hi)',
                color: filterSeverity === sev ? 'var(--text-hi)' : 'var(--text-mid)',
              }}
              onClick={() => setFilterSeverity(sev)}
            >
              {sev}
            </button>
          ))}
          <button
            className="n-btn"
            style={{ background: 'var(--red-dim)', color: 'var(--red)', borderColor: 'rgba(239,82,81,0.3)', marginLeft: '4px' }}
            disabled={clearing || events.length === 0}
            onClick={handleClearHistory}
          >
            {clearing ? 'Clearing...' : 'Clear Events'}
          </button>
        </div>
      </div>

      <div className="tile" style={{ overflow: 'hidden' }}>
        <div className="table-responsive table-scroll-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Description / Target</th>
                <th>Camera</th>
                <th>Severity</th>
                <th>Time</th>
                <th>Confidence</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && events.length === 0 ? (
                <TableRowSkeleton columns={7} rows={6} />
              ) : filteredEvents.length > 0 ? (
                filteredEvents.map((e) => (
                  <tr key={e.event_id}>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '11px' }}>{e.event_id}</td>
                    <td>
                      <b style={{ color: 'var(--text-hi)' }}>{e.description || e.event_type}</b>
                      {e.attributes?.vehicle_intelligence && (
                        <div style={{ display: 'flex', gap: '4px', marginTop: '4px', flexWrap: 'wrap' }}>
                          {e.attributes.vehicle_intelligence.color && (
                            <span
                              className="n-chip"
                              style={{
                                fontSize: '10px',
                                padding: '1px 5px',
                                background: 'rgba(201, 154, 91, 0.12)',
                                color: 'var(--gold)',
                                borderColor: 'rgba(201, 154, 91, 0.3)',
                              }}
                            >
                              {e.attributes.vehicle_intelligence.color.toUpperCase()}
                              {e.attributes.vehicle_intelligence.color_confidence ? ` (${Math.round(e.attributes.vehicle_intelligence.color_confidence * 100)}%)` : ''}
                            </span>
                          )}
                          {e.attributes.vehicle_intelligence.type && (
                            <span
                              className="n-chip"
                              style={{
                                fontSize: '10px',
                                padding: '1px 5px',
                                background: 'rgba(160, 125, 90, 0.12)',
                                color: '#D5B18A',
                                borderColor: 'rgba(160, 125, 90, 0.3)',
                              }}
                            >
                              {e.attributes.vehicle_intelligence.type.toUpperCase()}
                              {e.attributes.vehicle_intelligence.type_confidence ? ` (${Math.round(e.attributes.vehicle_intelligence.type_confidence * 100)}%)` : ''}
                            </span>
                          )}
                        </div>
                      )}
                      <div style={{ fontSize: '11px', color: 'var(--text-low)', marginTop: '2px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <span>
                          Track:{' '}
                          {e.track_id ? (
                            <span
                              style={{
                                color: 'var(--gold)',
                                cursor: 'pointer',
                                textDecoration: 'underline',
                              }}
                              onClick={() => onSelectTab && onSelectTab('threads', e.track_id)}
                              title="Open Activity Story"
                            >
                              {e.track_id}
                            </span>
                          ) : (
                            '—'
                          )}
                        </span>
                        {e.zone_id && (
                          <span>
                            Zone:{' '}
                            <span
                              style={{
                                color: 'var(--text-hi)',
                                cursor: onSelectTab ? 'pointer' : 'default',
                                textDecoration: 'underline',
                                fontFamily: 'var(--mono)',
                              }}
                              onClick={() => onSelectTab && onSelectTab('fencing')}
                              title="Open Perimeter Fencing"
                            >
                              {e.zone_id}
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span
                        style={{
                          color: 'var(--text-hi)',
                          cursor: onSelectTab ? 'pointer' : 'default',
                          textDecoration: 'underline',
                        }}
                        onClick={() => onSelectTab && onSelectTab('feeds')}
                        title="Jump to live feeds"
                      >
                        {e.camera_id}
                      </span>
                    </td>
                    <td>
                      <span
                        className="n-chip"
                        style={{
                          display: 'inline-flex',
                          background:
                            e.severity === 'CRITICAL'
                              ? 'var(--red-dim)'
                              : e.severity === 'HIGH'
                              ? 'var(--orange-dim)'
                              : 'var(--panel-hi)',
                          color:
                            e.severity === 'CRITICAL'
                              ? 'var(--red)'
                              : e.severity === 'HIGH'
                              ? 'var(--orange)'
                              : 'var(--text-mid)',
                        }}
                      >
                        {e.severity}
                      </span>
                    </td>
                    <td style={{ fontSize: '11.5px', color: 'var(--text-mid)', whiteSpace: 'nowrap' }}>
                      {e.timestamp ? new Date(e.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                    </td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '11.5px' }}>
                      {e.confidence ? `${Math.round(e.confidence * 100)}%` : '—'}
                    </td>
                    <td>
                      <button
                        className="n-btn ai-investigate"
                        style={{ fontSize: '10.5px', padding: '2px 8px' }}
                        onClick={() => onInvestigate && onInvestigate(e)}
                        title="Investigate with AI"
                      >
                        <AiSparklesIcon size={11} />
                        <span>Investigate AI</span>
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-low)' }}>
                    {eventsCategory === 'tracked'
                      ? 'No tracked events match the selected criteria.'
                      : eventsCategory === 'zone'
                      ? 'No zone perimeter events match the selected criteria.'
                      : 'No events match the selected filter.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
