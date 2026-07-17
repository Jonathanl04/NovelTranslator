import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api";
import type { BulkItem, BulkTranslationState, Chapter, Usage } from "@/types";

type Options = {
  novel: string;
  selectedFile: string;
  onStatus: (message: string, isError?: boolean) => void;
  onChapters: (chapters: Chapter[]) => void;
  onUsage: (usage: Usage) => void;
  onGlossaryRefresh: () => Promise<void>;
  onSelectedChapterRefresh: () => Promise<void>;
  onMetadataRefresh: () => Promise<void>;
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

  const applyState = useCallback((state: BulkTranslationState) => {
    previous.current = state;
    setItems(state.items);
    setRunning(state.running);
    setAborted(state.aborted);
    setSelection(selectionFor(state.items));
  }, []);

  const load = useCallback(async (nextNovel: string, isCurrent: () => boolean = () => true) => {
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
    if (!isCurrent()) return;
    applyState(state);
    if (state.aborted) onStatus("Bulk translation aborted.");
    else if (state.running) onStatus(progress(state));
  }, [applyState, onStatus]);

  const refresh = useCallback(async (state: BulkTranslationState, previousState: BulkTranslationState | null) => {
    const changed = !previousState || JSON.stringify(previousState.items) !== JSON.stringify(state.items);
    const finished = previousState?.running && !state.running;
    if (!changed && !finished) return;
    const [chapters, usage] = await Promise.all([api.chapters(novel), api.usage()]);
    onChapters(chapters);
    onUsage(usage);
    if (state.items.some((item) => item.status === "done" || item.status === "failed" || item.status === "aborted")) {
      await onGlossaryRefresh();
    }
    if (state.items.some((item) => item.mode === "name" && item.status === "done")) await onMetadataRefresh();
    if (selectedFile && state.items.some((item) => item.filename === selectedFile && item.status === "done")) {
      await onSelectedChapterRefresh();
    }
    if (finished) {
      onStatus(
        state.aborted ? "Bulk translation aborted." : state.items.some((item) => item.status === "failed") ? "Bulk translation stopped after a failure." : "Bulk translation complete.",
        state.items.some((item) => item.status === "failed")
      );
    }
  }, [novel, onChapters, onGlossaryRefresh, onMetadataRefresh, onSelectedChapterRefresh, onStatus, onUsage, selectedFile]);

  useEffect(() => {
    if (!novel || !running) return;
    const interval = window.setInterval(() => {
      api.bulkTranslation(novel).then(async (state) => {
        const previousState = previous.current;
        applyState(state);
        if (state.running) onStatus(progress(state));
        await refresh(state, previousState);
      }).catch((error: unknown) => onStatus(error instanceof Error ? error.message : String(error), true));
    }, 1500);
    return () => window.clearInterval(interval);
  }, [applyState, novel, onStatus, refresh, running]);

  const start = useCallback(async (queue: BulkItem[]) => {
    if (!novel || running || manualBusy) return;
    setItems(queue);
    setSelection(new Set(queue.map((item) => item.filename)));
    setManualBusy(true);
    onStatus(`Translating ${queue.length} ${queue.length === 1 ? "chapter" : "chapters"}...`);
    try {
      const state = await api.startBulkTranslation(novel, queue);
      applyState(state);
      if (!state.running) setSelection(new Set());
      onStatus(progress(state));
    } finally {
      setManualBusy(false);
    }
  }, [applyState, manualBusy, novel, onStatus, running]);

  const abort = useCallback(async () => {
    if (!novel || !running) return;
    const state = await api.abortBulkTranslation(novel);
    const previousState = previous.current;
    applyState(state);
    onStatus("Bulk translation aborted.");
    await refresh(state, previousState);
  }, [applyState, novel, onStatus, refresh, running]);

  const clear = useCallback(() => {
    previous.current = null;
    setItems([]);
    setRunning(false);
    setAborted(false);
    setSelection(new Set());
  }, []);

  return { aborted, abort, clear, items, load, manualBusy, running, selection, setSelection, start };
}
