import { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import { formatAiText, RenderAiActions } from '../utils/aiActions';

// In-line SVG Icons matching Cloudflare / Command Palette reference design
function SearchIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function AnalyticsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
      <path d="M22 12A10 10 0 0 0 12 2v10z" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function SparklesIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3z" />
      <path d="M5 3v4M3 5h4M19 17v4M17 19h4" />
    </svg>
  );
}

function AccessIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
      <polyline points="10 17 15 12 10 7" />
      <line x1="15" y1="12" x2="3" y2="12" />
    </svg>
  );
}

function AigIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="6" height="6" rx="1" />
      <rect x="16" y="2" width="6" height="6" rx="1" />
      <rect x="9" y="16" width="6" height="6" rx="1" />
      <path d="M5 8v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8" />
      <line x1="12" y1="13" x2="12" y2="16" />
    </svg>
  );
}

function AisIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="5" />
      <path d="m21 21-4.3-4.3" />
      <path d="M11 2a9 9 0 0 1 9 9" />
    </svg>
  );
}

function ContainersIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  );
}

function CameraIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 10l5-3v10l-5-3" />
      <rect x="1" y="6" width="14" height="12" rx="2" />
    </svg>
  );
}

function CarIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 16H9m10 0h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2l-3-4H7L4 9a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h1" />
      <circle cx="7" cy="16.5" r="2.5" />
      <circle cx="17" cy="16.5" r="2.5" />
    </svg>
  );
}

function IncidentShieldIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function FenceIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

function ThreadsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
      <circle cx="8" cy="6" r="2" fill="currentColor" />
      <circle cx="16" cy="12" r="2" fill="currentColor" />
      <circle cx="10" cy="18" r="2" fill="currentColor" />
    </svg>
  );
}

