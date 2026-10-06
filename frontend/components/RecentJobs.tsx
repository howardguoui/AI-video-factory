"use client";

import { useEffect, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  getJobHistory,
  getJobHistorySnapshot,
  getServerJobHistorySnapshot,
  subscribeJobHistory,
  updateJobStatus,
  removeJobFromHistory,
  clearJobHistory,
} from "@/lib/jobHistory";
import { getJob } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  done: "text-emerald-400 bg-emerald-950 border-emerald-800",
  failed: "text-red-400 bg-red-950 border-red-800",
  queued: "text-zinc-400 bg-zinc-800 border-zinc-700",
  extracting_audio: "text-sky-400 bg-sky-950 border-sky-800",
  transcribing: "text-sky-400 bg-sky-950 border-sky-800",
  translating: "text-violet-400 bg-violet-950 border-violet-800",
  synthesizing: "text-amber-400 bg-amber-950 border-amber-800",
  muxing: "text-sky-400 bg-sky-950 border-sky-800",
  rendering_downloads: "text-sky-400 bg-sky-950 border-sky-800",
};

const STATUS_LABEL: Record<string, string> = {
  done: "Done",
  failed: "Failed",
  queued: "Queued",
  extracting_audio: "Processing",
  transcribing: "Processing",
  translating: "Processing",
  synthesizing: "Processing",
  muxing: "Processing",
  rendering_downloads: "Processing",
};

function StatusBadge({ status }: { status?: string }) {
  const s = status || "queued";
  const cls = STATUS_COLOR[s] || "text-zinc-400 bg-zinc-800 border-zinc-700";
  const label = STATUS_LABEL[s] || s;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${cls}`}>
      {label}
    </span>
  );
}

interface RecentJobsProps {
  onSelect?: (id: string) => void;
}

export function RecentJobs({ onSelect }: RecentJobsProps = {}) {
  // Read straight from localStorage via an external store: no setState in an
  // effect, no hydration mismatch (server snapshot is empty), and every
  // RecentJobs instance updates when any of them (or another tab) writes.
  const jobs = useSyncExternalStore(
    subscribeJobHistory,
    getJobHistorySnapshot,
    getServerJobHistorySnapshot
  );

  // Poll the backend for jobs still in progress; updateJobStatus notifies the store.
  useEffect(() => {
    const interval = setInterval(() => {
      const active = getJobHistory().filter(
        (e) => e.status !== "done" && e.status !== "failed"
      );
      active.forEach((entry) => {
        getJob(entry.id)
          .then((data) => updateJobStatus(entry.id, data.status))
          .catch(() => {});
      });
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  function handleRemove(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    removeJobFromHistory(id);
  }

  function handleClearAll() {
    clearJobHistory();
  }

  if (jobs.length === 0) return null;

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">
          Recent Jobs
        </h2>
        <button
          onClick={handleClearAll}
          className="text-xs text-zinc-600 hover:text-red-400 transition-colors"
        >
          Clear all
        </button>
      </div>
      <div className="space-y-2">
        {jobs.map((job) => {
          const rowClass = "flex items-center gap-3 bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700/50 rounded-xl px-4 py-3 transition-colors group w-full text-left";
          const inner = (
            <>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-white truncate group-hover:text-indigo-300 transition-colors">
                  {job.label || job.id.slice(0, 8) + "…"}
                </p>
                <p className="text-xs text-zinc-500 mt-0.5">
                  {new Date(job.createdAt).toLocaleString()}
                </p>
              </div>
              {job.status && job.status !== "done" && job.status !== "failed" && job.status !== "queued" && (
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse flex-shrink-0" />
            )}
            <StatusBadge status={job.status} />
              <button
                onClick={(e) => handleRemove(e, job.id)}
                className="text-zinc-700 hover:text-red-400 transition-colors flex-shrink-0 ml-1"
                title="Remove from history"
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </>
          );
          return onSelect ? (
            <button key={job.id} onClick={() => onSelect(job.id)} className={rowClass}>
              {inner}
            </button>
          ) : (
            <Link key={job.id} href={`/jobs/${job.id}`} className={rowClass}>
              {inner}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
