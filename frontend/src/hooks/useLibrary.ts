import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { NavigateFunction } from "react-router-dom";
import { api } from "@/api";
import type { NovelMetadata, QidianAuthState, ScrapeState } from "@/types";
import { clearReadingProgress } from "@/appUtils";

const BOOKS_PER_PAGE = 12;

const emptyScrapeState: ScrapeState = {
  running: false,
  stage: "idle",
  current: 0,
  total: 0,
  message: "",
  novel: "",
  result: null,
  error: "",
};

type Options = {
  navigate: NavigateFunction;
  selectedNovel: string;
  onStatus: (message: string, isError?: boolean) => void;
  onDeleteSelected: () => void;
};

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export function useLibrary({ navigate, selectedNovel, onStatus, onDeleteSelected }: Options) {
  const [novels, setNovels] = useState<string[]>([]);
  const [metadataByName, setMetadataByName] = useState<Record<string, NovelMetadata>>({});
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"name" | "recent">("recent");
  const [page, setPage] = useState(1);
  const [scrapeUrl, setScrapeUrl] = useState("");
  const [scrapeStart, setScrapeStart] = useState("1");
  const [scrapeEnd, setScrapeEnd] = useState("1");
  const [scrapeState, setScrapeState] = useState<ScrapeState>(emptyScrapeState);
  const [qidianAuth, setQidianAuth] = useState<QidianAuthState>({ logged_in: false });
  const handledScrapeResult = useRef("");

  const displayName = useCallback(
    (name: string) => metadataByName[name]?.translated_name || name,
    [metadataByName]
  );

  const loadMetadata = useCallback(async (name: string) => {
    const metadata = await api.novel(name);
    setMetadataByName((current) => ({ ...current, [name]: metadata }));
    return metadata;
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([api.novels(), api.scrapeState(), api.qidianAuth()])
      .then(([nextNovels, nextScrapeState, nextQidianAuth]) => {
        if (!active) return;
        setNovels(nextNovels);
        setScrapeState(nextScrapeState);
        setQidianAuth(nextQidianAuth);
        return Promise.all(nextNovels.map(async (name) => {
          try { return [name, await api.novel(name)] as const; }
          catch { return null; }
        }));
      })
      .then((entries) => {
        if (!active || !entries) return;
        setMetadataByName(Object.fromEntries(
          entries.filter((entry): entry is [string, NovelMetadata] => entry !== null)
        ));
      })
      .catch((error) => onStatus(errorMessage(error), true));
    return () => { active = false; };
  }, [onStatus]);

  useEffect(() => {
    if (!scrapeState.running) return;
    const interval = window.setInterval(() => {
      api.scrapeState().then(setScrapeState).catch((error) => onStatus(errorMessage(error), true));
    }, 800);
    return () => window.clearInterval(interval);
  }, [onStatus, scrapeState.running]);

  useEffect(() => {
    if (scrapeState.stage === "failed" && scrapeState.error) {
      onStatus(scrapeState.message || scrapeState.error, true);
      return;
    }
    const result = scrapeState.result;
    if (scrapeState.stage !== "done" || !result) return;
    const key = `${result.novel}:${result.chapter_count}:${result.files.join("|")}`;
    if (handledScrapeResult.current === key) return;
    handledScrapeResult.current = key;
    Promise.all([api.novels(), loadMetadata(result.novel)])
      .then(([nextNovels]) => {
        setNovels(nextNovels);
        setQuery("");
        onStatus(`Downloaded ${result.chapter_count} ${result.chapter_count === 1 ? "chapter" : "chapters"} for ${result.novel}.`);
      })
      .catch((error) => onStatus(errorMessage(error), true));
  }, [loadMetadata, onStatus, scrapeState]);

  useEffect(() => setPage(1), [query, sort]);

  const filteredNovels = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const matched = normalized
      ? novels.filter((name) => `${name} ${metadataByName[name]?.translated_name || ""}`.toLocaleLowerCase().includes(normalized))
      : novels;
    return sort === "recent"
      ? [...matched].sort((a, b) => (metadataByName[b]?.updated_at || 0) - (metadataByName[a]?.updated_at || 0))
      : matched;
  }, [metadataByName, novels, query, sort]);
  const pageCount = Math.max(1, Math.ceil(filteredNovels.length / BOOKS_PER_PAGE));
  useEffect(() => setPage((current) => Math.min(current, pageCount)), [pageCount]);
  const visibleNovels = useMemo(() => {
    const start = (page - 1) * BOOKS_PER_PAGE;
    return filteredNovels.slice(start, start + BOOKS_PER_PAGE);
  }, [filteredNovels, page]);

  async function runScrape() {
    if (scrapeState.running) return;
    const start = Number(scrapeStart);
    const end = Number(scrapeEnd);
    if (!scrapeUrl.trim() || !Number.isInteger(start) || !Number.isInteger(end)) {
      onStatus("Enter a URL and chapter range.", true);
      return;
    }
    handledScrapeResult.current = "";
    onStatus("Downloading source chapters...");
    try { setScrapeState(await api.scrape({ url: scrapeUrl.trim(), start, end })); }
    catch (error) { onStatus(errorMessage(error), true); }
  }

  async function useSourceUrl(name: string, sourceUrl: string) {
    setScrapeUrl(sourceUrl);
    navigate("/books");
    try {
      const chapters = await api.chapters(name);
      const last = chapters.reduce((max, chapter) => Math.max(max, Number(chapter.filename.match(/^(\d+)/)?.[1] || 0)), 0);
      setScrapeStart(String(last + 1));
      setScrapeEnd(String(last + 30));
      onStatus(`Source URL loaded. Ready to download chapters ${last + 1}-${last + 30}.`);
    } catch (error) { onStatus(errorMessage(error), true); }
  }

  async function saveQidianCookies(cookies: string) {
    try { setQidianAuth(await api.qidianSetCookies(cookies)); onStatus("Qidian cookies saved."); }
    catch (error) { onStatus(errorMessage(error), true); }
  }

  async function logoutQidian() {
    try { setQidianAuth(await api.qidianLogout()); }
    catch (error) { onStatus(errorMessage(error), true); }
  }

  async function deleteBook(name: string) {
    if (!window.confirm(`Delete "${displayName(name)}" and all local files for this book?`)) return;
    try {
      await api.deleteNovel(name);
      clearReadingProgress(name);
      setNovels(await api.novels());
      setMetadataByName((current) => {
        const next = { ...current };
        delete next[name];
        return next;
      });
      if (name === selectedNovel) onDeleteSelected();
      onStatus(`Deleted ${displayName(name)}.`);
    } catch (error) { onStatus(errorMessage(error), true); }
  }

  return {
    allCount: novels.length, deleteBook, displayName, filteredCount: filteredNovels.length,
    loadMetadata, logoutQidian, metadataByName, page, pageCount, qidianAuth, query, runScrape,
    saveQidianCookies, scrapeEnd, scrapeStart, scrapeState, scrapeUrl, setPage, setQuery,
    setScrapeEnd, setScrapeStart, setScrapeUrl, setSort, sort, useSourceUrl, visibleNovels,
  };
}
