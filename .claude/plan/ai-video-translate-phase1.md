# Implementation Plan: AI Video Translation Platform — Phase 1 (MVP)

> Generated: 2026-03-29
> Status: Ready for execution

---

## Task Type
- [x] Fullstack (Frontend + Backend + ML pipeline)

---

## Technical Solution

**Architecture**: Next.js (port 3000) + FastAPI (port 8000) + Celery + Redis + local GPU pipeline.

**Key decisions confirmed:**
- faster-whisper Large-v3 for ASR (CUDA 12.8 / Blackwell compatible via ctranslate2 >= 4.x)
- GPT-4o API for translation (quality first for MVP)
- Qwen3-TTS 1.7B for voice cloning (zero-shot, 3s reference audio)
- FFmpeg for audio mux + subtitle burn-in
- Celery + Redis for async job queue
- Local filesystem storage for MVP (no S3 needed yet)

**VRAM budget per job** (sequential, not concurrent):
- faster-whisper: ~4GB → unload after transcription
- Qwen3-TTS: ~8GB → unload after synthesis
- Peak: 8GB (safe on 16GB RTX 5070 Ti)

---

## Implementation Steps

### Step 0: Environment Setup
**Deliverable**: Both services can start; Celery worker connects to Redis; GPU accessible.

```
backend/
  requirements.txt     # all Python deps
  .env                 # OPENAI_API_KEY, REDIS_URL, STORAGE_PATH
  app/
    main.py            # FastAPI entry
    worker.py          # Celery app definition
    config.py          # settings via pydantic-settings

frontend/
  package.json
  next.config.js
  .env.local           # NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Commands:**
```bash
# Backend
cd backend
python -m venv venv && source venv/Scripts/activate
pip install fastapi uvicorn celery[redis] python-dotenv pydantic-settings \
            faster-whisper openai moviepy ffmpeg-python torch

# Frontend
cd frontend
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir

# Redis (Docker)
docker run -d -p 6379:6379 redis:alpine
```

---

### Step 1: Project Scaffold

**1a. Backend structure**
```
backend/
  app/
    main.py           # FastAPI app, CORS, routes
    config.py         # Settings (OPENAI_API_KEY, REDIS_URL, STORAGE_PATH)
    worker.py         # Celery app
    routers/
      jobs.py         # POST /jobs, GET /jobs/{id}
    services/
      asr.py          # faster-whisper wrapper
      translate.py    # GPT-4o wrapper
      tts.py          # Qwen3-TTS wrapper
      mux.py          # FFmpeg mux/subtitle burn-in
    models/
      job.py          # Job dataclass/schema
    storage/
      local.py        # save/read files from STORAGE_PATH
```

**1b. Frontend structure**
```
frontend/
  app/
    page.tsx          # Upload form + status poll
    jobs/[id]/
      page.tsx        # Job detail + video preview + download
  components/
    UploadForm.tsx    # File drag-drop + YouTube URL input
    JobStatus.tsx     # Progress stepper (4 steps)
    VideoPlayer.tsx   # HTML5 video player
  lib/
    api.ts            # fetch wrappers for FastAPI
```

---

### Step 2: Job API (FastAPI)

**POST /jobs**
- Accept: `multipart/form-data` with `file` (video) OR `youtube_url` (string) + `target_lang`
- Save uploaded file to `STORAGE_PATH/{job_id}/input.mp4`
- Create job record (in-memory dict for MVP, Redis hash for persistence)
- Enqueue Celery task `process_video.delay(job_id)`
- Return: `{ job_id, status: "queued" }`

**GET /jobs/{job_id}**
- Return: `{ job_id, status, progress_step, output_url?, error? }`

**Status enum**: `queued → extracting_audio → transcribing → translating → synthesizing → muxing → done | failed`

Pseudo-code:
```python
@app.post("/jobs")
async def create_job(file: UploadFile = None, youtube_url: str = None, target_lang: str = "zh"):
    job_id = str(uuid4())
    # save file or note youtube_url
    job_store[job_id] = {"status": "queued", "step": 0}
    process_video.delay(job_id, target_lang)
    return {"job_id": job_id}
```

---

### Step 3: Celery Pipeline Task

One Celery task `process_video(job_id, target_lang)` orchestrates all stages:

```python
@celery_app.task
def process_video(job_id: str, target_lang: str):
    update_status(job_id, "extracting_audio")
    audio_path = extract_audio(job_id)          # FFmpeg: video → 16kHz WAV

    update_status(job_id, "transcribing")
    srt_path = transcribe(audio_path, job_id)   # faster-whisper → SRT

    update_status(job_id, "translating")
    translated_srt = translate_srt(srt_path, target_lang)  # GPT-4o

    update_status(job_id, "synthesizing")
    dubbed_audio = synthesize_tts(translated_srt, audio_path, job_id)  # Qwen3-TTS

    update_status(job_id, "muxing")
    output_path = mux_video(job_id, dubbed_audio, translated_srt)  # FFmpeg

    update_status(job_id, "done", output_path=output_path)
