import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { Model, UsageBucket } from "@/types";

export const MODELS: Model[] = ["deepseek-v4-flash", "deepseek-v4-pro", "mimo-v2.5", "mimo-v2.5-pro"];

export const emptyUsageBucket: UsageBucket = {
  prompt_cache_hit_tokens: 0,
  prompt_cache_miss_tokens: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
  cost_usd: 0,
};

export function ModelSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: Model;
  onChange: (value: Model) => void;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={(nextValue) => onChange(nextValue as Model)}>
        <SelectTrigger id={id} className="w-full bg-background">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {MODELS.map((model) => (
            <SelectItem key={model} value={model}>
              {model}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function UsageSummary({
  label,
  usage,
  prominent = false,
}: {
  label: string;
  usage: UsageBucket;
  prominent?: boolean;
}) {
  return (
    <div className={cn("grid gap-1 rounded-md border p-2", prominent && "bg-muted/30")}>
      <div className="flex items-center justify-between gap-2 text-xs font-semibold">
        <span>{label}</span>
        <span className="tabular-nums">{formatUsd(usage.cost_usd)}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
        <span>Input hit</span>
        <span className="text-right tabular-nums">{formatInteger(usage.prompt_cache_hit_tokens)}</span>
        <span>Input miss</span>
        <span className="text-right tabular-nums">{formatInteger(usage.prompt_cache_miss_tokens)}</span>
        <span>Output</span>
        <span className="text-right tabular-nums">{formatInteger(usage.completion_tokens)}</span>
        <span>Total tokens</span>
        <span className="text-right tabular-nums">{formatInteger(usage.total_tokens)}</span>
      </div>
    </div>
  );
}

export function formatInteger(value: number) {
  return new Intl.NumberFormat().format(value);
}

function formatUsd(value: number) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 6,
    maximumFractionDigits: 6,
  }).format(value);
}
