import { useEffect, useState } from 'react';
import { api } from './api';
export function useResource<T>(path: string | undefined) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setData(undefined); setError('');
    if (path === undefined) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api<T>(path, {signal: controller.signal}).then(setData).catch(e => { if (!controller.signal.aborted) setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path, revision]);
  return { data, error, loading, refresh: () => setRevision(v => v + 1) };
}
