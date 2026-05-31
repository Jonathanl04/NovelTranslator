import {
  BookOpen,
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
  chapters: Chapter[];
  visibleChapters: Chapter[];
  search: string;
  selectedFile: string;
  selection: Set<string>;
  itemsByFile: Map<string, BulkItem>;
  itemsTotal: number;
  counts: { done: number; failed: number; pending: number; translating: number };
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
  onReaderTabChange: (tab: ReaderTab) => void;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] bg-muted/20">
      <section className="mx-auto grid min-h-[calc(100vh-3.5rem)] w-full max-w-6xl grid-rows-[auto_auto_minmax(0,1fr)] gap-4 p-4 pb-0">
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
        />

        <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-4">
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
    <section className="grid gap-3 rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-center gap-3">
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
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onChooseBook}>
            <Library />
            Choose Book
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={!canExport || busy} onClick={onExport}>
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
}: {
  busy: boolean;
  chapters: Chapter[];
  visibleChapters: Chapter[];
  search: string;
  onSearchChange: (value: string) => void;
  selectedFile: string;
  selection: Set<string>;
  itemsByFile: Map<string, BulkItem>;
  itemsTotal: number;
  counts: { done: number; failed: number; pending: number; translating: number };
  untranslatedCount: number;
  onOpen: (filename: string) => void;
  onToggle: (filename: string, checked: boolean) => void;
  onSelectUntranslated: () => void;
  onSelectFromCurrent: () => void;
  onClear: () => void;
  onTranslate: (mode: "full" | "only") => void;
}) {
  const selectedCount = selection.size;
  const summary =
    itemsTotal > 0
      ? [
          `${counts.done}/${itemsTotal} done`,
          counts.translating ? `${counts.translating} active` : "",
          counts.pending ? `${counts.pending} pending` : "",
          counts.failed ? `${counts.failed} failed` : "",
        ]
          .filter(Boolean)
          .join(" · ")
      : `${untranslatedCount} new`;
  const target = selectedCount > 0 ? `${selectedCount} selected` : "current chapter";
  const canTranslate = !busy && (selectedCount > 0 || Boolean(selectedFile));

  return (
    <section className="grid gap-3 rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Chapters</h2>
          <div className="text-xs text-muted-foreground">{summary}</div>
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
          <Button type="button" variant="outline" size="sm" onClick={() => onTranslate("only")} disabled={!canTranslate}>
            <Check />
            Translate Only
          </Button>
          <Button type="button" size="sm" onClick={() => onTranslate("full")} disabled={!canTranslate}>
            <WandSparkles />
            Translate + Glossary
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={search}
            placeholder="Search chapters..."
            className="bg-background pl-9"
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
        <span className="text-xs text-muted-foreground">
          Translate target: <span className="font-medium text-foreground">{target}</span>
        </span>
      </div>
      <ScrollArea className="h-56 rounded-lg border bg-background max-[980px]:h-72">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">Use</TableHead>
              <TableHead>Chapter</TableHead>
              <TableHead className="w-28 text-right">State</TableHead>
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

function ReaderPanel({
  title,
  subtitle,
  tab,
  source,
  translated,
  onTabChange,
}: {
  title?: string;
  subtitle: string;
  tab: ReaderTab;
  source: string;
  translated: string;
  onTabChange: (tab: ReaderTab) => void;
}) {
  const value = tab === "raw" ? source : translated;

  return (
    <div className="grid min-h-0 grid-rows-[auto_auto_1fr] gap-3">
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
      <Textarea value={value} readOnly className="h-full min-h-64 resize-none whitespace-pre-wrap bg-background font-serif leading-relaxed" />
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
