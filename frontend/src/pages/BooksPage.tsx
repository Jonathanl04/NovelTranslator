import {
  ArrowDownAZ,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  Link,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { NovelMetadata, ScrapeState } from "@/types";
import { formatInteger } from "./shared";

export function BooksPage({
  novels,
  allCount,
  filteredCount,
  metadataByName,
  selectedNovel,
  query,
  sort,
  page,
  pageCount,
  scrapeUrl,
  scrapeStart,
  scrapeEnd,
  scrapeState,
  onQueryChange,
  onSortChange,
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
  sort: "name" | "recent";
  page: number;
  pageCount: number;
  scrapeUrl: string;
  scrapeStart: string;
  scrapeEnd: string;
  scrapeState: ScrapeState;
  onQueryChange: (value: string) => void;
  onSortChange: (value: "name" | "recent") => void;
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
                placeholder="https://twkan.com/book/92274.html"
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
          <div className="flex w-full max-w-md items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0"
              onClick={() => onSortChange(sort === "recent" ? "name" : "recent")}
              title={sort === "recent" ? "Sorting by most recently updated" : "Sorting by name"}
            >
              {sort === "recent" ? <Clock /> : <ArrowDownAZ />}
              {sort === "recent" ? "Recent" : "Name"}
            </Button>
            <div className="relative flex-1">
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
