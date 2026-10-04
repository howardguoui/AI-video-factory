"use client";

import { useState } from "react";
import { UploadForm } from "@/components/UploadForm";
import { RecentJobs } from "@/components/RecentJobs";

export default function Home() {
  // Bump this to force RecentJobs to re-mount and pick up the new entry immediately
  const [jobsVersion, setJobsVersion] = useState(0);

  return (
    <main className="flex-1 bg-zinc-950">
      {/* Hero */}
      <section className="border-b border-zinc-800/60 bg-gradient-to-b from-zinc-900 to-zinc-950 py-14 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-indigo-950 border border-indigo-800/60 text-indigo-300 text-xs font-medium px-3 py-1.5 rounded-full mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
            100% Local — No Cloud, No Data Leaves Your Machine
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-4 tracking-tight">
            Video Translation
            <span className="block text-indigo-400 mt-1">& Voice Dubbing</span>
          </h1>
          <p className="text-zinc-400 text-lg max-w-xl mx-auto">
            Translate and dub videos into any language using local AI. Powered by Whisper,
            Ollama, Qwen3-TTS, and IndexTTS — fully private, runs entirely on your machine.
          </p>
          <div className="flex flex-wrap justify-center gap-2 mt-8">
            {[
              { icon: "🎙", label: "Voice Cloning" },
              { icon: "🌍", label: "10+ Languages" },
              { icon: "⚡", label: "GPU Accelerated" },
              { icon: "🔒", label: "Fully Private" },
              { icon: "📝", label: "Bilingual Subtitles" },
            ].map((f) => (
              <span
                key={f.label}
                className="flex items-center gap-1.5 bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm px-3 py-1.5 rounded-lg"
              >
                <span>{f.icon}</span>
                {f.label}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Main content */}
      <section className="max-w-6xl mx-auto px-4 py-10">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left: upload form — always visible */}
          <div className="lg:col-span-2">
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">
              New Translation
            </h2>
            <UploadForm onJobCreated={() => setJobsVersion((v) => v + 1)} />
          </div>

          {/* Right sidebar */}
          <div className="lg:col-span-1 space-y-6">
            <RecentJobs key={jobsVersion} />

            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 space-y-3">
              <h3 className="text-sm font-semibold text-zinc-300">How it works</h3>
              {[
                { step: "1", label: "Extract audio", color: "bg-zinc-600" },
                { step: "2", label: "Transcribe (Whisper)", color: "bg-sky-700" },
                { step: "3", label: "Translate (Ollama LLM)", color: "bg-violet-700" },
                { step: "4", label: "Dub (Qwen3 / IndexTTS)", color: "bg-amber-700" },
                { step: "5", label: "Mux + subtitles", color: "bg-emerald-700" },
              ].map((s) => (
                <div key={s.step} className="flex items-center gap-3">
                  <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 ${s.color}`}>
                    {s.step}
                  </span>
                  <span className="text-sm text-zinc-400">{s.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
