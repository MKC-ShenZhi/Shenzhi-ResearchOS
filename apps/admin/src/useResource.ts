import { useEffect, useState } from 'react';
import { api } from './api';
export function useResource<T>(path: string) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setData(undefined); setError('');
    const controller = new AbortController();
    setLoading(true);
    api<T>(path, {signal: controller.signal}).then(value => { if (!controller.signal.aborted) setData(value); }).catch(e => { if (!controller.signal.aborted) setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path, revision]);
  return { data, error, loading, refresh: () => setRevision(v => v + 1) };
}
