import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Download,
  Eraser,
  Library,
  Link,
  Search,
  Moon,
  Plus,
  Save,
  Settings,
  Sun,
  Trash2,
  WandSparkles,
} from "lucide-react";
import { api } from "./api";
import type {
  BulkItem,
  BulkTranslationState,
  Chapter,
  Config,
  GlossaryEntry,
  Model,
  NovelMetadata,
  ScrapeState,
  Usage,
  UsageBucket,
} from "./types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const MODELS: Model[] = ["deepseek-v4-flash", "deepseek-v4-pro", "mimo-v2.5", "mimo-v2.5-pro"];
const PRONOUNS = ["__none__", "male", "female", "unknown", "it"];
const SELECTED_CHAPTER_STORAGE_KEY = "novel-translator:selected-chapter";

type Page = "library" | "workspace" | "glossary";
type ReaderTab = "raw" | "translated";
const BOOKS_PER_PAGE = 12;
const GLOSSARY_ENTRIES_PER_PAGE = 20;

const emptyConfig: Config = {
  has_api_key: false,
  api_key_mask: "",
  translation_model: "deepseek-v4-flash",
  glossary_model: "deepseek-v4-flash",
};

const emptyUsageBucket: UsageBucket = {
  prompt_cache_hit_tokens: 0,
  prompt_cache_miss_tokens: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
  cost_usd: 0,
};

