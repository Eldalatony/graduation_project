import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import ApplianceCard from '../components/ApplianceCard';
import { api, ApiError } from '../lib/api';
import { clearToken } from '../lib/auth';

const LIVE_POLL_MS = 1000;

export default function AppliancesScreen() {
  const router = useRouter();
  const [appliances, setAppliances] = useState([]);
  const [liveMap, setLiveMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const handleAuthError = useCallback(async (err) => {
    if (err instanceof ApiError && err.status === 401) {
      await clearToken();
      router.replace('/auth');
      return true;
    }
    return false;
  }, [router]);

  const fetchAppliances = useCallback(async () => {
    try {
      const data = await api.listAppliances();
      setAppliances(data.appliances || []);
      setError(null);
    } catch (err) {
      if (await handleAuthError(err)) return;
      setError(err.message);
    }
  }, [handleAuthError]);

  const fetchLive = useCallback(async () => {
    try {
      const data = await api.liveSnapshot();
      setLiveMap(data || {});
    } catch (err) {
      if (await handleAuthError(err)) return;
      // silent — live polling is best-effort
    }
  }, [handleAuthError]);

  useEffect(() => {
    (async () => {
      await Promise.all([fetchAppliances(), fetchLive()]);
      setLoading(false);
    })();

    pollRef.current = setInterval(fetchLive, LIVE_POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [fetchAppliances, fetchLive]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchAppliances(), fetchLive()]);
    setRefreshing(false);
  }, [fetchAppliances, fetchLive]);

  const onLogout = async () => {
    await clearToken();
    router.replace('/auth');
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>Appliances</Text>
        <TouchableOpacity onPress={onLogout}>
          <Text style={styles.logout}>Logout</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        >
          {error && <Text style={styles.error}>{error}</Text>}

          {appliances.length === 0 ? (
            <Text style={styles.empty}>
              No appliances yet. Add some from the web app.
            </Text>
          ) : (
            appliances.map((a) => {
              const liveKey = `${a.gateway_id}/${a.node_key}`;
              return (
                <ApplianceCard
                  key={a.id}
                  name={a.name}
                  nodeKey={a.node_key}
                  gatewayId={a.gateway_id}
                  reading={liveMap[liveKey]}
                  isActive={a.is_active}
                />
              );
            })
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f7f7f7' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
  },
  logout: {
    color: '#c00',
    fontSize: 14,
  },
  scrollContent: {
    padding: 16,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  empty: {
    color: '#666',
    textAlign: 'center',
    marginTop: 24,
  },
  error: {
    color: '#c00',
    marginBottom: 12,
  },
});
