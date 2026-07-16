import { KeyRound, Loader2, LogIn, LogOut, Plus, RefreshCw, Save, Settings, Trash2, WalletCards } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  AddedModel,
  CodexAuth,
  CodexModels,
  CodexRemainingUsage,
  Config,
  LlmBackend,
  OpenRouterProvider,
  ReasoningEffort,
  Usage,
} from "@/types";
import { UsageSummary } from "./shared";

export function SettingsPage({
  openrouterApiKey,
  config,
  usage,
  onOpenrouterApiKeyChange,
  onConfigChange,
  onSaveConfig,
  onResetUsage,
}: {
  openrouterApiKey: string;
  config: Config;
  usage: Usage;
  onOpenrouterApiKeyChange: (value: string) => void;
  onConfigChange: (patch: Partial<Config>) => void;
  onSaveConfig: (patch?: Partial<Config>) => void | Promise<void>;
  onResetUsage: () => void;
}) {
  const [newModel, setNewModel] = useState("");
  const [newProvider, setNewProvider] = useState("");
  const [newProviders, setNewProviders] = useState<OpenRouterProvider[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(false);
  const [providerError, setProviderError] = useState("");
  const [codexAuth, setCodexAuth] = useState<CodexAuth | null>(null);
  const [codexModels, setCodexModels] = useState<CodexModels | null>(null);
  const [codexUsage, setCodexUsage] = useState<CodexRemainingUsage | null>(null);
  const [codexBusy, setCodexBusy] = useState(false);
  const [codexError, setCodexError] = useState("");

  useEffect(() => {
    void loadCodexState();
  }, []);

  useEffect(() => {
    if (codexAuth?.status !== "pending") return;
    const timer = window.setInterval(() => { void loadCodexState(); }, 1000);
    return () => window.clearInterval(timer);
  }, [codexAuth?.status]);

  async function loadCodexState() {
    try {
      const auth = await api.codexAuth();
      setCodexAuth(auth);
      if (auth.signed_in) {
        const [models, remaining] = await Promise.allSettled([
          api.codexModels(false),
          api.codexRemainingUsage(false),
        ]);
        if (models.status === "fulfilled") setCodexModels(models.value);
        else setCodexError(errorText(models.reason));
        if (remaining.status === "fulfilled") setCodexUsage(remaining.value);
        else setCodexError(errorText(remaining.reason));
      }
    } catch (caught) {
      setCodexError(errorText(caught));
    }
  }

  async function loginCodex() {
    setCodexBusy(true);
    setCodexError("");
    try {
      const login = await api.codexLogin();
      window.open(login.auth_url, "_blank", "noopener,noreferrer");
      setCodexAuth((current) => ({
        available: current?.available ?? true,
        signed_in: false,
        status: "pending",
        account: null,
        error: "",
      }));
    } catch (caught) {
      setCodexError(errorText(caught));
    } finally {
      setCodexBusy(false);
    }
  }

  async function logoutCodex() {
    setCodexBusy(true);
    setCodexError("");
    try {
      setCodexAuth(await api.codexLogout());
      setCodexModels(null);
      setCodexUsage(null);
    } catch (caught) {
      setCodexError(errorText(caught));
    } finally {
      setCodexBusy(false);
    }
  }

  async function refreshCodexModels() {
    setCodexBusy(true);
    setCodexError("");
    try { setCodexModels(await api.codexModels(true)); }
    catch (caught) { setCodexError(errorText(caught)); }
    finally { setCodexBusy(false); }
  }

  async function refreshCodexUsage() {
    setCodexBusy(true);
    setCodexError("");
    try { setCodexUsage(await api.codexRemainingUsage(true)); }
    catch (caught) { setCodexError(errorText(caught)); }
    finally { setCodexBusy(false); }
  }

  async function loadProviders() {
    if (!newModel.trim()) {
      setProviderError("Enter a model before loading providers.");
      return;
    }
    setProviderError("");
    setLoadingProviders(true);
    try {
      const nextProviders = await api.openrouterProviders(newModel.trim());
      setNewProviders(nextProviders);
      if (nextProviders.length === 1) {
        setNewProvider(nextProviders[0].provider);
      }
      if (nextProviders.length === 0) {
        setProviderError("No providers returned for that model.");
      }
    } catch (caught) {
      setProviderError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoadingProviders(false);
    }
  }

  function addCurrentModel() {
    const model = newModel.trim();
    const provider = newProvider.trim();
    if (!model || !provider) return;
    const added_models = mergeModels(config.added_models, { model, provider });
    onConfigChange({ added_models });
    onSaveConfig({ added_models });
    setNewModel("");
    setNewProvider("");
    setNewProviders([]);
  }

  function selectModel(kind: "glossary" | "translation", indexValue: string) {
    const selected = modelChoices(config)[Number(indexValue)];
    if (!selected) return;
    const patch =
      kind === "glossary"
        ? { glossary_model: selected.model, glossary_provider: selected.provider }
        : { translation_model: selected.model, translation_provider: selected.provider };
    onConfigChange(patch);
    onSaveConfig(patch);
  }

  async function selectBackend(kind: "glossary" | "translation", backend: LlmBackend) {
    const backendKey = `${kind}_backend` as const;
    const codexModelKey = `codex_${kind}_model` as const;
    const patch: Partial<Config> = { [backendKey]: backend };
    if (backend === "codex" && !config[codexModelKey]) {
      const selected = codexModels?.models.find((model) => model.is_default) ?? codexModels?.models[0];
      if (!selected) return;
      patch[codexModelKey] = selected.id;
    }
    onConfigChange(patch);
    await onSaveConfig(patch);
  }

  async function selectCodexModel(kind: "glossary" | "translation", model: string) {
    const key = `codex_${kind}_model` as const;
    const patch: Partial<Config> = { [key]: model };
    onConfigChange(patch);
    await onSaveConfig(patch);
  }

  async function selectReasoning(kind: "glossary" | "translation", effort: ReasoningEffort) {
    const key = `${kind}_reasoning_effort` as const;
    const patch: Partial<Config> = { [key]: effort };
    onConfigChange(patch);
    await onSaveConfig(patch);
  }

  function removeAddedModel(index: number) {
    const added_models = config.added_models.filter((_, itemIndex) => itemIndex !== index);
    onConfigChange({ added_models });
    onSaveConfig({ added_models });
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)] bg-muted/20 p-3 sm:p-4">
      <section className="mx-auto grid max-w-5xl gap-4">
        <div>
          <h2 className="text-lg font-semibold">Settings</h2>
          <p className="text-sm text-muted-foreground">API key, models, and token usage.</p>
        </div>

        <section className="grid gap-3 rounded-lg border bg-background p-3">
          <div className="flex items-center gap-2">
            <KeyRound className="size-4 text-teal-700" />
            <h3 className="text-sm font-semibold">API keys</h3>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="openrouter-api-key">OpenRouter API key</Label>
            <Input
              id="openrouter-api-key"
              type="password"
              value={openrouterApiKey}
              placeholder={config.has_openrouter_api_key ? config.openrouter_api_key_mask : ""}
              autoComplete="off"
              onChange={(event) => onOpenrouterApiKeyChange(event.target.value)}
            />
          </div>
          <div>
            <Button type="button" onClick={() => onSaveConfig()}>
              <Save />
              Save API Key
            </Button>
          </div>
          <div className="mt-1 grid gap-2 border-t pt-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-medium">ChatGPT account for Codex</div>
                <div className="text-xs text-muted-foreground">
                  {codexAuth?.signed_in
                    ? `${codexAuth.account?.email || "Connected"} · ${codexAuth.account?.plan || "Codex"}`
                    : codexAuth?.status === "pending"
                      ? "Waiting for browser sign-in…"
                      : "Not connected"}
                </div>
              </div>
              {codexAuth?.signed_in ? (
                <Button type="button" variant="outline" onClick={logoutCodex} disabled={codexBusy}>
                  <LogOut /> Sign out
                </Button>
              ) : (
                <Button type="button" variant="outline" onClick={loginCodex} disabled={codexBusy || codexAuth?.status === "pending"}>
                  {codexBusy || codexAuth?.status === "pending" ? <Loader2 className="animate-spin" /> : <LogIn />}
                  Sign in with ChatGPT
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Uses Codex subscription limits, not general OpenAI API credits. Credentials remain in Codex's user store.
            </p>
            {codexError || codexAuth?.error ? <p className="text-xs text-destructive">{codexError || codexAuth?.error}</p> : null}
          </div>
        </section>

        <section className="grid gap-3 rounded-lg border bg-background p-3">
          <div className="flex items-center gap-2">
            <Settings className="size-4 text-teal-700" />
            <h3 className="text-sm font-semibold">Models</h3>
          </div>
          {codexAuth?.signed_in ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-xs">
              <span className="text-muted-foreground">
                {codexModels?.models.length ?? 0} Codex models
                {codexModels?.fetched_at ? ` · refreshed ${formatTime(codexModels.fetched_at)}` : ""}
                {codexModels?.stale ? " · stale" : ""}
              </span>
              <Button type="button" variant="outline" size="sm" onClick={refreshCodexModels} disabled={codexBusy}>
                <RefreshCw className={codexBusy ? "animate-spin" : ""} /> Refresh models
              </Button>
              {codexModels?.error ? <p className="w-full text-destructive">{codexModels.error}</p> : null}
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-2">
            <WorkloadModelEditor
              kind="glossary"
              title="Glossary model"
              backend={config.glossary_backend}
              model={config.glossary_model}
              provider={config.glossary_provider}
              choices={modelChoices(config)}
              codexModel={config.codex_glossary_model}
              codexModels={codexModels}
              codexSignedIn={Boolean(codexAuth?.signed_in)}
              reasoningEffort={config.glossary_reasoning_effort}
              onBackendChange={(backend) => selectBackend("glossary", backend)}
              onSelectCodexModel={(model) => selectCodexModel("glossary", model)}
              onSelectModel={(index) => selectModel("glossary", index)}
              onReasoningChange={(effort) => selectReasoning("glossary", effort)}
            />
            <WorkloadModelEditor
              kind="translation"
              title="Translation model"
              backend={config.translation_backend}
              model={config.translation_model}
              provider={config.translation_provider}
              choices={modelChoices(config)}
              codexModel={config.codex_translation_model}
              codexModels={codexModels}
              codexSignedIn={Boolean(codexAuth?.signed_in)}
              reasoningEffort={config.translation_reasoning_effort}
              onBackendChange={(backend) => selectBackend("translation", backend)}
              onSelectCodexModel={(model) => selectCodexModel("translation", model)}
              onSelectModel={(index) => selectModel("translation", index)}
              onReasoningChange={(effort) => selectReasoning("translation", effort)}
            />
          </div>
          <section className="grid gap-3 rounded-md border p-3">
            <div className="text-sm font-semibold">Add model</div>
            <div className="grid gap-3 md:grid-cols-[1fr_auto_auto] md:items-end">
              <div className="grid gap-1.5">
                <Label htmlFor="new-model-settings">Model ID</Label>
                <Input
                  id="new-model-settings"
                  value={newModel}
                  placeholder="provider/model-name"
                  autoComplete="off"
                  onChange={(event) => {
                    setNewModel(event.target.value);
                    setNewProvider("");
                    setNewProviders([]);
                  }}
                />
              </div>
              <Button type="button" variant="outline" onClick={loadProviders} disabled={loadingProviders || !newModel.trim()}>
                {loadingProviders ? <Loader2 className="animate-spin" /> : <Settings />}
                Load providers
              </Button>
              <Button type="button" variant="outline" onClick={addCurrentModel} disabled={!newModel.trim() || !newProvider.trim()}>
                <Plus />
                Add model
              </Button>
            </div>
            {newProviders.length > 0 ? (
              <div className="grid gap-1.5">
                <Label htmlFor="new-model-provider-settings">Provider</Label>
                <Select value={newProvider} onValueChange={setNewProvider}>
                  <SelectTrigger id="new-model-provider-settings" className="w-full bg-background">
                    <SelectValue placeholder="Select provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {newProviders.map((item) => (
                      <SelectItem key={item.provider} value={item.provider}>
                        {item.provider}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </section>
          {providerError ? <p className="text-xs text-destructive">{providerError}</p> : null}
          {config.added_models.length > 0 ? (
            <div className="grid gap-2">
              <Label>Added models</Label>
              <div className="grid gap-1.5">
                {config.added_models.map((model, index) => (
                  <div key={`${model.provider}:${model.model}`} className="flex min-w-0 items-center gap-2 rounded-md border p-2 text-xs">
                    <span className="min-w-0 flex-1 truncate font-medium">{modelLabel(model)}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => removeAddedModel(index)}
                      aria-label={`Remove ${modelLabel(model)}`}
                      title="Remove model"
                    >
                      <Trash2 />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>

        {codexAuth?.signed_in ? (
          <CodexUsageCard usage={codexUsage} busy={codexBusy} onRefresh={refreshCodexUsage} />
        ) : null}

        <section className="grid gap-3 rounded-lg border bg-background p-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <WalletCards className="size-4 text-teal-700" />
              <h3 className="font-semibold">Token usage</h3>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={onResetUsage}>
              Reset
            </Button>
          </div>
          <UsageSummary usage={usage.total} />
        </section>
      </section>
    </main>
  );
}

function WorkloadModelEditor({
  kind,
  title,
  backend,
  model,
  provider,
  choices,
  codexModel,
  codexModels,
  codexSignedIn,
  reasoningEffort,
  onBackendChange,
  onSelectModel,
  onSelectCodexModel,
  onReasoningChange,
}: {
  kind: "glossary" | "translation";
  title: string;
  backend: LlmBackend;
  model: string;
  provider: string;
  choices: AddedModel[];
  codexModel: string;
  codexModels: CodexModels | null;
  codexSignedIn: boolean;
  reasoningEffort: ReasoningEffort;
  onBackendChange: (backend: LlmBackend) => void;
  onSelectModel: (index: string) => void;
  onSelectCodexModel: (model: string) => void;
  onReasoningChange: (effort: ReasoningEffort) => void;
}) {
  const available = codexModels?.models.some((item) => item.id === codexModel) ?? false;
  return (
    <div className="grid gap-3 rounded-md border p-3">
      <div className="grid gap-1.5">
        <Label htmlFor={`${kind}-backend-settings`}>Backend</Label>
        <Select value={backend} onValueChange={(value) => onBackendChange(value as LlmBackend)}>
          <SelectTrigger id={`${kind}-backend-settings`} className="w-full bg-background"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="openrouter">OpenRouter</SelectItem>
            <SelectItem value="codex" disabled={!codexSignedIn || !codexModels?.models.length}>ChatGPT / Codex</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {backend === "openrouter" ? (
        <ModelProviderEditor kind={kind} title={title} model={model} provider={provider} choices={choices} onSelectModel={onSelectModel} plain />
      ) : (
        <div className="grid gap-1.5">
          <Label htmlFor={`${kind}-codex-model-settings`}>{title}</Label>
          <Select value={available ? codexModel : "unavailable"} onValueChange={onSelectCodexModel}>
            <SelectTrigger id={`${kind}-codex-model-settings`} className="w-full bg-background"><SelectValue /></SelectTrigger>
            <SelectContent>
              {!available ? <SelectItem value="unavailable" disabled>{codexModel || "Select a Codex model"} (unavailable)</SelectItem> : null}
              {codexModels?.models.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}
            </SelectContent>
          </Select>
          {!available ? <p className="text-xs text-destructive">Refresh models and select an available model.</p> : null}
        </div>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor={`${kind}-reasoning-settings`}>Reasoning</Label>
        <Select value={reasoningEffort} onValueChange={(value) => onReasoningChange(value as ReasoningEffort)}>
          <SelectTrigger id={`${kind}-reasoning-settings`} className="w-full bg-background"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="none">None</SelectItem>
            <SelectItem value="low">Low</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="high">High</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">Higher effort can improve difficult passages with additional latency and tokens.</p>
      </div>
    </div>
  );
}

function CodexUsageCard({ usage, busy, onRefresh }: { usage: CodexRemainingUsage | null; busy: boolean; onRefresh: () => void }) {
  return (
    <section className="grid gap-3 rounded-lg border bg-background p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2"><WalletCards className="size-4 text-teal-700" /><h3 className="font-semibold">Codex usage remaining</h3></div>
        <Button type="button" variant="outline" size="sm" onClick={onRefresh} disabled={busy}>
          <RefreshCw className={busy ? "animate-spin" : ""} /> Refresh usage
        </Button>
      </div>
      {usage?.available ? (
        <div className="grid gap-3">
          <UsageWindow label="Primary limit" value={usage.primary} />
          {usage.secondary ? <UsageWindow label="Secondary limit" value={usage.secondary} /> : null}
          {usage.individual_limit ? <div className="text-xs">Monthly limit: {usage.individual_limit.remainingPercent}% remaining</div> : null}
          {usage.credits ? <div className="text-xs">Credits: {usage.credits.unlimited ? "Unlimited" : usage.credits.balance ?? (usage.credits.hasCredits ? "Available" : "None")}</div> : null}
          {usage.rate_limit_reached_type ? <p className="text-xs text-destructive">Limit reached: {usage.rate_limit_reached_type}</p> : null}
        </div>
      ) : <p className="text-xs text-muted-foreground">Usage information unavailable.</p>}
      <div className="text-xs text-muted-foreground">
        {usage?.fetched_at ? `Last refreshed ${formatTime(usage.fetched_at)}${usage.stale ? " · stale" : ""}` : "Not refreshed yet"}
      </div>
      {usage?.error ? <p className="text-xs text-destructive">{usage.error}</p> : null}
    </section>
  );
}

function UsageWindow({ label, value }: { label: string; value: CodexRemainingUsage["primary"] }) {
  if (!value) return null;
  return (
    <div className="grid gap-1">
      <div className="flex justify-between gap-2 text-xs"><span>{label}</span><span className="font-medium">{value.remaining_percent}% remaining</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-teal-600" style={{ width: `${value.remaining_percent}%` }} /></div>
      <div className="text-xs text-muted-foreground">
        {value.window_duration_mins ? `${formatDuration(value.window_duration_mins)} window` : "Quota window"}
        {value.resets_at ? ` · resets ${formatTime(value.resets_at)}` : ""}
      </div>
    </div>
  );
}

function ModelProviderEditor({
  kind,
  title,
  model,
  provider,
  choices,
  onSelectModel,
  plain = false,
}: {
  kind: "glossary" | "translation";
  title: string;
  model: string;
  provider: string;
  choices: AddedModel[];
  onSelectModel: (index: string) => void;
  plain?: boolean;
}) {
  const selectedChoiceIndex = choices.findIndex(
    (item) => item.model === model && item.provider === provider
  );
  const selectedChoiceValue = selectedChoiceIndex >= 0 ? String(selectedChoiceIndex) : "custom";

  return (
    <div className={plain ? "grid gap-3" : "grid gap-3 rounded-md border p-3"}>
      {choices.length > 0 ? (
        <div className="grid gap-1.5">
          <Label htmlFor={`${kind}-saved-model-settings`}>{title}</Label>
          <Select value={selectedChoiceValue} onValueChange={onSelectModel}>
            <SelectTrigger id={`${kind}-saved-model-settings`} className="w-full bg-background">
              <SelectValue placeholder="Select model" />
            </SelectTrigger>
            <SelectContent>
              {selectedChoiceIndex < 0 ? (
                <SelectItem value="custom">{modelLabel({ model, provider })}</SelectItem>
              ) : null}
              {choices.map((item, index) => (
                <SelectItem key={`${item.provider}:${item.model}`} value={String(index)}>
                  {modelLabel(item)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <div className="text-sm font-semibold">{title}</div>
      )}
      {provider.trim() ? (
        <div className="text-xs text-muted-foreground">
          Provider: <span className="font-medium text-foreground">{provider}</span>
        </div>
      ) : null}
    </div>
  );
}

function mergeModels(models: AddedModel[], model: AddedModel) {
  if (models.some((item) => item.model === model.model && item.provider === model.provider)) {
    return models;
  }
  return [...models, model];
}

function modelLabel(model: AddedModel) {
  return `${model.model} (${model.provider})`;
}

function modelChoices(config: Config) {
  return [...config.model_presets, ...config.added_models].reduce<AddedModel[]>((items, model) => {
    return mergeModels(items, model);
  }, []);
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function formatTime(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleString();
}

function formatDuration(minutes: number) {
  if (minutes % (7 * 24 * 60) === 0) return `${minutes / (7 * 24 * 60)} week`;
  if (minutes % (24 * 60) === 0) return `${minutes / (24 * 60)} day`;
  if (minutes % 60 === 0) return `${minutes / 60} hour`;
  return `${minutes} minute`;
}