export function GlobalSearchModal({
  isOpen,
  onClose,
  cameras = [],
  events = [],
  tracks = [],
  alerts = [],
  onSelectTab,
  onInvestigate,
}) {
  const [query, setQuery] = useState('');
  const [aiResult, setAiResult] = useState(null);
  const [aiData, setAiData] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 40);
    } else {
      setQuery('');
      setAiResult(null);
      setAiData(null);
      setSelectedIndex(0);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handlers = {
    onInvestigate: (evt) => {
      onClose();
      if (onInvestigate) onInvestigate(evt);
    },
    onSelectTab: (tab, trackId = null) => {
      onClose();
      if (onSelectTab) onSelectTab(tab, trackId);
    },
  };

  const handleAskAi = async (forcedQuery = null) => {
    const q = (forcedQuery || query).trim();
    if (!q || aiLoading) return;
    setAiLoading(true);
    setAiResult(null);
    setAiData(null);
    try {
      const res = await api.askAi(q);
      setAiResult(res.answer || 'No AI intelligence found.');
      setAiData(res);
    } catch (err) {
      setAiResult(`Error querying AI: ${err.message}`);
    } finally {
      setAiLoading(false);
    }
  };

  const qLower = query.trim().toLowerCase();

  // Navigation pages list
  const pagesList = [
    { title: 'Overview', category: 'Surveillance telemetry', tab: 'overview', icon: <AnalyticsIcon /> },
    { title: 'Incidents', category: 'Developing situations', tab: 'incidents', icon: <IncidentShieldIcon /> },
    { title: 'Live Feeds', category: 'All cameras & RTSP', tab: 'feeds', icon: <CameraIcon /> },
    { title: 'Activity Threads', category: 'Track storylines', tab: 'threads', icon: <DocIcon /> },
    { title: 'Events', category: 'Forensic detection log', tab: 'events', icon: <DocIcon /> },
    { title: 'Evidence Locker', category: 'Forensic captures & ANPR', tab: 'evidence', icon: <CarIcon /> },
    { title: 'Spatial Fencing', category: 'Zones & perimeter', tab: 'fencing', icon: <GlobeIcon /> },
    { title: 'Members', category: 'Manage account', tab: 'settings', icon: <GearIcon /> },
    { title: 'Settings', category: 'System configuration', tab: 'settings', icon: <GearIcon /> },
    { title: 'Audit Logs', category: 'Security audit trail', tab: 'logs', icon: <DocIcon /> },
  ];

  const filteredPages = qLower
    ? pagesList.filter(
        (p) =>
          p.title.toLowerCase().includes(qLower) ||
          p.category.toLowerCase().includes(qLower)
      )
    : [];

  const filteredCameras = qLower
    ? cameras.filter(
        (c) =>
          c.name?.toLowerCase().includes(qLower) ||
          c.camera_id?.toLowerCase().includes(qLower) ||
          c.location?.toLowerCase().includes(qLower)
      )
    : [];

  const filteredEvents = qLower
    ? events.filter((e) => {
        const vi = e.attributes?.vehicle_intelligence;
        return (
          e.event_id?.toLowerCase().includes(qLower) ||
          e.event_type?.toLowerCase().includes(qLower) ||
          e.description?.toLowerCase().includes(qLower) ||
          e.camera_id?.toLowerCase().includes(qLower) ||
          vi?.type?.toLowerCase().includes(qLower) ||
          vi?.color?.toLowerCase().includes(qLower) ||
          vi?.vehicle_id?.toLowerCase().includes(qLower)
        );
      })
    : [];

  const filteredTracks = qLower
    ? tracks.filter((t) => {
        const vi = t.vehicle_intelligence || t.attributes?.vehicle_intelligence;
        return (
          t.track_id?.toLowerCase().includes(qLower) ||
          t.object_type?.toLowerCase().includes(qLower) ||
          t.camera_id?.toLowerCase().includes(qLower) ||
          vi?.type?.toLowerCase().includes(qLower) ||
          vi?.color?.toLowerCase().includes(qLower) ||
          vi?.vehicle_id?.toLowerCase().includes(qLower)
        );
      })
    : [];

  const filteredAlerts = qLower
    ? alerts.filter(
        (a) =>
          a.alert_id?.toLowerCase().includes(qLower) ||
          a.message?.toLowerCase().includes(qLower) ||
          a.severity?.toLowerCase().includes(qLower)
      )
    : [];

  // Helios Menu Items for "Recents" (excluding Overview and Evidence)
  const recentsList = [
    {
      id: 'rec-incidents',
      icon: <IncidentShieldIcon />,
      title: 'Incidents',
      subtitle: 'Developing situations',
      action: () => {
        if (onSelectTab) onSelectTab('incidents');
        onClose();
      },
    },
    {
      id: 'rec-feeds',
      icon: <CameraIcon />,
      title: 'Live Feeds',
      subtitle: 'Multi-camera streams',
      action: () => {
        if (onSelectTab) onSelectTab('feeds');
        onClose();
      },
    },
    {
      id: 'rec-fencing',
      icon: <FenceIcon />,
      title: 'Perimeter Fencing',
      subtitle: 'Spatial zones & fences',
      action: () => {
        if (onSelectTab) onSelectTab('fencing');
        onClose();
      },
    },
    {
      id: 'rec-events',
      icon: <DocIcon />,
      title: 'Events',
      subtitle: 'Forensic detections',
      action: () => {
        if (onSelectTab) onSelectTab('events');
        onClose();
      },
    },
    {
      id: 'rec-alerts',
      icon: <AlertIcon />,
      title: 'Alerts',
      subtitle: 'Active security warnings',
      action: () => {
        if (onSelectTab) onSelectTab('alerts');
        onClose();
      },
    },
    {
      id: 'rec-threads',
      icon: <ThreadsIcon />,
      title: 'Activity Threads',
      subtitle: 'Track storylines',
      action: () => {
        if (onSelectTab) onSelectTab('threads');
        onClose();
      },
    },
    {
      id: 'rec-settings',
      icon: <GearIcon />,
      title: 'Settings',
      subtitle: 'System configuration',
      action: () => {
        if (onSelectTab) onSelectTab('settings');
        onClose();
      },
    },
  ];

  // Helios Search Tips & Shortcuts
  const searchTips = [
    {
      id: 'tip-1',
      icon: <SparklesIcon />,
      prefix: 'ask:',
      desc: 'Ask AI',
      onClick: () => {
        setQuery('ask: ');
        inputRef.current?.focus();
      },
    },
    {
      id: 'tip-2',
      icon: <IncidentShieldIcon />,
      prefix: 'incident:',
      desc: 'Search correlated incidents',
      onClick: () => {
        setQuery('incident: ');
        inputRef.current?.focus();
      },
    },
    {
      id: 'tip-3',
      icon: <CameraIcon />,
      prefix: 'cam:',
      desc: 'Search live cameras & locations',
      onClick: () => {
        setQuery('cam: ');
        inputRef.current?.focus();
      },
    },
    {
      id: 'tip-4',
      icon: <CarIcon />,
      prefix: 'plate:',
      desc: 'Search license plates (ANPR)',
      onClick: () => {
        setQuery('plate: ');
        inputRef.current?.focus();
      },
    },
    {
      id: 'tip-5',
      icon: <FenceIcon />,
      prefix: 'zone:',
      desc: 'Search perimeter fencing zones',
      onClick: () => {
        setQuery('zone: ');
        inputRef.current?.focus();
      },
    },
    {
      id: 'tip-6',
      icon: <ThreadsIcon />,
      prefix: 'track:',
      desc: 'Search tracked entities',
      onClick: () => {
        setQuery('track: ');
        inputRef.current?.focus();
      },
    },
    {
      id: 'tip-7',
      icon: <AlertIcon />,
      prefix: 'alert:',
      desc: 'Search security alerts',
      onClick: () => {
        setQuery('alert: ');
        inputRef.current?.focus();
      },
    },
  ];

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      if (query.trim().startsWith('ask:') || query.trim().length > 3) {
        handleAskAi();
      } else if (!query.trim() && selectedIndex !== null && recentsList[selectedIndex]) {
        recentsList[selectedIndex].action();
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev === null ? 0 : Math.min(prev + 1, recentsList.length - 1)));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev === null ? 0 : Math.max(prev - 1, 0)));
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        {/* TOP COMMAND BAR HEADER */}
        <div className="search-modal-header">
          <span style={{ color: '#71717a', display: 'flex', alignItems: 'center' }}>
            <SearchIcon />
          </span>

          <input
            ref={inputRef}
            type="text"
            placeholder="Search cameras, events, tracks, zones, or ask AI..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setAiResult(null);
              setAiData(null);
            }}
            onKeyDown={handleKeyDown}
          />

          <kbd className="cmd-esc-kbd" onClick={onClose} title="Press Escape to close">
            Esc
          </kbd>
        </div>

        {/* MODAL BODY */}
        <div className="search-modal-body">
          {/* ASK AI CARD (IF QUERY PRESENT OR USER TYPES) */}
          {query.trim() && (
            <div className="search-ai-card">
              <div className="search-ai-title">
                <SparklesIcon />
                <span>Ask HELIOS AI</span>
              </div>
              {aiLoading ? (
                <div className="search-ai-text">
                  <em>Searching surveillance database & reasoning with AI...</em>
                </div>
              ) : aiResult ? (
                <div>
                  <div className="search-ai-text">{formatAiText(aiResult, handlers)}</div>
                  {aiData && (
                    <RenderAiActions
                      actions={aiData.actions}
                      references={aiData.references}
                      handlers={handlers}
                    />
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span className="search-ai-text">Ask AI to analyze: "{query}"</span>
                  <button
                    style={{
                      background: 'var(--gold-dim)',
                      color: 'var(--gold)',
                      border: '1px solid var(--gold)',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '11.5px',
                      fontWeight: '600',
                      cursor: 'pointer',
                    }}
                    onClick={() => handleAskAi()}
                  >
                    Ask AI
                  </button>
                </div>
              )}
            </div>
          )}

          {/* QUERY EMPTY: SHOW "Recents" AND "Search tips" MATCHING THE EXACT SCREENSHOT */}
          {!query.trim() && (
            <>
              {/* SECTION: Recents */}
              <div className="cmd-section-label">Recents</div>
              {recentsList.map((item, idx) => {
                const isSelected = selectedIndex === idx;
                return (
                  <div
                    key={item.id}
                    className={`cmd-item ${isSelected ? 'active' : ''}`}
                    onClick={item.action}
                    onMouseEnter={() => setSelectedIndex(idx)}
                  >
                    <div className="cmd-item-left">
                      <span className="cmd-item-icon">{item.icon}</span>
                      <div className="cmd-item-label">
                        <span className="cmd-item-title">{item.title}</span>
                        <span className="cmd-item-dash">—</span>
                        <span className="cmd-item-sub">{item.subtitle}</span>
                      </div>
                    </div>
                    <span className="cmd-item-arrow">
                      <ArrowRightIcon />
                    </span>
                  </div>
                );
              })}

              {/* SECTION: Search tips */}
              <div className="cmd-section-label" style={{ marginTop: '10px' }}>
                Search tips
              </div>
              {searchTips.map((tip) => {
                const isAi = tip.prefix === 'ask:';
                return (
                  <div
                    key={tip.id}
                    className={`cmd-item ${isAi ? 'cmd-item-ai' : ''}`}
                    onClick={tip.onClick}
                  >
                    <div className="cmd-item-left">
                      <span className="cmd-item-icon">{tip.icon}</span>
                      <div className="cmd-item-label">
                        <span className="cmd-item-prefix">{tip.prefix}</span>
                        <span className="cmd-item-dash">—</span>
                        <span className="cmd-item-sub">{tip.desc}</span>
                      </div>
                    </div>
                    <span className="cmd-item-arrow">
                      <ArrowRightIcon />
                    </span>
                  </div>
                );
              })}
            </>
          )}

          {/* QUERY SEARCH RESULTS (WHEN USER TYPES) */}
          {query.trim() && (
            <>
              {/* MATCHING PAGES */}
              {filteredPages.length > 0 && (
                <div>
                  <div className="cmd-section-label">Pages & Views</div>
                  {filteredPages.map((p) => (
                    <div
                      key={p.title}
                      className="cmd-item"
                      onClick={() => {
                        if (onSelectTab) onSelectTab(p.tab);
                        onClose();
                      }}
                    >
                      <div className="cmd-item-left">
                        <span className="cmd-item-icon">{p.icon}</span>
                        <div className="cmd-item-label">
                          <span className="cmd-item-title">{p.title}</span>
                          <span className="cmd-item-dash">—</span>
                          <span className="cmd-item-sub">{p.category}</span>
                        </div>
                      </div>
                      <span className="cmd-item-arrow">
                        <ArrowRightIcon />
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* MATCHING CAMERAS */}
              {filteredCameras.length > 0 && (
                <div>
                  <div className="cmd-section-label">Cameras</div>
                  {filteredCameras.map((c) => (
                    <div
                      key={c.camera_id}
                      className="cmd-item"
                      onClick={() => {
                        if (onSelectTab) onSelectTab('feeds');
                        onClose();
                      }}
                    >
                      <div className="cmd-item-left">
                        <span className="cmd-item-icon">
                          <CameraIcon />
                        </span>
                        <div className="cmd-item-label">
                          <span className="cmd-item-title">{c.name}</span>
                          <span className="cmd-item-dash">—</span>
                          <span className="cmd-item-sub">{c.location} ({c.camera_id})</span>
                        </div>
                      </div>
                      <div className="cmd-item-right">
                        <span
                          className="cmd-badge"
                          style={{
                            color: c.status === 'ONLINE' ? 'var(--green)' : 'var(--red)',
                          }}
                        >
                          {c.status}
                        </span>
                        <span className="cmd-item-arrow">
                          <ArrowRightIcon />
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* MATCHING EVENTS */}
              {filteredEvents.length > 0 && (
                <div>
                  <div className="cmd-section-label">Events</div>
                  {filteredEvents.map((e) => (
                    <div
                      key={e.event_id}
                      className="cmd-item"
                      onClick={() => {
                        if (onInvestigate) onInvestigate(e);
                        else if (onSelectTab) onSelectTab('events');
                        onClose();
                      }}
                    >
                      <div className="cmd-item-left">
                        <span className="cmd-item-icon">
                          <DocIcon />
                        </span>
                        <div className="cmd-item-label">
                          <span className="cmd-item-title">{e.description || e.event_type}</span>
                          <span className="cmd-item-dash">—</span>
                          <span className="cmd-item-sub">{e.camera_id} · {e.event_id}</span>
                        </div>
                      </div>
                      <div className="cmd-item-right">
                        <span
                          className="cmd-badge"
                          style={{
                            color: e.severity === 'CRITICAL' ? 'var(--red)' : 'var(--gold)',
                          }}
                        >
                          {e.severity}
                        </span>
                        <span className="cmd-item-arrow">
                          <ArrowRightIcon />
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* MATCHING TRACKS */}
              {filteredTracks.length > 0 && (
                <div>
                  <div className="cmd-section-label">Active Tracks</div>
                  {filteredTracks.map((t) => {
                    const vi = t.vehicle_intelligence || t.attributes?.vehicle_intelligence;
                    const subLabel = vi && (vi.color || vi.type)
                      ? `${vi.color || ''} ${vi.type || ''}`.trim()
                      : t.object_type;
                    return (
                      <div
                        key={t.track_id}
                        className="cmd-item"
                        onClick={() => {
                          if (onSelectTab) onSelectTab('threads', t.track_id);
                          onClose();
                        }}
                      >
                        <div className="cmd-item-left">
                          <span className="cmd-item-icon">
                            <CarIcon />
                          </span>
                          <div className="cmd-item-label">
                            <span className="cmd-item-title">{t.track_id}</span>
                            <span className="cmd-item-dash">—</span>
                            <span className="cmd-item-sub">Camera {t.camera_id} ({subLabel})</span>
                          </div>
                        </div>
                        <div className="cmd-item-right">
                          <span className="cmd-badge">
                            {Math.round((t.average_confidence || 0.9) * 100)}%
                          </span>
                          <span className="cmd-item-arrow">
                            <ArrowRightIcon />
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* MATCHING ALERTS */}
              {filteredAlerts.length > 0 && (
                <div>
                  <div className="cmd-section-label">Alerts</div>
                  {filteredAlerts.map((a) => (
                    <div
                      key={a.alert_id}
                      className="cmd-item"
                      onClick={() => {
                        if (onSelectTab) onSelectTab('alerts');
                        onClose();
                      }}
                    >
                      <div className="cmd-item-left">
                        <span className="cmd-item-icon">
                          <IncidentShieldIcon />
                        </span>
                        <div className="cmd-item-label">
                          <span className="cmd-item-title">{a.message}</span>
                          <span className="cmd-item-dash">—</span>
                          <span className="cmd-item-sub">{a.alert_id}</span>
                        </div>
                      </div>
                      <div className="cmd-item-right">
                        <span
                          className="cmd-badge"
                          style={{
                            color: a.status === 'ACTIVE' ? 'var(--red)' : 'var(--gold)',
                          }}
                        >
                          {a.status}
                        </span>
                        <span className="cmd-item-arrow">
                          <ArrowRightIcon />
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* NO RESULTS */}
              {filteredPages.length === 0 &&
                filteredCameras.length === 0 &&
                filteredEvents.length === 0 &&
                filteredTracks.length === 0 &&
                filteredAlerts.length === 0 &&
                !aiResult &&
                !aiLoading && (
                  <div style={{ textAlign: 'center', padding: '36px 0', color: '#71717a', fontSize: '13px' }}>
                    No exact matches for "{query}". Press <kbd className="cmd-esc-kbd">Enter</kbd> to ask HELIOS AI.
                  </div>
                )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
