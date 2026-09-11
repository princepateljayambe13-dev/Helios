import { useState, useEffect } from 'react';
import { api } from '../services/api';
import { formatAiText, RenderAiActions } from '../utils/aiActions';
import { CloseIcon, CameraIcon, AiSparklesIcon, FaceIcon } from './Icons';
import { SpatialGridBackground } from './SpatialGridBackground';

export function DailyBriefModal({ isOpen, onClose, onInvestigate, onSelectTab }) {
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      api
        .getDayBrief()
        .then((data) => setBrief(data))
        .catch((err) => setBrief({ activity_summary: `Failed to load briefing: ${err.message}` }))
        .finally(() => setLoading(false));
    }
  }, [isOpen]);

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

  const hasHighThreat = brief?.significant_events?.length > 0 || brief?.stats?.active_alerts > 0;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="search-modal"
        style={{ width: '100%', maxWidth: '680px', maxHeight: '88vh', position: 'relative', overflow: 'hidden' }}
        onClick={(e) => e.stopPropagation()}
      >
        <SpatialGridBackground active={isOpen} />
        {/* TACTICAL BRIEF HEADER */}
        <div className="search-modal-header" style={{ justifyContent: 'space-between', padding: '14px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div className="daily-brief-icon" style={{ width: '32px', height: '32px' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
              </svg>
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <b style={{ color: 'var(--text-hi)', fontSize: '15px' }}>24H Tactical Intelligence Brief</b>
                <span
                  className="n-chip"
                  style={{
                    background: hasHighThreat ? 'var(--red-dim)' : 'var(--green-dim)',
                    color: hasHighThreat ? 'var(--red)' : 'var(--green)',
                    border: `1px solid ${hasHighThreat ? 'rgba(239,82,81,0.3)' : 'rgba(47,204,139,0.3)'}`,
                    fontSize: '9.5px',
                  }}
                >
                  {hasHighThreat ? 'THREAT LEVEL: ELEVATED' : 'THREAT LEVEL: NOMINAL'}
                </span>
              </div>
              <div style={{ fontSize: '10.5px', color: 'var(--text-low)', fontFamily: 'var(--mono)' }}>
                HELIOS AI Agent · {brief?.date || 'Today'} · {brief?.ai_model || 'v1.0-grounded'}
              </div>
            </div>
          </div>
          <button style={{ color: 'var(--text-low)', background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }} onClick={onClose} aria-label="Close">
            <CloseIcon size={14} />
          </button>

        </div>

        {/* BODY */}
        <div className="search-modal-body" style={{ gap: '16px' }}>
          {loading ? (
            <div style={{ padding: '50px 0', textAlign: 'center', color: 'var(--text-low)' }}>
              <div className="daily-brief-icon" style={{ margin: '0 auto 12px', width: '40px', height: '40px' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
                </svg>
              </div>
              <em>Synthesizing 24-hour multi-camera streams, intrusion events & evidence records...</em>
            </div>
          ) : brief ? (
            <>
              {/* EXECUTIVE ACTIVITY SUMMARY */}
              <div className="tile" style={{ padding: '14px 16px', background: 'rgba(20,20,20,0.7)' }}>
                <div className="n-col-label" style={{ color: 'var(--gold)', marginBottom: '6px' }}>
                  Operational Overview
                </div>
                <div style={{ fontSize: '12.5px', color: 'var(--text-hi)', lineHeight: '1.55' }}>
                  {formatAiText(brief.activity_summary, handlers)}
                </div>
              </div>

              {/* SIGNIFICANT INTRUSION INCIDENTS WITH DIRECT COMMAND BUTTONS */}
              {brief.significant_events && brief.significant_events.length > 0 && (
                <div>
                  <div className="n-col-label" style={{ marginBottom: '8px' }}>
                    Critical Intrusion Incidents ({brief.significant_events.length})
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {brief.significant_events.map((evt, idx) => (
                      <div key={idx} className="tile n-tile critical" style={{ padding: '12px 14px' }}>
                        <div className="n-head" style={{ marginBottom: '6px' }}>
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
                              style={{ padding: '4px 8px' }}
                              onClick={() => handlers.onInvestigate(evt)}
                            >
                              <AiSparklesIcon size={11} />
                              <span>Investigate</span>
                            </button>
                            <button
                              className="n-btn"
                              style={{ background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.3)', padding: '4px 8px', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                              onClick={() => handlers.onSelectTab('evidence')}
                            >
                              <CameraIcon size={12} /> Evidence
                            </button>

                          </div>
                        </div>

                        <div className="n-headline" style={{ fontSize: '13px', margin: '0 0 4px' }}>
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
                          <b style={{ color: 'var(--text-hi)', fontSize: '12.5px' }}>{vf.name || vf.zone_id || 'Restricted Zone'}</b>
                          <div style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                            {vf.description || (vf.camera_id ? `Breach at ${vf.camera_id}` : 'Perimeter breach detected')}
                          </div>
                        </div>
                        <button className="n-btn ai-investigate" style={{ padding: '4px 9px' }} onClick={() => handlers.onInvestigate(vf)}>
                          <AiSparklesIcon size={11} />
                          <span>Inspect</span>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* EVIDENCE SUMMARY & DEEP LINKS */}
              {brief.evidence_summary && (
                <div className="tile" style={{ padding: '14px 16px', borderColor: 'rgba(224,170,62,0.3)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <div className="n-col-label" style={{ color: 'var(--gold)', margin: 0 }}>
                      Evidence Vault Captures
                    </div>
                    <button
                      className="n-btn"
                      style={{ background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.3)', padding: '3px 8px', fontSize: '10px' }}
                      onClick={() => handlers.onSelectTab('evidence')}
                    >
                      Open Evidence Vault →
                    </button>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-mid)', lineHeight: '1.5' }}>
                    {formatAiText(brief.evidence_summary, handlers)}
                  </div>
                </div>
              )}

              {/* AI ASSESSMENT & DIRECTIVES */}
              {brief.ai_assessment && (
                <div className="tile" style={{ padding: '14px 16px', background: 'var(--panel-hi)', borderColor: 'rgba(224, 170, 62, 0.3)' }}>
                  <div className="n-col-label" style={{ color: 'var(--gold)', marginBottom: '6px' }}>
                    AI Intelligence Assessment & Directives
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-hi)', lineHeight: '1.55' }}>
                    {formatAiText(brief.ai_assessment, handlers)}
                  </div>
                  <RenderAiActions actions={brief.actions} references={brief.references} handlers={handlers} />
                </div>
              )}

              {/* BIOMETRIC & FACE IDENTIFICATION HIGHLIGHTS */}
              {brief.stats && (brief.stats.faces_detected_today > 0 || brief.stats.faces_recognized_today > 0) && (
                <div className="tile" style={{ padding: '14px 16px', background: 'rgba(236, 72, 153, 0.06)', borderColor: 'rgba(236, 72, 153, 0.3)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div className="n-col-label" style={{ color: '#ec4899', margin: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <FaceIcon size={14} /> Biometric & Facial Recognition Telemetry
                    </div>
                    <button
                      className="n-btn"
                      style={{ background: 'rgba(236, 72, 153, 0.15)', color: '#ec4899', borderColor: 'rgba(236, 72, 153, 0.3)', padding: '2px 8px', fontSize: '10px' }}
                      onClick={() => handlers.onSelectTab('face-recognition')}
                    >
                      View Faces →
                    </button>
                  </div>
                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>Detected Today: </span>
                      <b style={{ color: 'var(--text-hi)', fontSize: '12.5px' }}>{brief.stats.faces_detected_today}</b>
                    </div>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>Recognized: </span>
                      <b style={{ color: 'var(--green)', fontSize: '12.5px' }}>{brief.stats.faces_recognized_today}</b>
                    </div>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>Unclassified: </span>
                      <b style={{ color: '#ec4899', fontSize: '12.5px' }}>{brief.stats.faces_unclassified_today}</b>
                    </div>
                    {brief.stats.recognized_persons_today?.length > 0 && (
                      <div style={{ width: '100%', marginTop: '4px', fontSize: '11.5px', color: 'var(--text-mid)' }}>
                        Verified Persons: <span style={{ color: 'var(--text-hi)', fontWeight: 600 }}>{brief.stats.recognized_persons_today.join(', ')}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* STATS HUD */}
              {brief.stats && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
                    gap: '8px',
                    paddingTop: '8px',
                    borderTop: '1px solid var(--hair-soft)',
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
                  {brief.stats.faces_detected_today !== undefined && (
                    <div className="stat-cell" style={{ cursor: 'pointer' }} onClick={() => handlers.onSelectTab('face-recognition')}>
                      <div className="sc-label">Faces Today</div>
                      <div className="sc-value" style={{ color: '#ec4899' }}>
                        {brief.stats.faces_recognized_today}/{brief.stats.faces_detected_today}
                      </div>
                    </div>
                  )}
                  <div className="stat-cell" style={{ cursor: 'pointer' }} onClick={() => handlers.onSelectTab('evidence')}>
                    <div className="sc-label">Evidence Cached</div>
                    <div className="sc-value" style={{ color: 'var(--gold)' }}>
                      {brief.stats.evidence_count || 30}/30
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
