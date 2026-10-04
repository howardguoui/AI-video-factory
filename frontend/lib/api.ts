const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export interface JobResponse {
  job_id: string;
  status: string;
  step: number;
  step_progress: number;
  step_detail?: string | null;
  output_path?: string;
  error?: string;
  target_lang: string;
  pipeline_mode: string;
  tts_engine: string;
  llm_model?: string | null;
  label?: string | null;
  source_vtt?: string;
  translated_vtt?: string;
  bilingual_download?: string;
  source_url?: string | null;
}

export async function createJob(formData: FormData): Promise<{ job_id: string; label: string }> {
  const res = await fetch(`${API_URL}/jobs`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`${API_URL}/jobs/${jobId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function getFileUrl(jobId: string, filename: string): string {
  return `${API_URL}/files/${jobId}/${filename}`;
}

export async function getOllamaModels(): Promise<{ models: string[]; default: string; error?: string }> {
  try {
    const res = await fetch(`${API_URL}/ollama/models`);
    if (!res.ok) return { models: [], default: "" };
    return res.json();
  } catch {
    return { models: [], default: "" };
  }
}

export async function triggerCleanup(): Promise<void> {
  try {
    await fetch(`${API_URL}/jobs/cleanup`, { method: "DELETE" });
  } catch {
    // Non-critical, ignore
  }
}
