import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Loads data on mount and whenever `deps` change. Stale responses are dropped. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(() => {
    const ticket = ++latest.current;
    setLoading(true);
    loader()
      .then((result) => {
        if (ticket !== latest.current) return;
        setData(result);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (ticket !== latest.current) return;
        setError(reason instanceof Error ? reason.message : "Request failed.");
      })
      .finally(() => {
        if (ticket === latest.current) setLoading(false);
      });
  }, deps);

  useEffect(load, [load]);
  return { data, error, loading, reload: load };
}
