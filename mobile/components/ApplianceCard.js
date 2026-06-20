import { View, Text, StyleSheet } from 'react-native';

const BADGE_STYLES = {
  active:  { bg: '#dcfce7', fg: '#166534' },
  idle:    { bg: '#f1f5f9', fg: '#475569' },
  offline: { bg: '#fee2e2', fg: '#991b1b' },
};

export default function ApplianceCard({ name, nodeKey, gatewayId, reading, isActive }) {
  const live = !!reading;
  const status = reading?.status || (isActive ? 'active' : 'idle');
  const badge = BADGE_STYLES[status] || BADGE_STYLES.idle;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.name}>{name}</Text>
        <View style={[styles.badge, { backgroundColor: badge.bg }]}>
          <Text style={[styles.badgeText, { color: badge.fg }]}>{status}</Text>
        </View>
      </View>

      {live ? (
        <>
          <View style={styles.powerRow}>
            <Text style={styles.powerValue}>{Number(reading.power_W ?? 0).toFixed(0)}</Text>
            <Text style={styles.powerUnit}> W</Text>
          </View>
          <Row label="Current" value={`${Number(reading.current_A  ?? 0).toFixed(2)} A`} />
          <Row label="Voltage" value={`${Number(reading.voltage_V  ?? 0).toFixed(0)} V`} />
          <Row label="Energy"  value={`${Number(reading.energy_kWh ?? 0).toFixed(4)} kWh`} />
          <Row label="Cost"    value={`${Number(reading.cost_EGP   ?? 0).toFixed(4)} EGP`} />
        </>
      ) : (
        <Text style={styles.noData}>No live data yet.</Text>
      )}

      <Text style={styles.meta}>
        gateway: {gatewayId || '—'} / {nodeKey}
      </Text>
    </View>
  );
}

function Row({ label, value }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 16,
    backgroundColor: '#fff',
    marginBottom: 12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  name: {
    fontWeight: '600',
    fontSize: 16,
    textTransform: 'capitalize',
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 12,
  },
  badgeText: {
    fontSize: 11,
  },
  powerRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginBottom: 4,
  },
  powerValue: {
    fontSize: 32,
    fontWeight: '600',
  },
  powerUnit: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 2,
  },
  rowLabel: {
    color: '#666',
    fontSize: 13,
  },
  rowValue: {
    fontSize: 13,
    fontVariant: ['tabular-nums'],
  },
  noData: {
    fontSize: 13,
    color: '#888',
    paddingVertical: 12,
  },
  meta: {
    fontSize: 11,
    color: '#888',
    marginTop: 8,
  },
});
