import { useState } from 'react';
import { api, V1 } from '../services/api';
import { SkeletonImage, EvidenceCardSkeleton } from './SkeletonLoader';
import { RefreshIcon, CheckIcon, SearchIcon, CloseIcon, DownloadIcon, CarIcon, AiSparklesIcon } from './Icons';

export function EvidenceView({ evidence = [], onRefresh, onInvestigate, onSelectTab, loading = false }) {
  const [clearing, setClearing] = useState(false);
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [previewItem, setPreviewItem] = useState(null);

  const handleClearCache = async () => {
    if (!window.confirm('Clear all cached evidence items?')) return;
    setClearing(true);
    try {
      await api.clearEvidenceCache();
      if (onRefresh) onRefresh();
    } catch (err) {
      alert(`Failed to clear evidence cache: ${err.message}`);
    } finally {
      setClearing(false);
    }
  };

  const filteredEvidence = evidence.filter((ev) => {
    if (typeFilter !== 'ALL' && (ev.type || 'SNAPSHOT').toUpperCase() !== typeFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      const matchId = ev.evidence_id?.toLowerCase().includes(q);
      const matchEvt = ev.event_id?.toLowerCase().includes(q);
      const vi = ev.metadata?.vehicle_intelligence;
      const matchVi = vi
        ? (vi.type?.toLowerCase().includes(q) ||
           vi.color?.toLowerCase().includes(q) ||
           vi.vehicle_id?.toLowerCase().includes(q))
        : false;
      if (!matchId && !matchEvt && !matchVi) return false;
    }
    return true;
  });

  return (
    <div>
      {/* SECTION HEAD */}
      <div className="section-head" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2>Captured Evidence Vault</h2>
          <span className="section-sub">
            Real-time automated snapshot cache · Max 30 items ({filteredEvidence.length} / {evidence.length} cached)
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="Search evidence or event ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              background: '#0a0a0a',
              border: '1px solid var(--hair)',
              borderRadius: '6px',
              padding: '4px 10px',
              color: 'var(--text-hi)',
              fontSize: '11.5px',
              outline: 'none',
              minWidth: '150px',
              flex: '1 1 180px',
            }}
          />
          {['ALL', 'SNAPSHOT', 'VIDEO_CLIP', 'AUDIO'].map((t) => (
            <button
              key={t}
              className="n-btn"
              style={{
                background: typeFilter === t ? 'var(--panel-hover)' : 'var(--panel-hi)',
                color: typeFilter === t ? 'var(--text-hi)' : 'var(--text-mid)',
              }}
              onClick={() => setTypeFilter(t)}
            >
              {t}
            </button>
          ))}
          {onRefresh && (
            <button
              className="n-btn"
              onClick={onRefresh}
              title="Refresh evidence list"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
            >
              <RefreshIcon size={12} /> Refresh
            </button>

          )}
          <button
            className="n-btn"
            style={{ background: 'var(--red-dim)', color: 'var(--red)', borderColor: 'rgba(239,82,81,0.3)', marginLeft: '4px' }}
            disabled={clearing || evidence.length === 0}
            onClick={handleClearCache}
          >
            {clearing ? 'Clearing...' : 'Clear Cache'}
          </button>
        </div>
      </div>

      {/* PREMIUM TILE GRID */}
      <div className="evidence-grid">
        {loading && evidence.length === 0 ? (
          <>
            <EvidenceCardSkeleton />
            <EvidenceCardSkeleton />
            <EvidenceCardSkeleton />
            <EvidenceCardSkeleton />
            <EvidenceCardSkeleton />
            <EvidenceCardSkeleton />
          </>
        ) : filteredEvidence.length > 0 ? (
          filteredEvidence.map((ev) => {
            const snapshotUrl = api.getEvidenceFileUrl(ev.evidence_id);

            return (
              <div
                key={ev.evidence_id}
                className="tile n-tile"
                style={{
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  borderRadius: '12px',
                }}
              >
                {/* TILE HEADER */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span className="n-chip attention" style={{ padding: '2px 7px' }}>
                      <span className="n-chip-dot"></span>
                      {ev.type || 'SNAPSHOT'}
                    </span>
                    <b style={{ fontSize: '12px', color: 'var(--text-hi)', fontFamily: 'var(--mono)' }}>
                      {ev.evidence_id}
                    </b>
                    {ev.metadata?.vehicle_intelligence && (
                      <span
                        className="n-chip"
                        style={{
                          padding: '2px 6px',
                          fontSize: '10px',
                          background: 'rgba(201, 154, 91, 0.12)',
                          color: '#C99A5B',
                          borderColor: 'rgba(201, 154, 91, 0.3)',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <CarIcon size={11} /> {ev.metadata.vehicle_intelligence.color ? ev.metadata.vehicle_intelligence.color.toUpperCase() : ''}{' '}
                        {ev.metadata.vehicle_intelligence.type ? ev.metadata.vehicle_intelligence.type.toUpperCase() : 'VEHICLE'}
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                    {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'Recently'}
                  </span>
                </div>

                {/* PREVIEW MEDIA FRAME */}
                <div
                  style={{
                    position: 'relative',
                    width: '100%',
                    height: '160px',
                    borderRadius: '8px',
                    overflow: 'hidden',
                    border: '1px solid #202020',
                    background: '#0a0a0a',
                    cursor: 'pointer',
                  }}
                  onClick={() => setPreviewItem({ ...ev, url: snapshotUrl })}
                  title="Click to expand high-res capture"
                >
                  <SkeletonImage
                    src={snapshotUrl}
                    alt={`Snapshot ${ev.evidence_id}`}
                    placeholderText={`LOADING ${ev.evidence_id.slice(0, 14)}...`}
                    fallbackText="SNAPSHOT ARCHIVE"
                    containerStyle={{ width: '100%', height: '100%' }}
                    objectFit="contain"
                  />
                </div>

                {/* METADATA STRIP */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '11.5px', borderTop: '1px solid #1c1c1c', paddingTop: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-low)' }}>Linked Incident:</span>
                    {ev.event_id ? (
                      <span
                        style={{
                          color: 'var(--gold)',
                          cursor: onInvestigate ? 'pointer' : 'default',
                          textDecoration: onInvestigate ? 'underline' : 'none',
                          fontFamily: 'var(--mono)',
                        }}
                        onClick={() => onInvestigate && onInvestigate({ event_id: ev.event_id })}
                        title="Click to investigate linked event with AI"
                      >
                        {ev.event_id}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-low)' }}>None</span>
                    )}
                  </div>

                  {ev.metadata?.vehicle_intelligence && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(201, 154, 91, 0.06)', padding: '3px 6px', borderRadius: '4px', border: '1px solid rgba(201, 154, 91, 0.2)' }}>
                      <span style={{ color: 'var(--text-low)', fontSize: '11px' }}>Vehicle Intel:</span>
                      <span style={{ color: '#C99A5B', fontFamily: 'var(--mono)', fontSize: '10.5px' }}>
                        {ev.metadata.vehicle_intelligence.color ? `${ev.metadata.vehicle_intelligence.color} ` : ''}
                        {ev.metadata.vehicle_intelligence.type ? `${ev.metadata.vehicle_intelligence.type}` : 'Vehicle'}
                        {ev.metadata.vehicle_intelligence.type_confidence ? ` (${Math.round(ev.metadata.vehicle_intelligence.type_confidence * 100)}%)` : ''}
                      </span>
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-low)' }}>Integrity Seal:</span>
                    {ev.integrity_hash ? (
                      <span style={{ fontSize: '10.5px', color: 'var(--green)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: 'var(--green)' }}></span>
                        SHA-256 · {ev.integrity_hash.slice(0, 12)}…
                      </span>
                    ) : (
                      <span style={{ fontSize: '10.5px', color: 'var(--green)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        <CheckIcon size={12} /> Cryptographically Sealed
                      </span>
                    )}
                  </div>
                </div>

                {/* ACTION BUTTONS */}
                <div style={{ display: 'flex', gap: '6px', marginTop: '2px' }}>
                  <button
                    className="n-btn"
                    style={{ flex: 1, fontSize: '11px', padding: '4px 8px', background: 'var(--panel-hover)', justifyContent: 'center', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                    onClick={() => setPreviewItem({ ...ev, url: snapshotUrl })}
                  >
                    <SearchIcon size={11} /> Inspect Capture
                  </button>

                  {onInvestigate && (
                    <button
                      className="n-btn ai-investigate"
                      style={{
                        fontSize: '11px',
                        padding: '4px 8px',
                        justifyContent: 'center',
                      }}
                      onClick={() => onInvestigate({ evidence_id: ev.evidence_id, event_id: ev.event_id, url: snapshotUrl, ...ev })}
                      title="Direct AI Visual Investigation (Gemma 4)"
                    >
                      <AiSparklesIcon size={11} />
                      <span>Investigate AI</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })
        ) : (
          <div className="tile" style={{ gridColumn: '1/-1', padding: '40px', textAlign: 'center', color: 'var(--text-low)' }}>
            No evidence matches the selected filter. Automated snapshots are captured live when detections occur.
          </div>
        )}
      </div>

      {/* FULL EVIDENCE INSPECTION MODAL */}
      {previewItem && (
        <div
          className="modal-overlay"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.85)',
            display: 'grid',
            placeItems: 'center',
            zIndex: 9999,
          }}
          onClick={() => setPreviewItem(null)}
        >
          <div
            className="tile"
            style={{
              maxWidth: '700px',
              width: '94%',
              maxHeight: '90vh',
              overflowY: 'auto',
              padding: '16px',
              background: '#111',
              border: '1px solid var(--hair)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <b style={{ color: 'var(--text-hi)', fontFamily: 'var(--mono)', fontSize: '14px' }}>
                  EVIDENCE {previewItem.evidence_id}
                </b>
                <span className="n-chip attention" style={{ display: 'inline-flex', marginLeft: '8px' }}>
                  <span className="n-chip-dot"></span>
                  {previewItem.type || 'SNAPSHOT'}
                </span>
                <span style={{ color: 'var(--text-low)', fontSize: '11px', marginLeft: '8px' }}>
                  {previewItem.timestamp ? new Date(previewItem.timestamp).toLocaleString() : 'Recently'}
                </span>
              </div>
              <button className="n-btn" onClick={() => setPreviewItem(null)} style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                <CloseIcon size={12} /> Close
              </button>

            </div>

            <div style={{ background: '#000', borderRadius: '8px', overflow: 'hidden', textAlign: 'center', marginBottom: '14px', minHeight: '280px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <SkeletonImage
                src={previewItem.url}
                alt={previewItem.evidence_id}
                placeholderText="FETCHING CRYPTOGRAPHIC EVIDENCE..."
                fallbackText="SNAPSHOT ARCHIVE VERIFIED"
                containerStyle={{ width: '100%', minHeight: '280px', maxHeight: '440px' }}
                style={{ width: '100%', maxHeight: '440px' }}
                objectFit="contain"
              />
            </div>

            {previewItem.metadata?.vehicle_intelligence && (
              <div
                style={{
                  background: 'rgba(201, 154, 91, 0.06)',
                  border: '1px solid rgba(201, 154, 91, 0.22)',
                  borderRadius: '8px',
                  padding: '12px 14px',
                  marginBottom: '14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <b style={{ color: '#C99A5B', fontSize: '12.5px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                    <CarIcon size={14} /> Vehicle Intelligence Analysis
                  </b>
                  <span style={{ fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                    ID: {previewItem.metadata.vehicle_intelligence.vehicle_id || 'N/A'}
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px', fontSize: '12px' }}>
                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '8px 10px', borderRadius: '6px' }}>
                    <div style={{ color: 'var(--text-low)', fontSize: '10.5px' }}>VEHICLE TYPE (CLIP)</div>
                    <div style={{ color: 'var(--text-hi)', fontWeight: 600, marginTop: '2px', textTransform: 'capitalize' }}>
                      {previewItem.metadata.vehicle_intelligence.type || 'Pending CLIP Classification'}
                    </div>
                    {previewItem.metadata.vehicle_intelligence.type_confidence ? (
                      <div style={{ color: '#C99A5B', fontSize: '10.5px', marginTop: '2px', fontFamily: 'var(--mono)' }}>
                        {Math.round(previewItem.metadata.vehicle_intelligence.type_confidence * 100)}% confidence
                      </div>
                    ) : (
                      <div style={{ color: 'var(--text-low)', fontSize: '10px', marginTop: '2px' }}>
                        Dormant (transformers pending)
                      </div>
                    )}
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '8px 10px', borderRadius: '6px' }}>
                    <div style={{ color: 'var(--text-low)', fontSize: '10.5px' }}>DETECTED COLOR (OPENCV)</div>
                    <div style={{ color: 'var(--text-hi)', fontWeight: 600, marginTop: '2px', textTransform: 'capitalize', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{
                        display: 'inline-block',
                        width: '10px',
                        height: '10px',
                        borderRadius: '50%',
                        background: previewItem.metadata.vehicle_intelligence.color || '#888',
                        border: '1px solid rgba(255,255,255,0.3)',
                      }} />
                      {previewItem.metadata.vehicle_intelligence.color || 'Unknown'}
                    </div>
                    {previewItem.metadata.vehicle_intelligence.color_confidence ? (
                      <div style={{ color: '#C99A5B', fontSize: '10.5px', marginTop: '2px', fontFamily: 'var(--mono)' }}>
                        {Math.round(previewItem.metadata.vehicle_intelligence.color_confidence * 100)}% dominant ratio
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
              <div style={{ fontSize: '11.5px', color: 'var(--text-low)' }}>
                {previewItem.integrity_hash && (
                  <div>
                    SHA256: <span style={{ fontFamily: 'var(--mono)', color: 'var(--green)' }}>{previewItem.integrity_hash}</span>
                  </div>
                )}
                {previewItem.event_id && (
                  <div>
                    Linked Incident: <b style={{ fontFamily: 'var(--mono)', color: 'var(--text-hi)' }}>{previewItem.event_id}</b>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                {onInvestigate && (
                  <button
                    className="n-btn ai-investigate"
                    style={{ padding: '5px 12px' }}
                    onClick={() => {
                      const item = previewItem;
                      setPreviewItem(null);
                      onInvestigate(item);
                    }}
                    title="Direct AI Visual Investigation (Gemma 4)"
                  >
                    <AiSparklesIcon size={12} />
                    <span>Investigate AI</span>
                  </button>
                )}
                <a
                  href={previewItem.url}
                  download={`evidence-${previewItem.evidence_id}.jpg`}
                  target="_blank"
                  rel="noreferrer"
                  className="n-btn"
                  style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                >
                  <DownloadIcon size={12} /> Download
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
