import type { AppPage } from "@/components/AppHeader";
import type { Chapter, GlossaryEntry } from "@/types";

export const SELECTED_CHAPTER_STORAGE_KEY = "novel-translator:selected-chapter";
export const SELECTED_NOVEL_STORAGE_KEY = "novel-translator:selected-novel";

export function cleanGlossary(entries: GlossaryEntry[]) {
  return entries
    .map((entry) => ({
      source_term: entry.source_term.trim(),
      english_term: entry.english_term.trim(),
      category: entry.category.trim(),
      gender_or_pronoun: entry.gender_or_pronoun,
    }))
    .filter((entry) => entry.source_term && entry.english_term);
}

export function routePage(pathname: string): AppPage | null {
  if (pathname === "/" || pathname === "/books") return pathname === "/" ? null : "library";
  if (pathname === "/translate") return "workspace";
  if (pathname === "/glossary") return "glossary";
  if (pathname === "/settings") return "settings";
  return null;
}

export function translatePath(book: string, chapter?: string) {
  const params = new URLSearchParams({ book });
  if (chapter) params.set("chapter", chapter);
  return `/translate?${params.toString()}`;
}

export function glossaryPath(book?: string) {
  return book ? `/glossary?${new URLSearchParams({ book }).toString()}` : "/glossary";
}

export function preferredChapter(novel: string, chapters: Chapter[]) {
  const stored = localStorage.getItem(`${SELECTED_CHAPTER_STORAGE_KEY}:${novel}`) || "";
  return chapters.find((chapter) => chapter.filename === stored) || chapters[0];
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export function decodeContentDispositionFilename(disposition: string) {
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) return decodeURIComponent(encoded);
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] || "";
}
