export interface JobHistoryEntry {
  id: string;
  label: string;
  createdAt: number;
  status?: string;
}

const STORAGE_KEY = "ai_vt_job_history";
const MAX_ENTRIES = 20;

// ---------------------------------------------------------------------------
// External-store plumbing so components can read history with
// useSyncExternalStore instead of copying it into state inside an effect.
// ---------------------------------------------------------------------------

const EMPTY: JobHistoryEntry[] = [];
const listeners = new Set<() => void>();
let cachedRaw: string | null = null;
let cachedEntries: JobHistoryEntry[] = EMPTY;

function notify(): void {
  listeners.forEach((l) => l());
}

function write(history: JobHistoryEntry[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  notify();
}

/** Subscribe to history changes in this tab and in other tabs. */
export function subscribeJobHistory(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY || e.key === null) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** Stable snapshot: returns the same array until the stored value changes. */
export function getJobHistorySnapshot(): JobHistoryEntry[] {
  let raw: string | null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    return EMPTY;
  }
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      cachedEntries = raw ? JSON.parse(raw) : EMPTY;
    } catch {
      cachedEntries = EMPTY;
    }
  }
  return cachedEntries;
}

/** Server render has no localStorage: always empty. */
export function getServerJobHistorySnapshot(): JobHistoryEntry[] {
  return EMPTY;
}

// ---------------------------------------------------------------------------
// Read / write helpers
// ---------------------------------------------------------------------------

export function getJobHistory(): JobHistoryEntry[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export function addJobToHistory(entry: JobHistoryEntry): void {
  const history = getJobHistory().filter((e) => e.id !== entry.id);
  history.unshift(entry);
  write(history.slice(0, MAX_ENTRIES));
}

export function updateJobStatus(id: string, status: string): void {
  const history = getJobHistory();
  const idx = history.findIndex((e) => e.id === id);
  if (idx !== -1 && history[idx].status !== status) {
    history[idx].status = status;
    write(history);
  }
}

export function removeJobFromHistory(id: string): void {
  write(getJobHistory().filter((e) => e.id !== id));
}

export function clearJobHistory(): void {
  localStorage.removeItem(STORAGE_KEY);
  notify();
}

export function removeStaleEntries(existingIds: Set<string>): void {
  write(getJobHistory().filter((e) => existingIds.has(e.id)));
}
