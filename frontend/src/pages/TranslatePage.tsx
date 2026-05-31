import {
  useEffect,
  useRef,
} from "react";
import {
  BookOpen,
  Ban,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Download,
  Eraser,
  Library,
  Search,
  WandSparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
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
import type { BulkItem, Chapter, Config, Model, NovelMetadata } from "@/types";
import { formatInteger, ModelSelect } from "./shared";

export type ReaderTab = "raw" | "translated";

export function TranslatePage({
  displayName,
  metadata,
  chapterCount,
  translatedCount,
  queuedCount,
  glossaryModel,
  translationModel,
  canExport,
  busy,
  bulkRunning,
  chapters,
  visibleChapters,
  search,
  selectedFile,
  selection,
  itemsByFile,
  itemsTotal,
  counts,
  untranslatedCount,
  selectedChapter,
  selectedChapterIndex,
  previousChapter,
  nextChapter,
  readerTab,
  source,
  translated,
  onChooseBook,
  onExport,
  onModelChange,
  onSearchChange,
  onOpen,
  onToggle,
  onSelectUntranslated,
  onSelectFromCurrent,
  onClear,
  onTranslate,
  onAbortBulk,
  onReaderTabChange,
  onPrevious,
  onNext,
}: {
  displayName: string;
  metadata: NovelMetadata | null;
  chapterCount: number;
  translatedCount: number;
  queuedCount: number;
  glossaryModel: Model;
  translationModel: Model;
  canExport: boolean;
  busy: boolean;
  bulkRunning: boolean;
  chapters: Chapter[];
  visibleChapters: Chapter[];
  search: string;
  selectedFile: string;
  selection: Set<string>;
  itemsByFile: Map<string, BulkItem>;
  itemsTotal: number;
  counts: { done: number; failed: number; aborted: number; pending: number; translating: number };
  untranslatedCount: number;
  selectedChapter?: Chapter;
  selectedChapterIndex: number;
  previousChapter?: Chapter;
  nextChapter?: Chapter;
  readerTab: ReaderTab;
  source: string;
  translated: string;
  onChooseBook: () => void;
  onExport: () => void;
  onModelChange: (patch: Partial<Pick<Config, "translation_model" | "glossary_model">>) => void;
  onSearchChange: (value: string) => void;
  onOpen: (filename: string) => void;
  onToggle: (filename: string, checked: boolean) => void;
  onSelectUntranslated: () => void;
  onSelectFromCurrent: () => void;
  onClear: () => void;
  onTranslate: (mode: "full" | "only") => void;
  onAbortBulk: () => void;
  onReaderTabChange: (tab: ReaderTab) => void;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] min-w-0 overflow-x-hidden bg-muted/20">
      <section className="mx-auto grid min-h-[calc(100vh-3.5rem)] w-full min-w-0 max-w-6xl grid-rows-[auto_auto_minmax(0,1fr)] gap-4 overflow-x-clip p-3 pb-32 sm:p-4 sm:pb-32">
        <WorkspaceHeader
          displayName={displayName}
          metadata={metadata}
          chapterCount={chapterCount}
          translatedCount={translatedCount}
          queuedCount={queuedCount}
          glossaryModel={glossaryModel}
          translationModel={translationModel}
          canExport={canExport}
          busy={busy}
          onChooseBook={onChooseBook}
          onExport={onExport}
          onModelChange={onModelChange}
        />

        <ChapterPanel
          busy={busy}
          bulkRunning={bulkRunning}
          chapters={chapters}
          visibleChapters={visibleChapters}
          search={search}
          onSearchChange={onSearchChange}
          selectedFile={selectedFile}
          selection={selection}
          itemsByFile={itemsByFile}
          itemsTotal={itemsTotal}
          counts={counts}
          untranslatedCount={untranslatedCount}
          onOpen={onOpen}
          onToggle={onToggle}
          onSelectUntranslated={onSelectUntranslated}
          onSelectFromCurrent={onSelectFromCurrent}
          onClear={onClear}
          onTranslate={onTranslate}
          onAbortBulk={onAbortBulk}
        />

        <div className="grid min-h-0 min-w-0 grid-rows-[minmax(0,1fr)_auto] gap-4">
          <ReaderPanel
            title={selectedChapter?.title}
            subtitle={
              selectedChapter
                ? `${formatInteger(selectedChapter.source_size)} source chars`
                : "Choose a chapter to preview and translate."
            }
            tab={readerTab}
            source={source}
            translated={translated}
            resetKey={selectedFile}
            onTabChange={onReaderTabChange}
          />

          <ChapterNavigation
            currentIndex={selectedChapterIndex}
            total={chapters.length}
            previousChapter={previousChapter}
            nextChapter={nextChapter}
            onPrevious={onPrevious}
            onNext={onNext}
          />
        </div>
      </section>
    </main>
  );
}

