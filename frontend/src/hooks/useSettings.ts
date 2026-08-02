import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api";
import type { Config, Usage } from "@/types";
import { emptyUsageBucket } from "@/pages/shared";

const emptyConfig: Config = {
  has_openrouter_api_key: false,
  openrouter_api_key_mask: "",
  translation_backend: "openrouter",
  glossary_backend: "openrouter",
  translation_reasoning_effort: "none",
  glossary_reasoning_effort: "none",
  codex_fast_mode: false,
  codex_translation_model: "",
  codex_glossary_model: "",
  translation_model: "",
  translation_provider: "",
  glossary_model: "",
  glossary_provider: "",
  glossary_strategy: "full",
  added_models: [],
};

const emptyUsage: Usage = { total: emptyUsageBucket, by_model: {} };

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export function useSettings(onStatus: (message: string, isError?: boolean) => void) {
  const [config, setConfig] = useState<Config>(emptyConfig);
  const [openrouterApiKey, setOpenrouterApiKey] = useState("");
  const [usage, setUsage] = useState<Usage>(emptyUsage);
  const requestVersion = useRef(0);

  useEffect(() => {
    let active = true;
    Promise.all([api.config(), api.usage()])
      .then(([nextConfig, nextUsage]) => {
        if (!active) return;
        setConfig(nextConfig);
        setUsage(nextUsage);
      })
      .catch((error) => onStatus(errorMessage(error), true));
    return () => { active = false; };
  }, [onStatus]);

  const save = useCallback(async (patch: Partial<Config> = {}) => {
    const version = ++requestVersion.current;
    const nextConfig = { ...config, ...patch };
    const saveApiKey = Object.keys(patch).length === 0;
    try {
      const current = await api.config();
      const saved = await api.saveConfig({
        openrouter_api_key: saveApiKey && openrouterApiKey.trim() ? openrouterApiKey.trim() : undefined,
        keep_existing_openrouter_key: !saveApiKey || (!openrouterApiKey.trim() && current.has_openrouter_api_key),
        translation_backend: nextConfig.translation_backend,
        glossary_backend: nextConfig.glossary_backend,
        translation_reasoning_effort: nextConfig.translation_reasoning_effort,
        glossary_reasoning_effort: nextConfig.glossary_reasoning_effort,
        codex_fast_mode: nextConfig.codex_fast_mode,
        codex_translation_model: nextConfig.codex_translation_model,
        codex_glossary_model: nextConfig.codex_glossary_model,
        translation_model: nextConfig.translation_model,
        translation_provider: nextConfig.translation_provider,
        glossary_model: nextConfig.glossary_model,
        glossary_provider: nextConfig.glossary_provider,
        glossary_strategy: nextConfig.glossary_strategy,
        added_models: nextConfig.added_models,
      });
      if (version !== requestVersion.current) return;
      setConfig(saved);
      setOpenrouterApiKey("");
      onStatus("Settings saved.");
    } catch (error) { onStatus(errorMessage(error), true); }
  }, [config, onStatus, openrouterApiKey]);

  const resetUsage = useCallback(async () => {
    try { setUsage(await api.resetUsage()); onStatus("Token usage reset."); }
    catch (error) { onStatus(errorMessage(error), true); }
  }, [onStatus]);

  const updateConfig = useCallback((patch: Partial<Config>) => {
    setConfig((current) => ({ ...current, ...patch }));
  }, []);

  return { config, openrouterApiKey, resetUsage, save, setOpenrouterApiKey, setUsage, updateConfig, usage };
}
