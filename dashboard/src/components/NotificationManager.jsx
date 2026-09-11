import { useState, useEffect, useRef, useCallback } from 'react';
import { playAlertChime, speakAlert } from '../utils/alertAudio';
import { AiSparklesIcon } from './Icons';

/**
 * Checks whether an alert or event represents an intrusion
 */
export function isIntrusionAlert(alert, event) {
  const alertType = (alert?.alert_type || '').toLowerCase();
  const alertMsg = (alert?.message || '').toLowerCase();
  const eventType = (event?.event_type || '').toLowerCase();
  const eventDesc = (event?.description || '').toLowerCase();

  return (
    alertType.includes('intrusion') ||
    alertType.includes('restricted') ||
    alertType.includes('breach') ||
    alertType.includes('line_cross') ||
    alertMsg.includes('intrusion') ||
    alertMsg.includes('restricted') ||
    alertMsg.includes('breach') ||
    eventType.includes('intrusion') ||
    eventType.includes('restricted') ||
    eventType.includes('breach') ||
    eventDesc.includes('intrusion') ||
    eventDesc.includes('breach')
  );
}

/**
 * Extracts camera name and detected entity from alert/event
 */
export function extractAlertDetails(alert, event) {
  let cam = alert?.camera_id || event?.camera_id || '';
  if (!cam && alert?.message) {
    const match = alert.message.match(/cam[-_]?\w+/i);
    if (match) cam = match[0];
  }
  if (!cam) cam = 'cam-01';

  let entity = event?.object_type || alert?.object_type || '';
  if (!entity && alert?.message) {
    const match = alert.message.match(/(person|human|vehicle|car|truck|drone|uav|intruder)/i);
    if (match) entity = match[0];
  }
  if (!entity) entity = 'person';

  return {
    camera: cam,
    entity: entity.toLowerCase(),
  };
}