const emptyUsage: Usage = {
  total: emptyUsageBucket,
  by_model: {
    "deepseek-v4-flash": emptyUsageBucket,
    "deepseek-v4-pro": emptyUsageBucket,
    "mimo-v2.5": emptyUsageBucket,
    "mimo-v2.5-pro": emptyUsageBucket,
  },
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
  const [page, setPage] = useState<Page>("library");
  const [config, setConfig] = useState<Config>(emptyConfig);
  const [apiKey, setApiKey] = useState("");
  const [novels, setNovels] = useState<string[]>([]);
  const [novelMetadata, setNovelMetadata] = useState<NovelMetadata | null>(null);
  const [novelMetadataByName, setNovelMetadataByName] = useState<Record<string, NovelMetadata>>({});
  const [novel, setNovel] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [source, setSource] = useState("");
  const [translated, setTranslated] = useState("");
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [chapterSearch, setChapterSearch] = useState("");
  const [bookSearch, setBookSearch] = useState("");
  const [bookPage, setBookPage] = useState(1);
  const [scrapeUrl, setScrapeUrl] = useState("");
  const [scrapeStart, setScrapeStart] = useState("1");
  const [scrapeEnd, setScrapeEnd] = useState("1");
  const [scrapeState, setScrapeState] = useState<ScrapeState>(emptyScrapeState);
  const [manualBusy, setManualBusy] = useState(false);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState(false);
  const [usage, setUsage] = useState<Usage>(emptyUsage);
  const [bulkItems, setBulkItems] = useState<BulkItem[]>([]);
  const [bulkSelection, setBulkSelection] = useState<Set<string>>(new Set());
  const [readerTab, setReaderTab] = useState<ReaderTab>("translated");
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("theme") === "dark");
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
      pending: bulkItems.filter((item) => item.status === "pending").length,
      translating: bulkItems.filter((item) => item.status === "translating").length,
    }),
    [bulkItems]
  );
  const filteredNovels = useMemo(() => {
    const query = bookSearch.trim().toLocaleLowerCase();
    if (!query) return novels;
    return novels.filter((name) =>
      `${name} ${novelMetadataByName[name]?.translated_name || ""}`.toLocaleLowerCase().includes(query)
    );
  }, [bookSearch, novelMetadataByName, novels]);
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
      setBulkSelection(new Set());
      previousBulkState.current = null;
      return;
    }
    const state = await api.bulkTranslation(nextNovel);
    setBulkItems(state.items);
    setBulkRunning(state.running);
    setBulkSelection(
      new Set(
        state.items
          .filter((item) => item.status === "pending" || item.status === "translating")
          .filter((item) => item.mode !== "name")
          .map((item) => item.filename)
      )
    );
    previousBulkState.current = state;
    if (state.running) {
      showStatus(describeBulkProgress(state));
    }
  }, [showStatus]);

  const loadChapters = useCallback(
    async (nextNovel: string) => {
      setNovel(nextNovel);
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
        return;
      }
      const nextChapters = await api.chapters(nextNovel);
      loadNovelMetadata(nextNovel)
        .then(setNovelMetadata)
        .catch(() => setNovelMetadata(null));
      setChapters(nextChapters);
      const storedSelectedFile = localStorage.getItem(`${SELECTED_CHAPTER_STORAGE_KEY}:${nextNovel}`) || "";
      const initialChapter =
        nextChapters.find((chapter) => chapter.filename === storedSelectedFile) || nextChapters[0];
      if (initialChapter) {
        await selectChapter(nextNovel, initialChapter.filename);
      }
    },
    [loadBulkState, loadGlossary, loadNovelMetadata, selectChapter]
  );

  const chooseNovel = useCallback(
    async (nextNovel: string) => {
      await loadChapters(nextNovel);
      setPage("workspace");
    },
    [loadChapters]
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
    setPage("library");
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
    let active = true;

    async function boot() {
      try {
        const [nextConfig, nextNovels, nextUsage, nextScrapeState] = await Promise.all([
          api.config(),
          api.novels(),
          api.usage(),
          api.scrapeState(),
        ]);
        if (!active) return;
        setConfig(nextConfig);
        setNovels(nextNovels);
        setUsage(nextUsage);
        setScrapeState(nextScrapeState);
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
  }, [bookSearch]);

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
              state.items.some((item) => item.status === "failed")
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
        api_key: apiKey.trim() || undefined,
        keep_existing_key: !apiKey.trim() && current.has_api_key,
        translation_model: config.translation_model,
        glossary_model: config.glossary_model,
      });
      if (requestVersion !== configRequestVersion.current) {
        return;
      }
      setConfig(saved);
      setApiKey("");
      showStatus("Config saved.");
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  function updateConfigModels(patch: Partial<Pick<Config, "translation_model" | "glossary_model">>) {
    const previous = {
      translation_model: config.translation_model,
      glossary_model: config.glossary_model,
    };
    const nextConfig = { ...config, ...patch };
    const requestVersion = ++configRequestVersion.current;
    setConfig(nextConfig);
    void api
      .saveConfig({
        keep_existing_key: true,
        translation_model: nextConfig.translation_model,
        glossary_model: nextConfig.glossary_model,
      })
      .then((saved) => {
        if (requestVersion !== configRequestVersion.current) {
          return;
        }
        setConfig((current) => ({ ...current, ...saved }));
        showStatus("Model saved.");
      })
      .catch((caught) => {
        if (requestVersion !== configRequestVersion.current) {
          return;
        }
        setConfig((current) => ({ ...current, ...previous }));
        showStatus(errorMessage(caught), true);
      });
  }

  async function runTranslation(mode: "full" | "only") {
    if (!novel || !selectedFile || busy) return;
    const chapter = chapters.find((item) => item.filename === selectedFile);
    if (!chapter) return;
    setManualBusy(true);
    const queue = [
      {
        filename: chapter.filename,
        title: chapter.title,
        status: "pending" as const,
        mode,
      },
    ];
    showStatus(mode === "full" ? "Populating glossary and translating..." : "Translating with current glossary...");
    try {
      const state = await api.startBulkTranslation(novel, queue);
      previousBulkState.current = state;
      setBulkItems(state.items);
      setBulkRunning(state.running);
      setBulkSelection(new Set(queue.map((item) => item.filename)));
      showStatus(describeBulkProgress(state));
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    } finally {
      setManualBusy(false);
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

  async function runBulkTranslation(mode: "full" | "only") {
    if (!novel || busy || selectedBulkChapters.length === 0) return;

    const queue = selectedBulkChapters.map((chapter) => ({
      filename: chapter.filename,
      title: chapter.title,
      status: "pending" as const,
      mode,
    }));

    setBulkItems(queue);
    setManualBusy(true);
    showStatus(
      mode === "full"
        ? `Bulk translating ${queue.length} selected ${queue.length === 1 ? "chapter" : "chapters"} with glossary...`
        : `Bulk translating ${queue.length} selected ${queue.length === 1 ? "chapter" : "chapters"} with current glossary...`
    );

    try {
      const state = await api.startBulkTranslation(novel, queue);
      previousBulkState.current = state;
      setBulkItems(state.items);
      setBulkRunning(state.running);
      setBulkSelection(new Set(queue.map((item) => item.filename)));
      showStatus(describeBulkProgress(state));
      if (!state.running) {
        setBulkSelection(new Set());
      }
    } finally {
      setManualBusy(false);
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
    selectChapter(novel, filename).catch((caught) => showStatus(errorMessage(caught), true));
  }

  async function exportEpub() {
    if (!novel || busy) return;
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

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 grid h-14 grid-cols-[1fr_auto_1fr] items-center gap-4 border-b bg-background/95 px-5 pr-16 backdrop-blur max-[760px]:grid-cols-1 max-[760px]:h-auto max-[760px]:gap-3 max-[760px]:py-3">
        <div className="flex items-center gap-2">
          <BookOpen className="size-5 text-teal-700" />
          <h1 className="text-base font-semibold">Novel Translator</h1>
        </div>
        <nav className="flex items-center justify-center gap-1 rounded-lg bg-muted p-1">
          <Button
            type="button"
            size="sm"
            variant={page === "library" ? "secondary" : "ghost"}
            className={cn("relative", page === "library" && "after:absolute after:inset-x-2 after:-bottom-1 after:h-0.5 after:rounded-full after:bg-primary")}
            onClick={() => setPage("library")}
          >
            <Library />
            Books
          </Button>
          <Button
            type="button"
            size="sm"
            variant={page === "workspace" ? "secondary" : "ghost"}
            className={cn("relative", page === "workspace" && "after:absolute after:inset-x-2 after:-bottom-1 after:h-0.5 after:rounded-full after:bg-primary")}
            onClick={() => setPage("workspace")}
          >
            <WandSparkles />
            Translate
          </Button>
          <Button
            type="button"
            size="sm"
            variant={page === "glossary" ? "secondary" : "ghost"}
            className={cn("relative", page === "glossary" && "after:absolute after:inset-x-2 after:-bottom-1 after:h-0.5 after:rounded-full after:bg-primary")}
            onClick={() => setPage("glossary")}
          >
            <ClipboardList />
            Glossary
          </Button>
        </nav>
        <div className={cn("min-w-0 truncate text-right text-sm text-muted-foreground max-[760px]:text-left", error && "text-destructive")}>
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
        <BookLibraryPage
          novels={paginatedNovels}
          allCount={novels.length}
          filteredCount={filteredNovels.length}
          metadataByName={novelMetadataByName}
          selectedNovel={novel}
          query={bookSearch}
          page={bookPage}
          pageCount={bookPageCount}
          scrapeUrl={scrapeUrl}
          scrapeStart={scrapeStart}
          scrapeEnd={scrapeEnd}
          scrapeState={scrapeState}
          onQueryChange={setBookSearch}
          onPageChange={setBookPage}
          onScrapeUrlChange={setScrapeUrl}
          onScrapeStartChange={setScrapeStart}
          onScrapeEndChange={setScrapeEnd}
          onScrape={runScrape}
          onUseSourceUrl={useSavedSourceUrl}
          onSelect={(name) => chooseNovel(name).catch((caught) => showStatus(errorMessage(caught), true))}
        />
      ) : page === "workspace" ? (
        <main className="grid min-h-[calc(100vh-3.5rem)] grid-cols-[320px_minmax(0,1fr)] max-[980px]:grid-cols-1">
          <aside className="sticky top-14 grid h-[calc(100vh-3.5rem)] min-w-0 grid-rows-[auto_minmax(0,1fr)] gap-4 overflow-hidden border-r bg-muted/20 p-4 max-[980px]:static max-[980px]:h-auto max-[980px]:overflow-visible max-[980px]:border-r-0 max-[980px]:border-b">
            <section className="grid gap-3">
              <NovelCover novel={novel} metadata={novelMetadata} />
              <Button type="button" variant="outline" onClick={() => setPage("library")}>
                <Library />
                Choose Book
              </Button>
              <div className="grid grid-cols-3 gap-2 rounded-lg border bg-background p-3 text-center text-xs">
                <Metric label="Chapters" value={chapters.length} />
                <Metric label="Translated" value={chapters.length - untranslatedCount} />
                <Metric label="Queued" value={bulkSelection.size} />
              </div>
              <Button type="button" variant="outline" disabled={!novel || busy || chapters.length === untranslatedCount} onClick={exportEpub}>
                <Download />
                Export EPUB
              </Button>
            </section>

            <section className="grid min-h-0 grid-rows-[auto_auto_minmax(0,1fr)] gap-2">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">Chapters</h2>
                <Badge variant="outline">{untranslatedCount} new</Badge>
              </div>
              <Input
                type="search"
                value={chapterSearch}
                placeholder="Search chapters..."
                className="bg-background"
                onChange={(event) => setChapterSearch(event.target.value)}
              />
              <ScrollArea className="h-full rounded-lg border bg-background pr-2 max-[980px]:h-72">
                <div className="grid gap-1.5 p-2">
                  {visibleChapters.map((chapter) => (
                    <button
                      key={chapter.filename}
                      type="button"
                      className={cn(
                        "grid min-h-11 w-full grid-cols-[1fr_auto] items-center gap-2 rounded-md border px-2.5 py-2 text-left text-sm transition-colors hover:bg-muted",
                        selectedFile === chapter.filename &&
                          "border-teal-700 bg-teal-50/70 dark:border-teal-400 dark:bg-teal-950/40"
                      )}
                      onClick={() => selectChapter(novel, chapter.filename).catch((caught) => showStatus(errorMessage(caught), true))}
                    >
                      <span className="min-w-0 [overflow-wrap:anywhere] font-medium leading-tight">{chapter.title}</span>
                      <Badge variant={chapter.translated ? "secondary" : "outline"} className={chapter.translated ? "bg-teal-50 text-teal-800" : ""}>
                        {chapter.translated ? "done" : "new"}
                      </Badge>
                    </button>
                  ))}
                  {!visibleChapters.length && (
                    <div className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
                      No chapters match your search.
                    </div>
                  )}
                </div>
              </ScrollArea>
            </section>
          </aside>

          <section className="grid min-w-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] gap-4 p-4 pb-0">
            <section className="grid gap-3 rounded-lg border bg-card p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold">{selectedChapter?.title || "Select a chapter"}</h2>
                  <div className="text-xs text-muted-foreground">
                    {selectedChapter ? `${formatInteger(selectedChapter.source_size)} source chars` : "Choose a chapter to preview and translate."}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" disabled={busy || !selectedFile} onClick={() => runTranslation("only")}>
                    <Check />
                    Translate Only
                  </Button>
                  <Button type="button" disabled={busy || !selectedFile} onClick={() => runTranslation("full")}>
                    <WandSparkles />
                    Translate + Glossary
                  </Button>
                </div>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                <ModelSelect
                  id="glossary-model"
                  label="Glossary model"
                  value={config.glossary_model}
                  onChange={(glossary_model) => updateConfigModels({ glossary_model })}
                />
                <ModelSelect
                  id="translation-model"
                  label="Translation model"
                  value={config.translation_model}
                  onChange={(translation_model) => updateConfigModels({ translation_model })}
                />
              </div>
            </section>

            <BulkPanel
              busy={busy}
              chapters={chapters}
              selectedFile={selectedFile}
              selectedCount={bulkSelection.size}
              selected={bulkSelection}
              items={bulkItems}
              counts={bulkCounts}
              onToggle={toggleBulkChapter}
              onSelectUntranslated={selectUntranslated}
              onSelectFromCurrent={selectFromCurrent}
              onClear={() => setBulkSelection(new Set())}
              onRun={runBulkTranslation}
            />

            <ReaderPanel
              tab={readerTab}
              source={source}
              translated={translated}
              onTabChange={setReaderTab}
            />

            <ChapterNavigation
              currentIndex={selectedChapterIndex}
              total={chapters.length}
              previousChapter={previousChapter}
              nextChapter={nextChapter}
              onPrevious={() => goToChapter(previousChapter?.filename)}
              onNext={() => goToChapter(nextChapter?.filename)}
            />
          </section>
        </main>
      ) : (
        <GlossaryPage
          apiKey={apiKey}
          config={config}
          glossary={glossary}
          novel={novel}
          usage={usage}
          onApiKeyChange={setApiKey}
          onConfigChange={updateConfigModels}
          onSaveConfig={saveConfig}
          onResetUsage={resetUsage}
          onAdd={addGlossaryEntry}
          onRemove={removeGlossaryEntry}
          onSave={saveGlossary}
          onUpdate={updateGlossaryEntry}
        />
      )}
    </div>
  );
}

