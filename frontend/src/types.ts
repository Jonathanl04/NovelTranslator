export type Model = "deepseek-v4-flash" | "deepseek-v4-pro" | "mimo-v2.5" | "mimo-v2.5-pro";

export type Config = {
  has_api_key: boolean;
  api_key_mask: string;
  translation_model: Model;
  glossary_model: Model;
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
  cover_url: string | null;
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
  by_model: Record<Model, UsageBucket>;
};

export type BulkStatus = "pending" | "translating" | "done" | "failed";
export type BulkMode = "full" | "only";

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
  items: BulkItem[];
};