export function NotificationManager({
  alerts = [],
  events = [],
  onInvestigate,
  onSelectTab,
  soundEnabled = true,
}) {
  const [notifications, setNotifications] = useState([]);
  const seenIdsRef = useRef(new Set());
  const initialLoadRef = useRef(true);

  // Push a new notification into the stack
  const addNotification = useCallback(
    (notifData) => {
      const id = notifData.id || `notif-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const isIntrusion = notifData.isIntrusion;
      const { camera, entity } = notifData;

      const spokenText = `Alert: intrusion detected on ${camera}, by ${entity}`;

      const newNotif = {
        id,
        title: isIntrusion ? 'Intrusion Detected!' : (notifData.title || 'Security Alert!'),
        message: notifData.message || spokenText,
        spokenText,
        camera,
        entity,
        severity: notifData.severity || (isIntrusion ? 'CRITICAL' : 'HIGH'),
        isIntrusion,
        timestamp: notifData.timestamp || new Date().toISOString(),
        event: notifData.event || null,
        duration: isIntrusion ? 12000 : 8000,
      };

      setNotifications((prev) => [newNotif, ...prev.filter((n) => n.id !== id)].slice(0, 3));

      // Trigger audio chime and speech dispatch if sound is active
      if (soundEnabled) {
        playAlertChime(isIntrusion);
        if (isIntrusion) {
          speakAlert(spokenText);
        }
      }
    },
    [soundEnabled]
  );

  // Seed existing alerts on initial mount so we don't alert retroactively
  useEffect(() => {
    if (initialLoadRef.current) {
      alerts.forEach((a) => {
        if (a.alert_id) seenIdsRef.current.add(a.alert_id);
      });
      events.forEach((e) => {
        if (e.event_id) seenIdsRef.current.add(e.event_id);
      });
      initialLoadRef.current = false;
      return;
    }

    // Check for incoming ACTIVE alerts that haven't been seen
    alerts.forEach((alert) => {
      if (alert.status === 'ACTIVE' && alert.alert_id && !seenIdsRef.current.has(alert.alert_id)) {
        seenIdsRef.current.add(alert.alert_id);

        const linkedEvent = events.find((e) => e.event_id === alert.event_id);
        const isIntrusion = isIntrusionAlert(alert, linkedEvent);
        const { camera, entity } = extractAlertDetails(alert, linkedEvent);

        addNotification({
          id: alert.alert_id,
          title: isIntrusion ? 'Intrusion Detected!' : alert.message || 'Security Alert!',
          message: alert.message,
          severity: alert.severity || 'HIGH',
          isIntrusion,
          camera,
          entity,
          timestamp: alert.timestamp,
          event: linkedEvent || { event_id: alert.event_id, camera_id: camera, object_type: entity },
        });
      }
    });
  }, [alerts, events, addNotification]);

  // Support external / custom event triggers (e.g. from Test button)
  useEffect(() => {
    const handleCustomTrigger = (e) => {
      const detail = e.detail || {};
      addNotification({
        id: `manual-${Date.now()}`,
        isIntrusion: detail.isIntrusion !== false,
        camera: detail.camera || 'cam-01',
        entity: detail.entity || 'person',
        title: detail.title || 'Intrusion Detected!',
        message: detail.message || 'Restricted perimeter breach at North Gate Alpha',
        severity: detail.severity || 'CRITICAL',
        event: detail.event || {
          event_id: `EVT-TEST-${Date.now()}`,
          camera_id: detail.camera || 'cam-01',
          object_type: detail.entity || 'person',
          severity: 'CRITICAL',
          description: 'Simulated perimeter breach detected on camera stream',
        },
      });
    };

    window.addEventListener('helios:trigger-alert', handleCustomTrigger);
    return () => window.removeEventListener('helios:trigger-alert', handleCustomTrigger);
  }, [addNotification]);

  // Dismiss a notification
  const dismissNotification = (id) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  if (notifications.length === 0) return null;

  return (
    <aside className="helios-notification-container" aria-label="Security alerts">
      {notifications.map((notif) => (
        <NotificationCard
          key={notif.id}
          notification={notif}
          onDismiss={() => dismissNotification(notif.id)}
          onInvestigate={onInvestigate}
          onSelectTab={onSelectTab}
        />
      ))}
    </aside>
  );
}

function NotificationCard({ notification, onDismiss, onInvestigate, onSelectTab }) {
  const [paused, setPaused] = useState(false);
  const remainingTimeRef = useRef(notification.duration);

  useEffect(() => {
    if (paused) return;

    const interval = 100;
    const timer = setInterval(() => {
      remainingTimeRef.current -= interval;
      if (remainingTimeRef.current <= 0) {
        clearInterval(timer);
        onDismiss();
      }
    }, interval);

    return () => clearInterval(timer);
  }, [paused, notification.duration, onDismiss]);

  const handleMouseEnter = () => setPaused(true);
  const handleMouseLeave = () => setPaused(false);

  return (
    <div
      className="helios-modal-card"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      role="alert"
    >
      {/* Top Row: Grey Icon Box + Title + Close Button */}
      <div className="hm-top-row">
        <div className="hm-header-left">
          {/* Swapped blue with grey icon badge */}
          <div className="hm-icon-box">
            {notification.isIntrusion ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
            )}
          </div>

          <span className="hm-title">{notification.title}</span>
        </div>

        <div className="hm-header-right">
          <button
            type="button"
            className="hm-investigate-btn"
            onClick={() => {
              if (onInvestigate) {
                onInvestigate(
                  notification.event || {
                    event_id: notification.id,
                    camera_id: notification.camera,
                    object_type: notification.entity,
                  }
                );
              }
              onDismiss();
            }}
          >
            <AiSparklesIcon size={12} />
            <span>Investigate</span>
          </button>

          <button
            type="button"
            className="hm-close-btn"
            onClick={onDismiss}
            aria-label="Close notification"
            title="Close"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* Description text */}
      <p
        className="hm-description"
        style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
        onClick={() => {
          if (onSelectTab) {
            onSelectTab('alerts');
            onDismiss();
          }
        }}
        title="Click to view alerts incident log"
      >
        {notification.spokenText || notification.message}
      </p>
    </div>
  );
}
