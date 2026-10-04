"use client";

import { useState, useRef, useEffect, DragEvent, FormEvent } from "react";
import { createJob, getOllamaModels } from "@/lib/api";
import { addJobToHistory } from "@/lib/jobHistory";

const LANGUAGES = [
  { code: "zh", name: "Chinese" },
  { code: "en", name: "English" },
  { code: "ja", name: "Japanese" },
  { code: "ko", name: "Korean" },
  { code: "de", name: "German" },
  { code: "fr", name: "French" },
  { code: "ru", name: "Russian" },
  { code: "pt", name: "Portuguese" },
  { code: "es", name: "Spanish" },
  { code: "it", name: "Italian" },
];

const TTS_ENGINES = [
  {
    id: "qwen3",
    name: "Qwen3-TTS",
    desc: "1.7B voice cloning model, excellent multilingual quality",
    badge: "Recommended",
    badgeCls: "bg-indigo-900 text-indigo-300 border-indigo-700",
  },
  {
    id: "indextts",
    name: "IndexTTS",
    desc: "Zero-shot voice cloning from Index Lab, fast batch inference",
    badge: "Local",
    badgeCls: "bg-zinc-700 text-zinc-300 border-zinc-600",
  },
  {
    id: "cosyvoice2",
    name: "CosyVoice2",
    desc: "0.5B voice cloning model, compact and fast",
    badge: "Local",
    badgeCls: "bg-zinc-700 text-zinc-300 border-zinc-600",
  },
  {
    id: "stub",
    name: "Stub (Dev)",
    desc: "Copies original audio — use for pipeline testing without GPU",
    badge: "Dev",
    badgeCls: "bg-yellow-900 text-yellow-300 border-yellow-700",
  },
];

interface UploadFormProps {
  onJobCreated?: (jobId: string) => void;
}

