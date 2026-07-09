export type FavoriteModel = {
  model: string;
  provider: string;
};

export type OpenRouterProvider = {
  provider: string;
  name: string;
};

export type Config = {
  has_openrouter_api_key: boolean;
  openrouter_api_key_mask: string;
  translation_model: string;
  translation_provider: string;
  glossary_model: string;
  glossary_provider: string;
  favorite_models: FavoriteModel[];
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