function BookLibraryPage({
  novels,
  allCount,
  filteredCount,
  metadataByName,
  selectedNovel,
  query,
  page,
  pageCount,
  scrapeUrl,
  scrapeStart,
  scrapeEnd,
  scrapeState,
  onQueryChange,
  onPageChange,
  onScrapeUrlChange,
  onScrapeStartChange,
  onScrapeEndChange,
  onScrape,
  onUseSourceUrl,
  onSelect,
}: {
  novels: string[];
  allCount: number;
  filteredCount: number;
  metadataByName: Record<string, NovelMetadata>;
  selectedNovel: string;
  query: string;
  page: number;
  pageCount: number;
  scrapeUrl: string;
  scrapeStart: string;
  scrapeEnd: string;
  scrapeState: ScrapeState;
  onQueryChange: (value: string) => void;
  onPageChange: (page: number) => void;
  onScrapeUrlChange: (value: string) => void;
  onScrapeStartChange: (value: string) => void;
  onScrapeEndChange: (value: string) => void;
  onScrape: () => void;
  onUseSourceUrl: (novelName: string, sourceUrl: string) => void;
  onSelect: (novel: string) => void;
}) {
  const scrapeBusy = scrapeState.running;
  const progressValue =
    scrapeState.total > 0 ? Math.min(100, Math.round((scrapeState.current / scrapeState.total) * 100)) : 0;

  return (
    <main className="min-h-[calc(100vh-3.5rem)] bg-muted/20">
      <section className="mx-auto grid w-full max-w-7xl gap-4 p-4">
        <section className="grid gap-3 rounded-lg border bg-background p-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid min-w-64 flex-1 gap-1.5">
              <Label htmlFor="scrape-url">Source URL</Label>
              <Input
                id="scrape-url"
                type="url"
                value={scrapeUrl}
                placeholder="https://www.69shuba.com/book/77582.htm"
                onChange={(event) => onScrapeUrlChange(event.target.value)}
              />
            </div>
            <div className="grid w-28 gap-1.5">
              <Label htmlFor="scrape-start">Start</Label>
              <Input
                id="scrape-start"
                type="number"
                min={1}
                value={scrapeStart}
                onChange={(event) => onScrapeStartChange(event.target.value)}
              />
            </div>
            <div className="grid w-28 gap-1.5">
              <Label htmlFor="scrape-end">End</Label>
              <Input
                id="scrape-end"
                type="number"
                min={1}
                value={scrapeEnd}
                onChange={(event) => onScrapeEndChange(event.target.value)}
              />
            </div>
            <Button type="button" className="min-w-32" disabled={scrapeBusy} onClick={onScrape}>
              <Download />
              {scrapeBusy ? "Downloading" : "Download"}
            </Button>
          </div>
          {(scrapeBusy || scrapeState.stage === "done" || scrapeState.stage === "failed") && (
            <div className="grid gap-1">
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className={cn(
                    "h-full rounded-full transition-all",
                    scrapeState.stage === "failed" ? "bg-destructive" : "bg-teal-700"
                  )}
                  style={{ width: `${scrapeState.total > 0 ? progressValue : scrapeBusy ? 12 : 100}%` }}
                />
              </div>
              <div className={cn("text-xs text-muted-foreground", scrapeState.stage === "failed" && "text-destructive")}>
                {scrapeState.total > 0
                  ? `${formatInteger(scrapeState.current)} of ${formatInteger(scrapeState.total)} chapters · ${scrapeState.message || scrapeState.stage}`
                  : scrapeState.message || scrapeState.stage}
              </div>
            </div>
          )}
        </section>

        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <h2 className="text-xl font-semibold">Books</h2>
            <div className="text-sm text-muted-foreground">
              {formatInteger(filteredCount)} of {formatInteger(allCount)} books
            </div>
          </div>
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              value={query}
              placeholder="Search books..."
              className="bg-background pl-9"
              onChange={(event) => onQueryChange(event.target.value)}
            />
          </div>
        </div>

        {novels.length ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
            {novels.map((name) => (
              <BookCard
                key={name}
                name={name}
                metadata={metadataByName[name]}
                selected={name === selectedNovel}
                onSelect={() => onSelect(name)}
                onUseSourceUrl={metadataByName[name]?.source_url ? () => onUseSourceUrl(name, metadataByName[name].source_url || "") : undefined}
              />
            ))}
          </div>
        ) : (
          <div className="grid min-h-72 place-items-center rounded-lg border border-dashed bg-background p-6 text-center text-sm text-muted-foreground">
            No books match your search.
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-background p-3">
          <div className="text-sm text-muted-foreground">
            Page {formatInteger(page)} of {formatInteger(pageCount)}
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(Math.max(1, page - 1))}
            >
              <ChevronLeft />
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= pageCount}
              onClick={() => onPageChange(Math.min(pageCount, page + 1))}
            >
              Next
              <ChevronRight />
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}

