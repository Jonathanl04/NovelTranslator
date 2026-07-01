import { KeyRound, Save, Settings, WalletCards } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Config, Usage } from "@/types";
import { emptyUsageBucket, MODELS, ModelSelect, UsageSummary } from "./shared";

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
            <ModelSelect
              id="glossary-model-settings"
              label="Glossary model"
              value={config.glossary_model}
              onChange={(glossary_model) => onConfigChange({ glossary_model })}
            />
            <ModelSelect
              id="translation-model-settings"
              label="Translation model"
              value={config.translation_model}
              onChange={(translation_model) => onConfigChange({ translation_model })}
            />
          </div>
          <div>
            <Button type="button" onClick={onSaveConfig}>
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
          <div className="grid gap-2 md:grid-cols-3">
            {MODELS.map((model) => (
              <UsageSummary key={model} label={model} usage={usage.by_model[model] || emptyUsageBucket} />
            ))}
          </div>
          <UsageSummary label="Total" usage={usage.total} prominent />
        </section>
      </section>
    </main>
  );
}
