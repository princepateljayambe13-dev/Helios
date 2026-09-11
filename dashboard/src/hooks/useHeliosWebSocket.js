import { useEffect, useState, useRef, useCallback } from 'react';
import { api, getApiBase } from '../services/api';

export function useHeliosWebSocket() {
  const [state, setState] = useState({
    cameras: [],
    tracks: [],
    events: [],
    alerts: [],
    evidence: [],
    summary: null,
    analytics: null,
    engines: {},
    zoneDensity: [],
    connected: false,
    loading: true,
  });

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Full refresh from REST API
  const refreshAll = useCallback(async () => {
    try {
      const [cameras, tracks, summary, alerts, events, evidence, health, analytics, zoneDensity] = await Promise.all([
        api.getCameras().catch(() => []),
        api.getTracks().catch(() => []),
        api.getSystemSummary().catch(() => null),
        api.getAlerts().catch(() => []),
        api.getEvents(100).catch(() => []),
        api.getEvidence().catch(() => []),
        api.getSystemHealth().catch(() => ({ engines: {} })),
        api.getAnalytics('24h').catch(() => null),
        api.getZoneDensity().catch(() => []),
      ]);

      setState((s) => ({
        ...s,
        cameras: cameras.length ? cameras : s.cameras,
        tracks: Array.isArray(tracks) ? tracks : s.tracks,
        summary: summary || s.summary,
        alerts: Array.isArray(alerts) ? alerts : s.alerts,
        events: Array.isArray(events) ? events : s.events,
        evidence: Array.isArray(evidence) ? evidence.slice(0, 30) : s.evidence,
        engines: health?.engines || s.engines,
        analytics: analytics || s.analytics,
        zoneDensity: Array.isArray(zoneDensity) ? zoneDensity : s.zoneDensity,
        loading: false,
      }));
    } catch (err) {
      console.error('Failed to fetch initial data:', err);
      setState((s) => ({ ...s, loading: false }));
    }
  }, []);

  useEffect(() => {
    refreshAll();

    // Fallback periodic poll every 10 seconds
    const interval = setInterval(() => {
      refreshAll();
    }, 10000);

    // WebSocket connection logic
    const connectWS = () => {
      const currentBase = getApiBase();
      const wsUrl = `${currentBase.replace(/^http/, 'ws')}/api/v1/ws`;
      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        setState((s) => ({ ...s, connected: true }));
      };

      socket.onmessage = (e) => {
        try {
          const message = JSON.parse(e.data);
          const { topic, data } = message;

          if (topic === 'system') {
            setState((s) => ({ ...s, summary: data }));
          } else if (topic === 'evidence') {
            if (data) {
              setState((s) => ({
                ...s,
                evidence: [data, ...s.evidence.filter((item) => item.evidence_id !== data.evidence_id)].slice(0, 30),
              }));
            }
          } else if (topic === 'observation') {
            const { event, alert, evidence, track } = data;
            setState((s) => {
              let updatedTracks = s.tracks;
              if (track && track.track_id) {
                const idx = s.tracks.findIndex((t) => t.track_id === track.track_id);
                if (idx >= 0) {
                  updatedTracks = [...s.tracks];
                  updatedTracks[idx] = { ...updatedTracks[idx], ...track };
                } else {
                  updatedTracks = [track, ...s.tracks];
                }
              }
              return {
                ...s,
                tracks: updatedTracks,
                events: event
                  ? [event, ...s.events.filter((item) => item.event_id !== event.event_id)].slice(0, 50)
                  : s.events,
                alerts: alert
                  ? [alert, ...s.alerts.filter((item) => item.alert_id !== alert.alert_id)]
                  : s.alerts,
                evidence: evidence
                  ? [evidence, ...s.evidence.filter((item) => item.evidence_id !== evidence.evidence_id)].slice(0, 30)
                  : s.evidence,
              };
            });
            api.getSystemSummary().then((sum) => sum && setState((s) => ({ ...s, summary: sum }))).catch(() => {});
          } else if (topic === 'track') {
            if (data && data.track_id) {
              setState((s) => {
                const idx = s.tracks.findIndex((t) => t.track_id === data.track_id);
                let updatedTracks;
                if (idx >= 0) {
                  updatedTracks = [...s.tracks];
                  updatedTracks[idx] = { ...updatedTracks[idx], ...data };
                } else {
                  updatedTracks = [data, ...s.tracks];
                }
                return { ...s, tracks: updatedTracks };
              });
            }
          } else if (topic === 'camera') {
            const updated = data;
            setState((s) => ({
              ...s,
              cameras: s.cameras.map((c) => (c.camera_id === updated.camera_id ? { ...c, ...updated } : c)),
            }));
          } else if (topic === 'camera_condition') {
            const updated = data;
            setState((s) => ({
              ...s,
              cameras: s.cameras.map((c) => (c.camera_id === updated.camera_id ? {
                ...c,
                reliability_score: updated.reliability_score,
                condition: updated.condition,
                condition_confidence: updated.confidence,
                condition_started_at: updated.started_at,
                condition_details: JSON.stringify({ metrics: updated.metrics, reason: updated.reason }),
              } : c)),
            }));
          } else if (topic === 'alert') {
            setState((s) => ({
              ...s,
              alerts: [data, ...s.alerts.filter((item) => item.alert_id !== data.alert_id)],
            }));
          } else if (topic === 'audio') {
            const { event, alert, evidence } = data;
            setState((s) => ({
              ...s,
              events: event
                ? [event, ...s.events.filter((item) => item.event_id !== event.event_id)].slice(0, 50)
                : s.events,
              alerts: alert
                ? [alert, ...s.alerts.filter((item) => item.alert_id !== alert.alert_id)]
                : s.alerts,
              evidence: evidence
                ? [evidence, ...s.evidence.filter((item) => item.evidence_id !== evidence.evidence_id)].slice(0, 30)
                : s.evidence,
            }));
          } else if (topic === 'zone_density') {
            if (Array.isArray(data)) {
              setState((s) => ({
                ...s,
                zoneDensity: data,
              }));
            }
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      socket.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        reconnectTimeoutRef.current = setTimeout(connectWS, 3000);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connectWS();

    return () => {
      clearInterval(interval);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [refreshAll]);

  return { ...state, refreshAll };
}
