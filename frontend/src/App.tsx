import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "./api";
import type {
  BulkItem,
  Chapter,
  GlossaryEntry,
  NovelMetadata,
} from "./types";
import { AppHeader } from "@/components/AppHeader";
import { BooksPage } from "@/pages/BooksPage";
import { GlossaryPage } from "@/pages/GlossaryPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TranslatePage, type ReaderTab } from "@/pages/TranslatePage";
import { useBulkTranslation } from "@/hooks/useBulkTranslation";
import { useLibrary } from "@/hooks/useLibrary";
import { useSettings } from "@/hooks/useSettings";
import {
  SELECTED_NOVEL_STORAGE_KEY,
  cleanGlossary,
  decodeContentDispositionFilename,
  errorMessage,
  glossaryPath,
  getReadingProgress,
  preferredChapter,
  routePage,
  saveReadingProgress,
  translatePath,
} from "@/appUtils";

export function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const page = routePage(location.pathname);
  const routeNovel = searchParams.get("book") || "";
  const routeChapter = searchParams.get("chapter") || "";
  const [novelMetadata, setNovelMetadata] = useState<NovelMetadata | null>(null);
  const [novel, setNovel] = useState("");
  const effectiveRouteNovel =
    routeNovel || (page === "glossary" ? novel || localStorage.getItem(SELECTED_NOVEL_STORAGE_KEY) || "" : "");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [loadedFile, setLoadedFile] = useState("");
  const [source, setSource] = useState("");
  const [translated, setTranslated] = useState("");
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [chapterSearch, setChapterSearch] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState(false);
  const [readerTab, setReaderTab] = useState<ReaderTab>("translated");
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("theme") === "dark");
  const bookLoadId = useRef(0);
  const chapterLoadId = useRef(0);

  useLayoutEffect(() => {
    if (page === "workspace" && routeChapter) return;
    window.scrollTo(0, 0);
  }, [location.key, page, routeChapter]);

  useEffect(() => {
    const previousScrollRestoration = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    return () => {
      window.history.scrollRestoration = previousScrollRestoration;
    };
  }, []);

  const showStatus = useCallback((message: string, isError = false) => {
    setStatus(message);
    setError(isError);
  }, []);
  const settings = useSettings(showStatus);
  const {
    aborted: bulkAborted,
    abort: abortBulk,
    clear: clearBulk,
    items: bulkItems,
    load: loadBulkState,
    manualBusy,
    running: bulkRunning,
    selection: bulkSelection,
    setSelection: setBulkSelection,
    start: startBulk,
  } = useBulkTranslation({
    novel,
    selectedFile,
    onStatus: showStatus,
    onChapters: setChapters,
    onUsage: settings.setUsage,
    onGlossaryRefresh: async () => {
      if (novel) setGlossary(await api.glossary(novel));
    },
    onSelectedChapterRefresh: async () => {
      if (!novel || !selectedFile) return;
      const chapter = await api.chapter(novel, selectedFile);
      setSource(chapter.source);
      setTranslated(chapter.translated);
    },
    onMetadataRefresh: async () => {
      if (!novel) return;
      const metadata = await api.novel(novel);
      setNovelMetadata(metadata);
    },
  });
  const busy = manualBusy || bulkRunning;

  const clearSelectedBook = useCallback(() => {
    bookLoadId.current += 1;
    chapterLoadId.current += 1;
    setNovel("");
    setNovelMetadata(null);
    setChapters([]);
    setSelectedFile("");
    setLoadedFile("");
    setSource("");
    setTranslated("");
    setGlossary([]);
    clearBulk();
    localStorage.removeItem(SELECTED_NOVEL_STORAGE_KEY);
    navigate("/books");
  }, [clearBulk, navigate]);

  const library = useLibrary({
    navigate,
    selectedNovel: novel,
    onStatus: showStatus,
    onDeleteSelected: clearSelectedBook,
  });
  const loadLibraryMetadata = library.loadMetadata;

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
  const selectChapter = useCallback(
    async (nextNovel: string, filename: string) => {
      const loadId = ++chapterLoadId.current;
      setSelectedFile(filename);
      setLoadedFile("");
      setSource("");
      setTranslated("");
      const progress = getReadingProgress(nextNovel);
      saveReadingProgress(nextNovel, {
        chapter: filename,
        scrollTop: progress?.chapter === filename ? progress.scrollTop : 0,
      });
      const chapter = await api.chapter(nextNovel, filename);
      if (chapterLoadId.current !== loadId) return;
      setSource(chapter.source);
      setTranslated(chapter.translated);
      setLoadedFile(filename);
      showStatus(chapter.translated_exists ? "Loaded existing translation." : "Loaded source chapter.");
    },
    [showStatus]
  );

  const loadChapters = useCallback(
    async (nextNovel: string) => {
      const loadId = ++bookLoadId.current;
      chapterLoadId.current += 1;
      const isCurrent = () => bookLoadId.current === loadId;
      setNovel(nextNovel);
      if (nextNovel) {
        localStorage.setItem(SELECTED_NOVEL_STORAGE_KEY, nextNovel);
      }
      setSelectedFile("");
      setLoadedFile("");
      setSource("");
      setTranslated("");
      setChapters([]);
      setNovelMetadata(null);
      setChapterSearch("");
      setBulkSelection(new Set());
      if (!nextNovel) {
        setGlossary([]);
        await loadBulkState(nextNovel, isCurrent);
        return [];
      }

      api.glossary(nextNovel)
        .then((nextGlossary) => {
          if (isCurrent()) setGlossary(nextGlossary);
        })
        .catch((caught) => {
          if (isCurrent()) showStatus(errorMessage(caught), true);
        });
      loadBulkState(nextNovel, isCurrent)
        .catch((caught) => {
          if (isCurrent()) showStatus(errorMessage(caught), true);
        });
      loadLibraryMetadata(nextNovel)
        .then((metadata) => {
          if (isCurrent()) setNovelMetadata(metadata);
        })
        .catch(() => {
          if (isCurrent()) setNovelMetadata(null);
        });

      const nextChapters = await api.chapters(nextNovel);
      if (!isCurrent()) return [];
      setChapters(nextChapters);
      return nextChapters;
    },
    [loadBulkState, loadLibraryMetadata, showStatus]
  );

  const chooseNovel = useCallback(
    async (nextNovel: string) => {
      navigate(translatePath(nextNovel));
      await loadChapters(nextNovel);
    },
    [loadChapters, navigate]
  );

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
    document.documentElement.classList.toggle("dark", darkMode);
    localStorage.setItem("theme", darkMode ? "dark" : "light");
  }, [darkMode]);

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

    showStatus(
      mode === "full"
        ? `Translating ${queue.length} ${queue.length === 1 ? "chapter" : "chapters"} with glossary...`
        : `Translating ${queue.length} ${queue.length === 1 ? "chapter" : "chapters"} with current glossary...`
    );

    try {
      await startBulk(queue);
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  async function abortBulkTranslation() {
    if (!novel || !bulkRunning) return;
    try {
      await abortBulk();
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
      <AppHeader
        page={page}
        status={status}
        error={error}
        darkMode={darkMode}
        onNavigate={(target) => {
          if (target === "library") navigate("/books");
          else if (target === "workspace") navigate(novel ? translatePath(novel, selectedFile) : "/translate");
          else if (target === "glossary") navigate(glossaryPath(novel));
          else navigate("/settings");
        }}
        onToggleTheme={() => setDarkMode((current) => !current)}
      />

      {page === "library" ? (
        <BooksPage
          novels={library.visibleNovels}
          allCount={library.allCount}
          filteredCount={library.filteredCount}
          metadataByName={library.metadataByName}
          selectedNovel={novel}
          query={library.query}
          sort={library.sort}
          page={library.page}
          pageCount={library.pageCount}
          scrapeUrl={library.scrapeUrl}
          scrapeStart={library.scrapeStart}
          scrapeEnd={library.scrapeEnd}
          scrapeState={library.scrapeState}
          onQueryChange={library.setQuery}
          onSortChange={library.setSort}
          onPageChange={library.setPage}
          onScrapeUrlChange={library.setScrapeUrl}
          onScrapeStartChange={library.setScrapeStart}
          onScrapeEndChange={library.setScrapeEnd}
          onScrape={library.runScrape}
          onUseSourceUrl={library.useSourceUrl}
          onSelect={(name) => chooseNovel(name).catch((caught) => showStatus(errorMessage(caught), true))}
          onDelete={library.deleteBook}
          qidianAuth={library.qidianAuth}
          onQidianSaveCookies={library.saveQidianCookies}
          onQidianLogout={library.logoutQidian}
        />
      ) : page === "workspace" ? (
        <TranslatePage
          novel={novel}
          displayName={library.displayName(novel)}
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
          readerReady={loadedFile === selectedFile && Boolean(selectedFile)}
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
          openrouterApiKey={settings.openrouterApiKey}
          config={settings.config}
          usage={settings.usage}
          onOpenrouterApiKeyChange={settings.setOpenrouterApiKey}
          onConfigChange={settings.updateConfig}
          onSaveConfig={settings.save}
          onResetUsage={settings.resetUsage}
        />
      )}
    </div>
  );
}

