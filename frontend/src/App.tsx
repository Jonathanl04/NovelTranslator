import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  BookOpen,
  ClipboardList,
  Library,
  Moon,
  Settings as SettingsIcon,
  Sun,
  WandSparkles,
} from "lucide-react";
import { api } from "./api";
import type {
  BulkItem,
  BulkTranslationState,
  Chapter,
  Config,
  GlossaryEntry,
  NovelMetadata,
  QidianAuthState,
  ScrapeState,
  Usage,
} from "./types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { BooksPage } from "@/pages/BooksPage";
import { GlossaryPage } from "@/pages/GlossaryPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TranslatePage, type ReaderTab } from "@/pages/TranslatePage";
import { emptyUsageBucket } from "@/pages/shared";

const SELECTED_CHAPTER_STORAGE_KEY = "novel-translator:selected-chapter";
const SELECTED_NOVEL_STORAGE_KEY = "novel-translator:selected-novel";

type RoutePage = "library" | "workspace" | "glossary" | "settings";

const BOOKS_PER_PAGE = 12;

const emptyConfig: Config = {
  has_openrouter_api_key: false,
  openrouter_api_key_mask: "",
  translation_model: "deepseek/deepseek-v4-flash",
  translation_provider: "deepseek",
  glossary_model: "deepseek/deepseek-v4-flash",
  glossary_provider: "deepseek",
  favorite_models: [],
  model_presets: [
    { model: "deepseek/deepseek-v4-flash", provider: "deepseek" },
    { model: "deepseek/deepseek-v4-pro", provider: "deepseek" },
    { model: "xiaomi/mimo-v2.5", provider: "xiaomi" },
    { model: "xiaomi/mimo-v2.5-pro", provider: "xiaomi" },
  ],
};

const emptyUsage: Usage = {
  total: emptyUsageBucket,
  by_model: {},
};

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

