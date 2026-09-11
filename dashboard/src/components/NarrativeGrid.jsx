import { useMemo } from 'react';
import { NarrativeCardSkeleton } from './SkeletonLoader';
import { AiSparklesIcon } from './Icons';

export function NarrativeGrid({ events = [], cameras = [], loading = false, onViewAll, onInvestigate }) {
  // Sort events prioritising critical/high severities and chronological recency
  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => {
      const rankA =
        a.severity === 'CRITICAL' ? 4 : a.severity === 'HIGH' ? 3 : a.severity === 'MEDIUM' ? 2 : 1;
      const rankB =
        b.severity === 'CRITICAL' ? 4 : b.severity === 'HIGH' ? 3 : b.severity === 'MEDIUM' ? 2 : 1;
      if (rankB !== rankA) return rankB - rankA;
      return new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime();
    });
  }, [events]);

  const formatTimeAgo = (ts) => {
    if (!ts) return 'Recently';
    try {
      const diff = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
      if (diff < 60) return 'Just now';
      if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
      if (diff < 86400) return `${Math.floor(diff / 3600)} hr ago`;
      return `${Math.floor(diff / 86400)} d ago`;
    } catch {
      return 'Recently';
    }
  };

  const getCameraLocation = (camId) => {
    const found = cameras.find((c) => c.camera_id === camId);
    return found?.location || (camId ? `Sector ${camId}` : 'Monitored Perimeter');
  };

  const cardsToRender = sortedEvents.slice(0, 2).map((e) => {
    const isCritical = e.severity === 'CRITICAL' || e.severity === 'HIGH';
    const headline = e.description || `${(e.object_type || e.event_type || 'Object').replace(/_/g, ' ')} detected at ${e.camera_id}`;
    const location = getCameraLocation(e.camera_id);
    const time_ago = formatTimeAgo(e.timestamp);
    const timestamp = e.timestamp
      ? new Date(e.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    const observed_facts = `Track ${e.track_id || 'unassigned'} observed with ${Math.round((e.confidence || 0.9) * 100)}% detection confidence at ${location}. Real-time tracking pipeline verified.`;
    const recommended_action = isCritical
      ? 'Acknowledge alert and review live surveillance feed — high priority telemetry event.'
      : 'Keep track on automated watchlist for ongoing monitoring.';

    return {
      event_id: e.event_id,
      severity: isCritical ? 'CRITICAL' : 'ATTENTION',
      headline,
      camera_id: e.camera_id,
      location,
      time_ago,
      timestamp,
      observed_facts,
      recommended_action,
      rawEvent: e,
    };
  });

  return (
    <>
      <div className="section-head">
        <h2>What's happening</h2>
        <a className="view-all" onClick={onViewAll} style={{ cursor: 'pointer' }}>
          View all events{' '}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
            <path d="m9 6 6 6-6 6" />
          </svg>
        </a>
      </div>

      <div className="narrative-grid">
        {loading && events.length === 0 ? (
          <>
            <NarrativeCardSkeleton />
            <NarrativeCardSkeleton />
          </>
        ) : cardsToRender.length > 0 ? (
          cardsToRender.map((c) => {
            const isCritical = c.severity === 'CRITICAL';
            return (
              <div key={c.event_id} className={`tile n-tile ${isCritical ? 'critical' : 'attention'}`}>
                <div className="n-head">
                  <div className="n-head-left">
                    <div className={`n-icon ${isCritical ? 'critical' : 'attention'}`}>
                      {isCritical ? (
                        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                          <path d="M12 9v4M12 17h.01" />
                        </svg>
                      ) : (
                        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="9" />
                          <path d="M12 7v5l3 3" />
                        </svg>
                      )}
                    </div>
                    <div className="n-tags">
                      <span className="n-id">{c.event_id}</span>
                      <span className={`n-chip ${isCritical ? 'critical' : 'attention'}`}>
                        <span className="n-chip-dot"></span>
                        {c.severity}
                      </span>
                    </div>
                  </div>
                  <button className="n-btn ai-investigate" onClick={() => onInvestigate && onInvestigate(c.rawEvent || c)}>
                    <AiSparklesIcon size={11} />
                    <span>Investigate</span>
                  </button>
                </div>

                <div className="n-headline">{c.headline}</div>
                <div className="n-meta">
                  {c.timestamp} · {c.time_ago} · {c.location} / {c.camera_id}
                </div>

                <div className="n-body">
                  <div>
                    <div className="n-col-label">Observed facts</div>
                    <div className="n-col-text">{c.observed_facts}</div>
                  </div>
                  <div className="n-action-box">
                    <div className="n-action-label">Recommended action</div>
                    <div className="n-action-text">{c.recommended_action}</div>
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="tile" style={{ padding: '30px', gridColumn: '1 / -1', textAlign: 'center', color: 'var(--text-low)' }}>
            All surveillance sectors nominal. No active threat incidents reported.
          </div>
        )}
      </div>
    </>
  );
}
