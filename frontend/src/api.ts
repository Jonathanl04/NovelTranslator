import type {
  Chapter,
  ChapterDetail,
  Config,
  GlossaryEntry,
  Model,
  NovelMetadata,
  TranslationResult,
  Usage,
} from "./types";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data as T;
}

export const api = {
  config: () => request<Config>("/api/config"),
  usage: () => request<Usage>("/api/usage"),
  resetUsage: () => request<Usage>("/api/usage", { method: "POST" }),
  saveConfig: (payload: {
    api_key?: string;
    keep_existing_key: boolean;
    translation_model: Model;
    glossary_model: Model;
  }) => request<Config>("/api/config", { method: "POST", body: JSON.stringify(payload) }),
  novels: () => request<string[]>("/api/novels"),
  novel: (novel: string) =>
    request<NovelMetadata>(`/api/novel?novel=${encodeURIComponent(novel)}`),
  chapters: (novel: string) =>
    request<Chapter[]>(`/api/chapters?novel=${encodeURIComponent(novel)}`),
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
};
