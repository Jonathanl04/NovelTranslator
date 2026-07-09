import { useState } from "react";
import {
  ArrowDownAZ,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  Link,
  LogOut,
  Search,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { NovelMetadata, QidianAuthState, ScrapeState } from "@/types";
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
  qidianAuth,
  onQueryChange,
  onSortChange,
  onPageChange,
  onScrapeUrlChange,
  onScrapeStartChange,
  onScrapeEndChange,
  onScrape,
  onUseSourceUrl,
  onSelect,
  onDelete,
  onQidianSaveCookies,
  onQidianLogout,
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
  qidianAuth: QidianAuthState;
  onQueryChange: (value: string) => void;
  onSortChange: (value: "name" | "recent") => void;
  onPageChange: (page: number) => void;
  onScrapeUrlChange: (value: string) => void;
  onScrapeStartChange: (value: string) => void;
  onScrapeEndChange: (value: string) => void;
  onScrape: () => void;
  onUseSourceUrl: (novelName: string, sourceUrl: string) => void;
  onSelect: (novel: string) => void;
  onDelete: (novel: string) => void;
  onQidianSaveCookies: (cookieStr: string) => void;
  onQidianLogout: () => void;
}) {
  const scrapeBusy = scrapeState.running;
  const progressValue =
    scrapeState.total > 0 ? Math.min(100, Math.round((scrapeState.current / scrapeState.total) * 100)) : 0;
  const isQidianUrl = /^https?:\/\/(www\.)?qidian\.com\//i.test(scrapeUrl);

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
          {isQidianUrl && (
            <QidianLoginPanel
              auth={qidianAuth}
              onSaveCookies={onQidianSaveCookies}
              onLogout={onQidianLogout}
            />
          )}
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
                onDelete={() => onDelete(name)}
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

function QidianLoginPanel({
  auth,
  onSaveCookies,
  onLogout,
}: {
  auth: QidianAuthState;
  onSaveCookies: (cookieStr: string) => void;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [cookieStr, setCookieStr] = useState("");

  function handleSave() {
    onSaveCookies(cookieStr.trim());
    setCookieStr("");
    setOpen(false);
  }

  return (
    <div className="grid gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-muted-foreground">Qidian login</span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-xs font-medium",
            auth.logged_in
              ? "bg-teal-100 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300"
              : "bg-muted text-muted-foreground"
          )}
        >
          {auth.logged_in ? "Logged in" : "Not logged in"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {auth.logged_in ? (
            <Button type="button" variant="outline" size="sm" onClick={onLogout}>
              <LogOut />
              Log out
            </Button>
          ) : (
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen((v) => !v)}>
              {open ? "Cancel" : "Paste cookies"}
            </Button>
          )}
        </div>
      </div>
      {open && !auth.logged_in && (
        <div className="grid gap-2">
          <p className="text-xs text-muted-foreground">
            Log in to{" "}
            <strong>qidian.com</strong>{" "}
            in your browser, then open DevTools → Console and run{" "}
            <code className="rounded bg-muted px-1 font-mono">document.cookie</code>.
            Copy the output and paste it below.
          </p>
          <textarea
            className="min-h-20 w-full rounded-md border bg-background px-3 py-2 font-mono text-xs outline-none focus:ring-1 focus:ring-ring"
            placeholder="ywguid=...; ywkey=...; ..."
            value={cookieStr}
            onChange={(e) => setCookieStr(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!cookieStr.trim()}
            onClick={handleSave}
          >
            Save cookies
          </Button>
        </div>
      )}
    </div>
  );
}

function BookCard({
  name,
  metadata,
  selected,
  onSelect,
  onDelete,
  onUseSourceUrl,
}: {
  name: string;
  metadata?: NovelMetadata;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
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
      <div className="grid grid-cols-[1fr_auto] gap-2">
        {onUseSourceUrl ? (
          <Button type="button" variant="outline" size="sm" onClick={onUseSourceUrl}>
            <Link />
            Use Link
          </Button>
        ) : (
          <div />
        )}
        <Button type="button" variant="outline" size="icon" onClick={onDelete} title="Delete book" aria-label={`Delete ${displayName}`}>
          <Trash2 />
        </Button>
      </div>
    </div>
  );
}
