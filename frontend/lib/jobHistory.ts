export interface JobHistoryEntry {
  id: string;
  label: string;
  createdAt: number;
  status?: string;
}

const STORAGE_KEY = "ai_vt_job_history";
const MAX_ENTRIES = 20;

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
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(0, MAX_ENTRIES)));
}

export function updateJobStatus(id: string, status: string): void {
  const history = getJobHistory();
  const idx = history.findIndex((e) => e.id === id);
  if (idx !== -1) {
    history[idx].status = status;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  }
}

export function removeJobFromHistory(id: string): void {
  const history = getJobHistory().filter((e) => e.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
}

export function clearJobHistory(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function removeStaleEntries(existingIds: Set<string>): void {
  const history = getJobHistory().filter((e) => existingIds.has(e.id));
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
}
