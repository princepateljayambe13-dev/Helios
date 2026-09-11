import React from 'react';
import { TargetIcon, CameraIcon, VideoIcon, AlertIcon, BoltIcon, AiSparklesIcon } from '../components/Icons';

/**
 * Parses text strings and replaces entity IDs (EVT-*, EVD-*, CAM-*, ALT-*) with interactive click badges.
 */
export function formatAiText(text, handlers = {}) {
  if (!text || typeof text !== 'string') return text;

  // Regex matching EVT-..., EVD-..., CAM-..., ALT-..., and #[A-Z]-[A-Z0-9]+
  const entityRegex = /(#[A-Z]-[A-Z0-9]{4,12}\b|\b(?:EVT-[A-Z0-9]{4,12}|EVD-[A-Z0-9]{4,12}|CAM-\d+|ALT-[A-Z0-9]{4,12})\b)/g;

  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = entityRegex.exec(text)) !== null) {
    const matchedId = match[0];
    const index = match.index;

    // Push preceding plain text
    if (index > lastIndex) {
      parts.push(text.substring(lastIndex, index));
    }

    // Determine type
    if (matchedId.startsWith('#')) {
      parts.push(
        <button
          key={`trk-${index}`}
          className="n-chip"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', margin: '0 3px', padding: '1px 6px', cursor: 'pointer', background: 'var(--panel-hover)', color: 'var(--gold)' }}
          onClick={(e) => {
            e.stopPropagation();
            if (handlers.onSelectTab) handlers.onSelectTab('threads', matchedId);
          }}
          title="Click to View Activity Story"
        >
          <TargetIcon size={10} />
          <span>{matchedId}</span>
        </button>
      );
    } else if (matchedId.startsWith('EVT-')) {
      parts.push(
        <button
          key={`evt-${index}`}
          className="n-chip critical"
          style={{ display: 'inline-flex', alignItems: 'center', margin: '0 3px', padding: '1px 6px', cursor: 'pointer' }}
          onClick={(e) => {
            e.stopPropagation();
            if (handlers.onInvestigate) handlers.onInvestigate({ event_id: matchedId });
          }}
          title="Click to Investigate Event"
        >
          <span>{matchedId}</span>
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" style={{ marginLeft: '3px' }}>
            <path d="M7 17L17 7M7 7h10v10" />
          </svg>
        </button>
      );
    } else if (matchedId.startsWith('EVD-')) {
      parts.push(
        <button
          key={`evd-${index}`}
          className="n-chip"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', margin: '0 3px', padding: '1px 6px', cursor: 'pointer', background: 'var(--gold-dim)', color: 'var(--gold)', border: '1px solid rgba(224,170,62,0.3)' }}
          onClick={(e) => {
            e.stopPropagation();
            if (handlers.onSelectTab) handlers.onSelectTab('evidence');
          }}
          title="Click to View in Evidence Vault"
        >
          <CameraIcon size={10} />
          <span>{matchedId}</span>
        </button>
      );
    } else if (matchedId.startsWith('CAM-')) {
      parts.push(
        <button
          key={`cam-${index}`}
          className="n-chip"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', margin: '0 3px', padding: '1px 6px', cursor: 'pointer', background: 'var(--panel-hover)', color: 'var(--text-hi)' }}
          onClick={(e) => {
            e.stopPropagation();
            if (handlers.onSelectTab) handlers.onSelectTab('feeds');
          }}
          title="Click to Open Camera Stream"
        >
          <VideoIcon size={10} />
          <span>{matchedId}</span>
        </button>
      );
    } else if (matchedId.startsWith('ALT-')) {
      parts.push(
        <button
          key={`alt-${index}`}
          className="n-chip attention"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', margin: '0 3px', padding: '1px 6px', cursor: 'pointer' }}
          onClick={(e) => {
            e.stopPropagation();
            if (handlers.onSelectTab) handlers.onSelectTab('alerts');
          }}
          title="Click to View Alert"
        >
          <AlertIcon size={10} />
          <span>{matchedId}</span>
        </button>
      );
    } else {
      parts.push(matchedId);
    }

    lastIndex = index + matchedId.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

/**
 * Renders structured AI Actions array as interactive command buttons.
 */
export function RenderAiActions({ actions = [], references = [], handlers = {} }) {
  if ((!actions || actions.length === 0) && (!references || references.length === 0)) {
    return null;
  }

  return (
    <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
      {actions.map((act, i) => {
        const label = act.label || act.type?.replace(/_/g, ' ');
        if (act.track_id || act.type === 'OPEN_TRACK') {
          return (
            <button
              key={i}
              className="n-btn"
              style={{ fontSize: '10.5px', background: 'var(--panel-hover)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.4)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
              onClick={() => handlers.onSelectTab && handlers.onSelectTab('threads', act.track_id)}
            >
              <TargetIcon size={11} /> Track {act.track_id || 'Story'}
            </button>
          );
        }
        if (act.event_id || act.type === 'INVESTIGATE_EVENT') {
          return (
            <button
              key={i}
              className="n-btn ai-investigate"
              style={{ fontSize: '10.5px', padding: '3px 8px' }}
              onClick={() => {
                if (act.event_id && handlers.onInvestigate) {
                  handlers.onInvestigate({ event_id: act.event_id });
                } else if (handlers.onSelectTab) {
                  handlers.onSelectTab('events');
                }
              }}
            >
              <AiSparklesIcon size={11} />
              <span>Investigate {act.event_id || 'Events'}</span>
            </button>
          );
        }
        if (act.evidence_id || act.type === 'VIEW_EVIDENCE') {
          return (
            <button
              key={i}
              className="n-btn"
              style={{ background: 'var(--gold-dim)', color: 'var(--gold)', borderColor: 'rgba(224,170,62,0.3)', fontSize: '10.5px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
              onClick={() => handlers.onSelectTab && handlers.onSelectTab('evidence')}
            >
              <CameraIcon size={11} /> Evidence {act.evidence_id || 'Vault'}
            </button>
          );
        }
        if (act.camera_id || act.type === 'OPEN_CAMERA') {
          return (
            <button
              key={i}
              className="n-btn"
              style={{ fontSize: '10.5px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
              onClick={() => handlers.onSelectTab && handlers.onSelectTab('feeds')}
            >
              <VideoIcon size={11} /> Stream {act.camera_id || 'Feeds'}
            </button>
          );
        }
        return (
          <button key={i} className="n-btn" style={{ fontSize: '10.5px', display: 'inline-flex', alignItems: 'center', gap: '4px' }} onClick={() => handlers.onSelectTab && handlers.onSelectTab('events')}>
            <BoltIcon size={11} /> {label}
          </button>
        );
      })}

      {references.map((ref, i) => {
        if (ref.track_id) {
          return (
            <button
              key={`ref-${i}`}
              className="n-chip"
              style={{ cursor: 'pointer', background: 'var(--panel-hover)', color: 'var(--gold)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}
              onClick={() => handlers.onSelectTab && handlers.onSelectTab('threads', ref.track_id)}
            >
              <TargetIcon size={10} />
              <span>Track: {ref.track_id}</span>
            </button>
          );
        }
        if (ref.evidence_id) {
          return (
            <button
              key={`ref-${i}`}
              className="n-chip info"
              style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '3px' }}
              onClick={() => handlers.onSelectTab && handlers.onSelectTab('evidence')}
            >
              <CameraIcon size={10} />
              <span>Evidence: {ref.evidence_id}</span>
            </button>
          );
        }
        if (ref.event_id) {
          return (
            <button
              key={`ref-${i}`}
              className="n-chip critical"
              style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '3px' }}
              onClick={() => handlers.onInvestigate && handlers.onInvestigate({ event_id: ref.event_id })}
            >
              <AlertIcon size={10} />
              <span>Event: {ref.event_id}</span>
            </button>
          );
        }
        return null;
      })}
    </div>
  );
}
