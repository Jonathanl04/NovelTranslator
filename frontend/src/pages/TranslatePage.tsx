import {
  useEffect,
  useRef,
  useState,
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
import type { BulkItem, Chapter, NovelMetadata } from "@/types";
import { getReadingProgress, saveReadingProgress, translatePath } from "@/appUtils";
import { formatInteger } from "./shared";

export type ReaderTab = "raw" | "translated";

export function TranslatePage({
  novel,
  displayName,
  metadata,
  chapterCount,
  translatedCount,
  queuedCount,
  canExport,
  busy,
  bulkQueueActive,
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
  readerReady,
  source,
  translated,
  onChooseBook,
  onExport,
  onSearchChange,
  onOpen,
  onToggle,
  onSelectUntranslated,
  onSelectFromCurrent,
  onClear,
  onTranslate,
  onAbortBulk,
  onRetryFailed,
  onReaderTabChange,
  onPrevious,
  onNext,
}: {
  novel: string;
  displayName: string;
  metadata: NovelMetadata | null;
  chapterCount: number;
  translatedCount: number;
  queuedCount: number;
  canExport: boolean;
  busy: boolean;
  bulkQueueActive: boolean;
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
  readerReady: boolean;
  source: string;
  translated: string;
  onChooseBook: () => void;
  onExport: () => void;
  onSearchChange: (value: string) => void;
  onOpen: (filename: string) => void;
  onToggle: (filename: string, checked: boolean) => void;
  onSelectUntranslated: () => void;
  onSelectFromCurrent: () => void;
  onClear: () => void;
  onTranslate: (mode: "full" | "only") => void;
  onAbortBulk: () => void;
  onRetryFailed: () => void;
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
          canExport={canExport}
          busy={busy}
          onChooseBook={onChooseBook}
          onExport={onExport}
        />

        <ChapterPanel
          key={novel}
          novel={novel}
          busy={busy}
          bulkQueueActive={bulkQueueActive}
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
          onRetryFailed={onRetryFailed}
        />

        <div className="grid min-h-0 min-w-0 grid-rows-[minmax(0,1fr)_auto] gap-4">
          <ReaderPanel
            novel={novel}
            title={selectedChapter?.title}
            subtitle={
              selectedChapter
                ? `${formatInteger(selectedChapter.source_size)} source chars`
                : "Choose a chapter to preview and translate."
            }
            tab={readerTab}
            ready={readerReady}
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
  canExport,
  busy,
  onChooseBook,
  onExport,
}: {
  displayName: string;
  metadata: NovelMetadata | null;
  chapterCount: number;
  translatedCount: number;
  queuedCount: number;
  canExport: boolean;
  busy: boolean;
  onChooseBook: () => void;
  onExport: () => void;
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
    </section>
  );
}

function ChapterPanel({
  novel,
  busy,
  bulkQueueActive,
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
  onRetryFailed,
}: {
  novel: string;
  busy: boolean;
  bulkQueueActive: boolean;
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
  onRetryFailed: () => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const rowHeight = 40;
  const windowSize = 20;
  const firstRow = Math.min(Math.max(0, Math.floor(scrollTop / rowHeight) - 5), Math.max(0, visibleChapters.length - windowSize));
  const lastRow = Math.min(visibleChapters.length, firstRow + windowSize);
  const renderedChapters = visibleChapters.slice(firstRow, lastRow);
  const failedItems = [...itemsByFile.values()].filter((item) => item.status === "failed" && item.mode !== "name");

  useEffect(() => {
    if (viewport.current) viewport.current.scrollTop = 0;
    setScrollTop(0);
  }, [search]);

  function focusChapter(index: number) {
    const target = Math.max(0, Math.min(visibleChapters.length - 1, index));
    if (!viewport.current) return;
    viewport.current.scrollTop = target * rowHeight;
    setScrollTop(viewport.current.scrollTop);
    requestAnimationFrame(() => viewport.current?.querySelector<HTMLAnchorElement>(`[data-chapter-index="${target}"] a`)?.focus());
  }
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
          {bulkQueueActive && (
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
      {failedItems.length > 0 && (
        <div className="grid gap-2 rounded-lg border border-destructive/40 p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-destructive">{failedItems.length} failed {failedItems.length === 1 ? "chapter" : "chapters"}</span>
            <Button type="button" variant="outline" size="sm" disabled={busy} onClick={onRetryFailed}>Retry failed chapters</Button>
          </div>
          <details>
            <summary className="cursor-pointer">Failure details</summary>
            {failedItems.map((item) => <p key={item.filename} className="mt-2 whitespace-pre-wrap break-words"><strong>{item.title}: </strong>{item.message || "Translation failed."}</p>)}
          </details>
        </div>
      )}
      <div ref={viewport} onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)} className="h-56 min-w-0 overflow-auto rounded-lg border bg-background max-[980px]:h-72" aria-label="Chapter list">
        <Table className="table-fixed" aria-rowcount={visibleChapters.length + 1}>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">Use</TableHead>
              <TableHead>Chapter</TableHead>
              <TableHead className="w-24 text-right sm:w-28">State</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {firstRow > 0 && <tr aria-hidden="true"><td colSpan={3} style={{ height: firstRow * rowHeight, padding: 0 }} /></tr>}
            {renderedChapters.map((chapter, offset) => {
              const item = itemsByFile.get(chapter.filename);
              const isOpen = selectedFile === chapter.filename;
              return (
                <TableRow
                  key={chapter.filename}
                  data-chapter-index={firstRow + offset}
                  aria-rowindex={firstRow + offset + 2}
                  style={{ height: rowHeight }}
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
                    <a
                      href={translatePath(novel, chapter.filename)}
                      title={chapter.title}
                      aria-current={isOpen ? "page" : undefined}
                      onClick={(event) => {
                        event.stopPropagation();
                        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                        event.preventDefault();
                        onOpen(chapter.filename);
                      }}
                      onKeyDown={(event) => {
                        const index = firstRow + offset;
                        const target = event.key === "ArrowDown" ? index + 1 : event.key === "ArrowUp" ? index - 1 : event.key === "Home" ? 0 : event.key === "End" ? visibleChapters.length - 1 : null;
                        if (target !== null) { event.preventDefault(); focusChapter(target); }
                      }}
                      className={cn(
                        "block truncate rounded-sm text-sm font-medium focus-visible:outline-2 focus-visible:outline-primary",
                        isOpen && "text-teal-800 dark:text-teal-300"
                      )}
                    >
                      {chapter.title}
                    </a>
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
            {lastRow < visibleChapters.length && <tr aria-hidden="true"><td colSpan={3} style={{ height: (visibleChapters.length - lastRow) * rowHeight, padding: 0 }} /></tr>}
            {visibleChapters.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-sm text-muted-foreground">
                  No chapters match your search.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
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
    <footer className="fixed inset-x-0 bottom-0 z-30 mx-auto grid min-w-0 max-w-6xl grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-2 border-t bg-background/95 px-3 py-3 shadow-[0_-8px_24px_rgba(15,23,42,0.12)] backdrop-blur sm:px-4">
      <Button
        type="button"
        variant="outline"
        className="min-h-10 min-w-0 justify-start gap-2 whitespace-normal"
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
        className="min-h-10 min-w-0 justify-end gap-2 whitespace-normal"
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
  novel,
  title,
  subtitle,
  tab,
  ready,
  source,
  translated,
  resetKey,
  onTabChange,
}: {
  novel: string;
  title?: string;
  subtitle: string;
  tab: ReaderTab;
  ready: boolean;
  source: string;
  translated: string;
  resetKey: string;
  onTabChange: (tab: ReaderTab) => void;
}) {
  const value = tab === "raw" ? source : translated;
  const readerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!novel || !resetKey || !ready) return;
    const progress = getReadingProgress(novel);
    const scrollTop = progress?.chapter === resetKey ? progress.scrollTop : 0;
    const frame = requestAnimationFrame(() => {
      const reader = readerRef.current;
      if (!reader) return;
      const readerTop = reader.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: readerTop + scrollTop });
    });
    return () => cancelAnimationFrame(frame);
  }, [novel, ready, resetKey]);

  useEffect(() => {
    if (!novel || !resetKey || !ready) return;
    let frame = 0;
    const saveScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const reader = readerRef.current;
        if (!reader) return;
        const readerTop = reader.getBoundingClientRect().top + window.scrollY;
        saveReadingProgress(novel, {
          chapter: resetKey,
          scrollTop: Math.max(0, window.scrollY - readerTop),
        });
      });
    };
    window.addEventListener("scroll", saveScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", saveScroll);
      cancelAnimationFrame(frame);
    };
  }, [novel, ready, resetKey]);

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
