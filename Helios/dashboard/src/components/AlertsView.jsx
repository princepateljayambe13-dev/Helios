import { useState } from 'react';
import { api } from '../services/api';
import { TableRowSkeleton } from './SkeletonLoader';
import { RefreshIcon, AlertIcon, AiSparklesIcon, CheckIcon } from './Icons';

export function AlertsView({ alerts = [], onRefresh, onInvestigate, onSelectTab, loading = false }) {
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [acking, setAcking] = useState({});
  const [ackingAll, setAckingAll] = useState(false);
  const [ackFeedback, setAckFeedback] = useState(null);

  const handleAck = async (alertId) => {
    setAcking((prev) => ({ ...prev, [alertId]: true }));
    try {
      await api.acknowledgeAlert(alertId, 'Operator');
      if (onRefresh) onRefresh();
    } catch (err) {
      alert(`Failed to acknowledge alert: ${err.message}`);
    } finally {
      setAcking((prev) => ({ ...prev, [alertId]: false }));
    }
  };

  const filteredAlerts = alerts.filter((a) => {
    if (statusFilter !== 'ALL' && a.status !== statusFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      const matchId = a.alert_id?.toLowerCase().includes(q);
      const matchMsg = a.message?.toLowerCase().includes(q);
      const matchEvt = a.event_id?.toLowerCase().includes(q);
      if (!matchId && !matchMsg && !matchEvt) return false;
    }
    return true;
  });

  const activeCount = alerts.filter((a) => a.status === 'ACTIVE').length;
  const filteredActiveAlerts = filteredAlerts.filter((a) => a.status === 'ACTIVE');
  const isFiltered = Boolean(searchQuery.trim() || statusFilter !== 'ALL');
  const targetAlerts = isFiltered ? filteredActiveAlerts : alerts.filter((a) => a.status === 'ACTIVE');
  const targetCount = targetAlerts.length;

  const handleAckAll = async () => {
    if (targetCount === 0 || ackingAll) return;
    setAckingAll(true);
    try {
      const ids = isFiltered ? targetAlerts.map((a) => a.alert_id) : null;
      await api.acknowledgeAllAlerts('Operator', ids);
      setAckFeedback(`Acknowledged ${targetCount} alert${targetCount === 1 ? '' : 's'}`);
      setTimeout(() => setAckFeedback(null), 3500);
      if (onRefresh) onRefresh();
    } catch (err) {
      alert(`Failed to acknowledge all alerts: ${err.message}`);
    } finally {
      setAckingAll(false);
    }
  };

  return (
    <div>
      <div className="section-head" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2>Security Alerts Incident Log</h2>
          <span className="section-sub">
            {activeCount} active alert{activeCount === 1 ? '' : 's'} requiring immediate response · {alerts.length} total logged
            {ackFeedback && (
              <span
                style={{
                  marginLeft: '10px',
                  color: 'var(--green)',
                  fontWeight: 600,
                  fontSize: '11px',
                  padding: '2px 8px',
                  background: 'rgba(34,197,94,0.15)',
                  borderRadius: '4px',
                  border: '1px solid rgba(34,197,94,0.3)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <CheckIcon size={11} /> {ackFeedback}
              </span>
            )}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="Search alerts, messages, event ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              background: '#0a0a0a',
              border: '1px solid var(--hair)',
              borderRadius: '6px',
              padding: '4px 10px',
              color: 'var(--text-hi)',
              fontSize: '11.5px',
              fontFamily: 'var(--mono)',
              outline: 'none',
              minWidth: '150px',
              flex: '1 1 180px',
            }}
          />
          {['ALL', 'ACTIVE', 'ACKNOWLEDGED'].map((st) => (
            <button
              key={st}
              className="n-btn"
              style={{
                background: statusFilter === st ? 'var(--panel-hover)' : 'var(--panel-hi)',
                color: statusFilter === st ? 'var(--text-hi)' : 'var(--text-mid)',
              }}
              onClick={() => setStatusFilter(st)}
            >
              {st}
            </button>
          ))}
          {onRefresh && (
            <button
              className="n-btn"
              style={{ marginLeft: '4px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
              onClick={onRefresh}
              title="Refresh alerts from backend"
            >
              <RefreshIcon size={12} /> Refresh
            </button>
          )}
          <button
            className="n-btn"
            disabled={targetCount === 0 || ackingAll}
            onClick={handleAckAll}
            style={{
              marginLeft: '4px',
              background: targetCount > 0 ? 'rgba(234,179,8,0.15)' : 'var(--panel-hi)',
              color: targetCount > 0 ? 'var(--gold)' : 'var(--text-low)',
              borderColor: targetCount > 0 ? 'rgba(234,179,8,0.45)' : 'var(--hair)',
              fontWeight: 600,
              cursor: targetCount === 0 || ackingAll ? 'not-allowed' : 'pointer',
              opacity: targetCount === 0 ? 0.5 : 1,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
            title={
              targetCount > 0
                ? `Acknowledge all ${targetCount} active alert${targetCount === 1 ? '' : 's'}`
                : 'No active alerts to acknowledge'
            }
          >
            <CheckIcon size={12} />
            <span>{ackingAll ? 'Acknowledging...' : `Acknowledge All${targetCount > 0 ? ` (${targetCount})` : ''}`}</span>
          </button>
          <button
            className="n-btn"
            style={{
              marginLeft: '4px',
              background: 'var(--red-dim)',
              color: 'var(--red)',
              borderColor: 'rgba(239,82,81,0.45)',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
            onClick={() => {
              window.dispatchEvent(
                new CustomEvent('helios:trigger-alert', {
                  detail: {
                    isIntrusion: true,
                    camera: 'cam-01',
                    entity: 'person',
                    title: 'CRITICAL INTRUSION DETECTED',
                    message: 'Restricted perimeter breach at North Gate Alpha',
                    severity: 'CRITICAL',
                  },
                })
              );
            }}
            title="Trigger simulated intrusion notification with voice alert"
          >
            <AlertIcon size={13} /> Test Intrusion Alert
          </button>

        </div>
      </div>

      <div className="tile" style={{ overflow: 'hidden' }}>
        <div className="table-responsive table-scroll-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Alert ID</th>
                <th>Severity</th>
                <th>Message</th>
                <th>Event ID</th>
                <th>Status</th>
                <th>Timestamp</th>
                <th>Action</th>
              </tr>
            </thead>
          <tbody>
            {loading && alerts.length === 0 ? (
              <TableRowSkeleton columns={7} rows={6} />
            ) : filteredAlerts.length > 0 ? (
              filteredAlerts.map((a) => (
                <tr key={a.alert_id}>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: '11px' }}>{a.alert_id}</td>
                  <td>
                    <span
                      className="n-chip"
                      style={{
                        display: 'inline-flex',
                        background: a.severity === 'CRITICAL' ? 'var(--red-dim)' : 'var(--gold-dim)',
                        color: a.severity === 'CRITICAL' ? 'var(--red)' : 'var(--gold)',
                      }}
                    >
                      {a.severity}
                    </span>
                  </td>
                  <td>
                    <b style={{ color: 'var(--text-hi)' }}>{a.message}</b>
                  </td>
                  <td>
                    {a.event_id ? (
                      <span
                        style={{
                          fontFamily: 'var(--mono)',
                          fontSize: '11px',
                          color: 'var(--gold)',
                          cursor: onInvestigate ? 'pointer' : 'default',
                          textDecoration: onInvestigate ? 'underline' : 'none',
                        }}
                        onClick={() => onInvestigate && onInvestigate({ event_id: a.event_id })}
                        title="Investigate linked event with AI"
                      >
                        {a.event_id}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-low)', fontSize: '11px' }}>N/A</span>
                    )}
                  </td>
                  <td>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: '600',
                        color: a.status === 'ACTIVE' ? 'var(--red)' : a.status === 'ACKNOWLEDGED' ? 'var(--gold)' : 'var(--green)',
                      }}
                    >
                      {a.status}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: '11px' }}>
                    {a.timestamp ? new Date(a.timestamp).toLocaleString() : 'Recently'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      {a.status === 'ACTIVE' ? (
                        <button
                          className="n-btn"
                          style={{ background: 'var(--red-dim)', color: 'var(--red)', borderColor: 'rgba(239,82,81,0.3)' }}
                          disabled={acking[a.alert_id]}
                          onClick={() => handleAck(a.alert_id)}
                        >
                          {acking[a.alert_id] ? 'Acking...' : 'Acknowledge'}
                        </button>
                      ) : (
                        <span style={{ fontSize: '11px', color: 'var(--text-low)' }}>
                          {a.acknowledged_by ? `Ack by ${a.acknowledged_by}` : 'Acknowledged'}
                        </span>
                      )}

                      {a.event_id && onInvestigate && (
                        <button
                          className="n-btn ai-investigate"
                          style={{ fontSize: '10.5px', padding: '3px 7px' }}
                          onClick={() => onInvestigate({ event_id: a.event_id })}
                          title="Investigate incident with AI"
                        >
                          <AiSparklesIcon size={11} />
                          <span>AI Investigate</span>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="7" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-low)' }}>
                  No security alerts match the selected criteria.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}
