import { useState, useEffect, useRef } from 'react';
import { api, resolveMediaUrl } from '../services/api';
import {
  FaceIcon,
  PersonIcon,
  UserPlusIcon,
  RefreshIcon,
  SearchIcon,
  CheckIcon,
  CloseIcon,
  CameraIcon,
  TargetIcon,
  AlertIcon,
} from './Icons';

const getFaceImageUrl = (item) => {
  if (!item) return '';
  if (typeof item === 'string') return resolveMediaUrl(item);
  if (item.snapshot_path) return resolveMediaUrl(item.snapshot_path);
  if (item.face_image_path) return resolveMediaUrl(item.face_image_path);
  if (item.recognition_id) return api.getFaceSnapshotUrl(item.recognition_id);
  if (item.person_id) return api.getFaceSnapshotUrl(item.person_id);
  return '';
};

export function FacialRecognitionView({ onSelectTab, onInvestigate }) {
  const [recognitions, setRecognitions] = useState([]);
  const [persons, setPersons] = useState([]);
  const [summary, setSummary] = useState({
    total_recognitions: 0,
    recognized_count: 0,
    unclassified_count: 0,
    registered_persons_count: 0,
  });
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState('ALL'); // ALL | RECOGNIZED | UNCLASSIFIED | PERSONS
  const [searchQuery, setSearchQuery] = useState('');
  const [cameraFilter, setCameraFilter] = useState('ALL');

  // Modals state
  const [registerModalOpen, setRegisterModalOpen] = useState(false);
  const [associateModalTarget, setAssociateModalTarget] = useState(null);
  const [previewSnapshot, setPreviewSnapshot] = useState(null);

  // Register form state
  const [regName, setRegName] = useState('');
  const [regPersonId, setRegPersonId] = useState('');
  const [regRole, setRegRole] = useState('');
  const [regNotes, setRegNotes] = useState('');
  const [regImageBase64, setRegImageBase64] = useState('');
  const [regImagePreview, setRegImagePreview] = useState(null);
  const [regSubmitting, setRegSubmitting] = useState(false);
  const [regError, setRegError] = useState('');
  const fileInputRef = useRef(null);

  // Association modal form state
  const [assocType, setAssocType] = useState('EXISTING'); // EXISTING | NEW
  const [selectedPersonId, setSelectedPersonId] = useState('');
  const [newPersonName, setNewPersonName] = useState('');
  const [newPersonRole, setNewPersonRole] = useState('');
  const [newPersonNotes, setNewPersonNotes] = useState('');
  const [assocSubmitting, setAssocSubmitting] = useState(false);
  const [assocError, setAssocError] = useState('');

  const fetchData = async () => {
    try {
      setLoading(true);
      const [sumRes, recRes, perRes] = await Promise.all([
        api.getFaceSummary().catch(() => ({})),
        api.getFaceRecognitions({ limit: 100 }).catch(() => []),
        api.getFacePersons().catch(() => []),
      ]);

      if (sumRes) setSummary(sumRes);
      if (Array.isArray(recRes)) setRecognitions(recRes);
      if (Array.isArray(perRes)) {
        setPersons(perRes);
        if (perRes.length > 0 && !selectedPersonId) {
          setSelectedPersonId(perRes[0].person_id);
        }
      }
    } catch (err) {
      console.error('Failed to load facial recognition data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setRegError('');
    const reader = new FileReader();
    reader.onload = () => {
      setRegImageBase64(reader.result);
      setRegImagePreview(reader.result);
    };
    reader.onerror = () => {
      setRegError('Failed to read image file.');
    };
    reader.readAsDataURL(file);
  };

  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    if (!regName.trim()) {
      setRegError('Person Name is required.');
      return;
    }
    if (!regImageBase64) {
      setRegError('Face photo is required for ArcFace enrollment.');
      return;
    }
    setRegSubmitting(true);
    setRegError('');
    try {
      await api.registerFacePerson({
        name: regName.trim(),
        person_id: regPersonId.trim() || undefined,
        role: regRole.trim(),
        notes: regNotes.trim(),
        image_base64: regImageBase64,
      });
      setRegisterModalOpen(false);
      setRegName('');
      setRegPersonId('');
      setRegRole('');
      setRegNotes('');
      setRegImageBase64('');
      setRegImagePreview(null);
      await fetchData();
    } catch (err) {
      setRegError(err.message || 'Enrollment failed.');
    } finally {
      setRegSubmitting(false);
    }
  };

  const handleAssociateSubmit = async (e) => {
    e.preventDefault();
    if (!associateModalTarget) return;
    setAssocSubmitting(true);
    setAssocError('');
    try {
      const payload =
        assocType === 'EXISTING'
          ? { person_id: selectedPersonId }
          : {
              name: newPersonName.trim(),
              role: newPersonRole.trim(),
              notes: newPersonNotes.trim(),
            };

      if (assocType === 'NEW' && !newPersonName.trim()) {
        setAssocError('Person Name is required.');
        setAssocSubmitting(false);
        return;
      }

      await api.associateFace(associateModalTarget.recognition_id, payload);
      setAssociateModalTarget(null);
      setNewPersonName('');
      setNewPersonRole('');
      setNewPersonNotes('');
      await fetchData();
    } catch (err) {
      setAssocError(err.message || 'Association failed.');
    } finally {
      setAssocSubmitting(false);
    }
  };

  const handleDeletePerson = async (personId, name) => {
    if (!window.confirm(`Delete registered profile for ${name} (${personId})?`)) return;
    try {
      await api.deleteFacePerson(personId);
      await fetchData();
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleClearHistory = async () => {
    if (!window.confirm('Clear all face recognition event records? Enrolled persons will be preserved.')) return;
    try {
      await api.clearFaceRecognitions();
      await fetchData();
    } catch (err) {
      alert(`Clear failed: ${err.message}`);
    }
  };

  const uniqueCameras = Array.from(new Set(recognitions.map((r) => r.camera_id).filter(Boolean)));

  const filteredRecognitions = recognitions.filter((r) => {
    if (activeFilter === 'RECOGNIZED' && r.status !== 'RECOGNIZED') return false;
    if (activeFilter === 'UNCLASSIFIED' && r.status !== 'UNCLASSIFIED') return false;
    if (cameraFilter !== 'ALL' && r.camera_id !== cameraFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = r.person_name?.toLowerCase().includes(q);
      const matchId = r.person_id?.toLowerCase().includes(q);
      const matchTrack = r.track_id?.toLowerCase().includes(q);
      const matchCam = r.camera_id?.toLowerCase().includes(q);
      if (!matchName && !matchId && !matchTrack && !matchCam) return false;
    }
    return true;
  });

  const filteredPersons = persons.filter((p) => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = p.name?.toLowerCase().includes(q);
      const matchId = p.person_id?.toLowerCase().includes(q);
      const matchRole = p.role?.toLowerCase().includes(q);
      if (!matchName && !matchId && !matchRole) return false;
    }
    return true;
  });

  const formatTimestamp = (ts) => {
    if (!ts) return 'Unknown';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return ts;
    }
  };

  const formatRelativeTime = (ts) => {
    if (!ts) return '';
    try {
      const diffSec = Math.round((Date.now() - new Date(ts).getTime()) / 1000);
      if (diffSec < 45) return 'Just now';
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
      if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
      return `${Math.floor(diffSec / 86400)}d ago`;
    } catch {
      return '';
    }
  };

  return (
    <div style={{ paddingBottom: '32px' }}>
      {/* SECTION HEAD */}
      <div className="section-head" style={{ flexWrap: 'wrap', gap: '14px', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FaceIcon size={18} style={{ color: 'var(--green)' }} />
              Facial Recognition & Identification
            </h2>
            <span
              className="beta-pill"
              style={{
                color: 'var(--green)',
                borderColor: 'rgba(47, 204, 139, 0.4)',
                background: 'var(--green-dim)',
                fontWeight: '600',
              }}
            >
              ArcFace 512-D
            </span>
          </div>
          <span className="section-sub">
            YOLO Face Detection → Face Crop → ArcFace Hypersphere Matching → Database Intelligence
          </span>
        </div>

        {/* STAT COUNTERS */}
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
          <div
            className="tile"
            style={{
              padding: '6px 14px',
              display: 'flex',
              flexDirection: 'column',
              minWidth: '95px',
              borderRadius: '6px',
            }}
          >
            <span style={{ fontSize: '10px', color: 'var(--text-low)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Total Faces
            </span>
            <span style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
              {summary.total_recognitions || 0}
            </span>
          </div>

          <div
            className="tile"
            style={{
              padding: '6px 14px',
              display: 'flex',
              flexDirection: 'column',
              minWidth: '95px',
              borderRadius: '6px',
              borderColor: 'rgba(47, 204, 139, 0.3)',
            }}
          >
            <span style={{ fontSize: '10px', color: 'var(--green)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Recognized
            </span>
            <span style={{ fontSize: '16px', fontWeight: '700', color: 'var(--green)', fontFamily: 'var(--mono)' }}>
              {summary.recognized_count || 0}
            </span>
          </div>

          <div
            className="tile"
            style={{
              padding: '6px 14px',
              display: 'flex',
              flexDirection: 'column',
              minWidth: '95px',
              borderRadius: '6px',
              borderColor: summary.unclassified_count > 0 ? 'rgba(239, 82, 81, 0.4)' : 'var(--hair)',
            }}
          >
            <span style={{ fontSize: '10px', color: 'var(--orange)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Unclassified
            </span>
            <span style={{ fontSize: '16px', fontWeight: '700', color: 'var(--orange)', fontFamily: 'var(--mono)' }}>
              {summary.unclassified_count || 0}
            </span>
          </div>

          <div
            className="tile"
            style={{
              padding: '6px 14px',
              display: 'flex',
              flexDirection: 'column',
              minWidth: '95px',
              borderRadius: '6px',
            }}
          >
            <span style={{ fontSize: '10px', color: 'var(--gold)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Enrolled
            </span>
            <span style={{ fontSize: '16px', fontWeight: '700', color: 'var(--gold)', fontFamily: 'var(--mono)' }}>
              {summary.registered_persons_count || persons.length || 0}
            </span>
          </div>

          <button
            className="n-btn"
            style={{
              background: 'var(--green-dim)',
              color: 'var(--green)',
              borderColor: 'rgba(47, 204, 139, 0.4)',
              fontWeight: '600',
              padding: '6px 14px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
            onClick={() => setRegisterModalOpen(true)}
          >
            <UserPlusIcon size={14} /> Enroll Person
          </button>
        </div>
      </div>

      {/* FILTER & SEARCH BAR */}
      <div
        className="tile"
        style={{
          padding: '10px 14px',
          marginBottom: '16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '12px',
          flexWrap: 'wrap',
          borderRadius: '8px',
        }}
      >
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
          {[
            { id: 'ALL', label: 'All Face Sightings' },
            { id: 'RECOGNIZED', label: 'Recognized' },
            { id: 'UNCLASSIFIED', label: `Unclassified (${summary.unclassified_count || 0})` },
            { id: 'PERSONS', label: `Enrolled Directory (${persons.length})` },
          ].map((tab) => (
            <button
              key={tab.id}
              className="n-btn"
              style={{
                background: activeFilter === tab.id ? 'var(--panel-hover)' : 'var(--panel-hi)',
                color: activeFilter === tab.id ? 'var(--text-hi)' : 'var(--text-mid)',
                borderColor: activeFilter === tab.id ? 'var(--hair)' : 'transparent',
                fontWeight: activeFilter === tab.id ? '600' : '400',
              }}
              onClick={() => setActiveFilter(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {activeFilter !== 'PERSONS' && uniqueCameras.length > 0 && (
            <select
              value={cameraFilter}
              onChange={(e) => setCameraFilter(e.target.value)}
              style={{
                background: '#0a0a0a',
                border: '1px solid var(--hair)',
                borderRadius: '6px',
                padding: '4px 8px',
                color: 'var(--text-hi)',
                fontSize: '11.5px',
                outline: 'none',
              }}
            >
              <option value="ALL">All Cameras</option>
              {uniqueCameras.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          )}

          <div style={{ position: 'relative', minWidth: '180px' }}>
            <input
              type="text"
              placeholder="Search name, ID, camera..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                background: '#0a0a0a',
                border: '1px solid var(--hair)',
                borderRadius: '6px',
                padding: '5px 10px 5px 28px',
                color: 'var(--text-hi)',
                fontSize: '11.5px',
                outline: 'none',
                width: '100%',
              }}
            />
            <SearchIcon
              size={12}
              style={{ position: 'absolute', left: '9px', top: '8px', color: 'var(--text-low)' }}
            />
          </div>

          <button
            className="n-btn"
            onClick={fetchData}
            title="Refresh list"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}
          >
            <RefreshIcon size={12} /> Refresh
          </button>

          {activeFilter !== 'PERSONS' && recognitions.length > 0 && (
            <button
              className="n-btn"
              style={{
                background: 'var(--red-dim)',
                color: 'var(--red)',
                borderColor: 'rgba(239,82,81,0.3)',
              }}
              onClick={handleClearHistory}
              title="Clear recognition sightings history"
            >
              Clear Log
            </button>
          )}
        </div>
      </div>

      {/* VIEW CONTENT */}
      {activeFilter === 'PERSONS' ? (
        /* ENROLLED PERSONS DIRECTORY */
        <div>
          {filteredPersons.length === 0 ? (
            <div
              className="tile"
              style={{
                padding: '48px 20px',
                textAlign: 'center',
                color: 'var(--text-mid)',
                borderRadius: '8px',
              }}
            >
              <PersonIcon size={32} style={{ color: 'var(--text-low)', marginBottom: '10px' }} />
              <div style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-hi)' }}>
                No Enrolled Persons Found
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-low)', marginTop: '4px' }}>
                Enroll personnel with a face image to enable automated ArcFace recognition.
              </div>
              <button
                className="n-btn"
                style={{
                  background: 'var(--green-dim)',
                  color: 'var(--green)',
                  borderColor: 'rgba(47, 204, 139, 0.4)',
                  fontWeight: '600',
                  marginTop: '16px',
                }}
                onClick={() => setRegisterModalOpen(true)}
              >
                + Enroll First Person
              </button>
            </div>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: '12px',
              }}
            >
              {filteredPersons.map((p) => (
                <div
                  key={p.person_id}
                  className="tile"
                  style={{
                    padding: '14px',
                    borderRadius: '8px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                  }}
                >
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <div
                      style={{
                        width: '54px',
                        height: '54px',
                        borderRadius: '6px',
                        overflow: 'hidden',
                        background: '#0a0a0a',
                        border: '1px solid var(--hair)',
                        flexShrink: 0,
                        cursor: 'pointer',
                      }}
                      onClick={() => setPreviewSnapshot(getFaceImageUrl(p))}
                    >
                      {getFaceImageUrl(p) ? (
                        <img
                          src={getFaceImageUrl(p)}
                          alt={p.name}
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={(e) => {
                            if (!e.currentTarget.dataset.retried && p.person_id) {
                              e.currentTarget.dataset.retried = '1';
                              e.currentTarget.src = api.getFaceSnapshotUrl(p.person_id);
                            }
                          }}
                        />
                      ) : (
                        <div
                          style={{
                            width: '100%',
                            height: '100%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: 'var(--text-low)',
                          }}
                        >
                          <FaceIcon size={22} />
                        </div>
                      )}
                    </div>

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: '14px',
                          fontWeight: '700',
                          color: 'var(--text-hi)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {p.name}
                      </div>
                      <div
                        style={{
                          fontSize: '11px',
                          fontFamily: 'var(--mono)',
                          color: 'var(--gold)',
                          marginTop: '2px',
                        }}
                      >
                        {p.person_id}
                      </div>
                      {p.role && (
                        <div
                          style={{
                            fontSize: '11px',
                            color: 'var(--text-mid)',
                            marginTop: '2px',
                          }}
                        >
                          {p.role}
                        </div>
                      )}
                    </div>
                  </div>

                  {p.notes && (
                    <div
                      style={{
                        fontSize: '11px',
                        color: 'var(--text-low)',
                        background: 'rgba(255,255,255,0.02)',
                        padding: '6px 8px',
                        borderRadius: '4px',
                        border: '1px solid var(--hair-soft)',
                      }}
                    >
                      {p.notes}
                    </div>
                  )}

                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginTop: 'auto',
                      paddingTop: '6px',
                      borderTop: '1px solid var(--hair-soft)',
                      fontSize: '10.5px',
                      color: 'var(--text-low)',
                    }}
                  >
                    <span>Enrolled {formatRelativeTime(p.created_at)}</span>
                    <button
                      className="n-btn"
                      style={{
                        padding: '2px 8px',
                        fontSize: '10px',
                        color: 'var(--red)',
                        background: 'transparent',
                        borderColor: 'transparent',
                      }}
                      onClick={() => handleDeletePerson(p.person_id, p.name)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* RECOGNITION / UNCLASSIFIED SIGHTINGS GRID */
        <div>
          {filteredRecognitions.length === 0 ? (
            <div
              className="tile"
              style={{
                padding: '48px 20px',
                textAlign: 'center',
                color: 'var(--text-mid)',
                borderRadius: '8px',
              }}
            >
              <FaceIcon size={32} style={{ color: 'var(--text-low)', marginBottom: '10px' }} />
              <div style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-hi)' }}>
                No Facial Detections Found
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-low)', marginTop: '4px' }}>
                {searchQuery || cameraFilter !== 'ALL'
                  ? 'No face sightings match the active filters.'
                  : 'YOLO face detections will automatically be cropped, matched through ArcFace, and recorded here.'}
              </div>
            </div>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                gap: '12px',
              }}
            >
              {filteredRecognitions.map((rec) => {
                const isRecognized = rec.status === 'RECOGNIZED';
                const simPercent = Math.round((rec.similarity || 0) * 100);

                return (
                  <div
                    key={rec.recognition_id}
                    className="tile"
                    style={{
                      padding: '14px',
                      borderRadius: '8px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '10px',
                      borderColor: isRecognized ? 'rgba(47, 204, 139, 0.25)' : 'rgba(181, 115, 46, 0.25)',
                    }}
                  >
                    {/* TOP STATUS BAR */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span
                        className="beta-pill"
                        style={{
                          color: isRecognized ? 'var(--green)' : 'var(--orange)',
                          borderColor: isRecognized ? 'rgba(47, 204, 139, 0.4)' : 'rgba(181, 115, 46, 0.4)',
                          background: isRecognized ? 'var(--green-dim)' : 'var(--orange-dim)',
                          fontWeight: '700',
                          fontSize: '10px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <span
                          style={{
                            width: '5px',
                            height: '5px',
                            borderRadius: '50%',
                            background: isRecognized ? 'var(--green)' : 'var(--orange)',
                          }}
                        />
                        {isRecognized ? 'RECOGNIZED' : 'UNCLASSIFIED'}
                      </span>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {rec.detection_count > 1 && (
                          <span
                            className="nav-badge neutral"
                            style={{ fontSize: '10px', padding: '1px 6px' }}
                            title="Number of times detected across stream"
                          >
                            Seen {rec.detection_count}x
                          </span>
                        )}
                        <span style={{ fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                          {formatRelativeTime(rec.last_seen)}
                        </span>
                      </div>
                    </div>

                    {/* MAIN INFO SECTION WITH PHOTO */}
                    <div style={{ display: 'flex', gap: '12px' }}>
                      {/* SNAPSHOT PREVIEW */}
                      <div
                        style={{
                          width: '78px',
                          height: '78px',
                          borderRadius: '6px',
                          overflow: 'hidden',
                          background: '#0a0a0a',
                          border: '1px solid var(--hair)',
                          flexShrink: 0,
                          position: 'relative',
                          cursor: 'pointer',
                        }}
                        onClick={() => setPreviewSnapshot(getFaceImageUrl(rec))}
                        title="Click to expand face snapshot"
                      >
                        {getFaceImageUrl(rec) ? (
                          <img
                            src={getFaceImageUrl(rec)}
                            alt={rec.person_name}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            onError={(e) => {
                              if (!e.currentTarget.dataset.retried && rec.recognition_id) {
                                e.currentTarget.dataset.retried = '1';
                                e.currentTarget.src = api.getFaceSnapshotUrl(rec.recognition_id);
                              }
                            }}
                          />
                        ) : (
                          <div
                            style={{
                              width: '100%',
                              height: '100%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: 'var(--text-low)',
                            }}
                          >
                            <FaceIcon size={24} />
                          </div>
                        )}
                        <div
                          style={{
                            position: 'absolute',
                            bottom: '2px',
                            right: '2px',
                            background: 'rgba(0,0,0,0.7)',
                            padding: '1px 4px',
                            borderRadius: '3px',
                            fontSize: '8.5px',
                            color: '#ffffff',
                          }}
                        >
                          CROP
                        </div>
                      </div>

                      {/* IDENTITY DETAILS */}
                      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '3px' }}>
                        <div
                          style={{
                            fontSize: '14.5px',
                            fontWeight: '700',
                            color: isRecognized ? 'var(--text-hi)' : 'var(--text-mid)',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {rec.person_name}
                        </div>

                        {rec.person_id ? (
                          <div
                            style={{
                              fontSize: '11px',
                              fontFamily: 'var(--mono)',
                              color: 'var(--gold)',
                            }}
                          >
                            ID: {rec.person_id}
                          </div>
                        ) : (
                          <div style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                            No identity associated
                          </div>
                        )}

                        {/* MATCH SIMILARITY METER */}
                        <div style={{ marginTop: '4px' }}>
                          <div
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              fontSize: '10px',
                              color: 'var(--text-low)',
                              marginBottom: '2px',
                            }}
                          >
                            <span>ArcFace Match</span>
                            <span
                              style={{
                                color: isRecognized ? 'var(--green)' : 'var(--text-mid)',
                                fontWeight: '600',
                                fontFamily: 'var(--mono)',
                              }}
                            >
                              {simPercent}%
                            </span>
                          </div>
                          <div
                            style={{
                              height: '4px',
                              background: '#1a1a1a',
                              borderRadius: '2px',
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                height: '100%',
                                width: `${Math.min(100, Math.max(5, simPercent))}%`,
                                background: isRecognized ? 'var(--green)' : 'var(--orange)',
                                borderRadius: '2px',
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* TELEMETRY METADATA ROW */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(2, 1fr)',
                        gap: '6px',
                        background: 'rgba(255,255,255,0.02)',
                        padding: '6px 8px',
                        borderRadius: '4px',
                        border: '1px solid var(--hair-soft)',
                        fontSize: '11px',
                      }}
                    >
                      <div>
                        <span style={{ color: 'var(--text-low)' }}>Camera: </span>
                        <span style={{ color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
                          {rec.camera_id}
                        </span>
                      </div>

                      <div>
                        <span style={{ color: 'var(--text-low)' }}>Track: </span>
                        {rec.track_id && onSelectTab ? (
                          <span
                            style={{
                              color: 'var(--gold)',
                              fontFamily: 'var(--mono)',
                              cursor: 'pointer',
                              textDecoration: 'underline',
                            }}
                            onClick={() => onSelectTab('threads', rec.track_id)}
                            title="Jump to Activity Thread"
                          >
                            {rec.track_id}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
                            {rec.track_id || 'N/A'}
                          </span>
                        )}
                      </div>

                      <div>
                        <span style={{ color: 'var(--text-low)' }}>First seen: </span>
                        <span style={{ color: 'var(--text-mid)' }}>{formatTimestamp(rec.first_seen)}</span>
                      </div>

                      <div>
                        <span style={{ color: 'var(--text-low)' }}>Last seen: </span>
                        <span style={{ color: 'var(--text-mid)' }}>{formatTimestamp(rec.last_seen)}</span>
                      </div>
                    </div>

                    {/* ACTIONS ROW */}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        paddingTop: '4px',
                        borderTop: '1px solid var(--hair-soft)',
                      }}
                    >
                      {rec.event_id && onInvestigate ? (
                        <button
                          className="n-btn"
                          style={{
                            padding: '2px 8px',
                            fontSize: '10.5px',
                            color: 'var(--text-mid)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                          onClick={() => onInvestigate({ event_id: rec.event_id, camera_id: rec.camera_id })}
                        >
                          <AlertIcon size={11} /> View Event
                        </button>
                      ) : (
                        <span style={{ fontSize: '10.5px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                          {rec.recognition_id}
                        </span>
                      )}

                      {!isRecognized ? (
                        <button
                          className="n-btn"
                          style={{
                            background: 'var(--gold-dim)',
                            color: 'var(--gold)',
                            borderColor: 'rgba(201, 154, 91, 0.4)',
                            fontWeight: '600',
                            padding: '3px 10px',
                            fontSize: '11px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '5px',
                          }}
                          onClick={() => {
                            setAssociateModalTarget(rec);
                            setAssocType('EXISTING');
                            setNewPersonName('');
                            setAssocError('');
                          }}
                        >
                          <UserPlusIcon size={12} /> Associate with Person
                        </button>
                      ) : (
                        <span
                          style={{
                            fontSize: '10.5px',
                            color: 'var(--green)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '3px',
                          }}
                        >
                          <CheckIcon size={11} /> Verified Match
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* MODAL 1: ADD / ENROLL PERSON */}
      {registerModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.85)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '16px',
          }}
          onClick={() => setRegisterModalOpen(false)}
        >
          <div
            className="tile"
            style={{
              width: '100%',
              maxWidth: '460px',
              background: '#101010',
              border: '1px solid var(--hair)',
              borderRadius: '10px',
              padding: '20px',
              boxShadow: '0 20px 50px rgba(0,0,0,0.8)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <UserPlusIcon size={16} style={{ color: 'var(--green)' }} />
                <h3 style={{ fontSize: '15px', fontWeight: '700', color: 'var(--text-hi)' }}>
                  Enroll Face Profile
                </h3>
              </div>
              <button
                className="n-btn"
                style={{ padding: '4px', border: 'none' }}
                onClick={() => setRegisterModalOpen(false)}
              >
                <CloseIcon size={14} />
              </button>
            </div>

            <p style={{ fontSize: '12px', color: 'var(--text-mid)', marginBottom: '16px' }}>
              Upload a clear face photo. Helios will extract the 512-D ArcFace embedding vector and persist it to the SQLite database.
            </p>

            {regError && (
              <div
                style={{
                  background: 'var(--red-dim)',
                  border: '1px solid rgba(239,82,81,0.4)',
                  color: 'var(--red)',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  marginBottom: '14px',
                }}
              >
                {regError}
              </div>
            )}

            <form onSubmit={handleRegisterSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {/* IMAGE UPLOAD / PREVIEW */}
              <div
                style={{
                  border: '1px dashed var(--hair)',
                  borderRadius: '8px',
                  padding: '16px',
                  textAlign: 'center',
                  background: '#0a0a0a',
                  cursor: 'pointer',
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  accept="image/jpeg,image/png,image/webp"
                  style={{ display: 'none' }}
                  onChange={handleFileSelect}
                />
                {regImagePreview ? (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
                    <img
                      src={regImagePreview}
                      alt="Preview"
                      style={{
                        width: '90px',
                        height: '90px',
                        objectFit: 'cover',
                        borderRadius: '8px',
                        border: '1px solid var(--green)',
                      }}
                    />
                    <span style={{ fontSize: '11px', color: 'var(--green)' }}>✓ Face image loaded (click to replace)</span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
                    <CameraIcon size={24} style={{ color: 'var(--text-low)' }} />
                    <span style={{ fontSize: '12px', color: 'var(--text-hi)', fontWeight: '600' }}>
                      Click to upload face photo
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                      JPEG, PNG or WebP · High clarity recommended
                    </span>
                  </div>
                )}
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-mid)', marginBottom: '4px' }}>
                  Person Name <span style={{ color: 'var(--red)' }}>*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. John Doe"
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  style={{
                    width: '100%',
                    background: '#0a0a0a',
                    border: '1px solid var(--hair)',
                    borderRadius: '6px',
                    padding: '7px 10px',
                    color: 'var(--text-hi)',
                    fontSize: '12px',
                    outline: 'none',
                  }}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-mid)', marginBottom: '4px' }}>
                    Person ID (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. EMP-104"
                    value={regPersonId}
                    onChange={(e) => setRegPersonId(e.target.value)}
                    style={{
                      width: '100%',
                      background: '#0a0a0a',
                      border: '1px solid var(--hair)',
                      borderRadius: '6px',
                      padding: '7px 10px',
                      color: 'var(--text-hi)',
                      fontSize: '12px',
                      outline: 'none',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-mid)', marginBottom: '4px' }}>
                    Role / Clearance
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Security Lead"
                    value={regRole}
                    onChange={(e) => setRegRole(e.target.value)}
                    style={{
                      width: '100%',
                      background: '#0a0a0a',
                      border: '1px solid var(--hair)',
                      borderRadius: '6px',
                      padding: '7px 10px',
                      color: 'var(--text-hi)',
                      fontSize: '12px',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-mid)', marginBottom: '4px' }}>
                  Notes / Description
                </label>
                <textarea
                  rows={2}
                  placeholder="Additional security notes or access details..."
                  value={regNotes}
                  onChange={(e) => setRegNotes(e.target.value)}
                  style={{
                    width: '100%',
                    background: '#0a0a0a',
                    border: '1px solid var(--hair)',
                    borderRadius: '6px',
                    padding: '7px 10px',
                    color: 'var(--text-hi)',
                    fontSize: '12px',
                    outline: 'none',
                    resize: 'none',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '6px' }}>
                <button
                  type="button"
                  className="n-btn"
                  onClick={() => setRegisterModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="n-btn"
                  style={{
                    background: 'var(--green-dim)',
                    color: 'var(--green)',
                    borderColor: 'rgba(47, 204, 139, 0.5)',
                    fontWeight: '600',
                  }}
                  disabled={regSubmitting}
                >
                  {regSubmitting ? 'Computing ArcFace Embedding...' : 'Save & Register Face'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: ASSOCIATE UNCLASSIFIED FACE */}
      {associateModalTarget && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.85)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '16px',
          }}
          onClick={() => setAssociateModalTarget(null)}
        >
          <div
            className="tile"
            style={{
              width: '100%',
              maxWidth: '460px',
              background: '#101010',
              border: '1px solid var(--hair)',
              borderRadius: '10px',
              padding: '20px',
              boxShadow: '0 20px 50px rgba(0,0,0,0.8)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <TargetIcon size={16} style={{ color: 'var(--gold)' }} />
                <h3 style={{ fontSize: '15px', fontWeight: '700', color: 'var(--text-hi)' }}>
                  Associate Unclassified Face
                </h3>
              </div>
              <button
                className="n-btn"
                style={{ padding: '4px', border: 'none' }}
                onClick={() => setAssociateModalTarget(null)}
              >
                <CloseIcon size={14} />
              </button>
            </div>

            {/* FACE CROP SNAPSHOT PREVIEW */}
            <div
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'center',
                background: '#0a0a0a',
                padding: '10px',
                borderRadius: '8px',
                border: '1px solid var(--hair)',
                marginBottom: '14px',
              }}
            >
              <div
                style={{
                  width: '60px',
                  height: '60px',
                  borderRadius: '6px',
                  overflow: 'hidden',
                  background: '#141414',
                  flexShrink: 0,
                }}
              >
                {getFaceImageUrl(associateModalTarget) ? (
                  <img
                    src={getFaceImageUrl(associateModalTarget)}
                    alt="Target"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => {
                      if (!e.currentTarget.dataset.retried && associateModalTarget.recognition_id) {
                        e.currentTarget.dataset.retried = '1';
                        e.currentTarget.src = api.getFaceSnapshotUrl(associateModalTarget.recognition_id);
                      }
                    }}
                  />
                ) : (
                  <FaceIcon size={24} />
                )}
              </div>
              <div style={{ fontSize: '12px' }}>
                <div style={{ color: 'var(--text-hi)', fontWeight: '600' }}>
                  Camera: {associateModalTarget.camera_id} · Track: {associateModalTarget.track_id || 'N/A'}
                </div>
                <div style={{ color: 'var(--text-low)', fontSize: '11px', marginTop: '2px' }}>
                  Seen at {formatTimestamp(associateModalTarget.last_seen)} ({associateModalTarget.detection_count || 1}x detections)
                </div>
              </div>
            </div>

            {assocError && (
              <div
                style={{
                  background: 'var(--red-dim)',
                  border: '1px solid rgba(239,82,81,0.4)',
                  color: 'var(--red)',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  marginBottom: '14px',
                }}
              >
                {assocError}
              </div>
            )}

            {/* TAB SELECTOR */}
            <div style={{ display: 'flex', gap: '6px', marginBottom: '14px' }}>
              <button
                type="button"
                className="n-btn"
                style={{
                  flex: 1,
                  background: assocType === 'EXISTING' ? 'var(--panel-hover)' : 'transparent',
                  color: assocType === 'EXISTING' ? 'var(--text-hi)' : 'var(--text-mid)',
                  borderColor: assocType === 'EXISTING' ? 'var(--hair)' : 'transparent',
                  fontWeight: assocType === 'EXISTING' ? '600' : '400',
                }}
                onClick={() => setAssocType('EXISTING')}
              >
                Link to Existing Person
              </button>
              <button
                type="button"
                className="n-btn"
                style={{
                  flex: 1,
                  background: assocType === 'NEW' ? 'var(--panel-hover)' : 'transparent',
                  color: assocType === 'NEW' ? 'var(--text-hi)' : 'var(--text-mid)',
                  borderColor: assocType === 'NEW' ? 'var(--hair)' : 'transparent',
                  fontWeight: assocType === 'NEW' ? '600' : '400',
                }}
                onClick={() => setAssocType('NEW')}
              >
                Create New Identity
              </button>
            </div>

            <form onSubmit={handleAssociateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {assocType === 'EXISTING' ? (
                <div>
                  <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-mid)', marginBottom: '4px' }}>
                    Select Enrolled Person
                  </label>
                  {persons.length === 0 ? (
                    <div style={{ fontSize: '12px', color: 'var(--text-low)', padding: '8px 0' }}>
                      No enrolled persons yet. Switch to "Create New Identity" to register.
                    </div>
                  ) : (
                    <select
                      value={selectedPersonId}
                      onChange={(e) => setSelectedPersonId(e.target.value)}
                      style={{
                        width: '100%',
                        background: '#0a0a0a',
                        border: '1px solid var(--hair)',
                        borderRadius: '6px',
                        padding: '7px 10px',
                        color: 'var(--text-hi)',
                        fontSize: '12px',
                        outline: 'none',
                      }}
                    >
                      {persons.map((p) => (
                        <option key={p.person_id} value={p.person_id}>
                          {p.name} ({p.person_id}) {p.role ? `— ${p.role}` : ''}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              ) : (
                <>
                  <div>
                    <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-mid)', marginBottom: '4px' }}>
                      Person Name <span style={{ color: 'var(--red)' }}>*</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Jane Doe"
                      value={newPersonName}
                      onChange={(e) => setNewPersonName(e.target.value)}
                      style={{
                        width: '100%',
                        background: '#0a0a0a',
                        border: '1px solid var(--hair)',
                        borderRadius: '6px',
                        padding: '7px 10px',
                        color: 'var(--text-hi)',
                        fontSize: '12px',
                        outline: 'none',
                      }}
                      required
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-mid)', marginBottom: '4px' }}>
                      Role / Department
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Logistics Contractor"
                      value={newPersonRole}
                      onChange={(e) => setNewPersonRole(e.target.value)}
                      style={{
                        width: '100%',
                        background: '#0a0a0a',
                        border: '1px solid var(--hair)',
                        borderRadius: '6px',
                        padding: '7px 10px',
                        color: 'var(--text-hi)',
                        fontSize: '12px',
                        outline: 'none',
                      }}
                    />
                  </div>
                </>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
                <button
                  type="button"
                  className="n-btn"
                  onClick={() => setAssociateModalTarget(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="n-btn"
                  style={{
                    background: 'var(--gold-dim)',
                    color: 'var(--gold)',
                    borderColor: 'rgba(201, 154, 91, 0.5)',
                    fontWeight: '600',
                  }}
                  disabled={assocSubmitting || (assocType === 'EXISTING' && persons.length === 0)}
                >
                  {assocSubmitting ? 'Updating Database...' : 'Confirm Association'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: SNAPSHOT FULL PREVIEW */}
      {previewSnapshot && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.9)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 99999,
            padding: '20px',
          }}
          onClick={() => setPreviewSnapshot(null)}
        >
          <div
            style={{
              position: 'relative',
              maxWidth: '90vw',
              maxHeight: '90vh',
              borderRadius: '8px',
              overflow: 'hidden',
              border: '1px solid var(--hair)',
              background: '#0a0a0a',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setPreviewSnapshot(null)}
              style={{
                position: 'absolute',
                top: '10px',
                right: '10px',
                background: 'rgba(0,0,0,0.7)',
                color: '#fff',
                padding: '6px',
                borderRadius: '50%',
                display: 'flex',
              }}
            >
              <CloseIcon size={16} />
            </button>
            <img
              src={resolveMediaUrl(previewSnapshot)}
              alt="High resolution face crop"
              style={{ width: '100%', height: 'auto', maxHeight: '80vh', display: 'block', objectFit: 'contain' }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
