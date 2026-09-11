import { AiSparklesIcon } from './Icons';

export function StatusBanner({ alerts = [], cameras = [], onSelectAlerts, onInvestigate }) {
  const onlineCameras = cameras.filter((c) => c.status === 'ONLINE');
  const allOffline = cameras.length > 0 && onlineCameras.length === 0;

  // Filter for genuine active security threats (ignore offline camera notes and dummy restricted zone alerts)
  const activeSecurityAlerts = alerts.filter(
    (a) =>
      a.status === 'ACTIVE' &&
      a.severity !== 'MEDIUM' &&
      a.severity !== 'LOW' &&
      a.alert_type !== 'camera-offline' &&
      !a.message?.toLowerCase().includes('offline') &&
      !a.message?.toLowerCase().includes('restricted zone')
  );

  let bannerMode = 'secure';
  let title = 'ALL SYSTEMS SECURE';
  let detail = `Monitoring ${onlineCameras.length} active camera${onlineCameras.length === 1 ? '' : 's'} · Situational awareness nominal`;
  let statusRightText = 'Status: Nominal';
  const criticalAlert = activeSecurityAlerts[0] || null;

  if (allOffline) {
    bannerMode = 'standby';
    title = 'ALL CAMERAS OFFLINE';
    detail = `All ${cameras.length} surveillance feeds are offline · Standby mode`;
    statusRightText = 'Status: Standby';
  } else if (criticalAlert) {
    bannerMode = 'critical';
    title = criticalAlert.message ? criticalAlert.message.toUpperCase() : 'ALERT DETECTED';
    detail = criticalAlert.message || 'Security alert flagged by sensory pipeline';
    statusRightText = `Since ${
      criticalAlert.timestamp
        ? new Date(criticalAlert.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })
        : 'recently'
    }`;
  }

  return (
    <div className={`status-banner ${bannerMode}`}>
      <div className="status-left">
        <div className="status-ring"></div>
        <span className="status-title">{title}</span>
        <span className="status-detail">{detail}</span>
      </div>
      <div className="status-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span>{statusRightText}</span>

        {bannerMode === 'critical' && criticalAlert?.event_id && onInvestigate && (
          <button
            className="n-btn ai-investigate"
            style={{
              fontSize: '11px',
              padding: '3px 8px',
            }}
            onClick={() => onInvestigate({ event_id: criticalAlert.event_id })}
          >
            <AiSparklesIcon size={11} />
            <span>Investigate AI</span>
          </button>
        )}

        <a className="status-link" onClick={onSelectAlerts} style={{ cursor: 'pointer' }}>
          {bannerMode === 'critical' ? 'View incident' : 'View status'}{' '}
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
            <path d="M7 17 17 7M7 7h10v10" />
          </svg>
        </a>
      </div>
    </div>
  );
}
