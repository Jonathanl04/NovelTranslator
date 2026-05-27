import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import {
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Download,
  Eraser,
  Library,
  Moon,
  Plus,
  Save,
  Settings,
  Sun,
  Trash2,
  WandSparkles,
} from "lucide-react";
import { api } from "./api";
import type { Chapter, Config, GlossaryEntry, Model, NovelMetadata, Usage, UsageBucket } from "./types";
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

const MODELS: Model[] = ["deepseek-v4-flash", "deepseek-v4-pro"];
const PRONOUNS = ["__none__", "male", "female", "unknown", "it"];

type Page = "workspace" | "glossary";
type ReaderTab = "raw" | "translated";
type BulkStatus = "pending" | "translating" | "done" | "failed";

type BulkItem = {
  filename: string;
  title: string;
  status: BulkStatus;
  message?: string;
};

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
  },
};

export function App() {
  const [page, setPage] = useState<Page>("workspace");
  const [config, setConfig] = useState<Config>(emptyConfig);
  const [apiKey, setApiKey] = useState("");
  const [novels, setNovels] = useState<string[]>([]);
  const [novelMetadata, setNovelMetadata] = useState<NovelMetadata | null>(null);
  const [novel, setNovel] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [source, setSource] = useState("");
  const [translated, setTranslated] = useState("");
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [chapterSearch, setChapterSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState(false);
  const [usage, setUsage] = useState<Usage>(emptyUsage);
  const [bulkItems, setBulkItems] = useState<BulkItem[]>([]);
  const [bulkSelection, setBulkSelection] = useState<Set<string>>(new Set());
  const [readerTab, setReaderTab] = useState<ReaderTab>("translated");
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("theme") === "dark");

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

  const showStatus = useCallback((message: string, isError = false) => {
    setStatus(message);
    setError(isError);
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
      const chapter = await api.chapter(nextNovel, filename);
      setSource(chapter.source);
      setTranslated(chapter.translated);
      showStatus(chapter.translated_exists ? "Loaded existing translation." : "Loaded source chapter.");
    },
    [showStatus]
  );

  const loadChapters = useCallback(
    async (nextNovel: string) => {
      setNovel(nextNovel);
      setSelectedFile("");
      setSource("");
      setTranslated("");
      setNovelMetadata(null);
      setChapterSearch("");
      setBulkSelection(new Set());
      setBulkItems([]);
      await loadGlossary(nextNovel);
      if (!nextNovel) {
        setChapters([]);
        return;
      }
      const nextChapters = await api.chapters(nextNovel);
      api
        .novel(nextNovel)
        .then(setNovelMetadata)
        .catch(() => setNovelMetadata(null));
      setChapters(nextChapters);
      if (nextChapters[0]) {
        await selectChapter(nextNovel, nextChapters[0].filename);
      }
    },
    [loadGlossary, selectChapter]
  );

  useEffect(() => {
    let active = true;

    async function boot() {
      try {
        const [nextConfig, nextNovels, nextUsage] = await Promise.all([api.config(), api.novels(), api.usage()]);
        if (!active) return;
        setConfig(nextConfig);
        setNovels(nextNovels);
        setUsage(nextUsage);
        if (nextNovels[0]) {
          await loadChapters(nextNovels[0]);
        }
      } catch (caught) {
        showStatus(errorMessage(caught), true);
      }
    }

    boot();
    return () => {
      active = false;
    };
  }, [loadChapters, showStatus]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    localStorage.setItem("theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  async function saveConfig() {
    try {
      const current = await api.config();
      const saved = await api.saveConfig({
        api_key: apiKey.trim() || undefined,
        keep_existing_key: !apiKey.trim() && current.has_api_key,
        translation_model: config.translation_model,
        glossary_model: config.glossary_model,
      });
      setConfig(saved);
      setApiKey("");
      showStatus("Config saved.");
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    }
  }

  async function runTranslation(mode: "full" | "only") {
    if (!novel || !selectedFile || busy) return;
    setBusy(true);
    showStatus(mode === "full" ? "Populating glossary, then translating..." : "Translating with current glossary...");
    try {
      const result = mode === "full" ? await api.translate(novel, selectedFile) : await api.translateOnly(novel, selectedFile);
      setUsage(await api.usage());
      setTranslated(result.translated);
      setGlossary(result.glossary);
      setChapters(await api.chapters(novel));
      showStatus(`Saved ${result.output_path}`);
    } catch (caught) {
      showStatus(errorMessage(caught), true);
    } finally {
      setBusy(false);
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

  async function runBulkTranslation() {
    if (!novel || busy || selectedBulkChapters.length === 0) return;

    const queue = selectedBulkChapters.map((chapter) => ({
      filename: chapter.filename,
      title: chapter.title,
      status: "pending" as const,
    }));

    setBulkItems(queue);
    setBusy(true);
    showStatus(`Bulk translating ${queue.length} selected ${queue.length === 1 ? "chapter" : "chapters"}...`);

    try {
      for (const item of queue) {
        setBulkItems((current) =>
          current.map((currentItem) =>
            currentItem.filename === item.filename
              ? { ...currentItem, status: "translating", message: "Translating..." }
              : currentItem
          )
        );

        try {
          const result = await api.translate(novel, item.filename);
          setUsage(await api.usage());
          setGlossary(result.glossary);
          if (item.filename === selectedFile) {
            setTranslated(result.translated);
          }
          setBulkItems((current) =>
            current.map((currentItem) =>
              currentItem.filename === item.filename
                ? { ...currentItem, status: "done", message: "Saved" }
                : currentItem
            )
          );
          setChapters(await api.chapters(novel));
        } catch (caught) {
          const message = errorMessage(caught);
          setBulkItems((current) =>
            current.map((currentItem) =>
              currentItem.filename === item.filename
                ? { ...currentItem, status: "failed", message }
                : currentItem
            )
          );
          showStatus(message, true);
          return;
        }
      }

      setBulkSelection(new Set());
      showStatus("Bulk translation complete.");
    } finally {
      setBusy(false);
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
          <Button type="button" size="sm" variant={page === "workspace" ? "secondary" : "ghost"} onClick={() => setPage("workspace")}>
            <Library />
            Translate
          </Button>
          <Button type="button" size="sm" variant={page === "glossary" ? "secondary" : "ghost"} onClick={() => setPage("glossary")}>
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

      {page === "workspace" ? (
        <main className="grid min-h-[calc(100vh-3.5rem)] grid-cols-[320px_minmax(0,1fr)] max-[980px]:grid-cols-1">
          <aside className="sticky top-14 grid h-[calc(100vh-3.5rem)] min-w-0 grid-rows-[auto_minmax(0,1fr)] gap-4 overflow-hidden border-r bg-muted/20 p-4 max-[980px]:static max-[980px]:h-auto max-[980px]:overflow-visible max-[980px]:border-r-0 max-[980px]:border-b">
            <section className="grid gap-3">
              <NovelCover novel={novel} metadata={novelMetadata} />
              <div className="grid gap-1.5">
                <Label>Novel</Label>
                <Select value={novel} onValueChange={(value) => loadChapters(value).catch((caught) => showStatus(errorMessage(caught), true))}>
                  <SelectTrigger className="w-full bg-background">
                    <SelectValue placeholder="No novels found" />
                  </SelectTrigger>
                  <SelectContent>
                    {novels.map((name) => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
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
                        selectedFile === chapter.filename && "border-teal-700 bg-teal-50/70"
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
                  <Button type="button" disabled={busy || !selectedFile} onClick={() => runTranslation("full")}>
                    <WandSparkles />
                    Translate Chapter
                  </Button>
                  <Button type="button" variant="outline" disabled={busy || !selectedFile} onClick={() => runTranslation("only")}>
                    <Check />
                    Translate Only
                  </Button>
                </div>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                <ModelSelect
                  id="glossary-model"
                  label="Glossary model"
                  value={config.glossary_model}
                  onChange={(glossary_model) => setConfig((current) => ({ ...current, glossary_model }))}
                />
                <ModelSelect
                  id="translation-model"
                  label="Translation model"
                  value={config.translation_model}
                  onChange={(translation_model) => setConfig((current) => ({ ...current, translation_model }))}
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
          onConfigChange={setConfig}
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

function NovelCover({ novel, metadata }: { novel: string; metadata: NovelMetadata | null }) {
  if (!novel || !metadata?.cover_url) {
    return null;
  }

  return (
    <div className="grid grid-cols-[72px_minmax(0,1fr)] items-center gap-3 rounded-lg border bg-background p-2">
      <img
        src={metadata.cover_url}
        alt={`${novel} cover`}
        className="aspect-[7/9] h-24 w-[72px] rounded-md object-cover"
      />
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold">{novel}</div>
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
  onRun: () => void;
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
          <Button type="button" size="sm" onClick={onRun} disabled={busy || selectedCount === 0}>
            <WandSparkles />
            Translate Selected
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
  onConfigChange: Dispatch<SetStateAction<Config>>;
  onSaveConfig: () => void;
  onResetUsage: () => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onSave: () => void;
  onUpdate: (index: number, patch: Partial<GlossaryEntry>) => void;
}) {
  return (
    <main className="grid min-h-[calc(100vh-3.5rem)] grid-cols-[320px_minmax(0,1fr)] max-[980px]:grid-cols-1">
      <aside className="grid content-start gap-4 border-r bg-muted/20 p-4 max-[980px]:border-r-0 max-[980px]:border-b">
        <section className="grid gap-3 rounded-lg border bg-background p-3">
          <div className="flex items-center gap-2">
            <Settings className="size-4 text-teal-700" />
            <h2 className="text-sm font-semibold">Settings</h2>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="api-key">DeepSeek API key</Label>
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
              onChange={(glossary_model) => onConfigChange((current) => ({ ...current, glossary_model }))}
            />
            <ModelSelect
              id="translation-model-settings"
              label="Translation model"
              value={config.translation_model}
              onChange={(translation_model) => onConfigChange((current) => ({ ...current, translation_model }))}
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
          <UsageSummary label="Flash" usage={usage.by_model["deepseek-v4-flash"]} />
          <UsageSummary label="Pro" usage={usage.by_model["deepseek-v4-pro"]} />
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
            <Button type="button" variant="outline" onClick={onAdd}>
              <Plus />
              Add Entry
            </Button>
            <Button type="button" onClick={onSave}>
              <Save />
              Save Glossary
            </Button>
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
              {glossary.map((entry, index) => (
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

function BulkBadge({ status }: { status: BulkStatus }) {
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