export function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const page = routePage(location.pathname);
  const routeNovel = searchParams.get("book") || "";
  const routeChapter = searchParams.get("chapter") || "";
  const [config, setConfig] = useState<Config>(emptyConfig);
  const [openrouterApiKey, setOpenrouterApiKey] = useState("");
  const [novels, setNovels] = useState<string[]>([]);
  const [novelMetadata, setNovelMetadata] = useState<NovelMetadata | null>(null);
  const [novelMetadataByName, setNovelMetadataByName] = useState<Record<string, NovelMetadata>>({});
  const [novel, setNovel] = useState("");
  const effectiveRouteNovel =
    routeNovel || (page === "glossary" ? novel || localStorage.getItem(SELECTED_NOVEL_STORAGE_KEY) || "" : "");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [source, setSource] = useState("");
  const [translated, setTranslated] = useState("");
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [chapterSearch, setChapterSearch] = useState("");
  const [bookSearch, setBookSearch] = useState("");
  const [bookSort, setBookSort] = useState<"name" | "recent">("recent");
  const [bookPage, setBookPage] = useState(1);
  const [scrapeUrl, setScrapeUrl] = useState("");
  const [scrapeStart, setScrapeStart] = useState("1");
  const [scrapeEnd, setScrapeEnd] = useState("1");
  const [scrapeState, setScrapeState] = useState<ScrapeState>(emptyScrapeState);
  const [manualBusy, setManualBusy] = useState(false);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkAborted, setBulkAborted] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState(false);
  const [usage, setUsage] = useState<Usage>(emptyUsage);
  const [bulkItems, setBulkItems] = useState<BulkItem[]>([]);
  const [bulkSelection, setBulkSelection] = useState<Set<string>>(new Set());
  const [readerTab, setReaderTab] = useState<ReaderTab>("translated");
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("theme") === "dark");
  const [qidianAuth, setQidianAuth] = useState<QidianAuthState>({ logged_in: false });
  const previousBulkState = useRef<BulkTranslationState | null>(null);
  const handledScrapeResult = useRef("");
  const configRequestVersion = useRef(0);
  const busy = manualBusy || bulkRunning;
  const scrapeBusy = scrapeState.running;

  const selectedChapter = useMemo(
    () => chapters.find((chapter) => chapter.filename === selectedFile),
    [chapters, selectedFile]
  );
  const selectedChapterIndex = useMemo(
    () => chapters.findIndex((chapter) => chapter.filename === selectedFile),
    [chapters, selectedFile]
  );
  const previousChapter = selectedChapterIndex > 0 ? chapters[selectedChapterIndex - 1] : undefined;
  const nextChapter =
    selectedChapterIndex >= 0 && selectedChapterIndex < chapters.length - 1
      ? chapters[selectedChapterIndex + 1]
      : undefined;
  const untranslatedCount = useMemo(() => chapters.filter((chapter) => !chapter.translated).length, [chapters]);
  const selectedBulkChapters = useMemo(
    () => chapters.filter((chapter) => bulkSelection.has(chapter.filename)),
    [chapters, bulkSelection]
  );
  const visibleChapters = useMemo(() => {
    const query = chapterSearch.trim().toLocaleLowerCase();
    if (!query) return chapters;
    return chapters.filter((chapter) =>
      `${chapter.title} ${chapter.filename}`.toLocaleLowerCase().includes(query)
    );
  }, [chapters, chapterSearch]);
  const bulkCounts = useMemo(
    () => ({
      done: bulkItems.filter((item) => item.status === "done").length,
      failed: bulkItems.filter((item) => item.status === "failed").length,
      aborted: bulkItems.filter((item) => item.status === "aborted").length,
      pending: bulkItems.filter((item) => item.status === "pending").length,
      translating: bulkItems.filter((item) => item.status === "translating").length,
    }),
    [bulkItems]
  );
  const bulkQueueActive = !bulkAborted && (bulkRunning || bulkItems.some((item) => item.status === "pending" || item.status === "translating"));
  const bulkItemByFile = useMemo(() => {
    const map = new Map<string, BulkItem>();
    for (const item of bulkItems) {
      map.set(item.filename, item);
    }
    return map;
  }, [bulkItems]);
  const filteredNovels = useMemo(() => {
    const query = bookSearch.trim().toLocaleLowerCase();
    const matched = query
      ? novels.filter((name) =>
          `${name} ${novelMetadataByName[name]?.translated_name || ""}`.toLocaleLowerCase().includes(query)
        )
      : novels;
    if (bookSort === "recent") {
      return [...matched].sort(
        (a, b) => (novelMetadataByName[b]?.updated_at || 0) - (novelMetadataByName[a]?.updated_at || 0)
      );
    }
    return matched;
  }, [bookSearch, bookSort, novelMetadataByName, novels]);
  const bookPageCount = Math.max(1, Math.ceil(filteredNovels.length / BOOKS_PER_PAGE));
  const paginatedNovels = useMemo(() => {
    const start = (bookPage - 1) * BOOKS_PER_PAGE;
    return filteredNovels.slice(start, start + BOOKS_PER_PAGE);
  }, [bookPage, filteredNovels]);

  const showStatus = useCallback((message: string, isError = false) => {
    setStatus(message);
    setError(isError);
  }, []);

  const novelDisplayName = useCallback(
    (name: string) => novelMetadataByName[name]?.translated_name || name,
    [novelMetadataByName]
  );

  const loadNovelMetadata = useCallback(async (nextNovel: string) => {
    const metadata = await api.novel(nextNovel);
    setNovelMetadataByName((current) => ({ ...current, [nextNovel]: metadata }));
    return metadata;
  }, []);

  const loadGlossary = useCallback(async (nextNovel: string) => {
    if (!nextNovel) {
      setGlossary([]);
      return;
    }
    setGlossary(await api.glossary(nextNovel));
  }, []);

  const selectChapter = useCallback(
    async (nextNovel: string, filename: string) => {
      setSelectedFile(filename);
      localStorage.setItem(`${SELECTED_CHAPTER_STORAGE_KEY}:${nextNovel}`, filename);
      const chapter = await api.chapter(nextNovel, filename);
      setSource(chapter.source);
      setTranslated(chapter.translated);
      showStatus(chapter.translated_exists ? "Loaded existing translation." : "Loaded source chapter.");
    },
    [showStatus]
  );

  const loadBulkState = useCallback(async (nextNovel: string) => {
    if (!nextNovel) {
      setBulkItems([]);
      setBulkRunning(false);
      setBulkAborted(false);
      setBulkSelection(new Set());
      previousBulkState.current = null;
      return;
    }
    const state = await api.bulkTranslation(nextNovel);
    setBulkItems(state.items);
    setBulkRunning(state.running);
    setBulkAborted(state.aborted);
    setBulkSelection(
      new Set(
        state.items
          .filter((item) => item.status === "pending" || item.status === "translating")
          .filter((item) => item.mode !== "name")
          .map((item) => item.filename)
      )
    );
    previousBulkState.current = state;
    if (state.aborted) {
      showStatus("Bulk translation aborted.");
    } else if (state.running) {
      showStatus(describeBulkProgress(state));
    }
  }, [showStatus]);

  const loadChapters = useCallback(
    async (nextNovel: string) => {
      setNovel(nextNovel);
      if (nextNovel) {
        localStorage.setItem(SELECTED_NOVEL_STORAGE_KEY, nextNovel);
      }
      setSelectedFile("");
      setSource("");
      setTranslated("");
      setNovelMetadata(null);
      setChapterSearch("");
      setBulkSelection(new Set());
      await loadGlossary(nextNovel);
      await loadBulkState(nextNovel);
      if (!nextNovel) {
        setChapters([]);
        return [];
      }
      const nextChapters = await api.chapters(nextNovel);
      loadNovelMetadata(nextNovel)
        .then(setNovelMetadata)
        .catch(() => setNovelMetadata(null));
      setChapters(nextChapters);
      return nextChapters;
    },
    [loadBulkState, loadGlossary, loadNovelMetadata]
  );

  const chooseNovel = useCallback(
    async (nextNovel: string) => {
      const nextChapters = await loadChapters(nextNovel);
      const initialChapter = preferredChapter(nextNovel, nextChapters);
      navigate(translatePath(nextNovel, initialChapter?.filename));
    },
    [loadChapters, navigate]
  );

  async function runScrape() {
    if (scrapeBusy) return;
    const start = Number(scrapeStart);
    const end = Number(scrapeEnd);
    if (!scrapeUrl.trim() || !Number.isInteger(start) || !Number.isInteger(end)) {
      showStatus("Enter a URL and chapter range.", true);
      return;
    }
    handledScrapeResult.current = "";
    showStatus("Downloading source chapters...");
    try {
      setScrapeState(await api.scrape({ url: scrapeUrl.trim(), start, end }));
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  async function useSavedSourceUrl(novelName: string, sourceUrl: string) {
    setScrapeUrl(sourceUrl);
    navigate("/books");
    try {
      const novelChapters = await api.chapters(novelName);
      const lastChapter = novelChapters.reduce((max, chapter) => {
        const match = chapter.filename.match(/^(\d+)/);
        const number = match ? Number(match[1]) : 0;
        return number > max ? number : max;
      }, 0);
      const nextStart = lastChapter + 1;
      setScrapeStart(String(nextStart));
      setScrapeEnd(String(nextStart + 29));
      showStatus(`Source URL loaded. Ready to download chapters ${nextStart}-${nextStart + 29}.`);
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  useEffect(() => {
    if ((page !== "workspace" && page !== "glossary") || !effectiveRouteNovel || effectiveRouteNovel === novel) {
      return;
    }
    loadChapters(effectiveRouteNovel).catch((caught) => showStatus(errorMessage(caught), true));
  }, [effectiveRouteNovel, loadChapters, novel, page, showStatus]);

  useEffect(() => {
    if (page !== "workspace" || !routeNovel || routeNovel !== novel || chapters.length === 0) {
      return;
    }

    const requestedChapter = routeChapter || preferredChapter(novel, chapters)?.filename || "";
    const chapter = chapters.find((item) => item.filename === requestedChapter) || chapters[0];
    if (!chapter) {
      return;
    }

    if (routeChapter !== chapter.filename) {
      navigate(translatePath(novel, chapter.filename), { replace: true });
      return;
    }

    if (selectedFile !== chapter.filename) {
      selectChapter(novel, chapter.filename).catch((caught) => showStatus(errorMessage(caught), true));
    }
  }, [chapters, navigate, novel, page, routeChapter, routeNovel, selectChapter, selectedFile, showStatus]);

  useEffect(() => {
    let active = true;

    async function boot() {
      try {
        const [nextConfig, nextNovels, nextUsage, nextScrapeState, nextQidianAuth] = await Promise.all([
          api.config(),
          api.novels(),
          api.usage(),
          api.scrapeState(),
          api.qidianAuth(),
        ]);
        if (!active) return;
        setConfig(nextConfig);
        setNovels(nextNovels);
        setUsage(nextUsage);
        setScrapeState(nextScrapeState);
        setQidianAuth(nextQidianAuth);
        Promise.all(
          nextNovels.map(async (name) => {
            try {
              return [name, await api.novel(name)] as const;
            } catch {
              return null;
            }
          })
        ).then((entries) => {
          if (!active) return;
          setNovelMetadataByName(
            Object.fromEntries(entries.filter((entry): entry is readonly [string, NovelMetadata] => entry !== null))
          );
        });
      } catch (caught) {
        showStatus(errorMessage(caught), true);
      }
    }

    boot();
    return () => {
      active = false;
    };
  }, [showStatus]);

  useEffect(() => {
    if (!scrapeState.running) {
      return;
    }
    const interval = window.setInterval(() => {
      api.scrapeState().then(setScrapeState).catch((caught) => showStatus(errorMessage(caught), true));
    }, 800);
    return () => window.clearInterval(interval);
  }, [scrapeState.running, showStatus]);

  async function saveQidianCookies(cookieStr: string) {
    try {
      setQidianAuth(await api.qidianSetCookies(cookieStr));
      showStatus("Qidian cookies saved.");
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  async function logoutQidian() {
    try {
      setQidianAuth(await api.qidianLogout());
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  useEffect(() => {
    if (scrapeState.stage === "failed" && scrapeState.error) {
      showStatus(scrapeState.message || scrapeState.error, true);
      return;
    }
    if (scrapeState.stage !== "done" || !scrapeState.result) {
      return;
    }
    const key = `${scrapeState.result.novel}:${scrapeState.result.chapter_count}:${scrapeState.result.files.join("|")}`;
    if (handledScrapeResult.current === key) {
      return;
    }
    handledScrapeResult.current = key;
    async function refreshAfterScrape() {
      const result = scrapeState.result;
      if (!result) return;
      const nextNovels = await api.novels();
      setNovels(nextNovels);
      const metadata = await loadNovelMetadata(result.novel);
      setNovelMetadataByName((current) => ({ ...current, [result.novel]: metadata }));
      setBookSearch("");
      showStatus(`Downloaded ${result.chapter_count} ${result.chapter_count === 1 ? "chapter" : "chapters"} for ${result.novel}.`);
    }
    refreshAfterScrape().catch((caught) => showStatus(errorMessage(caught), true));
  }, [loadNovelMetadata, scrapeState, showStatus]);

  useEffect(() => {
    setBookPage(1);
  }, [bookSearch, bookSort]);

  useEffect(() => {
    setBookPage((current) => Math.min(current, bookPageCount));
  }, [bookPageCount]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    localStorage.setItem("theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  useEffect(() => {
    if (!novel || !bulkRunning) {
      return;
    }
    const interval = window.setInterval(() => {
      api
        .bulkTranslation(novel)
        .then(async (state) => {
          const previous = previousBulkState.current;
          previousBulkState.current = state;
          setBulkItems(state.items);
          setBulkRunning(state.running);
          setBulkAborted(state.aborted);
          setBulkSelection(
            new Set(
              state.items
                .filter((item) => item.status === "pending" || item.status === "translating")
                .filter((item) => item.mode !== "name")
                .map((item) => item.filename)
            )
          );
          if (state.running) {
            showStatus(describeBulkProgress(state));
          }

          const hasChanges =
            !previous || JSON.stringify(previous.items) !== JSON.stringify(state.items);
          const queueFinished = previous?.running && !state.running;
          if (!hasChanges && !queueFinished) {
            return;
          }

          const [nextChapters, nextUsage] = await Promise.all([api.chapters(novel), api.usage()]);
          setChapters(nextChapters);
          setUsage(nextUsage);
          if (state.items.some((item) => item.status === "done" || item.status === "failed")) {
            setGlossary(await api.glossary(novel));
          }
          if (state.items.some((item) => item.mode === "name" && item.status === "done")) {
            const metadata = await loadNovelMetadata(novel);
            setNovelMetadata(metadata);
          }

          if (selectedFile && state.items.some((item) => item.filename === selectedFile && item.status === "done")) {
            const chapter = await api.chapter(novel, selectedFile);
            setSource(chapter.source);
            setTranslated(chapter.translated);
          }

          if (queueFinished) {
            showStatus(
              state.aborted
                ? "Bulk translation aborted."
                : state.items.some((item) => item.status === "failed")
                  ? "Bulk translation stopped after a failure."
                  : "Bulk translation complete.",
              state.items.some((item) => item.status === "failed")
            );
          }
        })
        .catch((caught) => showStatus(errorMessage(caught), true));
    }, 1500);

    return () => window.clearInterval(interval);
  }, [bulkRunning, loadNovelMetadata, novel, selectedFile, showStatus]);

  async function saveConfig() {
    const requestVersion = ++configRequestVersion.current;
    try {
      const current = await api.config();
      const saved = await api.saveConfig({
        openrouter_api_key: openrouterApiKey.trim() || undefined,
        keep_existing_openrouter_key: !openrouterApiKey.trim() && current.has_openrouter_api_key,
        translation_model: config.translation_model,
        translation_provider: config.translation_provider,
        glossary_model: config.glossary_model,
        glossary_provider: config.glossary_provider,
        favorite_models: config.favorite_models,
      });
      if (requestVersion !== configRequestVersion.current) {
        return;
      }
      setConfig(saved);
      setOpenrouterApiKey("");
      showStatus("Settings saved.");
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  function updateConfig(patch: Partial<Config>) {
    setConfig((current) => ({ ...current, ...patch }));
  }

  async function runTranslate(mode: "full" | "only") {
    if (!novel || busy) return;
    // Translate the checked chapters, or fall back to the currently open chapter.
    const targets =
      selectedBulkChapters.length > 0
        ? selectedBulkChapters
        : selectedChapter
          ? [selectedChapter]
          : [];
    if (targets.length === 0) return;

    const queue = targets.map((chapter) => ({
      filename: chapter.filename,
      title: chapter.title,
      status: "pending" as const,
      mode,
    }));

    setBulkItems(queue);
    setManualBusy(true);
    showStatus(
      mode === "full"
        ? `Translating ${queue.length} ${queue.length === 1 ? "chapter" : "chapters"} with glossary...`
        : `Translating ${queue.length} ${queue.length === 1 ? "chapter" : "chapters"} with current glossary...`
    );

    try {
      const state = await api.startBulkTranslation(novel, queue);
      previousBulkState.current = state;
      setBulkItems(state.items);
      setBulkRunning(state.running);
      setBulkAborted(state.aborted);
      setBulkSelection(new Set(queue.map((item) => item.filename)));
      showStatus(describeBulkProgress(state));
      if (!state.running) {
        setBulkSelection(new Set());
      }
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    } finally {
      setManualBusy(false);
    }
  }

  async function abortBulkTranslation() {
    if (!novel || !bulkRunning) return;
    try {
      const state = await api.abortBulkTranslation(novel);
      previousBulkState.current = state;
      setBulkItems(state.items);
      setBulkRunning(state.running);
      setBulkAborted(state.aborted);
      setBulkSelection(
        new Set(
          state.items
            .filter((item) => item.status === "pending" || item.status === "translating")
            .filter((item) => item.mode !== "name")
            .map((item) => item.filename)
        )
      );
      showStatus("Bulk translation aborted.");

      const [nextChapters, nextUsage] = await Promise.all([api.chapters(novel), api.usage()]);
      setChapters(nextChapters);
      setUsage(nextUsage);
      if (state.items.some((item) => item.status === "done" || item.status === "failed" || item.status === "aborted")) {
        setGlossary(await api.glossary(novel));
      }
      if (selectedFile && state.items.some((item) => item.filename === selectedFile && item.status === "done")) {
        const chapter = await api.chapter(novel, selectedFile);
        setSource(chapter.source);
        setTranslated(chapter.translated);
      }
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  async function saveGlossary() {
    try {
      const saved = await api.saveGlossary(novel, cleanGlossary(glossary));
      setGlossary(saved);
      showStatus("Glossary saved.");
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  async function resetUsage() {
    try {
      setUsage(await api.resetUsage());
      showStatus("Token usage reset.");
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  function addGlossaryEntry() {
    setGlossary((current) => [
      ...current,
      { source_term: "", english_term: "", category: "", gender_or_pronoun: "" },
    ]);
  }

  function updateGlossaryEntry(index: number, patch: Partial<GlossaryEntry>) {
    setGlossary((current) =>
      current.map((entry, entryIndex) => (entryIndex === index ? { ...entry, ...patch } : entry))
    );
  }

  function removeGlossaryEntry(index: number) {
    setGlossary((current) => current.filter((_, entryIndex) => entryIndex !== index));
  }

  function toggleBulkChapter(filename: string, checked: boolean) {
    setBulkSelection((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(filename);
      } else {
        next.delete(filename);
      }
      return next;
    });
  }

  function selectUntranslated() {
    setBulkSelection(new Set(chapters.filter((chapter) => !chapter.translated).map((chapter) => chapter.filename)));
  }

  function selectFromCurrent() {
    const startIndex = chapters.findIndex((chapter) => chapter.filename === selectedFile);
    if (startIndex < 0) return;
    setBulkSelection(new Set(chapters.slice(startIndex).map((chapter) => chapter.filename)));
  }

  function goToChapter(filename?: string) {
    if (!novel || !filename) return;
    navigate(translatePath(novel, filename));
  }

  async function exportEpub() {
    if (!novel) return;
    try {
      showStatus("Preparing EPUB export...");
      const response = await fetch(api.exportEpubUrl(novel));
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "EPUB export failed");
      }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const filename = decodeContentDispositionFilename(disposition) || `${novel}.epub`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      showStatus(`Exported ${filename}.`);
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  if (!page) {
    return <Navigate to="/books" replace />;
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 grid h-14 grid-cols-[1fr_auto_1fr] items-center gap-4 border-b bg-background/95 px-5 pr-16 backdrop-blur max-[760px]:h-auto max-[760px]:grid-cols-1 max-[760px]:gap-3 max-[760px]:px-3 max-[760px]:py-3">
        <div className="flex items-center gap-2 max-[760px]:pr-14">
          <BookOpen className="size-5 text-teal-700" />
          <h1 className="text-base font-semibold">Novel Translator</h1>
        </div>
        <nav className="flex w-full min-w-0 items-center justify-center gap-1 rounded-lg bg-muted p-1">
          <Button
            type="button"
            size="sm"
            variant={page === "library" ? "secondary" : "ghost"}
            className={cn("relative", page === "library" && "after:absolute after:inset-x-2 after:-bottom-1 after:h-0.5 after:rounded-full after:bg-primary")}
            onClick={() => navigate("/books")}
          >
            <Library />
            Books
          </Button>
          <Button
            type="button"
            size="sm"
            variant={page === "workspace" ? "secondary" : "ghost"}
            className={cn("relative", page === "workspace" && "after:absolute after:inset-x-2 after:-bottom-1 after:h-0.5 after:rounded-full after:bg-primary")}
            onClick={() => navigate(novel ? translatePath(novel, selectedFile) : "/translate")}
          >
            <WandSparkles />
            Translate
          </Button>
          <Button
            type="button"
            size="sm"
            variant={page === "glossary" ? "secondary" : "ghost"}
            className={cn("relative", page === "glossary" && "after:absolute after:inset-x-2 after:-bottom-1 after:h-0.5 after:rounded-full after:bg-primary")}
            onClick={() => navigate(glossaryPath(novel))}
          >
            <ClipboardList />
            Glossary
          </Button>
          <Button
            type="button"
            size="sm"
            variant={page === "settings" ? "secondary" : "ghost"}
            className={cn("relative", page === "settings" && "after:absolute after:inset-x-2 after:-bottom-1 after:h-0.5 after:rounded-full after:bg-primary")}
            onClick={() => navigate("/settings")}
          >
            <SettingsIcon />
            Settings
          </Button>
        </nav>
        <div className={cn("min-w-0 truncate text-right text-sm text-muted-foreground max-[760px]:pr-14 max-[760px]:text-left", error && "text-destructive")}>
          {status || "Ready"}
        </div>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="absolute right-5 top-3 max-[760px]:right-3 max-[760px]:top-3"
          onClick={() => setDarkMode((current) => !current)}
          aria-label={darkMode ? "Use light mode" : "Use dark mode"}
          title={darkMode ? "Light mode" : "Dark mode"}
        >
          {darkMode ? <Sun /> : <Moon />}
        </Button>
      </header>

      {page === "library" ? (
        <BooksPage
          novels={paginatedNovels}
          allCount={novels.length}
          filteredCount={filteredNovels.length}
          metadataByName={novelMetadataByName}
          selectedNovel={novel}
          query={bookSearch}
          sort={bookSort}
          page={bookPage}
          pageCount={bookPageCount}
          scrapeUrl={scrapeUrl}
          scrapeStart={scrapeStart}
          scrapeEnd={scrapeEnd}
          scrapeState={scrapeState}
          onQueryChange={setBookSearch}
          onSortChange={setBookSort}
          onPageChange={setBookPage}
          onScrapeUrlChange={setScrapeUrl}
          onScrapeStartChange={setScrapeStart}
          onScrapeEndChange={setScrapeEnd}
          onScrape={runScrape}
          onUseSourceUrl={useSavedSourceUrl}
          onSelect={(name) => chooseNovel(name).catch((caught) => showStatus(errorMessage(caught), true))}
          qidianAuth={qidianAuth}
          onQidianSaveCookies={saveQidianCookies}
          onQidianLogout={logoutQidian}
        />
      ) : page === "workspace" ? (
        <TranslatePage
          displayName={novelDisplayName(novel)}
          metadata={novelMetadata}
          chapterCount={chapters.length}
          translatedCount={chapters.length - untranslatedCount}
          queuedCount={bulkSelection.size}
          canExport={Boolean(novel) && chapters.length > 0 && chapters.length !== untranslatedCount}
          busy={busy}
          bulkQueueActive={bulkQueueActive}
          chapters={chapters}
          visibleChapters={visibleChapters}
          search={chapterSearch}
          selectedFile={selectedFile}
          selection={bulkSelection}
          itemsByFile={bulkItemByFile}
          itemsTotal={bulkItems.length}
          counts={bulkCounts}
          untranslatedCount={untranslatedCount}
          selectedChapter={selectedChapter}
          selectedChapterIndex={selectedChapterIndex}
          previousChapter={previousChapter}
          nextChapter={nextChapter}
          readerTab={readerTab}
          source={source}
          translated={translated}
          onChooseBook={() => navigate("/books")}
          onExport={exportEpub}
          onSearchChange={setChapterSearch}
          onOpen={(filename) => navigate(translatePath(novel, filename))}
          onToggle={toggleBulkChapter}
          onSelectUntranslated={selectUntranslated}
          onSelectFromCurrent={selectFromCurrent}
          onClear={() => setBulkSelection(new Set())}
          onTranslate={runTranslate}
          onAbortBulk={abortBulkTranslation}
          onReaderTabChange={setReaderTab}
          onPrevious={() => goToChapter(previousChapter?.filename)}
          onNext={() => goToChapter(nextChapter?.filename)}
        />
      ) : page === "glossary" ? (
        <GlossaryPage
          glossary={glossary}
          novel={novel}
          onAdd={addGlossaryEntry}
          onRemove={removeGlossaryEntry}
          onSave={saveGlossary}
          onUpdate={updateGlossaryEntry}
        />
      ) : (
        <SettingsPage
          openrouterApiKey={openrouterApiKey}
          config={config}
          usage={usage}
          onOpenrouterApiKeyChange={setOpenrouterApiKey}
          onConfigChange={updateConfig}
          onSaveConfig={saveConfig}
          onResetUsage={resetUsage}
        />
      )}
    </div>
  );
}

function cleanGlossary(entries: GlossaryEntry[]) {
  return entries
    .map((entry) => ({
      source_term: entry.source_term.trim(),
      english_term: entry.english_term.trim(),
      category: entry.category.trim(),
      gender_or_pronoun: entry.gender_or_pronoun,
    }))
    .filter((entry) => entry.source_term && entry.english_term);
}

function routePage(pathname: string): RoutePage | null {
  if (pathname === "/" || pathname === "/books") {
    return pathname === "/" ? null : "library";
  }
  if (pathname === "/translate") {
    return "workspace";
  }
  if (pathname === "/glossary") {
    return "glossary";
  }
  if (pathname === "/settings") {
    return "settings";
  }
  return null;
}

function translatePath(book: string, chapter?: string) {
  const params = new URLSearchParams({ book });
  if (chapter) {
    params.set("chapter", chapter);
  }
  return `/translate?${params.toString()}`;
}

function glossaryPath(book?: string) {
  if (!book) {
    return "/glossary";
  }
  return `/glossary?${new URLSearchParams({ book }).toString()}`;
}

function preferredChapter(novel: string, chapters: Chapter[]) {
  const storedSelectedFile = localStorage.getItem(`${SELECTED_CHAPTER_STORAGE_KEY}:${novel}`) || "";
  return chapters.find((chapter) => chapter.filename === storedSelectedFile) || chapters[0];
}

function describeBulkProgress(state: BulkTranslationState) {
  const total = state.items.length;
  const done = state.items.filter((item) => item.status === "done").length;
  if (state.aborted) {
    return "Bulk translation aborted.";
  }
  const failed = state.items.find((item) => item.status === "failed");
  const active = state.items.find((item) => item.status === "translating");
  const pending = state.items.find((item) => item.status === "pending");

  if (failed) {
    return `${failed.title} failed: ${failed.message || "Translation failed."}`;
  }
  if (active) {
    return `${active.message || "Translating..."} ${active.title} (${done + 1}/${total})`;
  }
  if (pending) {
    return `Queued ${pending.title} (${done}/${total} done)`;
  }
  if (total === 1) {
    return `Translation complete: ${state.items[0]?.title || "chapter"}.`;
  }
  return `Bulk translation complete: ${done}/${total}.`;
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function decodeContentDispositionFilename(disposition: string) {
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    return decodeURIComponent(encoded);
  }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] || "";
}