function BookCard({
  name,
  metadata,
  selected,
  onSelect,
  onUseSourceUrl,
}: {
  name: string;
  metadata?: NovelMetadata;
  selected: boolean;
  onSelect: () => void;
  onUseSourceUrl?: () => void;
}) {
  const displayName = metadata?.translated_name || name;
  return (
    <div
      className={cn(
        "group grid min-w-0 gap-2 rounded-lg border bg-background p-2 text-left transition-colors hover:border-teal-700 hover:bg-teal-50/40 dark:hover:border-teal-400 dark:hover:bg-teal-950/20",
        selected && "border-teal-700 bg-teal-50/70 dark:border-teal-400 dark:bg-teal-950/40"
      )}
    >
      <button type="button" className="grid min-w-0 gap-2 text-left" onClick={onSelect}>
        <div className="aspect-[7/9] overflow-hidden rounded-md border bg-muted">
          {metadata?.cover_url ? (
            <img src={metadata.cover_url} alt={`${displayName} cover`} className="h-full w-full object-cover" />
          ) : (
            <div className="grid h-full place-items-center text-muted-foreground">
              <BookOpen className="size-10" />
            </div>
          )}
        </div>
        <div className="grid min-w-0 gap-1">
          <div className="line-clamp-2 min-h-10 [overflow-wrap:anywhere] text-sm font-semibold leading-tight">
            {displayName}
          </div>
          {displayName !== name && <div className="truncate text-xs text-muted-foreground">{name}</div>}
        </div>
      </button>
      {onUseSourceUrl && (
        <Button type="button" variant="outline" size="sm" onClick={onUseSourceUrl}>
          <Link />
          Use Link
        </Button>
      )}
    </div>
  );
}

