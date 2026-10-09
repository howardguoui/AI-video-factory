import type { StageVram as StageVramEntry } from "@/lib/api";

const STAGE_LABELS: Record<string, string> = {
  download_video: "Download",
  extract_webpage: "Fetch Webpage",
  extract_audio: "Extract Audio",
  transcribe: "Transcribe (Whisper)",
  translate: "Translate (LLM)",
  translate_text: "Translate (LLM)",
  synthesize_tts: "Synthesize Voice (TTS)",
  mux_video: "Mux Video",
  bilingual_download: "Bilingual Download",
  export_mp3: "Export MP3",
  export_subtitles: "Export Subtitles",
};

function gib(mib: number): string {
  return (mib / 1024).toFixed(1);
}

/**
 * Peak GPU memory per pipeline stage, as sampled by the worker over NVML.
 * The figures are device-wide (every process on the GPU, including Ollama and
 * the desktop), so they show the real headroom on the card.
 */
export function StageVram({ stages }: { stages: Record<string, StageVramEntry> }) {
  const entries = Object.entries(stages);
  if (entries.length === 0) return null;
  const total = Math.max(...entries.map(([, s]) => s.total_mib));
  const peak = Math.max(...entries.map(([, s]) => s.peak_mib));

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-white font-semibold">GPU Memory per Stage</h2>
        <span className="text-xs text-zinc-400">
          peak {gib(peak)} of {gib(total)} GB · {gib(total - peak)} GB headroom
        </span>
      </div>
      <ul className="space-y-2.5">
        {entries.map(([stage, s]) => {
          const pct = s.total_mib > 0 ? Math.min(100, (s.peak_mib / s.total_mib) * 100) : 0;
          const bar = pct >= 95 ? "bg-red-500" : pct >= 85 ? "bg-amber-500" : "bg-indigo-500";
          return (
            <li key={stage} className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-zinc-300">{STAGE_LABELS[stage] ?? stage}</span>
                <span className="text-zinc-400 font-mono">
                  {gib(s.peak_mib)} / {gib(s.total_mib)} GB
                </span>
              </div>
              <div
                className="h-1.5 bg-zinc-800 rounded-full overflow-hidden"
                role="meter"
                aria-label={`${STAGE_LABELS[stage] ?? stage} peak GPU memory`}
                aria-valuemin={0}
                aria-valuemax={s.total_mib}
                aria-valuenow={s.peak_mib}
              >
                <div className={`h-full ${bar}`} style={{ width: `${pct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-zinc-500">
        Device-wide peak while each stage ran, including other processes on the GPU.
      </p>
    </div>
  );
}
