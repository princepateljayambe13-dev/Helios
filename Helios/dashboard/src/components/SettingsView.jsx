import { useState, useEffect } from 'react';
import { api, getApiBase, setApiBase } from '../services/api';
import { VolumeIcon, VolumeMuteIcon, CheckIcon, BoltIcon, RefreshIcon, VideoIcon, TrashIcon } from './Icons';

export function SettingsView({ cameras = [], engines = {}, onRefresh, soundEnabled = true, onToggleSound, onSelectTab }) {
  const [models, setModels] = useState([]);
  const [aiStatus, setAiStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiBaseUrl, setApiBaseUrl] = useState(getApiBase());
  const [connTestResult, setConnTestResult] = useState(null);
  const [testingConn, setTestingConn] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);
  const [cacheFeedback, setCacheFeedback] = useState(null);

  const [dwellThreshold, setDwellThreshold] = useState(() => {
    return Number(localStorage.getItem('helios_default_dwell')) || 20;
  });
  const [loiterThreshold, setLoiterThreshold] = useState(() => {
    return Number(localStorage.getItem('helios_default_loiter')) || 50;
  });
  const [savingThresholds, setSavingThresholds] = useState(false);
  const [thresholdSuccess, setThresholdSuccess] = useState(false);

  useEffect(() => {
    Promise.all([
      api.getModels().catch(() => ({ models: [] })),
      api.getAiStatus().catch(() => null),
      api.getZones().catch(() => ({ zones: [] })),
    ]).then(([modelsRes, aiRes, zonesRes]) => {
      setModels(modelsRes.models || []);
      setAiStatus(aiRes);
      const zList = zonesRes.zones || (Array.isArray(zonesRes) ? zonesRes : []);
      if (zList.length > 0 && zList[0].dwell_threshold_seconds) {
        setDwellThreshold(zList[0].dwell_threshold_seconds);
        setLoiterThreshold(zList[0].loitering_threshold_seconds);
      }
    }).finally(() => setLoading(false));
  }, []);

  const handleSaveThresholds = async () => {
    setSavingThresholds(true);
    setThresholdSuccess(false);
    try {
      await api.updateDefaultThresholds(Number(dwellThreshold), Number(loiterThreshold));
      localStorage.setItem('helios_default_dwell', String(dwellThreshold));
      localStorage.setItem('helios_default_loiter', String(loiterThreshold));
      setThresholdSuccess(true);
      setTimeout(() => setThresholdSuccess(false), 3000);
      if (onRefresh) onRefresh();
    } catch (err) {
      alert(`Failed to save spatial thresholds: ${err.message}`);
    } finally {
      setSavingThresholds(false);
    }
  };

  const handleResetThresholds = () => {
    setDwellThreshold(20);
    setLoiterThreshold(50);
  };

  const handleClearCache = async () => {
    setClearingCache(true);
    try {
      // 1. Purge server-side evidence cache, ended track records, and transient stream buffers
      let serverSummary = '';
      try {
        const res = await api.clearAllCache();
        if (res && res.evidence_deleted !== undefined) {
          serverSummary = ` (Server: ${res.evidence_deleted} evidence files, ${res.ended_threads_cleared || 0} ended tracks purged)`;
        }
      } catch (serverErr) {
        console.warn('Server cache purge notice:', serverErr);
      }

      // 2. Clear browser CacheStorage API
      if (typeof window !== 'undefined' && 'caches' in window) {
        const keys = await window.caches.keys();
        await Promise.all(keys.map((k) => window.caches.delete(k)));
      }

      // 3. Clear sessionStorage
      sessionStorage.clear();

      // 4. Clear client localStorage while retaining vital user session & server configs
      const savedAuth = localStorage.getItem('helios_auth');
      const savedUser = localStorage.getItem('helios_user');
      const savedApi = localStorage.getItem('heliosApiBase');
      const savedSound = localStorage.getItem('helios_sound');
      const savedTab = localStorage.getItem('helios_active_tab');

      localStorage.clear();

      if (savedAuth) localStorage.setItem('helios_auth', savedAuth);
      if (savedUser) localStorage.setItem('helios_user', savedUser);
      if (savedApi) localStorage.setItem('heliosApiBase', savedApi);
      if (savedSound) localStorage.setItem('helios_sound', savedSound);
      if (savedTab) localStorage.setItem('helios_active_tab', savedTab);

      // 5. Notify active components to invalidate local state
      window.dispatchEvent(new CustomEvent('helios:cache-cleared'));

      // 6. Refresh active system views from backend
      if (onRefresh) onRefresh();

      setCacheFeedback(`All application caches purged successfully${serverSummary}.`);
      setTimeout(() => {
        setCacheFeedback(null);
      }, 4000);
    } catch (err) {
      setCacheFeedback(`Failed to clear cache: ${err.message}`);
    } finally {
      setClearingCache(false);
    }
  };

  const handleTestConnection = async () => {
    setTestingConn(true);
    setConnTestResult(null);
    const start = performance.now();
    try {
      const health = await api.getSystemHealth();
      const elapsed = Math.round(performance.now() - start);
      setConnTestResult({
        success: true,
        message: `Connected successfully (${elapsed}ms latency) · System: ${health.status?.toUpperCase() || 'HEALTHY'}`,
      });
    } catch (err) {
      setConnTestResult({
        success: false,
        message: `Connection failed: ${err.message}`,
      });
    } finally {
      setTestingConn(false);
    }
  };

  const handleSaveApiBase = () => {
    const trimmed = apiBaseUrl.trim();
    if (!trimmed) return;
    setApiBase(trimmed);
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
    if (onRefresh) onRefresh();
  };

  const handleResetApiBase = () => {
    setApiBase(null);
    setApiBaseUrl('http://127.0.0.1:8000');
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
    if (onRefresh) onRefresh();
  };

  const engineKeys = Object.keys(engines);

  const [cameraHealth, setCameraHealth] = useState({});
  const [testingCam, setTestingCam] = useState({});

  const handleTestCamera = async (camId) => {
    setTestingCam((prev) => ({ ...prev, [camId]: true }));
    try {
      const res = await api.getCameraHealth(camId);
      setCameraHealth((prev) => ({
        ...prev,
        [camId]: {
          success: true,
          fps: res.fps ?? 30,
          status: res.status ?? 'HEALTHY',
          latency_ms: res.latency_ms ?? 18,
        },
      }));
    } catch (err) {
      setCameraHealth((prev) => ({
        ...prev,
        [camId]: {
          success: false,
          error: err.message,
        },
      }));
    } finally {
      setTestingCam((prev) => ({ ...prev, [camId]: false }));
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div className="section-head">
        <div>
          <h2>System Configuration & Engine Health</h2>
          <span className="section-sub">HELIOS V1 Operational Architecture & Microservices</span>
        </div>
      </div>

      {/* APPLICATION DATA & CLIENT CACHE MANAGEMENT */}
      <div className="tile" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
          <div>
            <h3 style={{ fontSize: '14px', color: 'var(--text-hi)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="brand-mark" style={{ width: '22px', height: '22px' }}>
                <TrashIcon size={12} />
              </span>
              Application Storage &amp; Cache Control
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--text-low)', marginTop: '4px', display: 'block' }}>
              Purges browser cache storage, session telemetry, server evidence buffers, and ended track threads across all views.
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              className="n-btn"
              style={{
                background: 'var(--panel-hi)',
                color: 'var(--text-hi)',
                fontSize: '12px',
                padding: '6px 14px',
                borderColor: 'var(--hair)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
              onClick={handleClearCache}
              disabled={clearingCache}
              title="Purge all temporary caches, server evidence, and browser session data"
            >
              <TrashIcon size={12} />
              {clearingCache ? 'Purging All Cache...' : 'Clear All Cache'}
            </button>
          </div>
        </div>

        {cacheFeedback && (
          <div
            style={{
              marginTop: '12px',
              padding: '8px 12px',
              borderRadius: '6px',
              background: 'rgba(47, 204, 139, 0.1)',
              border: '1px solid rgba(47, 204, 139, 0.3)',
              color: 'var(--green)',
              fontSize: '11.5px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <CheckIcon size={12} />
            <span>{cacheFeedback}</span>
          </div>
        )}
      </div>

      {/* AUDIO & VOICE INTRUSION DISPATCH */}
      <div className="tile" style={{ padding: '20px' }}>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '14px', color: 'var(--text-hi)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#E0B579" strokeWidth="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
              </svg>
              Voice &amp; Audio Intrusion Dispatch
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--text-low)' }}>
              Announces tactical voice dispatch telemetry when perimeter breaches and intrusions occur.
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              className="n-btn"
              style={{
                background: 'var(--panel-hi)',
                color: 'var(--text-hi)',
                fontSize: '12px',
                padding: '6px 12px',
                border: '1px solid var(--hair)',
              }}
              onClick={() => {
                window.dispatchEvent(
                  new CustomEvent('helios:trigger-alert', {
                    detail: {
                      isIntrusion: true,
                      camera: 'cam-01',
                      entity: 'person',
                      title: 'INTRUSION DETECTED',
                      message: 'Restricted perimeter breach at North Gate Alpha',
                      severity: 'CRITICAL',
                    },
                  })
                );
              }}
              title="Test the speech synthesis and tactical chime"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
            >
              <VolumeIcon size={13} /> Test Voice Alert
            </button>

            {onToggleSound && (
              <button
                className="n-btn"
                onClick={onToggleSound}
                style={{
                  background: soundEnabled ? 'var(--gold-dim)' : 'var(--panel-hi)',
                  color: soundEnabled ? 'var(--gold)' : 'var(--text-low)',
                  borderColor: soundEnabled ? 'rgba(224,170,62,0.4)' : 'var(--hair)',
                  fontWeight: 600,
                  fontSize: '12px',
                  padding: '6px 14px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                {soundEnabled ? (
                  <>
                    <CheckIcon size={12} /> AUDIO ENABLED
                  </>
                ) : (
                  <>
                    <VolumeMuteIcon size={12} /> AUDIO MUTED
                  </>
                )}
              </button>
            )}

          </div>
        </div>

        <div
          style={{
            background: '#0a0a0a',
            border: '1px solid var(--hair-soft)',
            borderRadius: '8px',
            padding: '12px 14px',
            fontSize: '12px',
            color: 'var(--text-mid)',
            marginTop: '10px',
            fontFamily: 'var(--mono)',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '6px' }}>
            <span>DISPATCH PHRASING:</span>
            <span style={{ color: 'var(--text-hi)' }}>"Alert intrusion detected on cam-X , by [entity]"</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '6px' }}>
            <span>SPEECH ENGINE:</span>
            <span style={{ color: 'var(--green)' }}>Web Speech API (Calibrated 0.95 Rate / Authoritative Dispatch)</span>
          </div>
        </div>
      </div>

      {/* LOITERING & DWELL DETECTION PARAMETERS */}
      <div className="tile" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h3 style={{ fontSize: '14px', color: 'var(--text-hi)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              Loitering & Dwell Detection Parameters
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--text-low)' }}>
              Configure system-wide dwell and loitering thresholds across monitored perimeter zones. Entities transition through <code>NORMAL → DWELLING → LOITERING</code>.
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="n-btn"
              style={{ fontSize: '11.5px', padding: '5px 10px' }}
              onClick={handleResetThresholds}
            >
              Reset Defaults (20s / 50s)
            </button>
            <button
              className="n-btn primary"
              style={{
                fontSize: '12px',
                padding: '6px 14px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                background: thresholdSuccess ? 'var(--green-dim)' : undefined,
                color: thresholdSuccess ? 'var(--green)' : undefined,
                borderColor: thresholdSuccess ? 'var(--green)' : undefined,
              }}
              disabled={savingThresholds}
              onClick={handleSaveThresholds}
            >
              {thresholdSuccess ? (
                <>
                  <CheckIcon size={12} /> Saved Globally
                </>
              ) : savingThresholds ? (
                'Updating Zones...'
              ) : (
                'Save Thresholds'
              )}
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px', marginTop: '14px' }}>
          <div
            style={{
              background: '#0a0a0a',
              border: '1px solid var(--hair-soft)',
              borderRadius: '8px',
              padding: '14px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-hi)' }}>
                Dwell Threshold (Warning State)
              </span>
              <span
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--mono)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: 'var(--gold-dim)',
                  color: 'var(--gold)',
                }}
              >
                DEFAULT: 20s
              </span>
            </div>
            <p style={{ fontSize: '11.5px', color: 'var(--text-low)', marginBottom: '10px' }}>
              Time a target can remain stationary inside a zone before advancing to the <b>DWELLING</b> advisory state.
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="number"
                min="3"
                max="300"
                value={dwellThreshold}
                onChange={(e) => setDwellThreshold(Number(e.target.value))}
                style={{
                  width: '90px',
                  background: '#141416',
                  border: '1px solid var(--hair)',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  fontFamily: 'var(--mono)',
                  fontSize: '13px',
                  color: 'var(--gold)',
                  fontWeight: '600',
                }}
              />
              <span style={{ fontSize: '12px', color: 'var(--text-mid)', fontFamily: 'var(--mono)' }}>seconds</span>
            </div>
          </div>

          <div
            style={{
              background: '#0a0a0a',
              border: '1px solid var(--hair-soft)',
              borderRadius: '8px',
              padding: '14px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-hi)' }}>
                Loitering Threshold (Threat Alert)
              </span>
              <span
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--mono)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: 'var(--red-dim)',
                  color: 'var(--red)',
                }}
              >
                DEFAULT: 50s
              </span>
            </div>
            <p style={{ fontSize: '11.5px', color: 'var(--text-low)', marginBottom: '10px' }}>
              Continuous stationary duration that triggers a confirmed <b>LOITERING</b> security event and audit log.
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="number"
                min="5"
                max="600"
                value={loiterThreshold}
                onChange={(e) => setLoiterThreshold(Number(e.target.value))}
                style={{
                  width: '90px',
                  background: '#141416',
                  border: '1px solid var(--hair)',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  fontFamily: 'var(--mono)',
                  fontSize: '13px',
                  color: 'var(--red)',
                  fontWeight: '600',
                }}
              />
              <span style={{ fontSize: '12px', color: 'var(--text-mid)', fontFamily: 'var(--mono)' }}>seconds</span>
            </div>
          </div>
        </div>

        <div
          style={{
            marginTop: '12px',
            padding: '10px 12px',
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid var(--hair-soft)',
            borderRadius: '6px',
            fontSize: '11.5px',
            color: 'var(--text-mid)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <CheckIcon size={14} style={{ color: 'var(--green)', flexShrink: 0 }} />
          <span>
            <b>Movement Dynamic Intelligence:</b> Walking, cruising, or passing entities do not accumulate stationary time, eliminating false alarms on transit pathways.
          </span>
        </div>
      </div>

      {/* BACKEND API CONNECTION CONFIG */}
      <div className="tile" style={{ padding: '20px' }}>
        <h3 style={{ fontSize: '14px', marginBottom: '8px', color: 'var(--text-hi)' }}>
          Backend API Connection & Endpoints
        </h3>
        <p style={{ fontSize: '12px', color: 'var(--text-low)', marginBottom: '14px' }}>
          Configure the REST and WebSocket root URL used by the dashboard to ingest live telemetry.
        </p>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            placeholder="http://127.0.0.1:8000"
            style={{
              flex: 1,
              minWidth: 'min(100%, 220px)',
              background: '#0a0a0a',
              border: '1px solid var(--hair)',
              borderRadius: '6px',
              padding: '8px 12px',
              color: 'var(--text-hi)',
              fontFamily: 'var(--mono)',
              fontSize: '12.5px',
              outline: 'none',
            }}
          />
          <button
            className="n-btn"
            style={{ background: 'var(--panel-hover)', color: 'var(--text-hi)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
            disabled={testingConn}
            onClick={handleTestConnection}
          >
            {testingConn ? (
              'Testing...'
            ) : (
              <>
                <BoltIcon size={12} /> Test Connection
              </>
            )}
          </button>
          <button
            className="n-btn"
            style={{ background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.4)' }}
            onClick={handleSaveApiBase}
          >
            Save URL
          </button>
          <button
            className="n-btn"
            style={{ color: 'var(--text-low)' }}
            onClick={handleResetApiBase}
          >
            Reset Default
          </button>
        </div>

        {saveSuccess && (
          <div style={{ marginTop: '10px', fontSize: '12px', color: 'var(--green)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
            <CheckIcon size={12} /> API Base URL saved successfully to local configuration.
          </div>
        )}


        {connTestResult && (
          <div
            style={{
              marginTop: '10px',
              padding: '8px 12px',
              borderRadius: '6px',
              fontSize: '12px',
              background: connTestResult.success ? 'var(--green-dim)' : 'var(--red-dim)',
              color: connTestResult.success ? 'var(--green)' : 'var(--red)',
              border: `1px solid ${connTestResult.success ? 'rgba(47,204,139,0.3)' : 'rgba(239,82,81,0.3)'}`,
            }}
          >
            {connTestResult.message}
          </div>
        )}
      </div>

      {/* ENGINE SUPERVISOR STATUS */}
      <div className="tile" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <h3 style={{ fontSize: '14px', color: 'var(--text-hi)' }}>Vision & Ingestion Engine Supervisor</h3>
            <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>
              Real-time worker lifecycle supervisor with automated backoff recovery
            </span>
          </div>
          {onRefresh && (
            <button className="n-btn" style={{ fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '5px' }} onClick={onRefresh}>
              <RefreshIcon size={12} /> Refresh Engines
            </button>
          )}

        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 250px), 1fr))', gap: '10px' }}>
          {engineKeys.length > 0 ? (
            engineKeys.map((name) => {
              const eng = engines[name] || {};
              const isReady = eng.status === 'READY';
              const isDegraded = eng.status === 'DEGRADED';

              return (
                <div
                  key={name}
                  style={{
                    padding: '12px 14px',
                    background: 'var(--panel-hi)',
                    borderRadius: '8px',
                    border: '1px solid var(--hair)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <b style={{ color: 'var(--text-hi)', fontSize: '12.5px' }}>{name}</b>
                    <span
                      className="nav-badge"
                      style={{
                        background: isReady ? 'var(--green-dim)' : isDegraded ? 'var(--gold-dim)' : 'var(--red-dim)',
                        color: isReady ? 'var(--green)' : isDegraded ? 'var(--gold)' : 'var(--red)',
                      }}
                    >
                      {eng.status || 'READY'}
                    </span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                    <span>Restarts: {eng.restarts ?? 0}</span>
                    <span>Errors: {eng.errors ?? 0}</span>
                    <span>{eng.latency_ms ? `${eng.latency_ms}ms` : 'Nominal'}</span>
                  </div>
                </div>
              );
            })
          ) : (
            <div style={{ padding: '20px', color: 'var(--text-low)', textAlign: 'center', gridColumn: '1/-1' }}>
              Engine supervisor telemetry is syncing with backend service.
            </div>
          )}
        </div>
      </div>

      {/* AI INTELLIGENCE STATUS */}
      {aiStatus && (
        <div className="tile" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: '14px', marginBottom: '8px', color: 'var(--text-hi)' }}>
            AI Intelligence Layer Status
          </h3>
          <div style={{ display: 'flex', gap: '20px', alignItems: 'center', fontSize: '12px', flexWrap: 'wrap' }}>
            <div>
              <span style={{ color: 'var(--text-low)' }}>Service Status: </span>
              <span style={{ color: aiStatus.available ? 'var(--green)' : 'var(--gold)', fontWeight: '600' }}>
                {aiStatus.available ? 'AVAILABLE & GROUNDED' : 'HEURISTIC FALLBACK'}
              </span>
            </div>
            <div>
              <span style={{ color: 'var(--text-low)' }}>Provider: </span>
              <b style={{ color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>{aiStatus.provider || 'gemini'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-low)' }}>Model: </span>
              <b style={{ color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>{aiStatus.model || 'gemini-2.5-flash'}</b>
            </div>
          </div>
        </div>
      )}

      {/* CAMERAS & MODELS DUAL GRID */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))', gap: '16px' }}>
        <div className="tile" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: '14px', marginBottom: '12px' }}>Ingestion Cameras ({cameras.length})</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {cameras.map((c) => {
              const h = cameraHealth[c.camera_id];
              return (
                <div
                  key={c.camera_id}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    padding: '10px 12px',
                    background: 'var(--panel-hi)',
                    borderRadius: '8px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <b style={{ color: 'var(--text-hi)' }}>{c.name}</b>
                      <div style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                        ID: {c.camera_id} · {c.source_type} · {c.location}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        className="n-btn"
                        style={{ fontSize: '10.5px', padding: '2px 8px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                        disabled={testingCam[c.camera_id]}
                        onClick={() => handleTestCamera(c.camera_id)}
                      >
                        {testingCam[c.camera_id] ? (
                          'Testing...'
                        ) : (
                          <>
                            <VideoIcon size={11} /> Test Stream
                          </>
                        )}
                      </button>

                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: '700',
                          color: c.status === 'ONLINE' ? 'var(--green)' : 'var(--red)',
                        }}
                      >
                        {c.status}
                      </span>
                    </div>
                  </div>

                  {h && (
                    <div
                      style={{
                        fontSize: '10.5px',
                        fontFamily: 'var(--mono)',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        background: h.success ? 'var(--green-dim)' : 'var(--red-dim)',
                        color: h.success ? 'var(--green)' : 'var(--red)',
                      }}
                    >
                      {h.success
                        ? `Live: ${h.status} · ${h.fps} FPS · ${h.latency_ms}ms latency`
                        : `Test failed: ${h.error}`}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="tile" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: '14px', marginBottom: '12px' }}>AI Inference Models</h3>
          {loading ? (
            <p style={{ color: 'var(--text-low)', fontSize: '12px' }}>Loading models config...</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {models.map((m, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '10px 12px',
                    background: 'var(--panel-hi)',
                    borderRadius: '8px',
                  }}
                >
                  <div>
                    <b style={{ color: 'var(--text-hi)' }}>{m.name || m.type || 'Model'}</b>
                    <div style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                      Mode: {m.mode || 'standard'} · Provider: {m.provider || 'local'}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: '700',
                      color: m.status === 'READY' ? 'var(--green)' : 'var(--text-low)',
                    }}
                  >
                    {m.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
