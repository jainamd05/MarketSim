import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { AppConfig, DataMode } from "@/lib/types";

interface AppState {
  config: AppConfig | null;
  configError: string | null;
  /** Mode of the analysis currently on screen; overrides the server default in the banner. */
  viewMode: DataMode | null;
  setViewMode: (m: DataMode | null) => void;
}

const Ctx = createContext<AppState>({ config: null, configError: null, viewMode: null, setViewMode: () => {} });

export function AppProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<DataMode | null>(null);
  useEffect(() => {
    api.config().then(setConfig).catch((e: Error) => setConfigError(e.message));
  }, []);
  return <Ctx.Provider value={{ config, configError, viewMode, setViewMode }}>{children}</Ctx.Provider>;
}

export function useApp() {
  return useContext(Ctx);
}

/** Pages showing a specific analysis declare its data mode so the banner is accurate. */
export function useViewMode(mode: DataMode | null | undefined) {
  const { setViewMode } = useApp();
  useEffect(() => {
    setViewMode(mode ?? null);
    return () => setViewMode(null);
  }, [mode, setViewMode]);
}