```

---

### Step 4: ASR Stage (`services/asr.py`)

```python
from faster_whisper import WhisperModel

model = WhisperModel("large-v3", device="cuda", compute_type="float16")

def transcribe(audio_path: str, job_id: str) -> str:
    segments, info = model.transcribe(audio_path, word_timestamps=True)
    srt_content = segments_to_srt(segments)
    srt_path = f"{STORAGE_PATH}/{job_id}/source.srt"
    write_file(srt_path, srt_content)
    return srt_path
```

**Notes:**
- Use `compute_type="float16"` for Blackwell/CUDA 12.8
- Unload model after use: `del model; torch.cuda.empty_cache()`
- ctranslate2 >= 4.4.0 required for Blackwell support

---

### Step 5: Translation Stage (`services/translate.py`)

```python
from openai import OpenAI

client = OpenAI()

def translate_srt(srt_path: str, target_lang: str) -> str:
    segments = parse_srt(srt_path)
    # Batch translate: send 20 segments per API call to reduce cost
    translated = []
    for batch in chunks(segments, 20):
        texts = [s.text for s in batch]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"Translate to {target_lang}. Preserve tone and emotion. Return JSON array of strings."},
                {"role": "user", "content": json.dumps(texts)}
            ]
        )
        translated.extend(json.loads(response.choices[0].message.content))
    return rebuild_srt(segments, translated)
```

**Notes:**
- Keep segment timestamps unchanged — only replace text
- Batch 20 segments = ~$0.005/min video at GPT-4o pricing

---

### Step 6: TTS + Voice Clone Stage (`services/tts.py`)

Qwen3-TTS requires: extract 3-second reference clip from source audio, then synthesize each translated segment.

```python
# Install: pip install git+https://github.com/QwenLM/Qwen3-TTS
from qwen3_tts import Qwen3TTS

def synthesize_tts(translated_srt_path: str, source_audio: str, job_id: str) -> str:
    model = Qwen3TTS.from_pretrained("Qwen/Qwen3-TTS-1.7B-Base")
    ref_audio = extract_reference_clip(source_audio, duration=3.0)

    segments = parse_srt(translated_srt_path)
    audio_clips = []
    for seg in segments:
        duration = seg.end_time - seg.start_time  # enforce duration
        wav = model.synthesize(
            text=seg.text,
            reference_audio=ref_audio,
            target_duration=duration
        )
        audio_clips.append((seg.start_time, wav))

    dubbed_audio = assemble_audio_clips(audio_clips, total_duration=get_video_duration(source_audio))
    out = f"{STORAGE_PATH}/{job_id}/dubbed.wav"
    save_wav(dubbed_audio, out)
    del model; torch.cuda.empty_cache()
    return out
```

**Notes:**
- Load/unload model per job to stay within 16GB VRAM budget
- Duration control is built-in — prevents audio/video desync
- Reference clip: first 3 seconds of source audio (or loudest segment)

---

### Step 7: FFmpeg Mux Stage (`services/mux.py`)

```python
import ffmpeg

def mux_video(job_id: str, dubbed_audio: str, srt_path: str) -> str:
    input_video = f"{STORAGE_PATH}/{job_id}/input.mp4"
    output_video = f"{STORAGE_PATH}/{job_id}/output.mp4"

    (
        ffmpeg
        .input(input_video)
        .output(
            ffmpeg.input(dubbed_audio),
            output_video,
            vcodec="copy",          # keep original video stream
            acodec="aac",
            map=["0:v:0", "1:a:0"],
            # Subtitle burn-in (optional for MVP):
            vf=f"subtitles={srt_path}"
        )
        .overwrite_output()
        .run()
    )
    return output_video
