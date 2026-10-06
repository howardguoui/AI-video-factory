"use client";

import { useEffect, useRef, useState } from "react";

interface SubtitleTrack {
  src: string;
  label: string;
  srcLang: string;
}

interface Cue {
  start: number;
  end: number;
  text: string;
}

type SubtitleMode = "off" | "original" | "translation" | "both";

interface VideoPlayerProps {
  src: string;
  subtitles?: SubtitleTrack[];
}

function parseVtt(vttText: string): Cue[] {
  const cues: Cue[] = [];
  const blocks = vttText.replace(/^WEBVTT.*\n/, "").trim().split(/\n\s*\n/);
  for (const block of blocks) {
    const lines = block.trim().split("\n");
    const timeLine = lines.find((l) => l.includes("-->"));
    if (!timeLine) continue;
    const [startStr, endStr] = timeLine.split("-->").map((s) => s.trim());
    const toSec = (t: string) => {
      const parts = t.replace(",", ".").split(":");
      return parts.reduce((acc, p) => acc * 60 + parseFloat(p), 0);
    };
    const textLines = lines.slice(lines.indexOf(timeLine) + 1).filter(Boolean);
    cues.push({ start: toSec(startStr), end: toSec(endStr), text: textLines.join("\n") });
  }
  return cues;
}

function getActiveCue(cues: Cue[], time: number): string | null {
  return cues.find((c) => time >= c.start && time <= c.end)?.text ?? null;
}

const MODES: { value: SubtitleMode; label: string }[] = [
  { value: "off", label: "Off" },
  { value: "original", label: "Original" },
  { value: "translation", label: "Translation" },
  { value: "both", label: "Both" },
];

export function VideoPlayer({ src, subtitles = [] }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [mode, setMode] = useState<SubtitleMode>(subtitles.length > 0 ? "both" : "off");
  const [originalCues, setOriginalCues] = useState<Cue[]>([]);
  const [translationCues, setTranslationCues] = useState<Cue[]>([]);

  const originalSrc = subtitles.find((s) => s.srcLang === "orig")?.src;
  const translationSrc = subtitles.find((s) => s.srcLang !== "orig")?.src;

  // Fetch and parse VTT files. Each track has its own effect, and a cancelled
  // flag drops responses that arrive after the source changed or unmounted.
  useEffect(() => {
    if (!originalSrc) return;
    let cancelled = false;
    fetch(originalSrc)
      .then((r) => r.text())
      .then((t) => {
        if (!cancelled) setOriginalCues(parseVtt(t));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [originalSrc]);

  useEffect(() => {
    if (!translationSrc) return;
    let cancelled = false;
    fetch(translationSrc)
      .then((r) => r.text())
      .then((t) => {
        if (!cancelled) setTranslationCues(parseVtt(t));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [translationSrc]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTimeUpdate = () => setCurrentTime(video.currentTime);
    video.addEventListener("timeupdate", onTimeUpdate);
    return () => video.removeEventListener("timeupdate", onTimeUpdate);
  }, []);

  const origText = getActiveCue(originalCues, currentTime);
  const transText = getActiveCue(translationCues, currentTime);

  const showOriginal = (mode === "original" || mode === "both") && origText;
  const showTranslation = (mode === "translation" || mode === "both") && transText;

  return (
    <div className="space-y-2">
      {/* Video + subtitle overlay */}
      <div className="relative rounded-xl overflow-hidden bg-black">
        <video
          ref={videoRef}
          src={src}
          controls
          className="w-full"
          style={{ maxHeight: "480px", display: "block" }}
        />

        {/* Subtitle overlay */}
        {(showOriginal || showTranslation) && (
          <div className="absolute bottom-12 left-0 right-0 flex flex-col items-center gap-1 px-4 pointer-events-none">
            {showOriginal && (
              <span className="bg-black/70 text-white text-sm px-3 py-1 rounded text-center leading-snug">
                {origText}
              </span>
            )}
            {showTranslation && (
              <span className="bg-black/70 text-yellow-300 text-base font-medium px-3 py-1 rounded text-center leading-snug">
                {transText}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Subtitle mode selector — only shown when subtitles are available */}
      {subtitles.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-zinc-400 text-xs">Subtitles:</span>
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                mode === m.value
                  ? "bg-indigo-600 border-indigo-600 text-white"
                  : "border-zinc-600 text-zinc-400 hover:border-zinc-400"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
