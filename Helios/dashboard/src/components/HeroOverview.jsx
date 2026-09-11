import { useState, useEffect, useMemo } from 'react';
import { api } from '../services/api';
import { HeroSkeleton } from './SkeletonLoader';

/**
 * Catmull-Rom to Cubic Bézier spline generator for smooth SVG charts.
 */
function generateSmoothPath(points) {
  if (!points || points.length === 0) return '';
  if (points.length === 1) return `M ${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`;

  let d = `M ${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }
  return d;
}

/**
 * Generates an inline SVG sparkline path from a sequence of numeric data points.
 */
function generateSparkline(values, width = 68, height = 30) {
  const safeVals = Array.isArray(values) && values.length > 0 ? values : [0, 0, 0, 0, 0, 0, 0];
  const minVal = Math.min(...safeVals);
  const maxVal = Math.max(...safeVals, minVal + 1);
  const paddingX = 1;
  const paddingY = 4;
  const usableW = width - paddingX * 2;
  const usableH = height - paddingY * 2;

  const points = safeVals.map((val, idx) => {
    const x = paddingX + (idx / Math.max(1, safeVals.length - 1)) * usableW;
    const norm = (val - minVal) / (maxVal - minVal);
    const y = height - paddingY - norm * usableH;
    return { x, y };
  });

  const linePath = points.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const lastPoint = points[points.length - 1];
  const firstPoint = points[0];
  const areaPath = `${linePath} L ${lastPoint.x.toFixed(1)} ${height - 1} L ${firstPoint.x.toFixed(1)} ${height - 1} Z`;

  return { linePath, areaPath, lastPoint };
}

export function HeroOverview({ summary, analytics, events = [], tracks = [], alerts = [], cameras = [], evidence = [], loading = false, onSelectTab }) {
  const [activeTab, setActiveTab] = useState('24H');
  const [activeAnalytics, setActiveAnalytics] = useState(analytics);
  const [hoverIndex, setHoverIndex] = useState(null);

  // Fetch or update analytics when activeTab changes
  useEffect(() => {
    let isCurrent = true;
    const tf = activeTab.toLowerCase();
    api
      .getAnalytics(tf)
      .then((data) => {
        if (isCurrent && data) {
          setActiveAnalytics(data);
        }
      })
      .catch((err) => {
        console.warn('Failed to load timeframe analytics:', err);
      });
    return () => {
      isCurrent = false;
    };
  }, [activeTab]);

  // Sync initial analytics if provided
  useEffect(() => {
    if (analytics && !activeAnalytics) {
      setActiveAnalytics(analytics);
    }
  }, [analytics, activeAnalytics]);

  const totalEventsCount = activeAnalytics?.total_events ?? summary?.total_events ?? summary?.events_today ?? events.length;
  const deltaStr = activeAnalytics?.delta_str || (totalEventsCount > 0 ? `${totalEventsCount} recorded` : '0 nominal');
  const activeAlertsCount = alerts.filter((a) => a.status === 'ACTIVE').length;
  const activeTracksCount = tracks.filter((t) => t.status === 'ACTIVE').length;
  const camerasOnline = summary?.cameras?.online ?? cameras.filter((c) => c.status === 'ONLINE').length;
  const camerasTotal = summary?.cameras?.total ?? cameras.length;
  const evidenceCount = summary?.evidence?.total ?? summary?.evidence_count ?? evidence.length;

  const evidenceToday = useMemo(() => {
    if (summary?.evidence?.today !== undefined) return summary.evidence.today;
    const todayStr = new Date().toDateString();
    return evidence.filter((ev) => new Date(ev.timestamp || ev.created_at || 0).toDateString() === todayStr).length;
  }, [summary, evidence]);

  // Compute live SVG points for the main chart
  const { points, lineD, areaD, buckets } = useMemo(() => {
    const rawBuckets = activeAnalytics?.buckets || [];
    if (rawBuckets.length === 0) {
      // Compute actual buckets from events prop
      const bucketCount = activeTab === 'Live' ? 12 : activeTab === '7D' ? 7 : 24;
      const computedBuckets = [];
      const nowMs = Date.now();
      const stepMs = activeTab === 'Live' ? 5 * 60 * 1000 : activeTab === '7D' ? 24 * 3600 * 1000 : 3600 * 1000;

      for (let i = bucketCount - 1; i >= 0; i--) {
        const bStart = nowMs - (i + 1) * stepMs;
        const bEnd = nowMs - i * stepMs;
        const bDate = new Date(bEnd);
        const label = activeTab === '7D'
          ? bDate.toLocaleDateString([], { month: 'short', day: 'numeric' })
          : bDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        const count = events.filter((e) => {
          const t = new Date(e.timestamp || 0).getTime();
          return t >= bStart && t < bEnd;
        }).length;

        const restricted_count = events.filter((e) => {
          const t = new Date(e.timestamp || 0).getTime();
          return t >= bStart && t < bEnd && (e.severity === 'CRITICAL' || e.severity === 'HIGH');
        }).length;

        computedBuckets.push({ label, count, restricted_count });
      }

      const maxC = Math.max(...computedBuckets.map((b) => b.count), 1);
      const pts = computedBuckets.map((b, i) => ({
        x: 5 + (i / Math.max(1, computedBuckets.length - 1)) * 610,
        y: 165 - (b.count / maxC) * 130,
        ...b,
      }));
      const lD = generateSmoothPath(pts);
      const aD = `${lD} L 615,186 L 5,186 Z`;
      return { points: pts, lineD: lD, areaD: aD, buckets: computedBuckets };
    }

    const maxC = Math.max(...rawBuckets.map((b) => b.count), 1);
    const pts = rawBuckets.map((b, i) => {
      const x = 5 + (i / Math.max(1, rawBuckets.length - 1)) * 610;
      const y = 165 - (b.count / maxC) * 130;
      return {
        x,
        y,
        ...b,
      };
    });

    const lD = generateSmoothPath(pts);
    const aD = `${lD} L 615,186 L 5,186 Z`;
    return { points: pts, lineD: lD, areaD: aD, buckets: rawBuckets };
  }, [activeAnalytics, events, activeTab]);

  // Selected point for tooltip / callout
  const activePoint = useMemo(() => {
    if (points.length === 0) return null;
    if (hoverIndex !== null && points[hoverIndex]) {
      return points[hoverIndex];
    }
    // Default to the peak point
    let best = points[0];
    for (const p of points) {
      if (p.count > best.count) best = p;
    }
    return best;
  }, [points, hoverIndex]);

  // Severity Distribution Bar calculations
  const severities = activeAnalytics?.severities || {
    critical: events.filter((e) => e.severity === 'CRITICAL').length,
    high: events.filter((e) => e.severity === 'HIGH').length,
    medium: events.filter((e) => e.severity === 'MEDIUM').length,
    info: events.filter((e) => e.severity === 'INFO' || !e.severity).length,
  };
  const totalSev = (severities.critical || 0) + (severities.high || 0) + (severities.medium || 0) + (severities.info || 0);
  const critWidth = totalSev > 0 && (severities.critical || 0) > 0 ? ((severities.critical || 0) / totalSev) * 100 : 0;
  const highWidth = totalSev > 0 && (severities.high || 0) > 0 ? ((severities.high || 0) / totalSev) * 100 : 0;
  const medWidth = totalSev > 0 && (severities.medium || 0) > 0 ? ((severities.medium || 0) / totalSev) * 100 : 0;
  const infoWidth = totalSev > 0 && (severities.info || 0) > 0 ? Math.max(0, 100 - critWidth - highWidth - medWidth) : 0;

  // Day vs Night split computed from real events
  const { dayPercent, nightPercent } = useMemo(() => {
    if (activeAnalytics?.day_night?.day_percent !== undefined) {
      return {
        dayPercent: activeAnalytics.day_night.day_percent,
        nightPercent: activeAnalytics.day_night.night_percent,
      };
    }
    let d = 0, n = 0;
    events.forEach((e) => {
      const hour = new Date(e.timestamp || Date.now()).getHours();
      if (hour >= 6 && hour < 18) d++;
      else n++;
    });
    const total = d + n || 1;
    const dp = Math.round((d / total) * 100);
    return { dayPercent: dp, nightPercent: 100 - dp };
  }, [activeAnalytics, events]);

  // Dynamic peak hour, busiest camera, and median duration
  const peakHourInfo = useMemo(() => {
    if (activeAnalytics?.peak_hour?.hour) return activeAnalytics.peak_hour;
    if (events.length === 0) return { hour: 'Nominal', count: 0 };
    const hourCounts = {};
    events.forEach((e) => {
      const h = new Date(e.timestamp || Date.now()).getHours();
      const str = `${String(h).padStart(2, '0')}:00`;
      hourCounts[str] = (hourCounts[str] || 0) + 1;
    });
    const bestHour = Object.keys(hourCounts).reduce((a, b) => hourCounts[a] > hourCounts[b] ? a : b, '00:00');
    return { hour: bestHour, count: hourCounts[bestHour] || 0 };
  }, [activeAnalytics, events]);

  const busiestCameraId = useMemo(() => {
    if (activeAnalytics?.busiest_camera) return activeAnalytics.busiest_camera;
    if (events.length === 0) return cameras[0]?.camera_id || 'Nominal';
    const camCounts = {};
    events.forEach((e) => {
      if (e.camera_id) camCounts[e.camera_id] = (camCounts[e.camera_id] || 0) + 1;
    });
    const sorted = Object.keys(camCounts).sort((a, b) => camCounts[b] - camCounts[a]);
    return sorted[0] || (cameras[0]?.camera_id || 'Nominal');
  }, [activeAnalytics, events, cameras]);

  const medianDuration = useMemo(() => {
    if (activeAnalytics?.median_duration_seconds !== undefined) return activeAnalytics.median_duration_seconds;
    if (tracks.length === 0) return 0;
    const durations = tracks.map((t) => {
      const s = new Date(t.created_at || 0).getTime();
      const e = new Date(t.last_seen_at || t.ended_at || t.created_at || 0).getTime();
      return Math.max(1, Math.round((e - s) / 1000));
    }).sort((a, b) => a - b);
    const mid = Math.floor(durations.length / 2);
    return durations[mid] || 0;
  }, [activeAnalytics, tracks]);

  // Sparklines for summary cards computed from real event telemetry
  const alertsSpark = useMemo(() => {
    if (activeAnalytics?.buckets?.length >= 6) {
      const vals = activeAnalytics.buckets.slice(-6).map((b) => b.restricted_count || 0);
      vals.push(activeAlertsCount);
      return generateSparkline(vals);
    }
    const slices = 6;
    const now = Date.now();
    const interval = 4 * 3600 * 1000;
    const vals = [];
    for (let i = slices - 1; i >= 0; i--) {
      const start = now - (i + 1) * interval;
      const end = now - i * interval;
      const c = alerts.filter((a) => {
        const t = new Date(a.timestamp || 0).getTime();
        return t >= start && t < end;
      }).length;
      vals.push(c);
    }
    vals.push(activeAlertsCount);
    return generateSparkline(vals);
  }, [activeAnalytics, alerts, activeAlertsCount]);

  const tracksSpark = useMemo(() => {
    if (activeAnalytics?.buckets?.length >= 6) {
      const vals = activeAnalytics.buckets.slice(-6).map((b) => Math.max(0, b.count));
      vals.push(activeTracksCount);
      return generateSparkline(vals);
    }
    const slices = 6;
    const now = Date.now();
    const interval = 4 * 3600 * 1000;
    const vals = [];
    for (let i = slices - 1; i >= 0; i--) {
      const start = now - (i + 1) * interval;
      const end = now - i * interval;
      const c = tracks.filter((t) => {
        const tm = new Date(t.created_at || t.last_seen_at || 0).getTime();
        return tm >= start && tm < end;
      }).length;
      vals.push(c);
    }
    vals.push(activeTracksCount);
    return generateSparkline(vals);
  }, [activeAnalytics, tracks, activeTracksCount]);

  const camerasSpark = useMemo(() => {
    const vals = [camerasTotal, camerasTotal, camerasOnline, camerasOnline, camerasOnline, camerasOnline];
    return generateSparkline(vals);
  }, [camerasOnline, camerasTotal]);

  const evidenceSpark = useMemo(() => {
    const slices = 6;
    const now = Date.now();
    const interval = 4 * 3600 * 1000;
    const vals = [];
    for (let i = slices - 1; i >= 0; i--) {
      const start = now - (i + 1) * interval;
      const end = now - i * interval;
      const c = evidence.filter((ev) => {
        const t = new Date(ev.timestamp || ev.created_at || 0).getTime();
        return t >= start && t < end;
      }).length;
      vals.push(c);
    }
    vals.push(evidence.length);
    return generateSparkline(vals);
  }, [evidence]);

  if (loading && !summary && events.length === 0) {
    return <HeroSkeleton />;
  }

  return (
    <div className="hero">
      {/* MAIN CHART TILE */}
      <div className="tile chart-tile">
        <div className="chart-head">
          <div>
            <div className="chart-title">Events Trend Overview</div>
            <div className="chart-title-sub">
              All monitored cameras · Live timeline telemetry
            </div>
          </div>
          <div className="chart-tabs">
            {['Live', '24H', '7D'].map((tab) => (
              <span
                key={tab}
                className={`chart-tab ${activeTab === tab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </span>
            ))}
          </div>
        </div>

        <div className="chart-body">
          <div>
            <div className="chart-bignum">
              <b>{totalEventsCount}</b>
              <span className="delta">{deltaStr}</span>
              <span className="label">vs. prior window</span>
            </div>

            <div
              className="chart-svg-wrap"
              onMouseMove={(e) => {
                if (points.length < 2) return;
                const rect = e.currentTarget.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const ratio = Math.max(0, Math.min(1, mouseX / rect.width));
                const idx = Math.round(ratio * (points.length - 1));
                setHoverIndex(idx);
              }}
              onMouseLeave={() => setHoverIndex(null)}
              style={{ cursor: 'crosshair' }}
            >
              <svg viewBox="0 0 620 190" width="100%" height="170" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
                <defs>
                  <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#EF5251" stopOpacity="0.28" />
                    <stop offset="100%" stopColor="#EF5251" stopOpacity="0" />
                  </linearGradient>
                  <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="2.6" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>

                {/* Grid guidelines */}
                <g stroke="#161616" strokeWidth="1">
                  <line x1="0" y1="42" x2="620" y2="42" />
                  <line x1="0" y1="90" x2="620" y2="90" />
                  <line x1="0" y1="138" x2="620" y2="138" />
                </g>

                {/* Area Fill */}
                {areaD && <path d={areaD} fill="url(#areaFill)" stroke="none" />}

                {/* Curve Line */}
                {lineD && (
                  <path
                    d={lineD}
                    fill="none"
                    stroke="#EF5251"
                    strokeWidth="2.2"
                    filter="url(#glow)"
                    strokeLinecap="round"
                  />
                )}

                {/* Active Hover Dot */}
                {activePoint && (
                  <g>
                    <line
                      x1={activePoint.x}
                      y1={30}
                      x2={activePoint.x}
                      y2={186}
                      stroke="rgba(239, 82, 81, 0.4)"
                      strokeWidth="1"
                      strokeDasharray="3 3"
                    />
                    <circle
                      cx={activePoint.x}
                      cy={activePoint.y}
                      r="4.5"
                      fill="#050505"
                      stroke="#EF5251"
                      strokeWidth="2.5"
                    />
                  </g>
                )}
              </svg>

              {/* DYNAMIC CALLOUT HUD */}
              {activePoint && (
                <div
                  className="chart-callout"
                  style={{
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div className="cd-time">{activePoint.label || 'Active window'}</div>
                  <div className="cd-row">
                    <span>Events</span>
                    <b>{activePoint.count || 0}</b>
                  </div>
                  <div className="cd-row">
                    <span>Critical</span>
                    <b style={{ color: activePoint.restricted_count > 0 ? 'var(--red)' : 'var(--text-mid)' }}>
                      {activePoint.restricted_count || 0}
                    </b>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ANALYTICS RAIL */}
          <div className="analytics-rail">
            {/* SEVERITY DISTRIBUTION BAR */}
            <div className="sev-bar-wrap">
              <div className="sev-bar-track">
                {critWidth > 0 && (
                  <div className="sev-seg" style={{ width: `${critWidth}%`, background: 'var(--red)' }} title={`Critical: ${severities.critical}`}></div>
                )}
                {highWidth > 0 && (
                  <div className="sev-seg" style={{ width: `${highWidth}%`, background: 'var(--orange)' }} title={`High: ${severities.high}`}></div>
                )}
                {medWidth > 0 && (
                  <div className="sev-seg" style={{ width: `${medWidth}%`, background: 'var(--gold)' }} title={`Medium: ${severities.medium}`}></div>
                )}
                {infoWidth > 0 && (
                  <div className="sev-seg" style={{ width: `${infoWidth}%`, background: '#333' }} title={`Info: ${severities.info}`}></div>
                )}
              </div>
              <div className="sev-legend">
                <span>
                  <i style={{ background: 'var(--red)' }}></i>Critical · {severities.critical || 0}
                </span>
                <span>
                  <i style={{ background: 'var(--orange)' }}></i>High · {severities.high || 0}
                </span>
                <span>
                  <i style={{ background: 'var(--gold)' }}></i>Medium · {severities.medium || 0}
                </span>
                <span>
                  <i style={{ background: '#333' }}></i>Info · {severities.info || 0}
                </span>
              </div>
            </div>

            {/* DYNAMIC STAT GRID */}
            <div className="stat-grid">
              <div className="stat-cell">
                <div className="sc-label">Peak hour</div>
                <div className="sc-value">
                  {peakHourInfo.hour}{' '}
                  <small>{peakHourInfo.count} evts</small>
                </div>
              </div>
              <div className="stat-cell">
                <div className="sc-label">Avg / hour</div>
                <div className="sc-value">{activeAnalytics?.avg_per_hour ?? Math.round((totalEventsCount / 24) * 10) / 10}</div>
              </div>
              <div className="stat-cell">
                <div className="sc-label">Busiest camera</div>
                <div className="sc-value" style={{ fontSize: '12.5px' }}>
                  {busiestCameraId}
                </div>
              </div>
              <div className="stat-cell">
                <div className="sc-label">Median duration</div>
                <div className="sc-value">
                  {medianDuration}
                  <small>s</small>
                </div>
              </div>
            </div>

            {/* LIVE DAY/NIGHT SPLIT */}
            <div className="split-row">
              <span style={{ width: '34px', color: 'var(--text-low)', fontFamily: 'var(--mono)', fontSize: '10.5px' }}>
                Day
              </span>
              <div className="split-track">
                <div style={{ width: `${dayPercent}%`, background: 'var(--text-mid)', transition: 'width 0.3s ease' }}></div>
                <div style={{ width: `${nightPercent}%`, background: '#2a2a2a', transition: 'width 0.3s ease' }}></div>
              </div>
              <span style={{ width: '34px', textAlign: 'right', color: 'var(--text-low)', fontFamily: 'var(--mono)', fontSize: '10.5px' }}>
                Night
              </span>
            </div>
            <div style={{ fontSize: '10.5px', color: 'var(--text-low)', fontFamily: 'var(--mono)', textAlign: 'right', marginTop: '-4px' }}>
              {dayPercent}% / {nightPercent}% split
            </div>
          </div>
        </div>
      </div>

      {/* SUMMARY KPI CARDS COLUMN */}
      <div className="summary-col">
        {/* CARD 1: ACTIVE ALERTS */}
        <div
          className="tile summary-row"
          style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
          onClick={() => onSelectTab && onSelectTab('alerts')}
          title="View Active Alerts"
        >
          <div className="sum-icon status">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
              <path d="M12 9v4M12 17h.01" />
            </svg>
          </div>
          <div className="sum-body">
            <div className="sum-top">
              <span className="sum-num">{activeAlertsCount}</span>
              <span className={`sum-delta ${activeAlertsCount > 0 ? 'up-bad' : 'up-good'}`}>
                {activeAlertsCount > 0 ? `+${activeAlertsCount}` : '0'}
              </span>
            </div>
            <div className="sum-label">Active alerts</div>
          </div>
          <div className="sum-spark" style={{ color: 'var(--red)' }} aria-hidden="true">
            <svg viewBox="0 0 68 30" preserveAspectRatio="none">
              <line className="spark-grid" x1="0" y1="24" x2="68" y2="24" />
              <path className="spark-area" d={alertsSpark.areaPath} />
              <path className="spark-line" d={alertsSpark.linePath} />
              <circle className="spark-dot" cx={alertsSpark.lastPoint.x} cy={alertsSpark.lastPoint.y} r="2.2" />
            </svg>
          </div>
        </div>

        {/* CARD 2: ACTIVE TRACKS */}
        <div
          className="tile summary-row"
          style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
          onClick={() => onSelectTab && onSelectTab('threads')}
          title="View Activity Stories"
        >
          <div className="sum-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" />
            </svg>
          </div>
          <div className="sum-body">
            <div className="sum-top">
              <span className="sum-num">{activeTracksCount}</span>
              <span className={`sum-delta ${activeTracksCount > 0 ? 'up-bad' : 'up-good'}`}>
                {activeTracksCount > 0 ? `+${activeTracksCount}` : '0'}
              </span>
            </div>
            <div className="sum-label">Active tracks</div>
          </div>
          <div className="sum-spark" style={{ color: 'var(--gold)' }} aria-hidden="true">
            <svg viewBox="0 0 68 30" preserveAspectRatio="none">
              <line className="spark-grid" x1="0" y1="24" x2="68" y2="24" />
              <path className="spark-area" d={tracksSpark.areaPath} />
              <path className="spark-line" d={tracksSpark.linePath} />
              <circle className="spark-dot" cx={tracksSpark.lastPoint.x} cy={tracksSpark.lastPoint.y} r="2.2" />
            </svg>
          </div>
        </div>

        {/* CARD 3: CAMERAS ONLINE */}
        <div
          className="tile summary-row"
          style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
          onClick={() => onSelectTab && onSelectTab('feeds')}
          title="View Surveillance Streams"
        >
          <div className="sum-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 10l5-3v10l-5-3" />
              <rect x="1" y="6" width="14" height="12" rx="2" />
            </svg>
          </div>
          <div className="sum-body">
            <div className="sum-top">
              <span className="sum-num">
                {camerasOnline}/{camerasTotal}
              </span>
              <span className="sum-delta up-good">
                {Math.round((camerasOnline / (camerasTotal || 1)) * 100)}%
              </span>
            </div>
            <div className="sum-label">Cameras online</div>
          </div>
          <div className="sum-spark" style={{ color: 'var(--green)' }} aria-hidden="true">
            <svg viewBox="0 0 68 30" preserveAspectRatio="none">
              <line className="spark-grid" x1="0" y1="24" x2="68" y2="24" />
              <path className="spark-area" d={camerasSpark.areaPath} />
              <path className="spark-line" d={camerasSpark.linePath} />
              <circle className="spark-dot" cx={camerasSpark.lastPoint.x} cy={camerasSpark.lastPoint.y} r="2.2" />
            </svg>
          </div>
        </div>

        {/* CARD 4: EVIDENCE CAPTURED */}
        <div
          className="tile summary-row"
          style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
          onClick={() => onSelectTab && onSelectTab('evidence')}
          title="Open Evidence Vault"
        >
          <div className="sum-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="9" cy="9" r="2" />
              <path d="m21 15-5-5L5 21" />
            </svg>
          </div>
          <div className="sum-body">
            <div className="sum-top">
              <span className="sum-num">{evidenceCount}</span>
              <span className="sum-delta up-good">+{evidenceToday}</span>
            </div>
            <div className="sum-label">Evidence captured</div>
          </div>
          <div className="sum-spark" style={{ color: 'var(--gold)' }} aria-hidden="true">
            <svg viewBox="0 0 68 30" preserveAspectRatio="none">
              <line className="spark-grid" x1="0" y1="24" x2="68" y2="24" />
              <path className="spark-area" d={evidenceSpark.areaPath} />
              <path className="spark-line" d={evidenceSpark.linePath} />
              <circle className="spark-dot" cx={evidenceSpark.lastPoint.x} cy={evidenceSpark.lastPoint.y} r="2.2" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}