export function UploadForm({ onJobCreated }: UploadFormProps = {}) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<"file" | "url" | "webpage">("file");
  const [pipelineMode, setPipelineMode] = useState<"dubbing" | "subtitles_only" | "mp3_only" | "subtitles_export">("dubbing");
  const [ttsEngine, setTtsEngine] = useState("qwen3");
  const [file, setFile] = useState<File | null>(null);
  const [ytUrl, setYtUrl] = useState("");
  const [targetLang, setTargetLang] = useState("zh");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Ollama model state
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [ollamaError, setOllamaError] = useState(false);

  useEffect(() => {
    getOllamaModels().then(({ models, default: def, error }) => {
      setOllamaModels(models);
      setSelectedModel(def || (models[0] ?? ""));
      if (error || models.length === 0) setOllamaError(true);
    });
  }, []);

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    setDragging(true);
  }

  function handleDragLeave() {
    setDragging(false);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.type.startsWith("video/")) {
      setFile(dropped);
      setError(null);
    } else {
      setError("Please drop a video file.");
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (mode === "file" && !file) {
      setError("Please select a video file.");
      return;
    }
    if ((mode === "url" || mode === "webpage") && !ytUrl.trim()) {
      setError(`Please enter a ${mode === "webpage" ? "webpage" : "video"} URL.`);
      return;
    }

    const formData = new FormData();
    if (mode === "file" && file) {
      formData.append("file", file);
    } else {
      formData.append("source_url", ytUrl.trim());
    }
    formData.append("target_lang", targetLang);
    formData.append("pipeline_mode", mode === "webpage" ? "webpage" : pipelineMode);
    formData.append("tts_engine", ttsEngine);
    if (selectedModel) formData.append("llm_model", selectedModel);

    try {
      setLoading(true);
      const { job_id, label } = await createJob(formData);
      addJobToHistory({ id: job_id, label: label || file?.name || ytUrl, createdAt: Date.now(), status: "queued" });
      if (onJobCreated) onJobCreated(job_id);
      // Reset form so the user can immediately queue another video
      setFile(null);
      setYtUrl("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit job.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 shadow-xl space-y-5">
      {/* Mode toggle */}
      <div className="flex rounded-xl overflow-hidden border border-zinc-700">
        {(["file", "url", "webpage"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
              mode === m ? "bg-indigo-600 text-white" : "bg-zinc-800 text-zinc-400 hover:text-white"
            }`}
          >
            {m === "file" ? "Upload File" : m === "url" ? "Video URL" : "Webpage"}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* File drop or URL input — key forces full remount when switching between file and URL modes */}
        {mode === "file" ? (
          <div
            key="file-input-zone"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
              dragging
                ? "border-indigo-500 bg-indigo-950/40"
                : file
                ? "border-emerald-600 bg-emerald-950/20"
                : "border-zinc-700 hover:border-indigo-500/60 hover:bg-zinc-800/50"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) { setFile(f); setError(null); }
              }}
            />
            {file ? (
              <div>
                <p className="text-emerald-400 font-medium text-sm">{file.name}</p>
                <p className="text-zinc-500 text-xs mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
              </div>
            ) : (
              <>
                <div className="w-10 h-10 rounded-xl bg-zinc-800 border border-zinc-700 flex items-center justify-center mx-auto mb-3">
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-zinc-400">
                    <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
                <p className="text-zinc-300 text-sm font-medium">Drop a video file here</p>
                <p className="text-zinc-500 text-xs mt-1">or click to browse — MP4, MOV, MKV, AVI…</p>
              </>
            )}
          </div>
        ) : (
          <div key="url-input-zone" className="space-y-1.5">
            <input
              type="text"
              placeholder={
                mode === "url"
                  ? "https://www.youtube.com/watch?v=… or https://www.bilibili.com/video/BV…"
                  : "https://example.com/article…"
              }
              value={ytUrl}
              onChange={(e) => setYtUrl(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 text-white placeholder-zinc-500 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
            <p className="text-zinc-600 text-xs px-1">
              {mode === "url"
                ? "YouTube, Bilibili, and any yt-dlp supported platform"
                : "Extracts and translates readable text content from any webpage"}
            </p>
          </div>
        )}

        {/* Language + Pipeline row */}
        <div className={`grid gap-3 ${mode === "webpage" ? "grid-cols-1" : "grid-cols-2"}`}>
          <div>
            <label className="block text-zinc-400 text-xs font-medium mb-1.5 uppercase tracking-wider">
              Translate to
            </label>
            <select
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 text-white rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>{lang.name}</option>
              ))}
            </select>
          </div>
          {mode !== "webpage" && (
            <div>
              <label className="block text-zinc-400 text-xs font-medium mb-1.5 uppercase tracking-wider">
                Output mode
              </label>
              <select
                value={pipelineMode}
                onChange={(e) => setPipelineMode(e.target.value as "dubbing" | "subtitles_only" | "mp3_only" | "subtitles_export")}
                className="w-full bg-zinc-800 border border-zinc-700 text-white rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="dubbing">Full Dubbing</option>
                <option value="subtitles_only">Subtitles Only</option>
                <option value="mp3_only">MP3 Audio Only</option>
                <option value="subtitles_export">Export Subtitles</option>
              </select>
            </div>
          )}
        </div>

        {/* TTS Engine selector */}
        {mode !== "webpage" && (pipelineMode === "dubbing" || pipelineMode === "mp3_only") && (
          <div>
            <label className="block text-zinc-400 text-xs font-medium mb-2 uppercase tracking-wider">
              TTS Engine
            </label>
            <div className="grid grid-cols-2 gap-2">
              {TTS_ENGINES.map((eng) => (
                <button
                  key={eng.id}
                  type="button"
                  onClick={() => setTtsEngine(eng.id)}
                  className={`text-left px-3 py-2.5 rounded-xl border transition-all ${
                    ttsEngine === eng.id
                      ? "border-indigo-500 bg-indigo-950/60 ring-1 ring-indigo-500/40"
                      : "border-zinc-700 bg-zinc-800 hover:border-zinc-500"
                  }`}
                >
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-white text-sm font-medium">{eng.name}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded border ${eng.badgeCls}`}>
                      {eng.badge}
                    </span>
                  </div>
                  <p className="text-zinc-500 text-xs leading-snug">{eng.desc}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Advanced settings toggle */}
        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`w-3.5 h-3.5 transition-transform ${showAdvanced ? "rotate-90" : ""}`}
            >
              <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
            </svg>
            Advanced settings
          </button>

          {showAdvanced && (
            <div className="mt-3 bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-4 space-y-3">
              <div>
                <label className="block text-zinc-400 text-xs font-medium mb-1.5 uppercase tracking-wider">
                  Translation LLM (Ollama)
                </label>
                {ollamaError && ollamaModels.length === 0 ? (
                  <p className="text-xs text-amber-400 bg-amber-950 border border-amber-800 rounded-lg px-3 py-2">
                    Ollama unreachable — using default model from config
                  </p>
                ) : (
                  <select
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 text-white rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {ollamaModels.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                )}
                <p className="text-zinc-600 text-xs mt-1">
                  Populated from <code className="text-zinc-500">GET /api/tags</code> — shows locally installed Ollama models
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <p className="text-red-400 text-sm bg-red-950 border border-red-800 rounded-xl px-4 py-2.5">
            {error}
          </p>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-3.5 rounded-xl transition-colors text-sm tracking-wide"
        >
          {loading
            ? "Submitting…"
            : mode === "webpage"
            ? "Extract & Translate Webpage"
            : pipelineMode === "dubbing"
            ? "Translate & Dub Video"
            : pipelineMode === "mp3_only"
            ? "Translate & Export MP3"
            : pipelineMode === "subtitles_export"
            ? "Export Subtitle Files"
            : "Generate Subtitles"}
        </button>
      </form>
    </div>
  );
}
