export type Model = "deepseek-v4-flash" | "deepseek-v4-pro";

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
