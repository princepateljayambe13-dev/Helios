import { useState, useEffect } from 'react';
import { api, V1, resolveMediaUrl } from '../services/api';
import { formatAiText, RenderAiActions } from '../utils/aiActions';
import { SkeletonBox, SkeletonText, SkeletonImage } from './SkeletonLoader';
import { CloseIcon, CameraIcon, AiSparklesIcon, FaceIcon } from './Icons';

export function InvestigateModal({ event, onClose, onSelectTab }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [currentTarget, setCurrentTarget] = useState(event);

  const runInvestigation = (targetObj) => {
    if (!targetObj) return;
    const tid = targetObj.evidence_id || targetObj.track_id || targetObj.event_id || targetObj.id;
    if (!tid) return;
    setCurrentTarget(targetObj);
    setLoading(true);
    setResult(null);

    // Call unified POST /ai/investigate with JSON payload to avoid URL fragment issues
    api.investigate(tid)
      .then((res) => setResult(res))
      .catch((err) => {
        // Fallback to target-specific endpoint
        const fallbackCall = targetObj.evidence_id
          ? api.investigateEvidence(targetObj.evidence_id)
          : targetObj.track_id && !targetObj.event_id
          ? api.investigateEntity(targetObj.track_id)
          : api.investigateEvent(targetObj.event_id || tid);

        fallbackCall
          .then((res) => setResult(res))
          .catch((finalErr) =>
            setResult({
              explanation: `Investigation error: ${finalErr.message || err.message}`,
              summary: `Investigation error: ${finalErr.message || err.message}`,
              error_code: 'API_ERROR',
              target_id: tid,
            })
          );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!event) return;
    runInvestigation(event);
  }, [event]);

  if (!event) return null;

  const displayTarget = currentTarget || event;
  const displayId = displayTarget.evidence_id || displayTarget.track_id || displayTarget.event_id || displayTarget.id;
  const targetType = displayTarget.evidence_id ? 'EVIDENCE' : displayTarget.track_id && !displayTarget.event_id ? 'ENTITY TRACK' : 'EVENT';

  // Determine if there is an image to preview
  const previewImageUrl =
    displayTarget.url ||
    (displayTarget.evidence_id ? api.getEvidenceFileUrl(displayTarget.evidence_id) : null) ||
    (result?.context?.evidence?.[0]?.evidence_id ? api.getEvidenceFileUrl(result.context.evidence[0].evidence_id) : null);

  const handlers = {
    onInvestigate: (evt) => {
      runInvestigation(evt);
    },
    onSelectTab: (tab, trackId = null) => {
      onClose();
      if (onSelectTab) onSelectTab(tab, trackId);
    },
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="search-modal investigate-modal" style={{ width: '100%', maxWidth: '640px', maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
        <div className="search-modal-header" style={{ justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="n-chip critical">{targetType} INVESTIGATION</span>
            <b style={{ color: 'var(--text-hi)', fontSize: '13px', fontFamily: 'var(--mono)' }}>{displayId}</b>
          </div>
          <button style={{ color: 'var(--text-low)', fontSize: '12px', background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }} onClick={onClose}>
            <CloseIcon size={14} />
          </button>
        </div>

        <div className="search-modal-body">
          <div style={{ marginBottom: '12px' }}>
            <div className="n-headline" style={{ fontSize: '15px' }}>
              {event.headline || event.description || event.event_type || event.type || `Analysis for ${displayId}`}
            </div>
            <div className="n-meta" style={{ marginTop: '3px' }}>
              {event.camera_id ? `Camera: ${event.camera_id} · ` : ''}
              Location: {event.location || 'Monitored Zone'}
              {event.severity ? ` · Severity: ${event.severity}` : ''}
              {event.object_type ? ` · Classification: ${event.object_type}` : ''}
            </div>
          </div>

          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="skeleton-card" style={{ padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <SkeletonBox width="200px" height="14px" />
                  <span style={{ fontSize: '10px', color: 'var(--gold)', fontFamily: 'var(--mono)' }}>MINIMAX M3 / GEMMA 4 REASONING...</span>
                </div>
                <SkeletonText lines={4} height={12} gap={8} />
              </div>
              <div className="skeleton-card" style={{ padding: '14px', minHeight: '60px' }}>
                <SkeletonBox width="140px" height="12px" style={{ marginBottom: '10px' }} />
                <div style={{ display: 'flex', gap: '8px' }}>
                  <SkeletonBox width="100px" height="24px" borderRadius="12px" />
                  <SkeletonBox width="100px" height="24px" borderRadius="12px" />
                </div>
              </div>
            </div>
          ) : result ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {/* Multimodal Captured Evidence Image Frame */}
              {previewImageUrl && (
                <div
                  style={{
                    position: 'relative',
                    width: '100%',
                    height: '200px',
                    borderRadius: '8px',
                    overflow: 'hidden',
                    border: '1px solid #202020',
                    background: '#0a0a0a',
                  }}
                >
                  <SkeletonImage
                    src={previewImageUrl}
                    alt={`Evidence ${displayId}`}
                    placeholderText="LOADING FORENSIC FRAME..."
                    fallbackText="SNAPSHOT ARCHIVE"
                    containerStyle={{ width: '100%', height: '100%' }}
                    objectFit="contain"
                  />
                  <div
                    style={{
                      position: 'absolute',
                      top: '8px',
                      left: '8px',
                      background: 'rgba(0,0,0,0.7)',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontFamily: 'var(--mono)',
                      color: 'var(--gold)',
                      border: '1px solid rgba(224,170,62,0.3)',
                    }}
                  >
                    AI Multimodal Visual Frame
                  </div>
                </div>
              )}

              {/* Dedicated Picture Description from Minimax M3 / Gemma 4 */}
              {result.image_description && (
                <div className="tile" style={{ padding: '12px 14px', background: 'rgba(56, 189, 248, 0.06)', border: '1px solid rgba(56, 189, 248, 0.25)', borderRadius: '8px' }}>
                  <div className="n-col-label" style={{ color: '#38bdf8', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <CameraIcon size={14} style={{ color: '#38bdf8' }} /> AI Picture Description ({result.ai_model ? result.ai_model.split('/')[1] : 'Visual AI'})
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-hi)', lineHeight: '1.55' }}>
                    {result.image_description}
                  </div>
                </div>
              )}

              {/* Biometric Facial Intelligence Card */}
              {result.face_intel && (
                <div className="tile" style={{ padding: '12px 14px', background: 'rgba(213, 177, 138, 0.07)', border: '1px solid rgba(213, 177, 138, 0.3)', borderRadius: '8px' }}>
                  <div className="n-col-label" style={{ color: 'var(--gold)', marginBottom: '8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <FaceIcon size={14} style={{ color: 'var(--gold)' }} />
                      <span>ArcFace Biometric Intelligence</span>
                    </div>
                    <span
                      className="n-chip"
                      style={{
                        fontSize: '9px',
                        padding: '1px 6px',
                        background: result.face_intel.status === 'RECOGNIZED' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(236, 72, 153, 0.15)',
                        color: result.face_intel.status === 'RECOGNIZED' ? 'var(--green)' : '#ec4899',
                        borderColor: result.face_intel.status === 'RECOGNIZED' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(236, 72, 153, 0.3)',
                      }}
                    >
                      {result.face_intel.status || 'UNCLASSIFIED'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    {result.face_intel.snapshot_path && (
                      <img
                        src={resolveMediaUrl(result.face_intel.snapshot_path)}
                        alt={result.face_intel.person_name || 'Face Snapshot'}
                        style={{ width: '56px', height: '56px', borderRadius: '6px', objectFit: 'cover', border: '1px solid rgba(213, 177, 138, 0.4)', background: '#000' }}
                        onError={(e) => { e.currentTarget.style.display = 'none'; }}
                      />
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '13.5px', fontWeight: 600, color: 'var(--text-hi)' }}>
                        {result.face_intel.person_name || 'Unclassified Subject'}
                        {result.face_intel.role && (
                          <span style={{ fontSize: '11px', fontWeight: 400, color: 'var(--text-mid)', marginLeft: '6px' }}>
                            · {result.face_intel.role}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-low)', fontFamily: 'var(--mono)', marginTop: '2px' }}>
                        {result.face_intel.person_id ? `ID: ${result.face_intel.person_id} · ` : ''}
                        {result.face_intel.similarity ? `Match: ${Math.round(result.face_intel.similarity * 100)}% · ` : ''}
                        Seen: {result.face_intel.detection_count || 1}x
                      </div>
                    </div>
                    <button
                      className="n-btn"
                      style={{ fontSize: '11px', padding: '4px 9px', background: 'rgba(213, 177, 138, 0.15)', color: 'var(--gold)', borderColor: 'rgba(213, 177, 138, 0.3)', flexShrink: 0 }}
                      onClick={() => handlers.onSelectTab('face-recognition')}
                    >
                      Face Directory →
                    </button>
                  </div>
                </div>
              )}

              {result.error_code === 'API_ERROR' && (
                <div className="tile" style={{ padding: '12px 14px', background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
                  <div style={{ fontSize: '12px', color: 'var(--red)' }}>
                    {result.explanation}
                  </div>
                  <button className="n-btn" onClick={() => runInvestigation(displayTarget)} style={{ fontSize: '11px', padding: '4px 10px', flexShrink: 0 }}>
                    Retry
                  </button>
                </div>
              )}

              {/* Main AI Forensic Investigation Explanation */}
              <div className="tile" style={{ padding: '14px 16px', background: 'var(--panel-hi)', borderRadius: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <div className="n-col-label" style={{ color: 'var(--gold)', marginBottom: 0 }}>
                    Forensic Investigation Analysis
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {result.ai_model === 'local-helios-ai' && (
                      <span className="n-chip" style={{ fontSize: '9px', padding: '1px 5px', color: 'var(--text-mid)', background: 'rgba(255,255,255,0.06)' }}>
                        LOCAL SENSOR DB VERIFIED
                      </span>
                    )}
                    <span style={{ fontSize: '10px', fontFamily: 'var(--mono)', color: 'var(--text-low)' }}>
                      {result.ai_model || 'google/gemma-4-31b-it'}
                    </span>
                  </div>
                </div>
                <div style={{ fontSize: '12.5px', color: 'var(--text-hi)', lineHeight: '1.55' }}>
                  {formatAiText(result.explanation || result.summary || 'Database facts verified by sensor pipeline.', handlers)}
                </div>
              </div>

              {/* Entity Timeline Steps */}
              {result.entity_timeline && result.entity_timeline.length > 0 && (
                <div className="tile" style={{ padding: '12px 14px', borderColor: 'rgba(224,170,62,0.3)', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div className="n-col-label" style={{ color: 'var(--gold)', marginBottom: 0 }}>
                      Detected Entity Timeline ({result.entity_timeline.length} Steps)
                    </div>
                    <span style={{ fontSize: '10px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                      Chronological Trail
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '220px', overflowY: 'auto' }}>
                    {result.entity_timeline.map((step, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '8px',
                          padding: '6px 10px',
                          background: 'var(--panel-hi)',
                          borderRadius: '6px',
                          border: '1px solid #1c1c1c',
                        }}
                      >
                        <span
                          className="n-chip"
                          style={{
                            fontSize: '9px',
                            padding: '2px 5px',
                            minWidth: '76px',
                            textAlign: 'center',
                            textTransform: 'uppercase',
                            background: step.step_type === 'EVENT_TRIGGERED' ? 'var(--red-dim)' : step.step_type === 'FACE_RECOGNITION' ? 'rgba(236,72,153,0.15)' : 'rgba(255,255,255,0.05)',
                            color: step.step_type === 'EVENT_TRIGGERED' ? 'var(--red)' : step.step_type === 'FACE_RECOGNITION' ? '#ec4899' : 'var(--text-mid)',
                            borderColor: step.step_type === 'EVENT_TRIGGERED' ? 'rgba(239,82,81,0.3)' : step.step_type === 'FACE_RECOGNITION' ? 'rgba(236,72,153,0.35)' : 'var(--hair)',
                          }}
                        >
                          {step.step_type?.replace('_', ' ') || 'STEP'}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: '11.5px', color: 'var(--text-hi)' }}>{step.description}</div>
                          <div style={{ fontSize: '10px', color: 'var(--text-low)', marginTop: '2px', fontFamily: 'var(--mono)' }}>
                            {step.timestamp ? new Date(step.timestamp).toLocaleTimeString() : ''}
                            {step.camera_id ? ` · ${step.camera_id}` : ''}
                            {step.zone_id ? ` · Zone: ${step.zone_id}` : ''}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Direct Evidence Links */}
              {result.context?.evidence && result.context.evidence.length > 0 && (
                <div className="tile" style={{ padding: '12px 14px', borderColor: 'rgba(224,170,62,0.3)', borderRadius: '8px' }}>
                  <div className="n-col-label" style={{ color: 'var(--gold)', marginBottom: '6px' }}>
                    Linked Evidence Artifacts ({result.context.evidence.length})
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {result.context.evidence.map((ev, idx) => (
                      <button
                        key={idx}
                        className="n-btn"
                        style={{ background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.3)', fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                        onClick={() => handlers.onSelectTab('evidence')}
                      >
                        <CameraIcon size={12} /> {ev.evidence_id || `EVD-${idx + 1}`} ({ev.type || 'SNAPSHOT'})
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Related Correlation Events */}
              {result.context?.related_events && result.context.related_events.length > 0 && (
                <div>
                  <div className="n-col-label" style={{ marginBottom: '6px' }}>
                    Correlated Sensor Events
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {result.context.related_events.map((re, idx) => (
                      <div
                        key={idx}
                        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--panel-hi)', borderRadius: '6px' }}
                      >
                        <span style={{ fontSize: '12px', color: 'var(--text-hi)' }}>
                          {re.event_id}: {re.description || re.event_type}
                        </span>
                        <button className="n-btn ai-investigate" style={{ fontSize: '11px', padding: '3px 8px' }} onClick={() => handlers.onInvestigate(re)}>
                          <AiSparklesIcon size={11} />
                          <span>Investigate</span>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <RenderAiActions actions={result.actions} references={result.references} handlers={handlers} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
