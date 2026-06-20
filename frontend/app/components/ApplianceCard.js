'use client';

// Shared card used by the home page (read-only) and the appliances page
// (with control / edit / delete / readings actions).
//
// Props:
//   name        — display name
//   nodeKey     — node identifier
//   gatewayId   — gateway identifier
//   reading     — optional live reading object { power_W, current_A, voltage_V,
//                 energy_kWh, cost_EGP, status }. If absent, only metadata shows.
//   isActive    — optional boolean used when there's no live reading (DB flag)
//   actions     — optional object with handlers:
//                 { onTurnOn, onTurnOff, onEdit, onDelete, onReadings }

export default function ApplianceCard({
  name,
  nodeKey,
  gatewayId,
  reading,
  isActive,
  actions,
}) {
  const live = !!reading;
  const status = reading?.status || (isActive ? 'active' : 'idle');

  const badgeStyles = {
    active:  { bg: '#dcfce7', fg: '#166534' },
    idle:    { bg: '#f1f5f9', fg: '#475569' },
    offline: { bg: '#fee2e2', fg: '#991b1b' },
  };
  const badge = badgeStyles[status] || badgeStyles.idle;

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 16, background: '#fff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <strong style={{ textTransform: 'capitalize' }}>{name}</strong>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 12,
          background: badge.bg,
          color:      badge.fg,
        }}>
          {status}
        </span>
      </div>

      {live ? (
        <>
          <div style={{ fontSize: 32, fontWeight: 600, marginBottom: 4 }}>
            {Number(reading.power_W ?? 0).toFixed(0)} <span style={{ fontSize: 14, color: '#666' }}>W</span>
          </div>
          <Row label="Current" value={`${Number(reading.current_A  ?? 0).toFixed(2)} A`} />
          <Row label="Voltage" value={`${Number(reading.voltage_V  ?? 0).toFixed(0)} V`} />
          <Row label="Energy"  value={`${Number(reading.energy_kWh ?? 0).toFixed(4)} kWh`} />
          <Row label="Cost"    value={`${Number(reading.cost_EGP   ?? 0).toFixed(4)} EGP`} />
        </>
      ) : (
        <div style={{ fontSize: 13, color: '#888', padding: '12px 0' }}>
          No live data yet.
        </div>
      )}

      <div style={{ fontSize: 11, color: '#888', marginTop: 8 }}>
        gateway: {gatewayId || '—'} / {nodeKey}
      </div>

      {actions && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12, paddingTop: 12, borderTop: '1px solid #eee' }}>
          {actions.onTurnOn   && <button onClick={actions.onTurnOn}>Turn On</button>}
          {actions.onTurnOff  && <button onClick={actions.onTurnOff}>Turn Off</button>}
          {actions.onEdit     && <button onClick={actions.onEdit}>Edit</button>}
          {actions.onDelete   && <button onClick={actions.onDelete}>Delete</button>}
          {actions.onReadings && <button onClick={actions.onReadings}>Readings</button>}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '2px 0' }}>
      <span style={{ color: '#666' }}>{label}</span>
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  );
}
