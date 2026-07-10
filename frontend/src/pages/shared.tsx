import type { UsageBucket } from "@/types";

export const emptyUsageBucket: UsageBucket = {
  prompt_cache_hit_tokens: 0,
  prompt_cache_miss_tokens: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
  cost_usd: 0,
};

export function UsageSummary({ usage }: { usage: UsageBucket }) {
  return (
    <div className="grid gap-1 rounded-md border bg-muted/30 p-2">
      <div className="flex items-center justify-between gap-2 text-xs font-semibold">
        <span>Cost</span>
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
