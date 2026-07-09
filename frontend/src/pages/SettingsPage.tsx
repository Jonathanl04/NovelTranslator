import { Loader2, KeyRound, Save, Settings, Star, Trash2, WalletCards } from "lucide-react";
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
import type { Config, FavoriteModel, OpenRouterProvider, Usage } from "@/types";
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
  onSaveConfig: () => void;
  onResetUsage: () => void;
}) {
  const [providers, setProviders] = useState<Record<"glossary" | "translation", OpenRouterProvider[]>>({
    glossary: [],
    translation: [],
  });
  const [loadingProviders, setLoadingProviders] = useState<"glossary" | "translation" | "">("");
  const [providerError, setProviderError] = useState("");
  const canSave = Boolean(
    config.glossary_model.trim() &&
      config.glossary_provider.trim() &&
      config.translation_model.trim() &&
      config.translation_provider.trim()
  );

  async function loadProviders(kind: "glossary" | "translation") {
    const model = kind === "glossary" ? config.glossary_model : config.translation_model;
    if (!model.trim()) {
      setProviderError("Enter a model before loading providers.");
      return;
    }
    setProviderError("");
    setLoadingProviders(kind);
    try {
      const nextProviders = await api.openrouterProviders(model.trim());
      setProviders((current) => ({ ...current, [kind]: nextProviders }));
      if (nextProviders.length === 1) {
        onConfigChange({ [`${kind}_provider`]: nextProviders[0].provider } as Partial<Config>);
      }
      if (nextProviders.length === 0) {
        setProviderError("No providers returned for that model.");
      }
    } catch (caught) {
      setProviderError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoadingProviders("");
    }
  }

  function favoriteCurrent(kind: "glossary" | "translation") {
    const model = (kind === "glossary" ? config.glossary_model : config.translation_model).trim();
    const provider = (kind === "glossary" ? config.glossary_provider : config.translation_provider).trim();
    if (!model || !provider) return;
    const favorite = { model, provider };
    onConfigChange({ favorite_models: mergeFavorites(config.favorite_models, favorite) });
  }

  function applyFavorite(kind: "glossary" | "translation", indexValue: string) {
    const favorite = modelChoices(config)[Number(indexValue)];
    if (!favorite) return;
    setProviders((current) => ({ ...current, [kind]: [] }));
    if (kind === "glossary") {
      onConfigChange({ glossary_model: favorite.model, glossary_provider: favorite.provider });
    } else {
      onConfigChange({ translation_model: favorite.model, translation_provider: favorite.provider });
    }
  }

  function removeFavorite(index: number) {
    onConfigChange({ favorite_models: config.favorite_models.filter((_, itemIndex) => itemIndex !== index) });
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
              providers={providers.glossary}
              choices={modelChoices(config)}
              loading={loadingProviders === "glossary"}
              onModelChange={(glossary_model) => {
                setProviders((current) => ({ ...current, glossary: [] }));
                onConfigChange({ glossary_model, glossary_provider: "" });
              }}
              onProviderChange={(glossary_provider) => onConfigChange({ glossary_provider })}
              onLoadProviders={() => loadProviders("glossary")}
              onFavorite={() => favoriteCurrent("glossary")}
              onApplyFavorite={(index) => applyFavorite("glossary", index)}
            />
            <ModelProviderEditor
              kind="translation"
              title="Translation model"
              model={config.translation_model}
              provider={config.translation_provider}
              providers={providers.translation}
              choices={modelChoices(config)}
              loading={loadingProviders === "translation"}
              onModelChange={(translation_model) => {
                setProviders((current) => ({ ...current, translation: [] }));
                onConfigChange({ translation_model, translation_provider: "" });
              }}
              onProviderChange={(translation_provider) => onConfigChange({ translation_provider })}
              onLoadProviders={() => loadProviders("translation")}
              onFavorite={() => favoriteCurrent("translation")}
              onApplyFavorite={(index) => applyFavorite("translation", index)}
            />
          </div>
          {providerError ? <p className="text-xs text-destructive">{providerError}</p> : null}
          {config.favorite_models.length > 0 ? (
            <div className="grid gap-2">
              <Label>Favorite models</Label>
              <div className="grid gap-1.5">
                {config.favorite_models.map((favorite, index) => (
                  <div key={`${favorite.provider}:${favorite.model}`} className="flex min-w-0 items-center gap-2 rounded-md border p-2 text-xs">
                    <span className="min-w-0 flex-1 truncate font-medium">{modelLabel(favorite)}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => removeFavorite(index)}
                      aria-label={`Remove ${modelLabel(favorite)}`}
                      title="Remove favorite"
                    >
                      <Trash2 />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div>
            <Button type="button" onClick={onSaveConfig} disabled={!canSave}>
              <Save />
              Save Settings
            </Button>
          </div>
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
  providers,
  choices,
  loading,
  onModelChange,
  onProviderChange,
  onLoadProviders,
  onFavorite,
  onApplyFavorite,
}: {
  kind: "glossary" | "translation";
  title: string;
  model: string;
  provider: string;
  providers: OpenRouterProvider[];
  choices: FavoriteModel[];
  loading: boolean;
  onModelChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onLoadProviders: () => void;
  onFavorite: () => void;
  onApplyFavorite: (index: string) => void;
}) {
  const canFavorite = Boolean(model.trim() && provider.trim());

  return (
    <div className="grid gap-3 rounded-md border p-3">
      {choices.length > 0 ? (
        <div className="grid gap-1.5">
          <Label htmlFor={`${kind}-saved-model-settings`}>{title}</Label>
          <Select value="" onValueChange={onApplyFavorite}>
            <SelectTrigger id={`${kind}-saved-model-settings`} className="w-full bg-background">
              <SelectValue placeholder="Apply favorite" />
            </SelectTrigger>
            <SelectContent>
              {choices.map((favorite, index) => (
                <SelectItem key={`${favorite.provider}:${favorite.model}`} value={String(index)}>
                  {modelLabel(favorite)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <div className="text-sm font-semibold">{title}</div>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor={`${kind}-custom-model-settings`}>Model ID</Label>
        <Input
          id={`${kind}-custom-model-settings`}
          value={model}
          placeholder="provider/model-name"
          autoComplete="off"
          onChange={(event) => onModelChange(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={onLoadProviders} disabled={loading || !model.trim()}>
          {loading ? <Loader2 className="animate-spin" /> : <Settings />}
          Load providers
        </Button>
        <Button type="button" variant="outline" onClick={onFavorite} disabled={!canFavorite}>
          <Star />
          Favorite
        </Button>
      </div>
      {providers.length > 0 ? <div className="grid gap-1.5">
        <Label htmlFor={`${kind}-provider-settings`}>Provider</Label>
        <Select value={provider} onValueChange={onProviderChange}>
          <SelectTrigger id={`${kind}-provider-settings`} className="w-full bg-background">
            <SelectValue placeholder="Select provider" />
          </SelectTrigger>
          <SelectContent>
            {providers.map((item) => (
              <SelectItem key={item.provider} value={item.provider}>
                {item.provider}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div> : null}
      {providers.length === 0 && provider.trim() ? (
        <div className="text-xs text-muted-foreground">
          Provider: <span className="font-medium text-foreground">{provider}</span>
        </div>
      ) : null}
    </div>
  );
}

function mergeFavorites(favorites: FavoriteModel[], favorite: FavoriteModel) {
  if (favorites.some((item) => item.model === favorite.model && item.provider === favorite.provider)) {
    return favorites;
  }
  return [...favorites, favorite];
}

function modelLabel(favorite: FavoriteModel) {
  return `${favorite.model} (${favorite.provider})`;
}

function modelChoices(config: Config) {
  return [...config.model_presets, ...config.favorite_models].reduce<FavoriteModel[]>((items, favorite) => {
    return mergeFavorites(items, favorite);
  }, []);
}
