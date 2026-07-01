import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Plus, Save, Search, Trash2 } from "lucide-react";
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
import type { GlossaryEntry } from "@/types";
import { formatInteger } from "./shared";

const PRONOUNS = ["__none__", "male", "female", "unknown", "it"];
const GLOSSARY_ENTRIES_PER_PAGE = 20;

export function GlossaryPage({
  glossary,
  novel,
  onAdd,
  onRemove,
  onSave,
  onUpdate,
}: {
  glossary: GlossaryEntry[];
  novel: string;
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
    <main className="min-h-[calc(100vh-3.5rem)] min-w-0 overflow-x-hidden bg-muted/20">
      <section className="mx-auto grid min-h-[calc(100vh-3.5rem)] max-w-6xl min-w-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] gap-4 p-3 sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Glossary</h2>
            <div className="text-sm text-muted-foreground">
              {novel || "No novel selected"} · {glossary.length} {glossary.length === 1 ? "entry" : "entries"}
            </div>
          </div>
          <div className="flex min-w-0 flex-wrap gap-2 max-[520px]:grid max-[520px]:w-full max-[520px]:grid-cols-2">
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
          <div className="relative min-w-0 flex-1 max-[520px]:basis-full sm:min-w-64">
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

        <ScrollArea className="min-h-0 min-w-0 overflow-hidden rounded-lg border bg-background max-[760px]:hidden">
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

        <div className="grid min-w-0 gap-3 min-[761px]:hidden">
          {visibleGlossary.map(({ entry, index }) => (
            <section key={index} className="grid min-w-0 gap-3 rounded-lg border bg-background p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-sm font-semibold">{entry.source_term || "New glossary entry"}</h3>
                  <p className="text-xs text-muted-foreground">Entry {index + 1}</p>
                </div>
                <Button type="button" variant="destructive" size="icon" onClick={() => onRemove(index)} aria-label="Remove entry">
                  <Trash2 />
                </Button>
              </div>
              <div className="grid min-w-0 gap-3">
                <div className="grid gap-1.5">
                  <Label htmlFor={`glossary-source-${index}`}>Source</Label>
                  <Input
                    id={`glossary-source-${index}`}
                    value={entry.source_term}
                    onChange={(event) => onUpdate(index, { source_term: event.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`glossary-english-${index}`}>English</Label>
                  <Input
                    id={`glossary-english-${index}`}
                    value={entry.english_term}
                    onChange={(event) => onUpdate(index, { english_term: event.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`glossary-category-${index}`}>Category</Label>
                  <Input
                    id={`glossary-category-${index}`}
                    value={entry.category}
                    onChange={(event) => onUpdate(index, { category: event.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`glossary-pronoun-${index}`}>Pronoun</Label>
                  <Select
                    value={entry.gender_or_pronoun || "__none__"}
                    onValueChange={(value) => onUpdate(index, { gender_or_pronoun: value === "__none__" ? "" : value })}
                  >
                    <SelectTrigger id={`glossary-pronoun-${index}`} className="w-full">
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
                </div>
              </div>
            </section>
          ))}
          {visibleGlossary.length === 0 && (
            <section className="rounded-lg border bg-background p-6 text-center text-sm text-muted-foreground">
              No glossary entries match your search.
            </section>
          )}
        </div>

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