function NovelCover({ novel, metadata }: { novel: string; metadata: NovelMetadata | null }) {
  const displayName = metadata?.translated_name || novel;
  if (!novel || !metadata?.cover_url) {
    return null;
  }

  return (
    <div className="grid grid-cols-[72px_minmax(0,1fr)] items-center gap-3 rounded-lg border bg-background p-2">
      <img
        src={metadata.cover_url}
        alt={`${displayName} cover`}
        className="aspect-[7/9] h-24 w-[72px] rounded-md object-cover"
      />
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold">{displayName}</div>
      </div>
    </div>
  );
}

function BulkPanel({
  busy,
  chapters,
  selectedFile,
  selectedCount,
  selected,
  items,
  counts,
  onToggle,
  onSelectUntranslated,
  onSelectFromCurrent,
  onClear,
  onRun,
}: {
  busy: boolean;
  chapters: Chapter[];
  selectedFile: string;
  selectedCount: number;
  selected: Set<string>;
  items: BulkItem[];
  counts: { done: number; failed: number; pending: number; translating: number };
  onToggle: (filename: string, checked: boolean) => void;
  onSelectUntranslated: () => void;
  onSelectFromCurrent: () => void;
  onClear: () => void;
  onRun: (mode: "full" | "only") => void;
}) {
  return (
    <section className="grid gap-3 rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Bulk Translate</h2>
          <div className="text-xs text-muted-foreground">
            {selectedCount} selected; {counts.done}/{items.length || 0} completed
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onSelectUntranslated} disabled={busy || chapters.length === 0}>
            <Check />
            New
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onSelectFromCurrent} disabled={busy || !selectedFile}>
            <ClipboardList />
            From Current
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onClear} disabled={busy || selectedCount === 0}>
            <Eraser />
            Clear
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => onRun("only")} disabled={busy || selectedCount === 0}>
            <Check />
            Translate Only
          </Button>
          <Button type="button" size="sm" onClick={() => onRun("full")} disabled={busy || selectedCount === 0}>
            <WandSparkles />
            Translate + Glossary
          </Button>
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
        <ScrollArea className="h-44 rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">Use</TableHead>
                <TableHead>Chapter</TableHead>
                <TableHead className="w-24">State</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {chapters.map((chapter) => (
                <TableRow key={chapter.filename}>
                  <TableCell>
                    <input
                      type="checkbox"
                      className="size-4 accent-teal-700"
                      checked={selected.has(chapter.filename)}
                      disabled={busy}
                      onChange={(event) => onToggle(chapter.filename, event.target.checked)}
                      aria-label={`Select ${chapter.title}`}
                    />
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    <span className="line-clamp-2 [overflow-wrap:anywhere] text-sm font-medium">{chapter.title}</span>
                  </TableCell>
                  <TableCell>
                    <Badge variant={chapter.translated ? "secondary" : "outline"}>{chapter.translated ? "done" : "new"}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
        <BulkProgress items={items} counts={counts} />
      </div>
    </section>
  );
}

function ChapterNavigation({
  currentIndex,
  total,
  previousChapter,
  nextChapter,
  onPrevious,
  onNext,
}: {
  currentIndex: number;
  total: number;
  previousChapter?: Chapter;
  nextChapter?: Chapter;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const hasChapter = currentIndex >= 0 && total > 0;

  return (
    <footer className="sticky bottom-0 z-10 -mx-4 grid gap-2 border-t bg-background/95 px-4 py-3 shadow-[0_-8px_24px_rgba(15,23,42,0.06)] backdrop-blur md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
      <Button
        type="button"
        variant="outline"
        className="min-h-10 justify-start gap-2 whitespace-normal"
        disabled={!previousChapter}
        onClick={onPrevious}
      >
        <ChevronLeft />
        <span className="grid min-w-0 text-left leading-tight">
          <span className="text-xs text-muted-foreground">Previous</span>
          <span className="truncate">{previousChapter?.title || "No previous chapter"}</span>
        </span>
      </Button>

      <div className="grid content-center text-center text-xs text-muted-foreground">
        {hasChapter ? (
          <>
            <span className="font-medium text-foreground">
              Chapter {currentIndex + 1} of {total}
            </span>
            <span>Navigation</span>
          </>
        ) : (
          <span>No chapter selected</span>
        )}
      </div>

      <Button
        type="button"
        variant="outline"
        className="min-h-10 justify-end gap-2 whitespace-normal"
        disabled={!nextChapter}
        onClick={onNext}
      >
        <span className="grid min-w-0 text-right leading-tight">
          <span className="text-xs text-muted-foreground">Next</span>
          <span className="truncate">{nextChapter?.title || "No next chapter"}</span>
        </span>
        <ChevronRight />
      </Button>
    </footer>
  );
}

function GlossaryPage({
  apiKey,
  config,
  glossary,
  novel,
  usage,
  onApiKeyChange,
  onConfigChange,
  onSaveConfig,
  onResetUsage,
  onAdd,
  onRemove,
  onSave,
  onUpdate,
}: {
  apiKey: string;
  config: Config;
  glossary: GlossaryEntry[];
  novel: string;
  usage: Usage;
  onApiKeyChange: (value: string) => void;
  onConfigChange: (patch: Partial<Pick<Config, "translation_model" | "glossary_model">>) => void;
  onSaveConfig: () => void;
  onResetUsage: () => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onSave: () => void;
  onUpdate: (index: number, patch: Partial<GlossaryEntry>) => void;
}) {
  const [glossarySearch, setGlossarySearch] = useState("");
  const [glossaryPage, setGlossaryPage] = useState(1);
  const glossaryQuery = glossarySearch.trim().toLocaleLowerCase();
  const filteredGlossary = useMemo(
    () =>
      glossary
        .map((entry, index) => ({ entry, index }))
        .filter(({ entry }) => {
          if (!glossaryQuery) {
            return true;
          }
          return [
            entry.source_term,
            entry.english_term,
            entry.category,
            entry.gender_or_pronoun,
          ].some((value) => value.toLocaleLowerCase().includes(glossaryQuery));
        }),
    [glossary, glossaryQuery]
  );
  const totalGlossaryPages = Math.max(
    1,
    Math.ceil(filteredGlossary.length / GLOSSARY_ENTRIES_PER_PAGE)
  );
  const currentGlossaryPage = Math.min(glossaryPage, totalGlossaryPages);
  const firstGlossaryIndex = (currentGlossaryPage - 1) * GLOSSARY_ENTRIES_PER_PAGE;
  const visibleGlossary = filteredGlossary.slice(
    firstGlossaryIndex,
    firstGlossaryIndex + GLOSSARY_ENTRIES_PER_PAGE
  );
  const showingStart = filteredGlossary.length ? firstGlossaryIndex + 1 : 0;
  const showingEnd = Math.min(
    firstGlossaryIndex + GLOSSARY_ENTRIES_PER_PAGE,
    filteredGlossary.length
  );

  useEffect(() => {
    setGlossaryPage(1);
  }, [glossaryQuery, novel]);

  useEffect(() => {
    if (glossaryPage > totalGlossaryPages) {
      setGlossaryPage(totalGlossaryPages);
    }
  }, [glossaryPage, totalGlossaryPages]);

  return (
    <main className="grid min-h-[calc(100vh-3.5rem)] grid-cols-[320px_minmax(0,1fr)] max-[980px]:grid-cols-1">
      <aside className="grid content-start gap-4 border-r bg-muted/20 p-4 max-[980px]:border-r-0 max-[980px]:border-b">
        <section className="grid gap-3 rounded-lg border bg-background p-3">
          <div className="flex items-center gap-2">
            <Settings className="size-4 text-teal-700" />
            <h2 className="text-sm font-semibold">Settings</h2>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="api-key">OpenRouter API key</Label>
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <Input
                id="api-key"
                type="password"
                value={apiKey}
                placeholder={config.has_api_key ? config.api_key_mask : ""}
                autoComplete="off"
                onChange={(event) => onApiKeyChange(event.target.value)}
              />
              <Button type="button" onClick={onSaveConfig}>
                <Save />
                Save
              </Button>
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
            <ModelSelect
              id="glossary-model-settings"
              label="Glossary model"
              value={config.glossary_model}
              onChange={(glossary_model) => onConfigChange({ glossary_model })}
            />
            <ModelSelect
              id="translation-model-settings"
              label="Translation model"
              value={config.translation_model}
              onChange={(translation_model) => onConfigChange({ translation_model })}
            />
          </div>
        </section>

        <section className="grid gap-2 rounded-lg border bg-background p-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">Token usage</h2>
            <Button type="button" variant="outline" size="sm" onClick={onResetUsage}>
              Reset
            </Button>
          </div>
          {MODELS.map((model) => (
            <UsageSummary key={model} label={model} usage={usage.by_model[model] || emptyUsageBucket} />
          ))}
          <UsageSummary label="Total" usage={usage.total} prominent />
        </section>
      </aside>

      <section className="grid min-w-0 grid-rows-[auto_minmax(0,1fr)] gap-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Glossary</h2>
            <div className="text-sm text-muted-foreground">
              {novel || "No novel selected"} · {glossary.length} {glossary.length === 1 ? "entry" : "entries"}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setGlossarySearch("");
                setGlossaryPage(Math.ceil((glossary.length + 1) / GLOSSARY_ENTRIES_PER_PAGE));
                onAdd();
              }}
            >
              <Plus />
              Add Entry
            </Button>
            <Button type="button" onClick={onSave}>
              <Save />
              Save Glossary
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="relative min-w-64 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={glossarySearch}
              onChange={(event) => setGlossarySearch(event.target.value)}
              placeholder="Search glossary..."
              className="pl-9"
            />
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>
              Showing {showingStart}-{showingEnd} of {filteredGlossary.length}
            </span>
            {glossaryQuery && <span>matching {glossary.length} total</span>}
          </div>
        </div>

        <ScrollArea className="min-h-0 rounded-lg border bg-background">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>English</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Pronoun</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleGlossary.map(({ entry, index }) => (
                <TableRow key={index}>
                  <TableCell className="min-w-44">
                    <Input value={entry.source_term} onChange={(event) => onUpdate(index, { source_term: event.target.value })} />
                  </TableCell>
                  <TableCell className="min-w-48">
                    <Input value={entry.english_term} onChange={(event) => onUpdate(index, { english_term: event.target.value })} />
                  </TableCell>
                  <TableCell className="min-w-40">
                    <Input value={entry.category} onChange={(event) => onUpdate(index, { category: event.target.value })} />
                  </TableCell>
                  <TableCell className="min-w-36">
                    <Select
                      value={entry.gender_or_pronoun || "__none__"}
                      onValueChange={(value) => onUpdate(index, { gender_or_pronoun: value === "__none__" ? "" : value })}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PRONOUNS.map((pronoun) => (
                          <SelectItem key={pronoun} value={pronoun}>
                            {pronoun === "__none__" ? "none" : pronoun}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Button type="button" variant="destructive" size="icon" onClick={() => onRemove(index)} aria-label="Remove entry">
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>

        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <span className="text-muted-foreground">
            Page {currentGlossaryPage} of {totalGlossaryPages}
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={currentGlossaryPage <= 1}
              onClick={() => setGlossaryPage((current) => Math.max(1, current - 1))}
            >
              <ChevronLeft />
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={currentGlossaryPage >= totalGlossaryPages}
              onClick={() =>
                setGlossaryPage((current) => Math.min(totalGlossaryPages, current + 1))
              }
            >
              Next
              <ChevronRight />
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}

function ModelSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: Model;
  onChange: (value: Model) => void;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={(nextValue) => onChange(nextValue as Model)}>
        <SelectTrigger id={id} className="w-full bg-background">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {MODELS.map((model) => (
            <SelectItem key={model} value={model}>
              {model}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function ReaderPanel({
  tab,
  source,
  translated,
  onTabChange,
}: {
  tab: ReaderTab;
  source: string;
  translated: string;
  onTabChange: (tab: ReaderTab) => void;
}) {
  const value = tab === "raw" ? source : translated;

  return (
    <div className="grid min-h-0 grid-rows-[auto_1fr] gap-3">
      <div className="mx-auto grid w-full max-w-xl grid-cols-2 rounded-lg bg-muted p-1">
        <button
          type="button"
          className={cn(
            "h-9 rounded-md text-sm font-semibold transition-colors",
            tab === "raw"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
          onClick={() => onTabChange("raw")}
        >
          Raw
        </button>
        <button
          type="button"
          className={cn(
            "h-9 rounded-md text-sm font-semibold transition-colors",
            tab === "translated"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
          onClick={() => onTabChange("translated")}
        >
          Translated
        </button>
      </div>
      <Textarea value={value} readOnly className="h-full min-h-64 resize-none whitespace-pre-wrap bg-background font-serif leading-relaxed" />
    </div>
  );
}

function BulkProgress({
  items,
  counts,
}: {
  items: BulkItem[];
  counts: { done: number; failed: number; pending: number; translating: number };
}) {
  if (!items.length) {
    return (
      <div className="grid min-h-44 content-center rounded-lg border bg-muted/20 p-4 text-center text-sm text-muted-foreground">
        Select chapters, then start a bulk translation to track progress here.
      </div>
    );
  }

  return (
    <div className="grid gap-2 rounded-lg border bg-muted/20 p-2">
      <div className="flex flex-wrap gap-1 px-1 text-xs text-muted-foreground">
        <span>{counts.pending} pending</span>
        <span>{counts.translating} active</span>
        <span>{counts.failed} failed</span>
      </div>
      <ScrollArea className="h-36 pr-2">
        <div className="grid gap-1">
          {items.map((item) => (
            <div key={item.filename} className="grid gap-1 rounded-md border bg-background p-2 text-xs">
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 [overflow-wrap:anywhere] font-medium leading-tight">{item.title}</span>
                <BulkBadge status={item.status} />
              </div>
              {item.message && <div className="text-muted-foreground [overflow-wrap:anywhere]">{item.message}</div>}
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}

function BulkBadge({ status }: { status: BulkItem["status"] }) {
  if (status === "done") {
    return <Badge className="bg-teal-50 text-teal-800">done</Badge>;
  }
  if (status === "translating") {
    return <Badge variant="secondary">active</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">failed</Badge>;
  }
  return <Badge variant="outline">pending</Badge>;
}

function UsageSummary({
  label,
  usage,
  prominent = false,
}: {
  label: string;
  usage: UsageBucket;
  prominent?: boolean;
}) {
  return (
    <div className={cn("grid gap-1 rounded-md border p-2", prominent && "bg-muted/30")}>
      <div className="flex items-center justify-between gap-2 text-xs font-semibold">
        <span>{label}</span>
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

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="grid gap-0.5">
      <span className="text-base font-semibold tabular-nums">{formatInteger(value)}</span>
      <span className="text-muted-foreground">{label}</span>
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

function describeBulkProgress(state: BulkTranslationState) {
  const total = state.items.length;
  const done = state.items.filter((item) => item.status === "done").length;
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

function formatInteger(value: number) {
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
