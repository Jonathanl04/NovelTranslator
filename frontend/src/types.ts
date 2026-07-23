export type AddedModel = {
  model: string;
  provider: string;
};

export type OpenRouterProvider = {
  provider: string;
  name: string;
};

export type LlmBackend = "openrouter" | "codex";
export type ReasoningEffort = "none" | "low" | "medium" | "high";
export type GlossaryStrategy = "full" | "rolling";

export type CodexAuth = {
  available: boolean;
  signed_in: boolean;
  status: "signed_out" | "pending" | "signed_in" | "error";
  account: { email: string; plan: string } | null;
  error: string;
};

export type CodexModel = {
  id: string;
  name: string;
  description: string;
  is_default: boolean;
};

export type CodexModels = {
  models: CodexModel[];
  fetched_at: number;
  stale: boolean;
  error: string;
};

export type CodexUsageWindow = {
  used_percent: number;
  remaining_percent: number;
  window_duration_mins: number | null;
  resets_at: number | null;
};

export type CodexRemainingUsage = {
  available: boolean;
  fetched_at: number;
  stale: boolean;
  error: string;
  plan: string | null;
  limit_name: string | null;
  primary: CodexUsageWindow | null;
  secondary: CodexUsageWindow | null;
  rate_limit_reached_type: string | null;
  credits: { balance: string | null; hasCredits: boolean; unlimited: boolean } | null;
  individual_limit: {
    limit: string;
    used: string;
    remainingPercent: number;
    resetsAt: number;
  } | null;
};

export type Config = {
  has_openrouter_api_key: boolean;
  openrouter_api_key_mask: string;
  translation_backend: LlmBackend;
  glossary_backend: LlmBackend;
  translation_reasoning_effort: ReasoningEffort;
  glossary_reasoning_effort: ReasoningEffort;
  codex_translation_model: string;
  codex_glossary_model: string;
  translation_model: string;
  translation_provider: string;
  glossary_model: string;
  glossary_provider: string;
  glossary_strategy: GlossaryStrategy;
  added_models: AddedModel[];
  model_presets: AddedModel[];
};

export type Chapter = {
  filename: string;
  title: string;
  translated: boolean;
  source_size: number;
  translated_size: number;
};

export type NovelMetadata = {
  name: string;
  translated_name: string;
  cover_url: string | null;
  source_url: string | null;
  updated_at: number;
};

export type LibraryMetadata = {
  novels: string[];
  metadata: Record<string, NovelMetadata>;
};

export type ChapterDetail = {
  filename: string;
  source: string;
  translated: string;
  translated_exists: boolean;
};

export type GlossaryEntry = {
  source_term: string;
  english_term: string;
  category: string;
  gender_or_pronoun: string;
};

export type TranslationResult = {
  filename: string;
  translated: string;
  output_path: string;
  glossary: GlossaryEntry[];
};

export type ScrapeResult = {
  novel: string;
  source_url: string;
  output_dir: string;
  chapter_count: number;
  files: string[];
};

export type ScrapeState = {
  running: boolean;
  stage: "idle" | "queued" | "fetching" | "downloading" | "done" | "failed";
  current: number;
  total: number;
  message: string;
  novel: string;
  result: ScrapeResult | null;
  error: string;
};

export type UsageBucket = {
  prompt_cache_hit_tokens: number;
  prompt_cache_miss_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  cost_usd: number;
};

export type Usage = {
  total: UsageBucket;
  by_model: Record<string, UsageBucket>;
};

export type BulkStatus = "pending" | "translating" | "done" | "failed" | "aborted";
export type BulkMode = "full" | "only" | "name";

export type BulkItem = {
  filename: string;
  title: string;
  status: BulkStatus;
  mode?: BulkMode;
  message?: string;
};

export type BulkTranslationState = {
  novel: string;
  running: boolean;
  aborted: boolean;
  items: BulkItem[];
};

export type QidianAuthState = {
  logged_in: boolean;
};