```

---

### Step 8: Frontend — Upload Form

```tsx
// components/UploadForm.tsx
export function UploadForm() {
  const [file, setFile] = useState<File | null>(null)
  const [ytUrl, setYtUrl] = useState("")
  const [targetLang, setTargetLang] = useState("zh")

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const form = new FormData()
    if (file) form.append("file", file)
    else form.append("youtube_url", ytUrl)
    form.append("target_lang", targetLang)

    const res = await fetch(`${API_URL}/jobs`, { method: "POST", body: form })
    const { job_id } = await res.json()
    router.push(`/jobs/${job_id}`)
  }

  return (
    <form onSubmit={handleSubmit}>
      <input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0])} />
      <span>OR</span>
      <input type="url" placeholder="YouTube URL" value={ytUrl} onChange={e => setYtUrl(e.target.value)} />
      <select value={targetLang} onChange={e => setTargetLang(e.target.value)}>
        <option value="zh">Chinese</option>
        <option value="en">English</option>
        <option value="ja">Japanese</option>
        {/* ... */}
      </select>
      <button type="submit">Translate Video</button>
    </form>
  )
}
```

---

### Step 9: Frontend — Job Status Polling

```tsx
// app/jobs/[id]/page.tsx
const STEPS = ["queued", "extracting_audio", "transcribing", "translating", "synthesizing", "muxing", "done"]

export default function JobPage({ params }: { params: { id: string } }) {
  const [job, setJob] = useState<Job | null>(null)

  useEffect(() => {
    const interval = setInterval(async () => {
      const res = await fetch(`${API_URL}/jobs/${params.id}`)
      const data = await res.json()
      setJob(data)
      if (data.status === "done" || data.status === "failed") clearInterval(interval)
    }, 2000)
    return () => clearInterval(interval)
  }, [params.id])

  return (
    <div>
      <ProgressStepper steps={STEPS} current={job?.status} />
      {job?.status === "done" && (
        <>
          <VideoPlayer src={`${API_URL}/files/${params.id}/output.mp4`} />
          <a href={`${API_URL}/files/${params.id}/output.mp4`} download>Download</a>
        </>
      )}
    </div>
  )
}
```

---

## Key Files Summary

| File | Operation | Description |
|------|-----------|-------------|
| `backend/app/main.py` | Create | FastAPI app + CORS + routes |
| `backend/app/worker.py` | Create | Celery app definition |
| `backend/app/routers/jobs.py` | Create | POST /jobs, GET /jobs/{id}, GET /files/{id}/{filename} |
| `backend/app/services/asr.py` | Create | faster-whisper transcription |
| `backend/app/services/translate.py` | Create | GPT-4o batch translation |
| `backend/app/services/tts.py` | Create | Qwen3-TTS voice clone + synthesis |
| `backend/app/services/mux.py` | Create | FFmpeg audio replacement + subtitle |
| `backend/app/config.py` | Create | Pydantic settings |
| `backend/requirements.txt` | Create | All Python dependencies |
| `backend/.env` | Create | OPENAI_API_KEY, REDIS_URL, STORAGE_PATH |
| `frontend/app/page.tsx` | Create | Home page with UploadForm |
| `frontend/app/jobs/[id]/page.tsx` | Create | Job status + video player |
| `frontend/components/UploadForm.tsx` | Create | File upload + YouTube URL form |
| `frontend/components/JobStatus.tsx` | Create | 4-step progress stepper |
| `frontend/lib/api.ts` | Create | fetch wrappers |

---

## Risks and Mitigation

| Risk | Mitigation |
|------|------------|
| Qwen3-TTS not released yet / API unstable | Fallback: use CosyVoice2 (same team, stable, similar quality) or ElevenLabs API |
| ctranslate2 Blackwell (SM_100) not supported | Install ctranslate2 from source with `CUDA_ARCH=100` flag, or use CUDA 12.6 compat mode |
| Audio duration mismatch causing desync | Use FFmpeg `atempo` filter to stretch/compress if TTS duration diverges >200ms |
| VRAM OOM running both Whisper + TTS | Load models sequentially, call `torch.cuda.empty_cache()` between stages |
| GPT-4o API cost for long videos | Cap video length at 10 min for MVP; add local Qwen3-8B fallback later |
| Celery task fails mid-pipeline | Store per-stage output files; on retry, skip completed stages |

---

## Execution Order

1. Step 0 — Environment + Docker Redis (30 min)
2. Step 1 — Project scaffold, folder structure (20 min)
3. Step 2 — Job API routes + in-memory store (30 min)
4. Step 3 — Celery pipeline skeleton (status updates only, no real processing) (20 min)
5. Step 4 — ASR integration + test with sample video (45 min)
6. Step 5 — Translation integration + test (30 min)
7. Step 6 — TTS integration + test (60 min — most complex)
8. Step 7 — FFmpeg mux + test end-to-end (30 min)
9. Step 8-9 — Frontend upload form + status page (60 min)
10. Integration test: upload video → watch progress → download output

---

## SESSION_ID (for /ccg:execute use)
- CODEX_SESSION: N/A (MCP unavailable, plan generated by Claude directly)
- GEMINI_SESSION: N/A
