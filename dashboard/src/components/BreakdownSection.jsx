import { useState } from 'react';
import { SkeletonBox, SkeletonText } from './SkeletonLoader';

export function BreakdownSection({ cameras = [], events = [], tracks = [], alerts = [], loading = false, onSelectTab }) {
  const [toggle, setToggle] = useState('Events');

  if (loading && cameras.length === 0) {
    return (
      <>
        <div className="section-head">
          <h2>Activity breakdown</h2>
          <span className="section-sub">live telemetry distribution</span>
        </div>
        <div className="breakdown">
          <div className="skeleton-card" style={{ height: '240px' }}>
            <SkeletonBox width="140px" height="16px" style={{ marginBottom: '16px' }} />
            <SkeletonText lines={5} height={18} gap={12} />
          </div>
          <div className="skeleton-card" style={{ height: '240px' }}>
            <SkeletonBox width="140px" height="16px" style={{ marginBottom: '16px' }} />
            <SkeletonText lines={5} height={18} gap={12} />
          </div>
        </div>
      </>
    );
  }

  // Compute breakdown stats dynamically from events & tracks without placeholder constants
  const humanCount = tracks.filter((t) => (t.object_type || '').toUpperCase() === 'HUMAN').length;
  const vehicleCount = tracks.filter((t) => (t.object_type || '').toUpperCase() === 'VEHICLE').length;
  const uavCount = tracks.filter((t) => (t.object_type || '').toUpperCase() === 'UAV').length;
  const plateCount = tracks.filter((t) => (t.object_type || '').toUpperCase() === 'LICENSE_PLATE').length;
  const unclassifiedCount = tracks.filter(
    (t) =>
      (t.object_type || '').toUpperCase() === 'UNCLASSIFIED' ||
      (t.object_type || '').toUpperCase() === 'MOTION'
  ).length;

  const maxObj = Math.max(humanCount, vehicleCount, uavCount, plateCount, unclassifiedCount, 1);

  // Dynamic camera counts
  const totalItems = toggle === 'Events' ? events.length : alerts.length;

  const cameraBreakdowns = cameras.map((c) => {
    let count = 0;
    if (toggle === 'Events') {
      count = events.filter((e) => e.camera_id === c.camera_id).length;
    } else {
      count = alerts.filter(
        (a) =>
          a.camera_id === c.camera_id ||
          a.message?.includes(c.camera_id) ||
          events.some((e) => e.event_id === a.event_id && e.camera_id === c.camera_id)
      ).length;
    }

    const criticalCount = events.filter(
      (e) =>
        e.camera_id === c.camera_id &&
        (e.severity === 'CRITICAL' || e.severity === 'HIGH')
    ).length;

    const share = totalItems > 0 ? Math.round((count / totalItems) * 100) : 0;
    const isUp = share >= 20;

    return {
      camera_id: c.camera_id,
      name: c.name || c.camera_id,
      location: c.location || 'Monitored Zone',
      status: c.status || 'ONLINE',
      count,
      criticalCount,
      share,
      isUp,
    };
  });

  return (
    <>
      <div className="section-head">
        <h2>Activity breakdown</h2>
        <span className="section-sub">live telemetry distribution</span>
      </div>

      <div className="breakdown">
        {/* BY CAMERA STREAM */}
        <div className="tile list-tile">
          <div className="list-head">
            <h3>By camera stream</h3>
            <div className="list-toggle">
              <span className={toggle === 'Events' ? 'active' : ''} onClick={() => setToggle('Events')}>
                Events
              </span>
              <span className={toggle === 'Alerts' ? 'active' : ''} onClick={() => setToggle('Alerts')}>
                Alerts
              </span>
            </div>
          </div>

          <div className="list-cols">
            <span style={{ flex: 1 }}>Camera</span>
            <span className="col-fixed">{toggle}</span>
            <span className="col-fixed">Critical</span>
            <span className="col-trend">Share</span>
          </div>

          {cameraBreakdowns.length > 0 ? (
            cameraBreakdowns.map((cam) => (
              <div
                key={cam.camera_id}
                className="list-row"
                style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
                onClick={() => onSelectTab && onSelectTab('feeds')}
                title={`View feed for ${cam.name}`}
              >
                <span className="row-name">
                  <span className={`dot ${cam.status !== 'ONLINE' || cam.criticalCount > 0 ? 'warn' : ''}`}></span>
                  {cam.name} — {cam.camera_id}
                </span>
                <span className="col-fixed">{cam.count}</span>
                <span
                  className="col-fixed"
                  style={{ color: cam.criticalCount > 0 ? 'var(--red)' : 'var(--text-mid)' }}
                >
                  {cam.criticalCount}
                </span>
                <span className={`col-trend ${cam.isUp ? 'trend-up' : 'trend-down'}`}>
                  {cam.isUp ? `↑ ${cam.share}%` : `↓ ${cam.share}%`}
                </span>
              </div>
            ))
          ) : (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-low)' }}>
              No cameras configured.
            </div>
          )}
        </div>

        {/* BY OBJECT TYPE */}
        <div className="tile obj-tile">
          <div className="list-head" style={{ padding: '0 0 14px', border: 'none' }}>
            <h3>By object type</h3>
          </div>

          {/* HUMAN */}
          <div
            className="obj-row"
            style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
            onClick={() => onSelectTab && onSelectTab('threads')}
            title="Inspect human activity stories"
          >
            <div className="obj-bar-wrap">
              <div className="obj-bar-top">
                <span>Human</span>
                <b>{humanCount}</b>
              </div>
              <div className="obj-bar-track">
                <div
                  className="obj-bar-fill"
                  style={{ width: `${Math.min(100, Math.round((humanCount / maxObj) * 100))}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* VEHICLE */}
          <div
            className="obj-row"
            style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
            onClick={() => onSelectTab && onSelectTab('threads')}
            title="Inspect vehicle activity stories"
          >
            <div className="obj-bar-wrap">
              <div className="obj-bar-top">
                <span>Vehicle</span>
                <b>{vehicleCount}</b>
              </div>
              <div className="obj-bar-track">
                <div
                  className="obj-bar-fill"
                  style={{ width: `${Math.min(100, Math.round((vehicleCount / maxObj) * 100))}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* UAV */}
          <div
            className="obj-row"
            style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
            onClick={() => onSelectTab && onSelectTab('threads')}
            title="Inspect UAV activity stories"
          >
            <div className="obj-bar-wrap">
              <div className="obj-bar-top">
                <span>UAV</span>
                <b>{uavCount}</b>
              </div>
              <div className="obj-bar-track">
                <div
                  className="obj-bar-fill"
                  style={{
                    width: `${Math.min(100, Math.round((uavCount / maxObj) * 100))}%`,
                    background: 'var(--red)',
                  }}
                ></div>
              </div>
            </div>
          </div>

          {/* LICENSE PLATE READS */}
          <div
            className="obj-row"
            style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
            onClick={() => onSelectTab && onSelectTab('evidence')}
            title="Inspect license plate evidence reads"
          >
            <div className="obj-bar-wrap">
              <div className="obj-bar-top">
                <span>License plate reads</span>
                <b>{plateCount}</b>
              </div>
              <div className="obj-bar-track">
                <div
                  className="obj-bar-fill"
                  style={{ width: `${Math.min(100, Math.round((plateCount / maxObj) * 100))}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* UNCLASSIFIED MOTION */}
          <div
            className="obj-row"
            style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
            onClick={() => onSelectTab && onSelectTab('events')}
            title="Inspect motion events"
          >
            <div className="obj-bar-wrap">
              <div className="obj-bar-top">
                <span>Unclassified motion (MOG2)</span>
                <b style={{ color: '#D5B18A' }}>{unclassifiedCount}</b>
              </div>
              <div className="obj-bar-track">
                <div
                  className="obj-bar-fill"
                  style={{
                    width: `${Math.min(100, Math.round((unclassifiedCount / maxObj) * 100))}%`,
                    background: '#8C6544',
                  }}
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
