import { useState, useEffect } from 'react';
import { useHeliosWebSocket } from './hooks/useHeliosWebSocket';
import { TopBar } from './components/TopBar';
import { StatusBanner } from './components/StatusBanner';
import { Sidebar } from './components/Sidebar';
import { GreetingBar } from './components/GreetingBar';
import { HeroOverview } from './components/HeroOverview';
import { NarrativeGrid } from './components/NarrativeGrid';
import { BreakdownSection } from './components/BreakdownSection';
import { AskAiPopup } from './components/AskAiPopup';
import { GlobalSearchModal } from './components/GlobalSearchModal';
import { LiveFeedsView } from './components/LiveFeedsView';
import { EventsView } from './components/EventsView';
import { AlertsView } from './components/AlertsView';
import { SettingsView } from './components/SettingsView';
import { EvidenceView } from './components/EvidenceView';
import { ActivityThreadsView } from './components/ActivityThreadsView';
import { SystemLogsView } from './components/SystemLogsView';
import { InvestigateModal } from './components/InvestigateModal';
import { NotificationManager } from './components/NotificationManager';
import { LoginPage } from './components/LoginPage';
import { FencingView } from './components/FencingView';
import { ZoneEventsView } from './components/ZoneEventsView';
import { IncidentsView } from './components/IncidentsView';
import { InsightsView } from './components/InsightsView';
import { FacialRecognitionView } from './components/FacialRecognitionView';
import { api } from './services/api';

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return (
      localStorage.getItem('helios_auth') === 'true' ||
      sessionStorage.getItem('helios_auth') === 'true'
    );
  });

  const { cameras, tracks, events, alerts, evidence, summary, analytics, engines, zoneDensity, connected, loading, refreshAll } = useHeliosWebSocket();

  const [soundEnabled, setSoundEnabled] = useState(() => {
    return localStorage.getItem('helios_sound') !== 'false';
  });

  const handleToggleSound = () => {
    setSoundEnabled((prev) => {
      const next = !prev;
      localStorage.setItem('helios_sound', String(next));
      return next;
    });
  };

  const getInitialTab = () => {
    if (typeof window !== 'undefined' && window.location.pathname.startsWith('/fencing')) {
      return 'fencing';
    }
    return 'overview';
  };

  const [activeTab, setActiveTab] = useState(getInitialTab);
  const [eventsCategory, setEventsCategory] = useState('all');
  const [selectedTrackId, setSelectedTrackId] = useState(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [aiPopupOpen, setAiPopupOpen] = useState(false);
  const [aiInitialTab, setAiInitialTab] = useState('chat');
  const [investigateEvent, setInvestigateEvent] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [incidentsCount, setIncidentsCount] = useState(0);
  const [insightsCount, setInsightsCount] = useState(0);
  const [facesCount, setFacesCount] = useState(0);

  useEffect(() => {
    api.getIncidentsSummary()
      .then((res) => {
        if (res && res.active_incidents !== undefined) {
          setIncidentsCount(res.active_incidents);
        }
      })
      .catch(() => {});

    api.getInsightsSummary()
      .then((res) => {
        if (res && res.active !== undefined) {
          setInsightsCount(res.active);
        }
      })
      .catch(() => {});

    api.getFaceSummary()
      .then((res) => {
        if (res && res.total_recognitions !== undefined) {
          setFacesCount(res.total_recognitions);
        }
      })
      .catch(() => {});
  }, [events]);

  // Synchronize browser URL on popstate
  useEffect(() => {
    const handlePopState = () => {
      if (window.location.pathname.startsWith('/fencing')) {
        setActiveTab('fencing');
      } else {
        setActiveTab('overview');
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Global keyboard shortcut: Cmd+K / Ctrl+K toggles global search
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const activeAlertsCount = alerts.filter((a) => a.status === 'ACTIVE').length;

  const isZoneEvent = (e) => Boolean(
    e.zone_id ||
    e.attributes?.zone_id ||
    (e.event_type && (e.event_type.includes('ZONE') || e.event_type === 'INTRUSION')) ||
    (e.description && (e.description.toLowerCase().includes('zone') || e.description.toLowerCase().includes('perimeter')))
  );

  const trackedEventsCount = events.filter((e) => Boolean(e.track_id)).length;
  const zoneEventsCount = events.filter(isZoneEvent).length;

  const handleSelectTab = (tab, trackId = null, category = null) => {
    if (trackId) setSelectedTrackId(trackId);
    if (category) setEventsCategory(category);
    setActiveTab(tab);
    setMobileMenuOpen(false);
    if (tab === 'fencing') {
      if (window.location.pathname !== '/fencing') {
        window.history.pushState(null, '', '/fencing');
      }
    } else if (window.location.pathname === '/fencing') {
      window.history.pushState(null, '', '/');
    }
  };


  const handleLogout = () => {
    localStorage.removeItem('helios_auth');
    localStorage.removeItem('helios_user');
    sessionStorage.removeItem('helios_auth');
    sessionStorage.removeItem('helios_user');
    setIsAuthenticated(false);
  };

  if (!isAuthenticated) {
    return <LoginPage onLogin={() => setIsAuthenticated(true)} />;
  }

  return (
    <div className="shell">
      {/* TOP BAR */}
      <TopBar
        connected={connected}
        onOpenSearch={() => setSearchOpen(true)}
        onLogout={handleLogout}
        onSelectTab={handleSelectTab}
        onToggleMenu={() => setMobileMenuOpen((prev) => !prev)}
        mobileMenuOpen={mobileMenuOpen}
      />

      {/* STATUS BANNER */}
      <StatusBanner
        alerts={alerts}
        cameras={cameras}
        onSelectAlerts={() => setActiveTab('alerts')}
        onInvestigate={(evt) => setInvestigateEvent(evt)}
      />

      {/* SIDEBAR */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        eventsCategory={eventsCategory}
        onSelectEventsCategory={setEventsCategory}
        eventsCount={events.length}
        trackedEventsCount={trackedEventsCount}
        zoneEventsCount={zoneEventsCount}
        camerasCount={cameras.length}
        alertsCount={activeAlertsCount}
        evidenceCount={evidence.length}
        threadsCount={tracks.filter((t) => t.status !== 'ENDED').length}
        facesCount={facesCount}
        incidentsCount={incidentsCount}
        insightsCount={insightsCount}
        engines={engines}
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      />

      {/* MAIN CONTENT AREA */}
      <div className="main">
        <GreetingBar
          onOpenBrief={() => {
            setAiInitialTab('brief');
            setAiPopupOpen(true);
          }}
        />

        {activeTab === 'overview' && (
          <>
            <HeroOverview
              summary={summary}
              analytics={analytics}
              events={events}
              tracks={tracks}
              alerts={alerts}
              cameras={cameras}
              evidence={evidence}
              loading={loading}
              onSelectTab={handleSelectTab}
            />

            <NarrativeGrid
              events={events}
              cameras={cameras}
              loading={loading}
              onViewAll={() => handleSelectTab('events', null, 'all')}
              onInvestigate={(evt) => setInvestigateEvent(evt)}
            />

            <BreakdownSection
              cameras={cameras}
              events={events}
              tracks={tracks}
              alerts={alerts}
              loading={loading}
              onSelectTab={handleSelectTab}
            />
          </>
        )}

        {activeTab === 'feeds' && (
          <LiveFeedsView
            cameras={cameras}
            tracks={tracks}
            events={events}
            alerts={alerts}
            loading={loading}
            connected={connected}
            onSelectTab={handleSelectTab}
            onRefresh={refreshAll}
            onInvestigate={(evt) => setInvestigateEvent(evt)}
          />
        )}

        {activeTab === 'events' && eventsCategory === 'zone' ? (
          <ZoneEventsView
            events={events}
            loading={loading}
            onInvestigate={(evt) => setInvestigateEvent(evt)}
            onSelectTab={handleSelectTab}
            onRefresh={refreshAll}
            eventsCategory={eventsCategory}
            onSelectCategory={setEventsCategory}
            isZoneEvent={isZoneEvent}
          />
        ) : activeTab === 'events' ? (
          <EventsView
            events={events}
            loading={loading}
            onInvestigate={(evt) => setInvestigateEvent(evt)}
            onSelectTab={handleSelectTab}
            onRefresh={refreshAll}
            eventsCategory={eventsCategory}
            onSelectCategory={setEventsCategory}
            isZoneEvent={isZoneEvent}
          />
        ) : null}

        {activeTab === 'alerts' && (
          <AlertsView
            alerts={alerts}
            loading={loading}
            onRefresh={refreshAll}
            onInvestigate={(evt) => setInvestigateEvent(evt)}
            onSelectTab={handleSelectTab}
          />
        )}

        {activeTab === 'insights' && (
          <InsightsView
            onInvestigate={(evt) => setInvestigateEvent(evt)}
            onSelectTab={handleSelectTab}
          />
        )}

        {activeTab === 'incidents' && (
          <IncidentsView
            onInvestigate={(evt) => setInvestigateEvent(evt)}
            onSelectTab={handleSelectTab}
            onRefresh={refreshAll}
          />
        )}

        {activeTab === 'logs' && (
          <SystemLogsView
            events={events}
            alerts={alerts}
            evidence={evidence}
            cameras={cameras}
            engines={engines}
            loading={loading}
            onSelectTab={handleSelectTab}
          />
        )}

        {activeTab === 'evidence' && (
          <EvidenceView
            evidence={evidence}
            loading={loading}
            onRefresh={refreshAll}
            onInvestigate={(evt) => setInvestigateEvent(evt)}
            onSelectTab={handleSelectTab}
          />
        )}

        {activeTab === 'threads' && (
          <ActivityThreadsView
            tracks={tracks}
            selectedTrackId={selectedTrackId}
            onInvestigate={(evt) => setInvestigateEvent(evt)}
            onSelectTab={handleSelectTab}
          />
        )}

        {activeTab === 'fencing' && (
          <FencingView
            cameras={cameras}
            tracks={tracks}
            events={events}
            alerts={alerts}
            zoneDensity={zoneDensity}
            onSelectTab={handleSelectTab}
            onInvestigate={(evt) => setInvestigateEvent(evt)}
          />
        )}

        {activeTab === 'facial-recognition' && (
          <FacialRecognitionView
            onSelectTab={handleSelectTab}
            onInvestigate={(evt) => setInvestigateEvent(evt)}
          />
        )}

        {activeTab === 'settings' && (
          <SettingsView
            cameras={cameras}
            engines={engines}
            onRefresh={refreshAll}
            soundEnabled={soundEnabled}
            onToggleSound={handleToggleSound}
            onSelectTab={handleSelectTab}
          />
        )}
      </div>


      {/* AI ASSISTANT FAB & POPUP */}
      <AskAiPopup
        isOpen={aiPopupOpen}
        initialTab={aiInitialTab}
        onToggle={() => {
          setAiInitialTab('chat');
          setAiPopupOpen((prev) => !prev);
        }}
        onClose={() => setAiPopupOpen(false)}
        onInvestigate={(evt) => setInvestigateEvent(evt)}
        onSelectTab={handleSelectTab}
        events={events}
        cameras={cameras}
      />

      {/* GLOBAL SEARCH & AI CHAT MODAL */}
      <GlobalSearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        cameras={cameras}
        events={events}
        tracks={tracks}
        alerts={alerts}
        onSelectTab={handleSelectTab}
        onInvestigate={(evt) => setInvestigateEvent(evt)}
      />

      {/* EVENT INVESTIGATION MODAL */}
      <InvestigateModal
        event={investigateEvent}
        onClose={() => setInvestigateEvent(null)}
        onSelectTab={handleSelectTab}
      />

      {/* TACTICAL ALERT NOTIFICATIONS & INTRUSION VOICE DISPATCH */}
      <NotificationManager
        alerts={alerts}
        events={events}
        onInvestigate={(evt) => setInvestigateEvent(evt)}
        onSelectTab={handleSelectTab}
        soundEnabled={soundEnabled}
        onToggleSound={handleToggleSound}
      />
    </div>
  );
}
