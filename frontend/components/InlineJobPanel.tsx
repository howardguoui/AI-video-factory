"use client";

import { useEffect, useState } from "react";
import { getJob, getFileUrl, type JobResponse } from "@/lib/api";
import { updateJobStatus } from "@/lib/jobHistory";
import { JobStatus } from "@/components/JobStatus";
import { VideoPlayer } from "@/components/VideoPlayer";

interface InlineJobPanelProps {
  jobId: string;
  onNewJob: () => void;
}

export function InlineJobPanel({ jobId, onNewJob }: InlineJobPanelProps) {
  const [job, setJob] = useState<JobResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    async function poll() {
      try {
        const data = await getJob(jobId);
        setJob(data);
        updateJobStatus(jobId, data.status);
        if (data.status === "done" || data.status === "failed") {
          clearInterval(interval);
        }
      } catch (err) {
        setFetchError(err instanceof Error ? err.message : "Failed to fetch job status.");
        clearInterval(interval);
      }
    }

    const interval = setInterval(poll, 2000);
    poll();
    return () => clearInterval(interval);
  }, [jobId]);

  const isDone = job?.status === "done";
  const outputUrl = isDone ? getFileUrl(jobId, "output.mp4") : null;
  const bilingualUrl = job?.bilingual_download ? getFileUrl(jobId, "bilingual_with_subs.mp4") : null;

  const subtitles = isDone ? [
    ...(job.source_vtt ? [{ src: getFileUrl(jobId, "source.vtt"), label: "Original", srcLang: "orig" }] : []),
    ...(job.translated_vtt ? [{ src: getFileUrl(jobId, "translated.vtt"), label: "Translation", srcLang: job.target_lang, default: true }] : []),
  ] : [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">
            Translation Job
          </h2>
          {job?.label && (
            <p className="text-white text-sm mt-0.5 truncate max-w-sm">{job.label}</p>
          )}
        </div>
        <button
          onClick={onNewJob}
          className="flex items-center gap-1.5 text-sm text-indigo-400 hover:text-indigo-300 bg-zinc-800 border border-zinc-700 px-3 py-1.5 rounded-lg transition-colors"
        >
          ← New Translation
        </button>
      </div>

      {/* Job metadata badges */}
      {job && (
        <div className="flex flex-wrap gap-2">
          {job.tts_engine && job.tts_engine !== "stub" && (
            <span className="text-xs bg-zinc-800 border border-zinc-700 text-zinc-400 px-2.5 py-1 rounded-lg">
              TTS: {job.tts_engine}
            </span>
          )}
          {job.llm_model && (
            <span className="text-xs bg-zinc-800 border border-zinc-700 text-zinc-400 px-2.5 py-1 rounded-lg truncate max-w-[200px]">
              LLM: {job.llm_model}
            </span>
          )}
          {job.pipeline_mode && (
            <span className="text-xs bg-zinc-800 border border-zinc-700 text-zinc-400 px-2.5 py-1 rounded-lg">
              {job.pipeline_mode === "dubbing" ? "Full Dubbing" : "Subtitles Only"}
            </span>
          )}
          <span className="text-xs bg-zinc-800 border border-zinc-700 text-zinc-500 px-2.5 py-1 rounded-lg font-mono">
            {jobId.slice(0, 8)}…
          </span>
        </div>
      )}

      {/* Fetch error */}
      {fetchError && (
        <div className="bg-red-950 border border-red-800 rounded-xl p-4 text-red-400 text-sm">
          {fetchError}
        </div>
      )}

      {/* Status panel */}
      {job ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
          <JobStatus
            status={job.status}
            pipeline_mode={job.pipeline_mode}
            step_progress={job.step_progress}
            step_detail={job.step_detail}
            error={job.error}
          />
        </div>
      ) : !fetchError ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 text-zinc-400 text-sm animate-pulse">
          Loading job status…
        </div>
      ) : null}

      {/* Result */}
      {outputUrl && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
          <h3 className="text-white font-semibold">Result</h3>
          <VideoPlayer src={outputUrl} subtitles={subtitles} />
          <div className="flex gap-3">
            <a
              href={bilingualUrl ?? outputUrl}
              download="translated-bilingual.mp4"
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 text-center bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
            >
              Download with Bilingual Subtitles
            </a>
            <button
              type="button"
              disabled
              title="Video editor coming in a future update"
              className="px-4 py-3 bg-zinc-800 border border-zinc-700 text-zinc-500 rounded-xl text-sm font-medium cursor-not-allowed"
            >
              Edit Video
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
