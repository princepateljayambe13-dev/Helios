import { useState, useRef, useEffect } from 'react';
import { api } from '../services/api';
import { formatAiText, RenderAiActions } from '../utils/aiActions';
import { CameraIcon, AiSparklesIcon, FaceIcon } from './Icons';
import { SpatialGridBackground } from './SpatialGridBackground';
import logoImg from '../assets/89AAFAAC-3B6A-4DE1-B2E3-0BFA195F4A6F_1_201_a-Photoroom copy.png';


function ChatMessageButtons({ message, handlers, liveEvents = [], liveCameras = [] }) {
  const [showGotoMenu, setShowGotoMenu] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!showGotoMenu) return;
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setShowGotoMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showGotoMenu]);

  const text = message.text || '';
  const actions = message.actions || [];
  const references = message.references || [];

  // Extract Event IDs
  const eventIds = new Set();
  actions.forEach((a) => { if (a.event_id) eventIds.add(a.event_id); });
  references.forEach((r) => { if (r.event_id) eventIds.add(r.event_id); });
  const textEvents = text.match(/\bEVT-[A-Z0-9]{4,12}\b/g) || [];
  textEvents.forEach((id) => eventIds.add(id));
  const detectedEventId = Array.from(eventIds)[0];
  const targetEvent = detectedEventId
    ? { event_id: detectedEventId }
    : (liveEvents.length > 0 ? liveEvents[0] : null);

  // Extract Camera IDs
  const cameraIds = new Set();
  actions.forEach((a) => { if (a.camera_id) cameraIds.add(a.camera_id); });
  references.forEach((r) => { if (r.camera_id) cameraIds.add(r.camera_id); });
  const textCams = text.match(/\bCAM-\d+\b/g) || [];
  textCams.forEach((id) => cameraIds.add(id));
  const primaryCameraId = Array.from(cameraIds)[0];

  // Extract Track IDs
  const trackIds = new Set();
  actions.forEach((a) => { if (a.track_id) trackIds.add(a.track_id); });
  references.forEach((r) => { if (r.track_id) trackIds.add(r.track_id); });
  const textTracks = text.match(/#[A-Z]-[A-Z0-9]{4,12}\b/g) || [];
  textTracks.forEach((id) => trackIds.add(id));
  const primaryTrackId = Array.from(trackIds)[0];

  // Extract Evidence IDs
  const evidenceIds = new Set();
  actions.forEach((a) => { if (a.evidence_id) evidenceIds.add(a.evidence_id); });
  references.forEach((r) => { if (r.evidence_id) evidenceIds.add(r.evidence_id); });
  const textEvd = text.match(/\bEVD-[A-Z0-9]{4,12}\b/g) || [];
  textEvd.forEach((id) => evidenceIds.add(id));
  const primaryEvidenceId = Array.from(evidenceIds)[0];

  // Extract Alert IDs
  const alertIds = new Set();
  actions.forEach((a) => { if (a.alert_id) alertIds.add(a.alert_id); });
  references.forEach((r) => { if (r.alert_id) alertIds.add(r.alert_id); });
  const textAlts = text.match(/\bALT-[A-Z0-9]{4,12}\b/g) || [];
  textAlts.forEach((id) => alertIds.add(id));

  // Extract Face / Recognition / Person IDs
  const faceIds = new Set();
  actions.forEach((a) => {
    if (a.recognition_id) faceIds.add(a.recognition_id);
    if (a.person_id) faceIds.add(a.person_id);
    if (a.type === 'OPEN_FACE_DIRECTORY' || a.type === 'VIEW_FACE_RECOGNITION') faceIds.add('face-rec');
  });
  references.forEach((r) => {
    if (r.recognition_id) faceIds.add(r.recognition_id);
    if (r.person_id) faceIds.add(r.person_id);
  });
  const textFaces = text.match(/\b(FAC-[A-Z0-9]{4,12}|PRN-[A-Z0-9]{4,12})\b/g) || [];
  textFaces.forEach((id) => faceIds.add(id));
  const hasFaceIntent = faceIds.size > 0 || /\b(face|faces|biometric|arcface|facial recognition|recognized person)\b/i.test(text);

  // Determine smart primary destination for "Go to"
  let primaryGoto = { tab: 'events', label: 'Go to Events' };
  if (hasFaceIntent) {
    primaryGoto = { tab: 'face-recognition', label: 'Go to Face Recognition' };
  } else if (primaryCameraId) {
    primaryGoto = { tab: 'feeds', label: `Go to ${primaryCameraId}` };
  } else if (primaryTrackId) {
    primaryGoto = { tab: 'threads', trackId: primaryTrackId, label: `Go to Track ${primaryTrackId}` };
  } else if (primaryEvidenceId) {
    primaryGoto = { tab: 'evidence', label: 'Go to Evidence' };
  } else if (alertIds.size > 0) {
    primaryGoto = { tab: 'alerts', label: 'Go to Alerts' };
  } else if (detectedEventId) {
    primaryGoto = { tab: 'events', label: `Go to Events (${detectedEventId})` };
  } else if (/zone|fence|perimeter|boundary|intrusion/i.test(text)) {
    primaryGoto = { tab: 'fencing', label: 'Go to Fencing' };
  }

  const handleInvestigateClick = (e) => {
    e.stopPropagation();
    if (targetEvent && handlers.onInvestigate) {
      handlers.onInvestigate(targetEvent);
    } else if (handlers.onSelectTab) {
      handlers.onSelectTab('events');
    }
  };

  const handleGotoClick = (tab, trackId = null) => {
    setShowGotoMenu(false);
    if (handlers.onSelectTab) {
      handlers.onSelectTab(tab, trackId);
    }
  };

  return (
    <div className="ai-msg-actions-bar">
      {/* INVESTIGATE BUTTON */}
      <button
        type="button"
        className="n-btn ai-investigate ai-msg-action-btn"
        title={detectedEventId ? `Investigate ${detectedEventId} with HELIOS AI` : "Investigate security incidents with HELIOS AI"}
        onClick={handleInvestigateClick}
      >
        <AiSparklesIcon size={12} />
        <span>{detectedEventId ? `Investigate ${detectedEventId}` : "Investigate"}</span>
      </button>

      {/* GO-TO BUTTON */}
      <div className="ai-goto-wrapper" ref={menuRef}>
        <div className="ai-goto-btn-group">
          <button
            type="button"
            className="n-btn ai-goto-btn ai-msg-action-btn"
            title={`Navigate to ${primaryGoto.label}`}
            onClick={() => handleGotoClick(primaryGoto.tab, primaryGoto.trackId)}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 17L17 7M7 7h10v10" />
            </svg>
            <span>{primaryGoto.label}</span>
          </button>
          <button
            type="button"
            className="ai-goto-dropdown-toggle"
            title="More Go-to views"
            aria-label="More Go-to views"
            onClick={(e) => {
              e.stopPropagation();
              setShowGotoMenu((prev) => !prev);
            }}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        </div>

        {/* POPUP DESTINATIONS */}
        {showGotoMenu && (
          <div className="ai-goto-menu">
            <div className="ai-goto-menu-header">Jump To</div>
            {primaryCameraId && (
              <div className="ai-goto-menu-item" onClick={() => handleGotoClick('feeds')}>
                <span className="dot online"></span>
                <span>Camera Stream ({primaryCameraId})</span>
              </div>
            )}
            {primaryTrackId && (
              <div className="ai-goto-menu-item" onClick={() => handleGotoClick('threads', primaryTrackId)}>
                <span className="dot gold"></span>
                <span>Activity Track ({primaryTrackId})</span>
              </div>
            )}
            <div className="ai-goto-menu-item" onClick={() => handleGotoClick('events')}>
              <span className="dot"></span>
              <span>Forensic Events Log</span>
            </div>
            <div className="ai-goto-menu-item" onClick={() => handleGotoClick('feeds')}>
              <span className="dot"></span>
              <span>Live Camera Feeds</span>
            </div>
            <div className="ai-goto-menu-item" onClick={() => handleGotoClick('threads')}>
              <span className="dot"></span>
              <span>Activity Threads</span>
            </div>
            <div className="ai-goto-menu-item" onClick={() => handleGotoClick('evidence')}>
              <span className="dot"></span>
              <span>Evidence Vault</span>
            </div>
            <div className="ai-goto-menu-item" onClick={() => handleGotoClick('alerts')}>
              <span className="dot alert"></span>
              <span>Active Alerts</span>
            </div>
            <div className="ai-goto-menu-item" onClick={() => handleGotoClick('fencing')}>
              <span className="dot"></span>
              <span>Spatial Fencing</span>
            </div>
            <div className="ai-goto-menu-item" onClick={() => handleGotoClick('face-recognition')}>
              <span className="dot" style={{ background: '#ec4899' }}></span>
              <span>Facial Recognition</span>
            </div>
            <div className="ai-goto-menu-item" onClick={() => handleGotoClick('incidents')}>
              <span className="dot"></span>
              <span>Incidents Overview</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


export function AskAiPopup({
  isOpen,
  initialTab = 'chat',
  onToggle,
  onClose,
  onInvestigate,
  onSelectTab,
  events = [],
  cameras = [],
}) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [input, setInput] = useState('');
  const username = localStorage.getItem('helios_user') || sessionStorage.getItem('helios_user') || 'Operator';
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showToolGotoMenu, setShowToolGotoMenu] = useState(false);

  // Daily Brief state
  const [brief, setBrief] = useState(null);
  const [briefLoading, setBriefLoading] = useState(false);

  const chatEndRef = useRef(null);
  const panelRef = useRef(null);
  const inputRef = useRef(null);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  const suggestions = [
    {
      title: 'Summarize today',
      sub: 'Roll up events across every zone',
      prompt: 'Summarize the last 24 hours across all zones',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 12h4l3 8 4-16 3 8h4" />
        </svg>
      ),
    },
    {
      title: 'Top threats',
      sub: 'Rank active alerts by severity',
      prompt: 'What are the top threats detected right now?',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2 2 7v6c0 5 4 8.5 10 9 6-.5 10-4 10-9V7l-10-5z" />
          <path d="M12 8v5M12 16.5v.1" />
        </svg>
      ),
    },
    {
      title: 'Camera status',
      sub: 'Vehicle Lane — recent activity',
      prompt: 'Show status and recent events for CAM-02',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="6" width="13" height="12" rx="2" />
          <path d="M16 10.5 21 7v10l-5-3.5z" />
        </svg>
      ),
    },
    {
      title: 'Recognized faces',
      sub: 'Biometric identity & ArcFace log',
      prompt: 'Who has been recognized today and are there any unclassified faces?',
      icon: <FaceIcon size={16} />,
    },
    {
      title: 'Generate report',
      sub: 'Export a shift incident summary',
      prompt: 'Generate an incident report for the last shift',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6M9 13h6M9 17h6" />
        </svg>
      ),
    },
    {
      title: 'Restricted-zone entries',
      sub: 'Review access-control breaches',
      prompt: 'List every restricted-zone entry from the last 24 hours',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4" y="10" width="16" height="10" rx="2" />
          <path d="M8 10V7a4 4 0 0 1 8 0v3" />
        </svg>
      ),
    },
    {
      title: 'Search footage',
      sub: 'Find events by camera, time or object',
      prompt: 'Find footage of vehicles at the North Gate in the last hour',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>
      ),
    },
  ];

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

  const fetchBrief = () => {
    setBriefLoading(true);
    api
      .getDayBrief()
      .then((data) => setBrief(data))
      .catch((err) => setBrief({ activity_summary: `Failed to load briefing: ${err.message}` }))
      .finally(() => setBriefLoading(false));
  };

  // Sync activeTab when opening or initialTab changes
  useEffect(() => {
    if (isOpen) {
      const targetTab = initialTab || 'chat';
      setActiveTab(targetTab);
      if (targetTab === 'brief' && !brief) {
        fetchBrief();
      }
    }
  }, [isOpen, initialTab]);

  // Focus textarea when panel opens in chat mode
  useEffect(() => {
    if (isOpen && activeTab === 'chat') {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 200);
    }
  }, [isOpen, activeTab]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Cursor glow effect on docked panel
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;

    let pending = false;
    let lastX = 0;
    let lastY = 0;

    const apply = () => {
      panel.style.setProperty('--pcx', `${lastX}px`);
      panel.style.setProperty('--pcy', `${lastY}px`);
      pending = false;
    };

    const handleMouseMove = (e) => {
      const rect = panel.getBoundingClientRect();
      lastX = e.clientX - rect.left;
      lastY = e.clientY - rect.top;
      if (!pending) {
        pending = true;
        window.requestAnimationFrame(apply);
      }
    };

    const handleMouseLeave = () => {
      panel.style.setProperty('--pcx', '92%');
      panel.style.setProperty('--pcy', '16%');
    };

    panel.addEventListener('mousemove', handleMouseMove, { passive: true });
    panel.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      panel.removeEventListener('mousemove', handleMouseMove);
      panel.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, []);

  // Auto-scroll chat history
  useEffect(() => {
    if (activeTab === 'chat' && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading, activeTab]);

  const handleReset = () => {
    setMessages([]);
    setInput('');
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  };

  const handleSend = async (textToSend) => {
    const query = (textToSend || input).trim();
    if (!query || loading) return;

    if (activeTab !== 'chat') {
      setActiveTab('chat');
    }

    setInput('');
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    const userMsg = { sender: 'user', text: query };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const history = messages
        .filter((m) => m.text)
        .map((m) => ({
          role: m.sender === 'user' ? 'user' : 'model',
          content: m.text,
          reasoning_details: m.reasoning_details || undefined,
        }));

      const res = await api.askAi(query, history);

      const botMsg = {
        sender: 'bot',
        text: res.answer || 'No response available from intelligence service.',
        grounded: res.grounded,
        claims: res.claims || [],
        actions: res.actions || [],
        references: res.references || [],
        reasoning_details: res.reasoning_details,
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { sender: 'bot', text: `System Error: Unable to reach AI intelligence backend (${err.message}).` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* AI OVERLAY */}
      <div
        className={`ai-overlay ${isOpen ? 'open' : ''}`}
        id="aiOverlay"
        onClick={onClose}
      />

      {/* AI INTELLIGENCE PANEL (docked) */}
      <div
        className={`ai-panel ${isOpen ? 'open' : ''}`}
        id="aiPanel"
        role="dialog"
        aria-label="HELIOS AI Intelligence Assistant"
        ref={panelRef}
      >
        {/* SPATIAL 3D INTERACTIVE GRID BACKGROUND */}
        <SpatialGridBackground active={isOpen} containerRef={panelRef} />

        {/* PANEL HEADER */}
        <div className="ai-panel-head">
          <div className="ai-panel-head-left">
            <div className="ai-panel-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
                <path d="M19 3.2v3.1M17.45 4.75h3.1" />
              </svg>
            </div>
            <div className="ai-panel-titles">
              <div className="ai-panel-title-row">
                <span className="ai-panel-title">Helios AI</span>
                {activeTab === 'chat' ? (
                  <span
                    className="ai-panel-session"
                    onClick={handleReset}
                    title="Start new session"
                    style={{ cursor: 'pointer' }}
                  >
                    New session
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </span>
                ) : (
                  <span
                    className="ai-panel-session"
                    onClick={fetchBrief}
                    title="Refresh 24H daily briefing"
                    style={{ cursor: 'pointer' }}
                  >
                    <span className="dot" style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#d5b18a', boxShadow: '0 0 6px rgba(213, 177, 138, 0.8)' }}></span>
                    24H Digest
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '9px', height: '9px' }}>
                      <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                    </svg>
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="ai-panel-actions">
            {activeTab === 'brief' && (
              <button
                className="ai-panel-icon-btn"
                onClick={fetchBrief}
                title="Refresh daily brief"
                aria-label="Refresh daily brief"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                </svg>
              </button>
            )}
            {activeTab === 'chat' && (
              <button className="ai-panel-icon-btn" id="aiPanelNew" onClick={handleReset} title="New conversation" aria-label="New conversation">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
            )}
            <button className="ai-panel-icon-btn" id="aiPanelClose" onClick={onClose} title="Close" aria-label="Close AI assistant">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
        </div>

        {/* TACTICAL TAB SWITCHER: CHAT VS DAILY BRIEF */}
        <div className="ai-panel-tabs">
          <button
            type="button"
            className={`ai-panel-tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span>Intelligence Chat</span>
          </button>
          <button
            type="button"
            className={`ai-panel-tab-btn ${activeTab === 'brief' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('brief');
              if (!brief && !briefLoading) fetchBrief();
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
            </svg>
            <span>Daily Brief</span>
          </button>
        </div>

        {/* PANEL BODY */}
        <div className="ai-panel-body" id="aiPanelBody">
          {activeTab === 'chat' ? (
            /* CHAT MODE */
            messages.length === 0 ? (
              <div id="aiIntroState">
                <div className="ai-panel-emblem-wrap">
                  <div className="ai-panel-emblem">
                    <img src={logoImg} alt="HELIOS shield" />
                  </div>
                </div>
                <div className="ai-panel-greet">
                  <div className="ai-panel-greet-title" id="aiGreetTitle">{greeting}, {username}.</div>
                  <div className="ai-panel-greet-sub">What are we watching for today?</div>
                </div>

                <div className="ai-panel-suggestions">
                  {suggestions.map((item, idx) => (
                    <div
                      key={idx}
                      className="ai-suggestion"
                      data-prompt={item.prompt}
                      onClick={() => handleSend(item.prompt)}
                    >
                      <div className="ai-suggestion-icon">
                        {item.icon}
                      </div>
                      <div className="ai-suggestion-text">
                        <div className="ai-suggestion-title">{item.title}</div>
                        <div className="ai-suggestion-sub">{item.sub}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="ai-panel-messages" id="aiPanelMessages">
                {messages.map((m, idx) => (
                  <div key={idx} className={`ai-msg ${m.sender === 'user' ? 'user' : ''}`}>
                    <div className="ai-msg-avatar">
                      {m.sender === 'user' ? (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                          <circle cx="12" cy="7" r="4" />
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
                        </svg>
                      )}
                    </div>
                    <div className="ai-msg-bubble">
                      {m.sender === 'user' ? (
                        m.text
                      ) : (
                        <>
                          <div>{formatAiText(m.text, handlers)}</div>

                          {/* DEDICATED INVESTIGATE & GO-TO ACTION BUTTONS */}
                          <ChatMessageButtons
                            message={m}
                            handlers={handlers}
                            liveEvents={events}
                            liveCameras={cameras}
                          />

                          {(m.actions?.length > 0 || m.references?.length > 0) && (
                            <RenderAiActions actions={m.actions} references={m.references} handlers={handlers} />
                          )}
                        </>
                      )}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="ai-msg">
                    <div className="ai-msg-avatar">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
                      </svg>
                    </div>
                    <div className="ai-msg-bubble">
                      <em>Analyzing HELIOS sensor streams & intelligence records...</em>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )
          ) : (
            /* DAILY BRIEF MODE */
            <div className="ai-brief-container">
              {briefLoading ? (
                <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-low)' }}>
                  <div className="daily-brief-icon" style={{ margin: '0 auto 14px', width: '42px', height: '42px' }}>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
                    </svg>
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-hi)', fontWeight: 600, marginBottom: '6px' }}>
                    Synthesizing Daily Intelligence
                  </div>
                  <div style={{ fontSize: '11.5px', color: 'var(--text-low)', maxWidth: '280px', margin: '0 auto', lineHeight: 1.5 }}>
                    Aggregating 24-hour multi-camera streams, intrusion events & evidence records...
                  </div>
                </div>
              ) : brief ? (
                <>
                  {/* BRIEF HEADER CARD */}
                  <div className="ai-brief-header-card">
                    <div className="ai-brief-header-top">
                      <div className="ai-brief-title-wrap">
                        <div className="ai-brief-title">24H Tactical Briefing</div>
                        <div className="ai-brief-subtext">
                          HELIOS Grounded Agent · {brief.date || 'Today'} · {brief.ai_model || 'v1.0-grounded'}
                        </div>
                      </div>
                      <div className="ai-brief-status-pill">
                        <span className="ai-brief-pulse-dot"></span>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
                        </svg>
                        <span>AI Synthesized</span>
                      </div>
                    </div>

                    <div className="ai-brief-telemetry-row">
                      <div className="ai-brief-telemetry-item">
                        <span className="ai-brief-telemetry-label">Analysis Mode</span>
                        <span className="ai-brief-telemetry-val">Autonomous Grounded</span>
                      </div>
                      <div className="ai-brief-telemetry-item">
                        <span className="ai-brief-telemetry-label">Streams Scanned</span>
                        <span className="ai-brief-telemetry-val">{brief?.stats?.cameras_total || 4} Feeds</span>
                      </div>
                      <div className="ai-brief-telemetry-item">
                        <span className="ai-brief-telemetry-label">Time Horizon</span>
                        <span className="ai-brief-telemetry-val">24H Window</span>
                      </div>
                    </div>
                  </div>

                  {/* OPERATIONAL OVERVIEW */}
                  <div className="tile" style={{ padding: '14px', background: 'rgba(20,20,20,0.6)' }}>
                    <div className="n-col-label" style={{ color: 'var(--gold)', marginBottom: '6px' }}>
                      Operational Overview
                    </div>
                    <div style={{ fontSize: '12.5px', color: 'var(--text-hi)', lineHeight: '1.55' }}>
                      {formatAiText(brief.activity_summary, handlers)}
                    </div>
                  </div>

                  {/* STATS HUD */}
                  {brief.stats && (
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(2, 1fr)',
                        gap: '8px',
                      }}
                    >
                      <div className="stat-cell" style={{ cursor: 'pointer' }} onClick={() => handlers.onSelectTab('events')}>
                        <div className="sc-label">Total Events</div>
                        <div className="sc-value">{brief.stats.total_events || 0}</div>
                      </div>
                      <div className="stat-cell" style={{ cursor: 'pointer' }} onClick={() => handlers.onSelectTab('feeds')}>
                        <div className="sc-label">Cameras Online</div>
                        <div className="sc-value">
                          {brief.stats.cameras_online}/{brief.stats.cameras_total}
                        </div>
                      </div>
                      <div className="stat-cell" style={{ cursor: 'pointer' }} onClick={() => handlers.onSelectTab('alerts')}>
                        <div className="sc-label">Active Alerts</div>
                        <div className="sc-value" style={{ color: 'var(--red)' }}>
                          {brief.stats.active_alerts || 0}
                        </div>
                      </div>
                      <div className="stat-cell" style={{ cursor: 'pointer' }} onClick={() => handlers.onSelectTab('evidence')}>
                        <div className="sc-label">Evidence Cached</div>
                        <div className="sc-value" style={{ color: 'var(--gold)' }}>
                          {brief.stats.evidence_count || 30}/30
                        </div>
                      </div>
                    </div>
                  )}

                  {/* CRITICAL INTRUSION INCIDENTS */}
                  {brief.significant_events && brief.significant_events.length > 0 && (
                    <div>
                      <div className="n-col-label" style={{ marginBottom: '8px' }}>
                        Critical Intrusion Incidents ({brief.significant_events.length})
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        {brief.significant_events.map((evt, idx) => (
                          <div key={idx} className="tile n-tile critical" style={{ padding: '12px' }}>
                            <div className="n-head" style={{ marginBottom: '6px', flexWrap: 'wrap', gap: '6px' }}>
                              <div className="n-head-left">
                                <span className="n-id">{evt.event_id || `EVT-INC-${idx + 1}`}</span>
                                <span className="n-chip critical">{evt.severity || 'CRITICAL'}</span>
                                <span style={{ fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                                  {evt.camera_id}
                                </span>
                              </div>
                              <div style={{ display: 'flex', gap: '6px' }}>
                                <button
                                  className="n-btn ai-investigate"
                                  style={{ padding: '3px 8px', fontSize: '11px' }}
                                  onClick={() => handlers.onInvestigate(evt)}
                                >
                                  <AiSparklesIcon size={11} />
                                  <span>Investigate</span>
                                </button>
                                <button
                                  className="n-btn"
                                  style={{ background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.3)', padding: '3px 7px', fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                                  onClick={() => handlers.onSelectTab('evidence')}
                                >
                                  <CameraIcon size={11} /> Evidence
                                </button>

                              </div>
                            </div>

                            <div className="n-headline" style={{ fontSize: '12.5px', margin: '0 0 4px' }}>
                              {evt.description || evt.event_type || 'Restricted area entry detected'}
                            </div>
                            <div style={{ fontSize: '11.5px', color: 'var(--text-mid)', lineHeight: '1.45' }}>
                              {formatAiText(evt.observed_facts || `Detected object ${evt.object_type || 'vehicle'} crossing perimeter line.`, handlers)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* VIRTUAL FENCE EVENTS */}
                  {brief.virtual_fence_events && brief.virtual_fence_events.length > 0 && (
                    <div>
                      <div className="n-col-label" style={{ marginBottom: '8px', color: 'var(--gold)' }}>
                        Virtual Fence Breaches ({brief.virtual_fence_events.length})
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {brief.virtual_fence_events.map((vf, idx) => (
                          <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', background: 'var(--panel-hi)', borderRadius: '8px', border: '1px solid var(--hair)' }}>
                            <div>
                              <b style={{ color: 'var(--text-hi)', fontSize: '12px' }}>{vf.name || vf.zone_id || 'Restricted Zone'}</b>
                              <div style={{ fontSize: '10.5px', color: 'var(--text-low)' }}>
                                {vf.description || (vf.camera_id ? `Breach at ${vf.camera_id}` : 'Perimeter breach detected')}
                              </div>
                            </div>
                            <button className="n-btn ai-investigate" style={{ padding: '3px 8px', fontSize: '11px' }} onClick={() => handlers.onInvestigate(vf)}>
                              <AiSparklesIcon size={11} />
                              <span>Inspect</span>
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* EVIDENCE SUMMARY */}
                  {brief.evidence_summary && (
                    <div className="tile" style={{ padding: '14px', borderColor: 'rgba(224,170,62,0.3)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                        <div className="n-col-label" style={{ color: 'var(--gold)', margin: 0 }}>
                          Evidence Vault Captures
                        </div>
                        <button
                          className="n-btn"
                          style={{ background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.3)', padding: '2px 6px', fontSize: '10px' }}
                          onClick={() => handlers.onSelectTab('evidence')}
                        >
                          Vault →
                        </button>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-mid)', lineHeight: '1.5' }}>
                        {formatAiText(brief.evidence_summary, handlers)}
                      </div>
                    </div>
                  )}

                  {/* AI ASSESSMENT & DIRECTIVES */}
                  {brief.ai_assessment && (
                    <div className="tile" style={{ padding: '14px', background: 'var(--panel-hi)', borderColor: 'rgba(224, 170, 62, 0.3)' }}>
                      <div className="n-col-label" style={{ color: 'var(--gold)', marginBottom: '6px' }}>
                        AI Intelligence Assessment & Directives
                      </div>
                      <div style={{ fontSize: '12.5px', color: 'var(--text-hi)', lineHeight: '1.55' }}>
                        {formatAiText(brief.ai_assessment, handlers)}
                      </div>
                      <RenderAiActions actions={brief.actions} references={brief.references} handlers={handlers} />
                    </div>
                  )}

                  {/* QUICK CONVERSATIONAL FOLLOWUP BUTTON */}
                  <div style={{ paddingTop: '4px' }}>
                    <button
                      type="button"
                      className="n-btn"
                      style={{
                        width: '100%',
                        justifyContent: 'center',
                        background: 'rgba(139, 101, 72, 0.18)',
                        borderColor: 'rgba(139, 101, 72, 0.38)',
                        color: '#f2e7dc',
                        padding: '9px 14px',
                        borderRadius: '8px',
                        fontWeight: 600,
                        gap: '8px',
                      }}
                      onClick={() => {
                        handleSend("Provide a deeper intelligence analysis on today's highest priority threats and recommended countermeasures.");
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                      <span>Ask AI about this brief</span>
                    </button>
                  </div>
                </>
              ) : (
                <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-low)' }}>
                  No briefing data available.
                  <div style={{ marginTop: '12px' }}>
                    <button className="n-btn" onClick={fetchBrief}>Generate Brief</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* PANEL FOOTER / INPUT BAR */}
        <div className="ai-panel-foot">
          <div className="ai-panel-input-shell">
            <textarea
              ref={inputRef}
              className="ai-panel-input"
              id="aiPanelInput"
              rows={1}
              placeholder={activeTab === 'brief' ? "Ask HELIOS about this briefing…" : "Ask about events, alerts, cameras…"}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 90) + 'px';
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            <div className="ai-panel-input-bar">
              <div className="ai-panel-tools">
                <button
                  type="button"
                  className="ai-panel-tool-btn"
                  title="Investigate security incidents"
                  aria-label="Investigate security incidents"
                  onClick={() => {
                    handleSend("Investigate recent security events and identify any high-severity threats across the facility.");
                  }}
                >
                  <AiSparklesIcon size={13} />
                </button>
                <div style={{ position: 'relative' }}>
                  <button
                    type="button"
                    className="ai-panel-tool-btn"
                    title="Jump to facility view..."
                    aria-label="Jump to facility view"
                    onClick={() => setShowToolGotoMenu((prev) => !prev)}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polygon points="3 11 22 2 13 21 11 13 3 11" />
                    </svg>
                  </button>
                  {showToolGotoMenu && (
                    <div className="ai-goto-menu" style={{ bottom: 'calc(100% + 6px)', left: 0 }}>
                      <div className="ai-goto-menu-header">Jump To View</div>
                      <div className="ai-goto-menu-item" onClick={() => { setShowToolGotoMenu(false); handlers.onSelectTab('feeds'); }}>
                        <span className="dot online"></span>
                        <span>Live Camera Feeds</span>
                      </div>
                      <div className="ai-goto-menu-item" onClick={() => { setShowToolGotoMenu(false); handlers.onSelectTab('events'); }}>
                        <span className="dot"></span>
                        <span>Forensic Events</span>
                      </div>
                      <div className="ai-goto-menu-item" onClick={() => { setShowToolGotoMenu(false); handlers.onSelectTab('threads'); }}>
                        <span className="dot gold"></span>
                        <span>Activity Threads</span>
                      </div>
                      <div className="ai-goto-menu-item" onClick={() => { setShowToolGotoMenu(false); handlers.onSelectTab('evidence'); }}>
                        <span className="dot"></span>
                        <span>Evidence Locker</span>
                      </div>
                      <div className="ai-goto-menu-item" onClick={() => { setShowToolGotoMenu(false); handlers.onSelectTab('alerts'); }}>
                        <span className="dot alert"></span>
                        <span>Active Alerts</span>
                      </div>
                      <div className="ai-goto-menu-item" onClick={() => { setShowToolGotoMenu(false); handlers.onSelectTab('fencing'); }}>
                        <span className="dot"></span>
                        <span>Spatial Fencing</span>
                      </div>
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className="ai-panel-tool-btn"
                  title="Tag a camera or zone"
                  aria-label="Tag a resource"
                  onClick={() => {
                    setInput((prev) => (prev ? prev + ' #CAM-02 ' : '#CAM-02 '));
                    inputRef.current?.focus();
                  }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 20l9-9-9-9-9 9 9 9z" />
                  </svg>
                </button>
                <button
                  type="button"
                  className="ai-panel-tool-btn"
                  title="Assistant settings"
                  aria-label="Assistant settings"
                  onClick={() => {
                    if (handlers.onSelectTab) handlers.onSelectTab('settings');
                  }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3" />
                    <path d="M1 14h6M9 8h6M17 16h6" />
                  </svg>
                </button>
              </div>
              <button
                type="button"
                className="ai-panel-send"
                id="aiPanelSend"
                aria-label="Send question"
                onClick={() => handleSend()}
                disabled={loading}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 2 11 13" />
                  <path d="m22 2-7 20-4-9-9-4 20-7Z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* AI ASSISTANT FAB */}
      <div className="ai-fab-wrap">
        <div className="ai-fab-label">
          <span>Ask AI</span>
          <span style={{ fontSize: '9px', color: 'var(--text-low)' }}>⌘ K</span>
        </div>
        <button
          className="ai-fab"
          id="aiFabBtn"
          onClick={onToggle}
          title="Ask AI"
          aria-label="Ask AI"
        >
          <span className="ai-fab-ring"></span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
            <path d="M19 3.2v3.1M17.45 4.75h3.1" />
            <path d="M5.2 16.8v2.3M4.05 17.95h2.3" />
          </svg>
        </button>
      </div>
    </>
  );
}
