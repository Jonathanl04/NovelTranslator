import { Loader2, KeyRound, Plus, Save, Settings, Trash2, WalletCards } from "lucide-react";
import { useState } from "react";
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
import type { AddedModel, Config, OpenRouterProvider, Usage } from "@/types";
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
        </section>

        <section className="grid gap-3 rounded-lg border bg-background p-3">
          <div className="flex items-center gap-2">
            <Settings className="size-4 text-teal-700" />
            <h3 className="text-sm font-semibold">Models</h3>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <ModelProviderEditor
              kind="glossary"
              title="Glossary model"
              model={config.glossary_model}
              provider={config.glossary_provider}
              choices={modelChoices(config)}
              onSelectModel={(index) => selectModel("glossary", index)}
            />
            <ModelProviderEditor
              kind="translation"
              title="Translation model"
              model={config.translation_model}
              provider={config.translation_provider}
              choices={modelChoices(config)}
              onSelectModel={(index) => selectModel("translation", index)}
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

function ModelProviderEditor({
  kind,
  title,
  model,
  provider,
  choices,
  onSelectModel,
}: {
  kind: "glossary" | "translation";
  title: string;
  model: string;
  provider: string;
  choices: AddedModel[];
  onSelectModel: (index: string) => void;
}) {
  const selectedChoiceIndex = choices.findIndex(
    (item) => item.model === model && item.provider === provider
  );
  const selectedChoiceValue = selectedChoiceIndex >= 0 ? String(selectedChoiceIndex) : "custom";

  return (
    <div className="grid gap-3 rounded-md border p-3">
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
