import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api";
import type { BulkItem, BulkTranslationState, Chapter, Usage } from "@/types";

type Options = {
  novel: string;
  selectedFile: string;
  onStatus: (message: string, isError?: boolean) => void;
  onChapters: (chapters: Chapter[]) => void;
  onUsage: (usage: Usage) => void;
  onGlossaryRefresh: (isCurrent: () => boolean) => Promise<void>;
  onSelectedChapterRefresh: (isCurrent: () => boolean) => Promise<void>;
  onMetadataRefresh: (isCurrent: () => boolean) => Promise<void>;
};

function selectionFor(items: BulkItem[]) {
  return new Set(
    items
      .filter((item) => item.status === "pending" || item.status === "translating")
      .filter((item) => item.mode !== "name")
      .map((item) => item.filename)
  );
}

function progress(state: BulkTranslationState) {
  const current = state.items.filter((item) => item.status === "done" || item.status === "failed").length;
  return `Translating ${current}/${state.items.length} chapters...`;
}

export function useBulkTranslation({
  novel,
  selectedFile,
  onStatus,
  onChapters,
  onUsage,
  onGlossaryRefresh,
  onSelectedChapterRefresh,
  onMetadataRefresh,
}: Options) {
  const [items, setItems] = useState<BulkItem[]>([]);
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [running, setRunning] = useState(false);
  const [aborted, setAborted] = useState(false);
  const [manualBusy, setManualBusy] = useState(false);
  const previous = useRef<BulkTranslationState | null>(null);
  const generation = useRef(0);

  const currentRequest = useCallback(() => {
    const requestGeneration = generation.current;
    return () => generation.current === requestGeneration;
  }, []);

  useEffect(() => () => { generation.current += 1; }, []);

  const applyState = useCallback((state: BulkTranslationState) => {
    previous.current = state;
    setItems(state.items);
    setRunning(state.running);
    setAborted(state.aborted);
    setSelection(selectionFor(state.items));
  }, []);

  const load = useCallback(async (nextNovel: string, isCurrent: () => boolean = () => true) => {
    generation.current += 1;
    const requestIsCurrent = currentRequest();
    setManualBusy(false);
    if (!nextNovel) {
      if (!isCurrent()) return;
      previous.current = null;
      setItems([]);
      setRunning(false);
      setAborted(false);
      setSelection(new Set());
      return;
    }
    const state = await api.bulkTranslation(nextNovel);
    if (!isCurrent() || !requestIsCurrent()) return;
    applyState(state);
    if (state.aborted) onStatus("Bulk translation aborted.");
    else if (state.running) onStatus(progress(state));
  }, [applyState, currentRequest, onStatus]);

  const refresh = useCallback(async (state: BulkTranslationState, previousState: BulkTranslationState | null, isCurrent: () => boolean) => {
    const changed = !previousState || JSON.stringify(previousState.items) !== JSON.stringify(state.items);
    const finished = previousState?.running && !state.running;
    if (!changed && !finished) return;
    const [chapters, usage] = await Promise.all([api.chapters(novel), api.usage()]);
    if (!isCurrent()) return;
    onChapters(chapters);
    onUsage(usage);
    if (state.items.some((item) => item.status === "done" || item.status === "failed" || item.status === "aborted")) {
      await onGlossaryRefresh(isCurrent);
    }
    if (!isCurrent()) return;
    if (state.items.some((item) => item.mode === "name" && item.status === "done")) await onMetadataRefresh(isCurrent);
    if (!isCurrent()) return;
    if (selectedFile && state.items.some((item) => item.filename === selectedFile && item.status === "done")) {
      await onSelectedChapterRefresh(isCurrent);
    }
    if (!isCurrent()) return;
    if (finished) {
      onStatus(
        state.aborted ? "Bulk translation aborted." : state.items.some((item) => item.status === "failed") ? "Bulk translation stopped after a failure." : "Bulk translation complete.",
        state.items.some((item) => item.status === "failed")
      );
    }
  }, [novel, onChapters, onGlossaryRefresh, onMetadataRefresh, onSelectedChapterRefresh, onStatus, onUsage, selectedFile]);

  useEffect(() => {
    if (!novel || !running) return;
    let active = true;
    let pending = false;
    const isCurrent = currentRequest();
    const interval = window.setInterval(() => {
      if (pending || !isCurrent()) return;
      pending = true;
      api.bulkTranslation(novel).then(async (state) => {
        if (!active || !isCurrent()) return;
        const previousState = previous.current;
        applyState(state);
        if (state.running) onStatus(progress(state));
        await refresh(state, previousState, isCurrent);
      }).catch((error: unknown) => {
        if (active && isCurrent()) onStatus(error instanceof Error ? error.message : String(error), true);
      }).finally(() => { pending = false; });
    }, 1500);
    return () => { active = false; window.clearInterval(interval); };
  }, [applyState, currentRequest, novel, onStatus, refresh, running]);

  const start = useCallback(async (queue: BulkItem[]) => {
    if (!novel || running || manualBusy) return;
    const isCurrent = currentRequest();
    setItems(queue);
    setSelection(new Set(queue.map((item) => item.filename)));
    setManualBusy(true);
    onStatus(`Translating ${queue.length} ${queue.length === 1 ? "chapter" : "chapters"}...`);
    try {
      const state = await api.startBulkTranslation(novel, queue);
      if (!isCurrent()) return;
      applyState(state);
      if (!state.running) setSelection(new Set());
      onStatus(progress(state));
    } catch (error) {
      if (isCurrent()) throw error;
    } finally {
      if (isCurrent()) setManualBusy(false);
    }
  }, [applyState, currentRequest, manualBusy, novel, onStatus, running]);

  const abort = useCallback(async () => {
    if (!novel || !running) return;
    const isCurrent = currentRequest();
    try {
      const state = await api.abortBulkTranslation(novel);
      if (!isCurrent()) return;
      const previousState = previous.current;
      applyState(state);
      onStatus("Bulk translation aborted.");
      await refresh(state, previousState, isCurrent);
    } catch (error) {
      if (isCurrent()) throw error;
    }
  }, [applyState, currentRequest, novel, onStatus, refresh, running]);

  const clear = useCallback(() => {
    generation.current += 1;
    setManualBusy(false);
    previous.current = null;
    setItems([]);
    setRunning(false);
    setAborted(false);
    setSelection(new Set());
  }, []);

  return { aborted, abort, clear, items, load, manualBusy, running, selection, setSelection, start };
}
