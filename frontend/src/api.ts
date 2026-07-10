import type {
  BulkItem,
  BulkTranslationState,
  Chapter,
  ChapterDetail,
  CodexAuth,
  CodexModels,
  CodexRemainingUsage,
  Config,
  GlossaryEntry,
  NovelMetadata,
  OpenRouterProvider,
  QidianAuthState,
  ScrapeState,
  TranslationResult,
  Usage,
} from "./types";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  const data = text ? parseJsonResponse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || `Request failed: HTTP ${response.status}`);
  }
  return data as T;
}

function parseJsonResponse(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

export const api = {
  config: () => request<Config>("/api/config"),
  usage: () => request<Usage>("/api/usage"),
  resetUsage: () => request<Usage>("/api/usage", { method: "POST" }),
  saveConfig: (payload: {
    openrouter_api_key?: string;
    keep_existing_openrouter_key: boolean;
    translation_backend: Config["translation_backend"];
    glossary_backend: Config["glossary_backend"];
    codex_translation_model: string;
    codex_glossary_model: string;
    translation_model: string;
    translation_provider: string;
    glossary_model: string;
    glossary_provider: string;
    added_models: Config["added_models"];
  }) => request<Config>("/api/config", { method: "POST", body: JSON.stringify(payload) }),
  openrouterProviders: (model: string) =>
    request<OpenRouterProvider[]>(`/api/openrouter/providers?model=${encodeURIComponent(model)}`),
  codexAuth: () => request<CodexAuth>("/api/codex/auth"),
  codexLogin: () =>
    request<{ auth_url: string; status: "pending" }>("/api/codex/auth/login", { method: "POST" }),
  codexLogout: () => request<CodexAuth>("/api/codex/auth/logout", { method: "POST" }),
  codexModels: (refresh = false) =>
    request<CodexModels>(`/api/codex/models?refresh=${refresh}`),
  codexRemainingUsage: (refresh = false) =>
    request<CodexRemainingUsage>(`/api/codex/usage?refresh=${refresh}`),
  novels: () => request<string[]>("/api/novels"),
  novel: (novel: string) =>
    request<NovelMetadata>(`/api/novel?novel=${encodeURIComponent(novel)}`),
  deleteNovel: (novel: string) =>
    request<{ deleted: string }>(`/api/novel?novel=${encodeURIComponent(novel)}`, { method: "DELETE" }),
  chapters: (novel: string) =>
    request<Chapter[]>(`/api/chapters?novel=${encodeURIComponent(novel)}`),
  scrape: (payload: { url: string; start: number; end: number }) =>
    request<ScrapeState>("/api/scrape", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  scrapeState: () => request<ScrapeState>("/api/scrape"),
  chapter: (novel: string, file: string) =>
    request<ChapterDetail>(
      `/api/chapter?novel=${encodeURIComponent(novel)}&file=${encodeURIComponent(file)}`
    ),
  glossary: (novel: string) =>
    request<GlossaryEntry[]>(`/api/glossary?novel=${encodeURIComponent(novel)}`),
  exportEpubUrl: (novel: string) => `/api/export/epub?novel=${encodeURIComponent(novel)}`,
  saveGlossary: (novel: string, entries: GlossaryEntry[]) =>
    request<GlossaryEntry[]>("/api/glossary", {
      method: "POST",
      body: JSON.stringify({ novel, entries }),
    }),
  translate: (novel: string, file: string) =>
    request<TranslationResult>("/api/translate", {
      method: "POST",
      body: JSON.stringify({ novel, file }),
    }),
  translateOnly: (novel: string, file: string) =>
    request<TranslationResult>("/api/translate-only", {
      method: "POST",
      body: JSON.stringify({ novel, file }),
    }),
  bulkTranslation: (novel: string) =>
    request<BulkTranslationState>(`/api/bulk-translate?novel=${encodeURIComponent(novel)}`),
  startBulkTranslation: (novel: string, items: BulkItem[]) =>
    request<BulkTranslationState>("/api/bulk-translate", {
      method: "POST",
      body: JSON.stringify({ novel, items }),
    }),
  abortBulkTranslation: (novel: string) =>
    request<BulkTranslationState>("/api/bulk-translate/abort", {
      method: "POST",
      body: JSON.stringify({ novel }),
    }),
  qidianAuth: () => request<QidianAuthState>("/api/qidian-auth"),
  qidianSetCookies: (cookies: string) =>
    request<QidianAuthState>("/api/qidian-auth", {
      method: "POST",
      body: JSON.stringify({ action: "set_cookies", cookies }),
    }),
  qidianLogout: () =>
    request<QidianAuthState>("/api/qidian-auth", {
      method: "POST",
      body: JSON.stringify({ action: "logout" }),
    }),
};
