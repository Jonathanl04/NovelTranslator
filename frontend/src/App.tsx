import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, ChevronLeft, ChevronRight, Plus, Save, Trash2, WandSparkles } from "lucide-react";
import { api } from "./api";
import type { Chapter, Config, GlossaryEntry, Model } from "./types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent } from "@/components/ui/collapsible";
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

const emptyConfig: Config = {
  has_api_key: false,
  api_key_mask: "",
  translation_model: "deepseek-v4-flash",
  glossary_model: "deepseek-v4-flash",
};

export function App() {
  const [config, setConfig] = useState<Config>(emptyConfig);
  const [apiKey, setApiKey] = useState("");
  const [novels, setNovels] = useState<string[]>([]);
  const [novel, setNovel] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [source, setSource] = useState("");
  const [translated, setTranslated] = useState("");
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [dictionaryOpen, setDictionaryOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState(false);

  const dictionaryCount = useMemo(() => glossary.length, [glossary]);

  const showStatus = useCallback((message: string, isError = false) => {
    setStatus(message);
    setError(isError);
  }, []);

  const loadGlossary = useCallback(
    async (nextNovel: string) => {
      if (!nextNovel) {
        setGlossary([]);
        return;
      }
      setGlossary(await api.glossary(nextNovel));
    },
    []
  );

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
      await loadGlossary(nextNovel);
      if (!nextNovel) {
        setChapters([]);
        return;
      }
      const nextChapters = await api.chapters(nextNovel);
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
        const [nextConfig, nextNovels] = await Promise.all([api.config(), api.novels()]);
        if (!active) return;
        setConfig(nextConfig);
        setNovels(nextNovels);
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
      setTranslated(result.translated);
      setGlossary(result.glossary);
      const file = result.filename;
      await loadChapters(novel);
      await selectChapter(novel, file);
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

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between gap-4 border-b bg-background px-5">
        <div className="flex items-center gap-2">
          <BookOpen className="size-5 text-emerald-700" />
          <h1 className="text-base font-semibold">Novel Translator</h1>
        </div>
        <div className={cn("min-w-0 text-sm text-muted-foreground", error && "text-destructive")}>{status}</div>
      </header>

      <main
        className={cn(
          "grid min-h-[calc(100vh-3.5rem)] grid-cols-[300px_minmax(0,1fr)_380px]",
          !dictionaryOpen && "grid-cols-[300px_minmax(0,1fr)_150px]",
          "max-[1100px]:grid-cols-[280px_minmax(0,1fr)]"
        )}
      >
        <aside className="grid min-w-0 content-start gap-3 border-r p-4">
          <div className="grid gap-1.5">
            <Label htmlFor="api-key">DeepSeek API key</Label>
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <Input
                id="api-key"
                type="password"
                value={apiKey}
                placeholder={config.has_api_key ? config.api_key_mask : ""}
                autoComplete="off"
                onChange={(event) => setApiKey(event.target.value)}
              />
              <Button type="button" onClick={saveConfig}>
                <Save />
                Save
              </Button>
            </div>
          </div>

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

          <div className="grid gap-1.5">
            <Label>Novel</Label>
            <Select value={novel} onValueChange={(value) => loadChapters(value).catch((caught) => showStatus(errorMessage(caught), true))}>
              <SelectTrigger className="w-full">
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

          <Button type="button" disabled={busy || !selectedFile} onClick={() => runTranslation("full")}>
            <WandSparkles />
            Translate Selected Chapter
          </Button>
          <Button type="button" variant="outline" disabled={busy || !selectedFile} onClick={() => runTranslation("only")}>
            Translate Only
          </Button>

          <ScrollArea className="mt-1 h-[calc(100vh-16.25rem)] pr-2">
            <div className="grid gap-1.5">
              {chapters.map((chapter) => (
                <Button
                  key={chapter.filename}
                  type="button"
                  variant="outline"
                  className={cn(
                    "h-fit min-h-9 justify-between gap-2 whitespace-normal px-2.5 py-2 text-left font-medium",
                    selectedFile === chapter.filename && "border-emerald-600 ring-2 ring-emerald-100"
                  )}
                  onClick={() => selectChapter(novel, chapter.filename).catch((caught) => showStatus(errorMessage(caught), true))}
                >
                  <span className="min-w-0 [overflow-wrap:anywhere] leading-tight">{chapter.title}</span>
                  <Badge variant={chapter.translated ? "secondary" : "outline"} className={chapter.translated ? "bg-emerald-50 text-emerald-800" : ""}>
                    {chapter.translated ? "done" : "new"}
                  </Badge>
                </Button>
              ))}
            </div>
          </ScrollArea>
        </aside>

        <section className="min-w-0 p-4">
          <div className="grid h-[calc(100vh-5.5rem)] min-h-0 grid-cols-2 gap-3 max-[760px]:h-auto max-[760px]:grid-cols-1">
            <Reader label="Source" value={source} />
            <Reader label="Translation" value={translated} />
          </div>
        </section>

        <section className="grid min-w-0 content-start gap-3 border-l p-4 max-[1100px]:col-span-2 max-[1100px]:border-l-0 max-[1100px]:border-t">
          <Collapsible open={dictionaryOpen} onOpenChange={setDictionaryOpen}>
            <div
              className={cn(
                "grid items-start gap-2",
                dictionaryOpen ? "grid-cols-[1fr_auto]" : "grid-cols-1"
              )}
            >
              <div className="min-w-0">
                <h2 className="text-sm font-semibold">Dictionary</h2>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {dictionaryCount} {dictionaryCount === 1 ? "word" : "words"}
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={cn(!dictionaryOpen && "w-full justify-center")}
                onClick={() => setDictionaryOpen((open) => !open)}
              >
                {dictionaryOpen ? <ChevronRight /> : <ChevronLeft />}
                {dictionaryOpen ? "Collapse" : "Expand"}
              </Button>
            </div>

            <CollapsibleContent className="mt-3 grid gap-3">
              <div className="grid grid-cols-2 gap-2">
                <Button type="button" variant="outline" onClick={addGlossaryEntry}>
                  <Plus />
                  Add Entry
                </Button>
                <Button type="button" onClick={saveGlossary}>
                  <Save />
                  Save Glossary
                </Button>
              </div>

              <ScrollArea className="h-[calc(100vh-13rem)] rounded-lg border">
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
                        <TableCell className="min-w-36">
                          <Input value={entry.source_term} onChange={(event) => updateGlossaryEntry(index, { source_term: event.target.value })} />
                        </TableCell>
                        <TableCell className="min-w-40">
                          <Input value={entry.english_term} onChange={(event) => updateGlossaryEntry(index, { english_term: event.target.value })} />
                        </TableCell>
                        <TableCell className="min-w-36">
                          <Input value={entry.category} onChange={(event) => updateGlossaryEntry(index, { category: event.target.value })} />
                        </TableCell>
                        <TableCell className="min-w-32">
                          <Select
                            value={entry.gender_or_pronoun || "__none__"}
                            onValueChange={(value) => updateGlossaryEntry(index, { gender_or_pronoun: value === "__none__" ? "" : value })}
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
                          <Button type="button" variant="destructive" size="icon" onClick={() => removeGlossaryEntry(index)} aria-label="Remove entry">
                            <Trash2 />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            </CollapsibleContent>
          </Collapsible>
        </section>
      </main>
    </div>
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
        <SelectTrigger id={id} className="w-full">
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

function Reader({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-h-0 grid-rows-[auto_1fr] gap-2">
      <Label>{label}</Label>
      <Textarea value={value} readOnly className="h-full min-h-0 resize-none whitespace-pre-wrap font-serif leading-relaxed" />
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
