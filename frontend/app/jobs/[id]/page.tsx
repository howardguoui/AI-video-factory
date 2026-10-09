"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { getJob, getFileUrl, type JobResponse } from "@/lib/api";
import { updateJobStatus } from "@/lib/jobHistory";
import { JobStatus } from "@/components/JobStatus";
import { VideoPlayer } from "@/components/VideoPlayer";
import { StageVram } from "@/components/StageVram";

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    async function poll() {
      try {
        const data = await getJob(id);
        setJob(data);
        updateJobStatus(id, data.status);
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
  }, [id]);

  const isDone = job?.status === "done";
  const pipelineMode = job?.pipeline_mode ?? "dubbing";

  const outputUrl = isDone && (pipelineMode === "dubbing" || pipelineMode === "subtitles_only")
    ? getFileUrl(id, "output.mp4")
    : null;
  const mp3Url = isDone && pipelineMode === "mp3_only" ? getFileUrl(id, "output.mp3") : null;
  const bilingualDownloadUrl = job?.bilingual_download ? getFileUrl(id, "bilingual_with_subs.mp4") : null;

  const subtitles = isDone ? [
    ...(job!.source_vtt ? [{ src: getFileUrl(id, "source.vtt"), label: "Original", srcLang: "orig", default: false }] : []),
    ...(job!.translated_vtt ? [{ src: getFileUrl(id, "translated.vtt"), label: "Translation", srcLang: job!.target_lang, default: true }] : []),
  ] : [];

  return (
    <main className="flex-1 bg-zinc-950 p-6 md:p-12">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-sm font-medium text-indigo-400 hover:text-indigo-300 bg-zinc-800 border border-zinc-700 px-3 py-1.5 rounded-lg transition-colors"
          >
            ← New Translation
          </Link>
          <span className="text-zinc-600 text-xs font-mono">{id.slice(0, 8)}…</span>
        </div>

        <div>
          <h1 className="text-2xl font-bold text-white">Translation Job</h1>
          {job?.label && (
            <p className="text-zinc-400 text-sm mt-1 truncate">{job.label}</p>
          )}
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
                {job.pipeline_mode === "dubbing" ? "Full Dubbing"
                  : job.pipeline_mode === "subtitles_only" ? "Subtitles Only"
                  : job.pipeline_mode === "mp3_only" ? "MP3 Audio Only"
                  : job.pipeline_mode === "subtitles_export" ? "Export Subtitles"
                  : job.pipeline_mode === "webpage" ? "Webpage Extraction"
                  : job.pipeline_mode}
              </span>
            )}
          </div>
        )}

        {/* Fetch error */}
        {fetchError && (
          <div className="bg-red-950 border border-red-800 rounded-xl p-4 text-red-400 text-sm">
            {fetchError}
          </div>
        )}

        {/* Status */}
        {job ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
            <JobStatus
              status={job.status}
              pipeline_mode={job.pipeline_mode}
              source_url={job.source_url}
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

        {/* Peak GPU memory per stage (shown while running too, and after a failure) */}
        {job?.stage_vram && <StageVram stages={job.stage_vram} />}

        {/* Video player */}
        {outputUrl && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
            <h2 className="text-white font-semibold">Result</h2>
            <VideoPlayer src={outputUrl} subtitles={subtitles} />

            <div className="flex gap-3">
              <a
                href={bilingualDownloadUrl ?? outputUrl}
                download="translated-bilingual.mp4"
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 text-center bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
              >
                Download with Bilingual Subtitles
              </a>

              {/* P6 placeholder — video editor (deferred) */}
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

        {/* MP3 audio-only result */}
        {mp3Url && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
            <h2 className="text-white font-semibold">Result</h2>
            <audio controls className="w-full rounded-lg" src={mp3Url} />
            <a
              href={mp3Url}
              download="translated-dubbed.mp3"
              target="_blank"
              rel="noopener noreferrer"
              className="block text-center bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
            >
              Download MP3
            </a>
          </div>
        )}

        {/* Webpage extraction result */}
        {isDone && pipelineMode === "webpage" && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
            <h2 className="text-white font-semibold">Result</h2>
            <div className="grid grid-cols-2 gap-3">
              <a
                href={getFileUrl(id, "source.txt")}
                download="source.txt"
                className="text-center bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 font-medium py-3 rounded-xl transition-colors text-sm"
              >
                Source Text
              </a>
              <a
                href={getFileUrl(id, "translated.txt")}
                download="translated.txt"
                className="text-center bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
              >
                Translated Text
              </a>
            </div>
          </div>
        )}

        {/* Subtitle-export result */}
        {isDone && pipelineMode === "subtitles_export" && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
            <h2 className="text-white font-semibold">Result</h2>
            <div className="grid grid-cols-2 gap-3">
              <a
                href={getFileUrl(id, "source.srt")}
                download="source.srt"
                className="text-center bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 font-medium py-3 rounded-xl transition-colors text-sm"
              >
                Source SRT
              </a>
              <a
                href={getFileUrl(id, "translated.srt")}
                download="translated.srt"
                className="text-center bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
              >
                Translated SRT
              </a>
              <a
                href={getFileUrl(id, "source.vtt")}
                download="source.vtt"
                className="text-center bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 font-medium py-3 rounded-xl transition-colors text-sm"
              >
                Source VTT
              </a>
              <a
                href={getFileUrl(id, "translated.vtt")}
                download="translated.vtt"
                className="text-center bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 font-medium py-3 rounded-xl transition-colors text-sm"
              >
                Translated VTT
              </a>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