function WorkspaceHeader({
  displayName,
  metadata,
  chapterCount,
  translatedCount,
  queuedCount,
  glossaryModel,
  translationModel,
  canExport,
  busy,
  onChooseBook,
  onExport,
  onModelChange,
}: {
  displayName: string;
  metadata: NovelMetadata | null;
  chapterCount: number;
  translatedCount: number;
  queuedCount: number;
  glossaryModel: Model;
  translationModel: Model;
  canExport: boolean;
  busy: boolean;
  onChooseBook: () => void;
  onExport: () => void;
  onModelChange: (patch: Partial<Pick<Config, "translation_model" | "glossary_model">>) => void;
}) {
  return (
    <section className="grid min-w-0 gap-3 overflow-hidden rounded-lg border bg-card p-3">
      <div className="flex min-w-0 flex-wrap items-center gap-3 max-[700px]:grid max-[700px]:grid-cols-[auto_minmax(0,1fr)]">
        <div className="aspect-[7/9] h-16 w-[3rem] shrink-0 overflow-hidden rounded-md border bg-muted">
          {metadata?.cover_url ? (
            <img src={metadata.cover_url} alt={`${displayName} cover`} className="h-full w-full object-cover" />
          ) : (
            <div className="grid h-full place-items-center text-muted-foreground">
              <BookOpen className="size-5" />
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold">{displayName || "No book selected"}</h2>
          <div className="text-xs text-muted-foreground">
            {formatInteger(chapterCount)} chapters · {formatInteger(translatedCount)} translated · {formatInteger(queuedCount)} queued
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap gap-2 max-[700px]:col-span-2 max-[700px]:grid max-[700px]:w-full max-[700px]:grid-cols-2">
          <Button type="button" variant="outline" size="sm" className="min-w-0 whitespace-normal" onClick={onChooseBook}>
            <Library />
            Choose Book
          </Button>
          <Button type="button" variant="outline" size="sm" className="min-w-0 whitespace-normal" disabled={!canExport} onClick={onExport}>
            <Download />
            Export EPUB
          </Button>
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        <ModelSelect
          id="glossary-model"
          label="Glossary model"
          value={glossaryModel}
          onChange={(glossary_model) => onModelChange({ glossary_model })}
        />
        <ModelSelect
          id="translation-model"
          label="Translation model"
          value={translationModel}
          onChange={(translation_model) => onModelChange({ translation_model })}
        />
      </div>
    </section>
  );
}

function ChapterPanel({
  busy,
  bulkRunning,
  chapters,
  visibleChapters,
  search,
  onSearchChange,
  selectedFile,
  selection,
  itemsByFile,
  itemsTotal,
  counts,
  untranslatedCount,
  onOpen,
  onToggle,
  onSelectUntranslated,
  onSelectFromCurrent,
  onClear,
  onTranslate,
  onAbortBulk,
}: {
  busy: boolean;
  bulkRunning: boolean;
  chapters: Chapter[];
  visibleChapters: Chapter[];
  search: string;
  onSearchChange: (value: string) => void;
  selectedFile: string;
  selection: Set<string>;
  itemsByFile: Map<string, BulkItem>;
  itemsTotal: number;
  counts: { done: number; failed: number; aborted: number; pending: number; translating: number };
  untranslatedCount: number;
  onOpen: (filename: string) => void;
  onToggle: (filename: string, checked: boolean) => void;
  onSelectUntranslated: () => void;
  onSelectFromCurrent: () => void;
  onClear: () => void;
  onTranslate: (mode: "full" | "only") => void;
  onAbortBulk: () => void;
}) {
  const selectedCount = selection.size;
  const summary =
    itemsTotal > 0
      ? [
          `${counts.done}/${itemsTotal} done`,
          counts.translating ? `${counts.translating} active` : "",
          counts.pending ? `${counts.pending} pending` : "",
          counts.failed ? `${counts.failed} failed` : "",
          counts.aborted ? `${counts.aborted} aborted` : "",
        ]
          .filter(Boolean)
          .join(" · ")
      : `${untranslatedCount} new`;
  const target = selectedCount > 0 ? `${selectedCount} selected` : "current chapter";
  const canTranslate = !busy && (selectedCount > 0 || Boolean(selectedFile));

  return (
    <section className="grid min-w-0 gap-3 overflow-hidden rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Chapters</h2>
          <div className="text-xs text-muted-foreground">{summary}</div>
        </div>
        <div className="flex min-w-0 flex-wrap gap-2 max-[700px]:grid max-[700px]:w-full max-[700px]:grid-cols-2">
          <Button type="button" variant="outline" size="sm" className="min-w-0 whitespace-normal" onClick={onSelectUntranslated} disabled={busy || chapters.length === 0}>
            <Check />
            New
          </Button>
          <Button type="button" variant="outline" size="sm" className="min-w-0 whitespace-normal" onClick={onSelectFromCurrent} disabled={busy || !selectedFile}>
            <ClipboardList />
            From Current
          </Button>
          <Button type="button" variant="outline" size="sm" className="min-w-0 whitespace-normal" onClick={onClear} disabled={busy || selectedCount === 0}>
            <Eraser />
            Clear
          </Button>
          <Button type="button" variant="outline" size="sm" className="min-w-0 whitespace-normal" onClick={() => onTranslate("only")} disabled={!canTranslate}>
            <Check />
            Translate Only
          </Button>
          <Button
            type="button"
            size="sm"
            className="min-w-0 whitespace-normal max-[700px]:col-span-2"
            onClick={() => onTranslate("full")}
            disabled={!canTranslate}
          >
            <WandSparkles />
            Translate + Glossary
          </Button>
          {bulkRunning && (
            <Button
              type="button"
              variant="destructive"
              size="sm"
              className="min-w-0 whitespace-normal max-[700px]:col-span-2"
              onClick={onAbortBulk}
            >
              <Ban />
              Abort
            </Button>
          )}
        </div>
      </div>
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 max-[700px]:grid">
        <div className="relative min-w-0 flex-1 max-[700px]:w-full sm:min-w-48">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={search}
            placeholder="Search chapters..."
            className="bg-background pl-9"
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
        <span className="min-w-0 text-xs text-muted-foreground">
          Translate target: <span className="font-medium text-foreground">{target}</span>
        </span>
      </div>
      <ScrollArea className="h-56 min-w-0 overflow-hidden rounded-lg border bg-background max-[980px]:h-72">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">Use</TableHead>
              <TableHead>Chapter</TableHead>
              <TableHead className="w-24 text-right sm:w-28">State</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleChapters.map((chapter) => {
              const item = itemsByFile.get(chapter.filename);
              const isOpen = selectedFile === chapter.filename;
              return (
                <TableRow
                  key={chapter.filename}
                  className={cn(
                    "cursor-pointer",
                    isOpen && "bg-teal-50/70 hover:bg-teal-50/70 dark:bg-teal-950/40 dark:hover:bg-teal-950/40"
                  )}
                  onClick={() => onOpen(chapter.filename)}
                >
                  <TableCell onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      className="size-4 accent-teal-700"
                      checked={selection.has(chapter.filename)}
                      disabled={busy}
                      onChange={(event) => onToggle(chapter.filename, event.target.checked)}
                      aria-label={`Select ${chapter.title}`}
                    />
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    <span
                      className={cn(
                        "line-clamp-2 [overflow-wrap:anywhere] text-sm font-medium",
                        isOpen && "text-teal-800 dark:text-teal-300"
                      )}
                    >
                      {chapter.title}
                    </span>
                    {item?.status === "failed" && item.message && (
                      <span className="mt-0.5 block text-xs text-destructive [overflow-wrap:anywhere]">{item.message}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {item ? (
                      <BulkBadge status={item.status} />
                    ) : (
                      <Badge variant={chapter.translated ? "secondary" : "outline"} className={chapter.translated ? "bg-teal-50 text-teal-800" : ""}>
                        {chapter.translated ? "done" : "new"}
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {visibleChapters.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-sm text-muted-foreground">
                  No chapters match your search.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </ScrollArea>
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
    <footer className="fixed inset-x-0 bottom-0 z-30 mx-auto grid min-w-0 max-w-6xl gap-2 border-t bg-background/95 px-3 py-3 shadow-[0_-8px_24px_rgba(15,23,42,0.12)] backdrop-blur sm:px-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
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

function ReaderPanel({
  title,
  subtitle,
  tab,
  source,
  translated,
  resetKey,
  onTabChange,
}: {
  title?: string;
  subtitle: string;
  tab: ReaderTab;
  source: string;
  translated: string;
  resetKey: string;
  onTabChange: (tab: ReaderTab) => void;
}) {
  const value = tab === "raw" ? source : translated;
  const readerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.scrollTo({ top: 0 });
    readerRef.current?.scrollIntoView({ block: "start" });
  }, [resetKey]);

  return (
    <div ref={readerRef} className="grid min-h-0 min-w-0 scroll-mt-16 grid-rows-[auto_auto_1fr] gap-3">
      <div className="min-w-0">
        <h2 className="truncate text-sm font-semibold">{title || "Select a chapter"}</h2>
        <div className="text-xs text-muted-foreground">{subtitle}</div>
      </div>
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
      <Textarea
        ref={textareaRef}
        value={value}
        readOnly
        className="h-full min-h-64 min-w-0 resize-none whitespace-pre-wrap bg-background font-serif leading-relaxed"
      />
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
  if (status === "aborted") {
    return <Badge variant="secondary">aborted</Badge>;
  }
  return <Badge variant="outline">pending</Badge>;
}
