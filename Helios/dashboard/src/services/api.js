export const getApiBase = () => localStorage.getItem('heliosApiBase') || 'http://127.0.0.1:8000';
export const setApiBase = (url) => {
  if (url) localStorage.setItem('heliosApiBase', url.replace(/\/+$/, ''));
  else localStorage.removeItem('heliosApiBase');
};

const getV1 = () => `${getApiBase()}/api/v1`;

const fetchJson = async (endpoint, options = {}) => {
  const url = endpoint.startsWith('http') ? endpoint : `${getV1()}${endpoint}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const errorText = await res.text().catch(() => res.statusText);
    throw new Error(`API Error (${res.status}): ${errorText || res.statusText}`);
  }
  return res.json();
};

export const api = {
  getSystemSummary: () => fetchJson('/system/summary'),
  getAnalytics: (timeframe = '24h') => fetchJson(`/system/analytics?timeframe=${encodeURIComponent(timeframe)}`),
  getSystemHealth: () => fetchJson('/system/health'),
  getModels: () => fetchJson('/models'),
  
  getCameras: () => fetchJson('/cameras'),
  reloadCameras: () => fetchJson('/cameras/reload', { method: 'POST' }),
  getCamera: (id) => fetchJson(`/cameras/${encodeURIComponent(id)}`),
  getCameraHealth: (id) => fetchJson(`/cameras/${encodeURIComponent(id)}/health`),
  getCameraCondition: (id) => fetchJson(`/cameras/${encodeURIComponent(id)}/condition`),
  getCameraConditionHistory: (id, limit = 50) => fetchJson(`/cameras/${encodeURIComponent(id)}/condition/history?limit=${limit}`),
  getAllCameraConditions: () => fetchJson('/cameras/conditions'),
  getStreamUrl: (id) => `${getV1()}/cameras/${encodeURIComponent(id)}/stream`,
  getCameraSnapshotUrl: (id) => `${getV1()}/cameras/${encodeURIComponent(id)}/snapshot`,
  getEvidenceFileUrl: (id) => `${getV1()}/evidence/${encodeURIComponent(id)}/file`,

  // Zones & Perimeter Fencing
  getZones: (cameraId) => fetchJson(cameraId ? `/zones?camera_id=${encodeURIComponent(cameraId)}` : '/zones'),
  getZone: (id) => fetchJson(`/zones/${encodeURIComponent(id)}`),
  createZone: (data) => fetchJson('/zones', { method: 'POST', body: JSON.stringify(data) }),
  updateZone: (id, data) => fetchJson(`/zones/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteZone: (id) => fetchJson(`/zones/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  getZoneDensity: (cameraId, zoneId) => {
    let q = '/zones/density';
    const params = [];
    if (cameraId) params.push(`camera_id=${encodeURIComponent(cameraId)}`);
    if (zoneId) params.push(`zone_id=${encodeURIComponent(zoneId)}`);
    if (params.length) q += `?${params.join('&')}`;
    return fetchJson(q);
  },
  getZoneDwell: () => fetchJson('/zones/dwell'),
  getLoiteringHistory: (zoneId) => fetchJson(zoneId ? `/zones/loitering/history?zone_id=${encodeURIComponent(zoneId)}` : '/zones/loitering/history'),
  updateZoneThresholds: (zoneId, dwell, loiter) => fetchJson(`/zones/${encodeURIComponent(zoneId)}/thresholds`, {
    method: 'PUT',
    body: JSON.stringify({ dwell_threshold_seconds: dwell, loitering_threshold_seconds: loiter }),
  }),
  updateDefaultThresholds: (dwell, loiter) => fetchJson('/zones/thresholds/default', {
    method: 'PUT',
    body: JSON.stringify({ dwell_threshold_seconds: dwell, loitering_threshold_seconds: loiter }),
  }),
  postObservation: (data) => fetchJson('/observations', { method: 'POST', body: JSON.stringify(data) }),
  
  getTracks: (cameraId) => fetchJson(cameraId ? `/tracks?camera_id=${encodeURIComponent(cameraId)}` : '/tracks'),

  getTrack: (id) => fetchJson(`/tracks/${encodeURIComponent(id)}`),
  getThreads: (params = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.append('limit', params.limit);
    if (params.status) q.append('status', params.status);
    if (params.cameraId) q.append('camera_id', params.cameraId);
    if (params.objectType) q.append('object_type', params.objectType);
    if (params.vehicleType) q.append('vehicle_type', params.vehicleType);
    if (params.vehicleColor) q.append('vehicle_color', params.vehicleColor);
    if (params.threatLevel) q.append('threat_level', params.threatLevel);
    const qs = q.toString();
    return fetchJson(qs ? `/threads?${qs}` : '/threads');
  },
  getTrackThread: (trackId) => fetchJson(`/threads/${encodeURIComponent(trackId)}`),
  clearEndedThreads: () => fetchJson('/threads/ended', { method: 'DELETE' }),
  
  getEvents: (limit = 100, offset = 0, severity, cameraId) => {
    let q = `/events?limit=${limit}&offset=${offset}`;
    if (severity) q += `&severity=${encodeURIComponent(severity)}`;
    if (cameraId) q += `&camera_id=${encodeURIComponent(cameraId)}`;
    return fetchJson(q);
  },
  getEvent: (id) => fetchJson(`/events/${encodeURIComponent(id)}`),
  clearEventsHistory: (includeAlerts = true) =>
    fetchJson(`/events/clear?include_alerts=${includeAlerts}`, { method: 'DELETE' }),
  
  getAlerts: (status) => fetchJson(status ? `/alerts?status=${encodeURIComponent(status)}` : '/alerts'),
  acknowledgeAlert: (alertId, operator = 'Operator') =>
    fetchJson(`/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify({ operator }),
    }),
  acknowledgeAllAlerts: async (operator = 'Operator', alertIds = null) => {
    try {
      return await fetchJson('/alerts/acknowledge-all', {
        method: 'POST',
        body: JSON.stringify({ operator, alert_ids: alertIds }),
      });
    } catch {
      const active = alertIds || (await fetchJson('/alerts?status=ACTIVE')).map((a) => a.alert_id);
      return Promise.all(
        (active || []).map((id) =>
          fetchJson(`/alerts/${encodeURIComponent(id)}/acknowledge`, {
            method: 'POST',
            body: JSON.stringify({ operator }),
          })
        )
      );
    }
  },

  // Incident Correlation Engine Endpoints
  getIncidents: (params = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.append('limit', params.limit);
    if (params.offset) q.append('offset', params.offset);
    if (params.status && params.status !== 'ALL') q.append('status', params.status);
    if (params.severity && params.severity !== 'ALL') q.append('severity', params.severity);
    if (params.cameraId && params.cameraId !== 'ALL') q.append('camera_id', params.cameraId);
    const qs = q.toString();
    return fetchJson(qs ? `/incidents?${qs}` : '/incidents');
  },
  getIncident: (id) => fetchJson(`/incidents/${encodeURIComponent(id)}`),
  getIncidentsSummary: () => fetchJson('/incidents/summary'),
  acknowledgeIncident: (id, operator = 'Operator') =>
    fetchJson(`/incidents/${encodeURIComponent(id)}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify({ operator }),
    }),
  resolveIncident: (id, operator = 'Operator') =>
    fetchJson(`/incidents/${encodeURIComponent(id)}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ operator }),
    }),
    
  getEvidence: (eventId) => fetchJson(eventId ? `/evidence?event_id=${encodeURIComponent(eventId)}` : '/evidence'),
  clearEvidenceCache: () => fetchJson('/evidence/clear', { method: 'DELETE' }),
  clearAllCache: async () => {
    try {
      return await fetchJson('/system/clear-cache', { method: 'POST' });
    } catch {
      const [ev, th] = await Promise.allSettled([
        fetchJson('/evidence/clear', { method: 'DELETE' }),
        fetchJson('/threads/ended', { method: 'DELETE' }),
      ]);
      return {
        status: 'cleared',
        evidence: ev.status === 'fulfilled' ? ev.value : null,
        threads: th.status === 'fulfilled' ? th.value : null,
      };
    }
  },
  
  // AI Endpoints
  askAi: (question, history = []) =>
    fetchJson('/ai/ask', {
      method: 'POST',
      body: JSON.stringify({ question, history }),
    }),
  getDayBrief: (date) => fetchJson(date ? `/ai/day-brief?date=${encodeURIComponent(date)}` : '/ai/day-brief'),
  explainEvent: (eventId) => fetchJson(`/ai/event/${encodeURIComponent(eventId)}/explain`),
  investigateEvent: (eventId, windowHours = 6, focus) =>
    fetchJson(`/ai/event/${encodeURIComponent(eventId)}/investigate`, {
      method: 'POST',
      body: JSON.stringify({ context_window_hours: windowHours, focus }),
    }),
  investigateEvidence: (evidenceId, windowHours = 6, focus) =>
    fetchJson(`/ai/evidence/${encodeURIComponent(evidenceId)}/investigate`, {
      method: 'POST',
      body: JSON.stringify({ context_window_hours: windowHours, focus }),
    }),
  investigateEntity: (entityId, windowHours = 6, focus) =>
    fetchJson(`/ai/entity/${encodeURIComponent(entityId)}/investigate`, {
      method: 'POST',
      body: JSON.stringify({ context_window_hours: windowHours, focus }),
    }),
  investigate: (targetId, windowHours = 6, focus) =>
    fetchJson('/ai/investigate', {
      method: 'POST',
      body: JSON.stringify({ id: targetId, context_window_hours: windowHours, focus }),
    }),
  getAiStatus: () => fetchJson('/ai/status'),

  // Intelligence & Insights Endpoints
  getInsights: (params = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.append('limit', params.limit);
    if (params.offset) q.append('offset', params.offset);
    if (params.priority && params.priority !== 'ALL') q.append('priority', params.priority);
    if (params.status && params.status !== 'ALL') q.append('status', params.status);
    if (params.type && params.type !== 'ALL') q.append('type', params.type);
    const qs = q.toString();
    return fetchJson(qs ? `/insights?${qs}` : '/insights');
  },
  getInsight: (id) => fetchJson(`/insights/${encodeURIComponent(id)}`),
  getInsightsSummary: () => fetchJson('/insights/summary'),
  recordInsightFeedback: (insightId, feedback, cameraId = null, notes = null) =>
    fetchJson(`/insights/${encodeURIComponent(insightId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ operator_feedback: feedback, camera_id: cameraId, notes }),
    }),
  getWhatChanged: () => fetchJson('/insights/what-changed'),
  getRollingSummaries: (window = 'LIVE') =>
    fetchJson(`/insights/summaries/rolling${window ? `?window=${encodeURIComponent(window)}` : ''}`),
  investigateEvidenceNL: (question) =>
    fetchJson('/insights/investigate', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  getObservations: (params = {}) => {
    const q = new URLSearchParams();
    if (params.cameraId) q.append('camera_id', params.cameraId);
    if (params.zoneId) q.append('zone_id', params.zoneId);
    if (params.objectType) q.append('object_type', params.objectType);
    if (params.limit) q.append('limit', params.limit);
    const qs = q.toString();
    return fetchJson(qs ? `/observations?${qs}` : '/observations');
  },

  // Behavioral Analytics Endpoints
  getBehavioralEvents: (params = {}) => {
    const q = new URLSearchParams();
    if (params.cameraId) q.append('camera_id', params.cameraId);
    if (params.zoneId) q.append('zone_id', params.zoneId);
    if (params.trackId) q.append('track_id', params.trackId);
    if (params.behaviorType) q.append('behavior_type', params.behaviorType);
    if (params.minScore) q.append('min_score', params.minScore);
    if (params.status) q.append('status', params.status);
    if (params.limit) q.append('limit', params.limit);
    if (params.offset) q.append('offset', params.offset);
    const qs = q.toString();
    return fetchJson(qs ? `/behavioral/events?${qs}` : '/behavioral/events');
  },
  getBehavioralEvent: (behaviorId) => fetchJson(`/behavioral/events/${encodeURIComponent(behaviorId)}`),
  getBehavioralSummary: () => fetchJson('/behavioral/summary'),


  // Facial Recognition
  getFaceSummary: () => fetchJson('/faces/summary'),
  getFaceRecognitions: (params = {}) => {
    const q = new URLSearchParams();
    if (params.status && params.status !== 'ALL') q.append('status', params.status);
    if (params.cameraId) q.append('camera_id', params.cameraId);
    if (params.search) q.append('search', params.search);
    if (params.limit) q.append('limit', params.limit);
    if (params.offset) q.append('offset', params.offset);
    const qs = q.toString();
    return fetchJson(qs ? `/faces/recognitions?${qs}` : '/faces/recognitions');
  },
  getFaceRecognition: (id) => fetchJson(`/faces/recognitions/${encodeURIComponent(id)}`),
  associateFace: (recognitionId, data) =>
    fetchJson(`/faces/recognitions/${encodeURIComponent(recognitionId)}/associate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getFacePersons: () => fetchJson('/faces/persons'),
  registerFacePerson: (data) =>
    fetchJson('/faces/persons', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteFacePerson: (personId) =>
    fetchJson(`/faces/persons/${encodeURIComponent(personId)}`, {
      method: 'DELETE',
    }),
  getFaceSnapshotUrl: (filename) => `${getV1()}/faces/snapshots/${encodeURIComponent(filename)}`,
  clearFaceRecognitions: () => fetchJson('/faces/clear', { method: 'DELETE' }),
};

export const resolveMediaUrl = (urlOrPath) => {
  if (!urlOrPath) return '';
  if (urlOrPath.startsWith('http://') || urlOrPath.startsWith('https://') || urlOrPath.startsWith('data:')) {
    return urlOrPath;
  }
  const base = getApiBase().replace(/\/+$/, '');
  let cleanPath = urlOrPath.startsWith('/') ? urlOrPath : `/${urlOrPath}`;
  if (!cleanPath.startsWith('/api/')) {
    if (cleanPath.startsWith('/evidence/')) {
      cleanPath = `/api/v1${cleanPath}`;
    } else if (cleanPath.includes('FAC-') || cleanPath.endsWith('.jpg') || cleanPath.endsWith('.png') || cleanPath.endsWith('.jpeg')) {
      cleanPath = `/api/v1/faces/snapshots/${cleanPath.replace(/^\/+/, '')}`;
    }
  }
  return `${base}${cleanPath}`;
};

const API_BASE = getApiBase();
const V1 = getV1();
export { API_BASE, V1, getV1 };
