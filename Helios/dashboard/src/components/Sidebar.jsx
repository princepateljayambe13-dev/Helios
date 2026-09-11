import { useState } from 'react';
import { CloseIcon, IncidentIcon, InsightsIcon, FaceIcon } from './Icons';

export function Sidebar({
  activeTab,
  setActiveTab,
  eventsCategory = 'all',
  onSelectEventsCategory,
  camerasCount,
  eventsCount,
  trackedEventsCount,
  zoneEventsCount,
  alertsCount,
  evidenceCount,
  threadsCount,
  facesCount = 0,
  incidentsCount = 0,
  insightsCount = 0,
  isOpen = false,
  onClose,
}) {
  const [eventsOpen, setEventsOpen] = useState(true);
  const [alertsOpen, setAlertsOpen] = useState(true);

  const handleNav = (tab, category = null) => {
    if (category && onSelectEventsCategory) {
      onSelectEventsCategory(category);
    }
    setActiveTab(tab);
    if (onClose) onClose();
  };

  const handleEventsClick = () => {
    if (activeTab !== 'events') {
      setActiveTab('events');
      setEventsOpen(true);
      if (onClose) onClose();
    } else {
      setEventsOpen((prev) => !prev);
    }
  };

  const handleAlertsClick = () => {
    if (activeTab !== 'alerts' && activeTab !== 'logs') {
      setActiveTab('alerts');
      setAlertsOpen(true);
      if (onClose) onClose();
    } else {
      setAlertsOpen((prev) => !prev);
    }
  };

  return (
    <>
      {/* Mobile Drawer Dimmed Backdrop */}
      <div
        className={`sidebar-backdrop ${isOpen ? 'open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />

      <div className={`sidebar ${isOpen ? 'mobile-open' : ''}`}>
        {/* Mobile-only Drawer Header */}
        <div className="sidebar-mobile-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="brand-mark" style={{ width: '24px', height: '24px' }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            </div>
            <span style={{ fontSize: '13px', fontWeight: '700', letterSpacing: '0.5px' }}>HELIOS MENU</span>
          </div>
          <button
            className="sidebar-close-btn"
            onClick={onClose}
            aria-label="Close navigation menu"
            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
          >
            <CloseIcon size={14} />
          </button>

        </div>

        <div className="nav-group">
          <div
            className={`nav-item ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => handleNav('overview')}
          >
          <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="9" />
              <rect x="14" y="3" width="7" height="5" />
              <rect x="14" y="12" width="7" height="9" />
              <rect x="3" y="16" width="7" height="5" />
            </svg>
            Overview
          </span>
        </div>

        <div
          className={`nav-item ${activeTab === 'feeds' ? 'active' : ''}`}
          onClick={() => handleNav('feeds')}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 10l5-3v10l-5-3" />
              <rect x="1" y="6" width="14" height="12" rx="2" />
            </svg>
            Live Feeds
          </span>
          <span className="nav-badge neutral">{camerasCount}</span>
        </div>

        <div
          className={`nav-item ${activeTab === 'fencing' ? 'active' : ''}`}
          onClick={() => handleNav('fencing')}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="12 2 2 7 12 12 22 7 12 2" />
              <polyline points="2 17 12 22 22 17" />
              <polyline points="2 12 12 17 22 12" />
            </svg>
            Perimeter Fencing
          </span>
        </div>

        <div className="nav-item-expandable">
          <div
            className={`nav-item ${activeTab === 'events' ? 'active' : ''}`}
            onClick={handleEventsClick}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
                <path d="M22 12A10 10 0 0 0 12 2v10z" />
              </svg>
              Events
            </span>
            <span
              className={`nav-chevron-btn ${eventsOpen ? 'open' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                setEventsOpen((prev) => !prev);
              }}
              title={eventsOpen ? 'Collapse events' : 'Expand events'}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </span>
          </div>

          {eventsOpen && (
            <div className="nav-subgroup">
              <div
                className={`nav-sub-item ${activeTab === 'events' && eventsCategory === 'all' ? 'active' : ''}`}
                onClick={() => handleNav('events', 'all')}
              >
                <div className="nav-sub-label">
                  <span>All events</span>
                  {eventsCount > 0 && <span className="nav-badge-dashed">New</span>}
                </div>
              </div>

              <div
                className={`nav-sub-item ${activeTab === 'events' && eventsCategory === 'tracked' ? 'active' : ''}`}
                onClick={() => handleNav('events', 'tracked')}
              >
                <div className="nav-sub-label">
                  <span>Tracked events</span>
                </div>
              </div>

              <div
                className={`nav-sub-item ${activeTab === 'events' && eventsCategory === 'zone' ? 'active' : ''}`}
                onClick={() => handleNav('events', 'zone')}
              >
                <div className="nav-sub-label">
                  <span>Zone events</span>
                </div>
              </div>
            </div>
          )}
        </div>


        <div
          className={`nav-item ${activeTab === 'insights' ? 'active' : ''}`}
          onClick={() => handleNav('insights')}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <InsightsIcon size={15} />
            <span>Insights</span>
            <span
              className="beta-pill"
              style={{
                color: 'var(--gold, #C99A5B)',
                borderColor: 'rgba(201, 154, 91, 0.4)',
                background: 'var(--gold-dim, #241B14)',
                fontWeight: '600',
              }}
            >
              New
            </span>
          </span>
          {insightsCount > 0 && (
            <span
              className="nav-badge"
              style={{
                background: 'var(--gold, #C99A5B)',
                color: '#101010',
                fontWeight: '700',
              }}
            >
              {insightsCount}
            </span>
          )}
        </div>

        <div
          className={`nav-item ${activeTab === 'incidents' ? 'active' : ''}`}
          onClick={() => handleNav('incidents')}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <IncidentIcon size={15} />
            <span>Incidents</span>
            <span className="beta-pill">Beta</span>
          </span>
          {incidentsCount > 0 && (
            <span
              className="nav-badge"
              style={{
                background: 'var(--red)',
                color: '#ffffff',
                fontWeight: '700',
              }}
            >
              {incidentsCount}
            </span>
          )}
        </div>

        <div className="nav-item-expandable">
          <div
            className={`nav-item ${activeTab === 'alerts' || (activeTab === 'logs' && !alertsOpen) ? 'active' : ''}`}
            onClick={handleAlertsClick}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                <path d="M12 9v4M12 17h.01" />
              </svg>
              Alerts
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              {alertsCount > 0 && <span className="nav-badge">{alertsCount}</span>}
              <span
                className={`nav-chevron-btn ${alertsOpen ? 'open' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setAlertsOpen((prev) => !prev);
                }}
                title={alertsOpen ? 'Collapse alerts' : 'Expand alerts'}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </span>
            </div>
          </div>

          {alertsOpen && (
            <div className="nav-subgroup">
              <div
                className={`nav-sub-item ${activeTab === 'alerts' ? 'active' : ''}`}
                onClick={() => handleNav('alerts')}
              >
                <div className="nav-sub-label">
                  <span>All alerts</span>
                  {alertsCount > 0 && <span className="nav-badge">{alertsCount}</span>}
                </div>
              </div>

              <div
                className={`nav-sub-item ${activeTab === 'logs' ? 'active' : ''}`}
                onClick={() => handleNav('logs')}
              >
                <div className="nav-sub-label">
                  <span>Audit logs</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div
          className={`nav-item ${activeTab === 'evidence' ? 'active' : ''}`}
          onClick={() => handleNav('evidence')}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="9" cy="9" r="2" />
              <path d="m21 15-5-5L5 21" />
            </svg>
            Evidence
          </span>
          <span className="nav-badge neutral">{evidenceCount || 0}</span>
        </div>

        <div
          className={`nav-item ${activeTab === 'threads' ? 'active' : ''}`}
          onClick={() => handleNav('threads')}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 3v12" />
              <circle cx="18" cy="6" r="3" />
              <circle cx="6" cy="18" r="3" />
              <path d="M18 9a9 9 0 0 1-9 9" />
            </svg>
            Activity Threads
          </span>
          <span className="nav-badge neutral">{threadsCount || 0}</span>
        </div>

        <div
          className={`nav-item ${activeTab === 'facial-recognition' ? 'active' : ''}`}
          onClick={() => handleNav('facial-recognition')}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <FaceIcon size={15} />
            Face Recognition
          </span>
          {facesCount > 0 && <span className="nav-badge neutral">{facesCount}</span>}
        </div>
      </div>

      <div className="nav-group">
        <div className="nav-label">Configuration</div>
        <div
          className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => handleNav('settings')}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
            </svg>
            Settings
          </span>
        </div>
      </div>
    </div>
    </>
  );
}
