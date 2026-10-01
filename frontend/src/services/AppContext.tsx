import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { SystemInfo, User } from "../types";
import { api, getUserId, setUserId } from "./api";

interface AppState {
  users: User[];
  user: User | null;
  system: SystemInfo | null;
  /** Bumped whenever the acting user or the system state changes, so pages reload. */
  version: number;
  backendError: string | null;
  switchUser: (id: string) => void;
  refresh: () => void;
}

const Context = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setCurrentUserId] = useState(getUserId());
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [version, setVersion] = useState(0);
  const [backendError, setBackendError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    Promise.all([api.users(), api.system()])
      .then(([loadedUsers, loadedSystem]) => {
        setUsers(loadedUsers);
        setSystem(loadedSystem);
        setBackendError(null);
      })
      .catch((reason: Error) => setBackendError(reason.message))
      .finally(() => setVersion((v) => v + 1));
  }, []);

  useEffect(refresh, [refresh, userId]);

  const switchUser = useCallback((id: string) => {
    setUserId(id);
    setCurrentUserId(id);
  }, []);

  const value = useMemo<AppState>(
    () => ({
      users,
      user: users.find((u) => u.id === userId) ?? null,
      system,
      version,
      backendError,
      switchUser,
      refresh,
    }),
    [users, userId, system, version, backendError, switchUser, refresh],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useApp(): AppState {
  const state = useContext(Context);
  if (!state) throw new Error("useApp must be used inside AppProvider");
  return state;
}
