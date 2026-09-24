'use client';
import { useEffect, useState } from 'react';
import { api } from './api';

/** Independent read-only section state, including cancellation and retry. */
export function useResource<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError('');
    void api<T>(path, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setData(value);
    }).catch(cause => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load this section.');
    });
    return () => controller.abort();
  }, [path, version]);
  return { data, error, retry: () => setVersion(value => value + 1) };
}
