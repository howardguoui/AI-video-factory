interface Step {
  key: string;
  label: string;
  /** If set, only show this step when pipeline_mode is one of these values. */
  modes?: string[];
  /** If true, only show when the job has a source_url (URL-sourced job). */
  urlOnly?: boolean;
}

const VIDEO_MODES = ["dubbing", "subtitles_only", "mp3_only", "subtitles_export"];

const ALL_STEPS: Step[] = [
  { key: "queued", label: "Queued" },
  { key: "downloading", label: "Downloading Source", urlOnly: true },
  { key: "extracting_audio", label: "Extracting Audio", modes: VIDEO_MODES },
  { key: "transcribing", label: "Transcribing (Whisper)", modes: VIDEO_MODES },
  { key: "translating", label: "Translating" },
  { key: "synthesizing", label: "Synthesizing Voice", modes: ["dubbing", "mp3_only"] },
  { key: "muxing", label: "Muxing Video", modes: ["dubbing", "subtitles_only"] },
  { key: "rendering_downloads", label: "Rendering Downloads", modes: ["dubbing", "subtitles_only"] },
  { key: "exporting_mp3", label: "Exporting MP3", modes: ["mp3_only"] },
  { key: "exporting_subtitles", label: "Exporting Subtitles", modes: ["subtitles_export"] },
  { key: "done", label: "Complete" },
];

interface JobStatusProps {
  status: string;
  pipeline_mode?: string;
  source_url?: string | null;
  step_progress?: number;
  step_detail?: string | null;
  error?: string | null;
}

export function JobStatus({ status, pipeline_mode, source_url, step_progress = 0, step_detail, error }: JobStatusProps) {
  const mode = pipeline_mode ?? "dubbing";
  const steps = ALL_STEPS.filter((s) => {
    if (s.urlOnly && !source_url) return false;
    if (s.modes && !s.modes.includes(mode)) return false;
    return true;
  });
  const currentIndex = steps.findIndex((s) => s.key === status);
  const isFailed = status === "failed";
  const isDone = status === "done";

  return (
    <div className="space-y-1">
      {isFailed ? (
        <div className="bg-red-950 border border-red-800 rounded-xl p-4">
          <p className="text-red-400 font-semibold mb-1">Processing Failed</p>
          {error && <p className="text-red-300 text-sm">{error}</p>}
        </div>
      ) : (
        <ol className="space-y-2">
          {steps.map((step, idx) => {
            const isCompleted = isDone ? idx < steps.length : idx < currentIndex;
            const isActive = !isDone && idx === currentIndex;
            const isFuture = !isDone && idx > currentIndex;

            return (
              <li key={step.key}>
                <div className="flex items-center gap-3">
                  {/* Step indicator */}
                  <span
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 transition-colors ${
                      isCompleted
                        ? "bg-emerald-600 text-white"
                        : isActive
                        ? "bg-indigo-600 text-white"
                        : "bg-zinc-800 text-zinc-600 border border-zinc-700"
                    }`}
                  >
                    {isCompleted ? (
                      <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    ) : (
                      idx + 1
                    )}
                  </span>

                  {/* Label */}
                  <div className="flex-1 min-w-0">
                    <span
                      className={`text-sm font-medium ${
                        isCompleted
                          ? "text-emerald-400"
                          : isActive
                          ? "text-white"
                          : "text-zinc-600"
                      }`}
                    >
                      {step.label}
                    </span>

                    {/* Active step: detail text */}
                    {isActive && step_detail && (
                      <p className="text-xs text-zinc-400 mt-0.5 truncate">{step_detail}</p>
                    )}
                  </div>

                  {/* Active spinner */}
                  {isActive && (
                    <svg className="animate-spin w-4 h-4 text-indigo-400 flex-shrink-0" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                  )}
                </div>

                {/* Per-step progress bar for active step */}
                {isActive && step_progress > 0 && (
                  <div className="ml-10 mt-1.5">
                    <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(step_progress * 100, 100).toFixed(1)}%` }}
                      />
                    </div>
                    <p className="text-xs text-zinc-600 mt-0.5 text-right">
                      {Math.min(Math.round(step_progress * 100), 100)}%
                    </p>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
