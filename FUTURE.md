# Future: P6 — In-Browser Video Editor

## Status
Deferred. The "Edit Video" button on the job result page is present but disabled
pending this implementation.

## Goal
Allow users to trim, cut, and preview the translated output video directly in the
browser before downloading — no server round-trip needed.

## Recommended Approach

### Library: `@ffmpeg/ffmpeg` (FFmpeg.wasm)
- Runs FFmpeg compiled to WebAssembly inside the browser
- No backend changes needed — all processing is client-side
- Install: `npm install @ffmpeg/ffmpeg @ffmpeg/util`
- Enables: trim, cut, merge, format convert, subtitle burn

### Implementation Plan

1. **Install FFmpeg.wasm**
   ```bash
   npm install @ffmpeg/ffmpeg @ffmpeg/util
   ```

2. **Create `components/VideoEditor.tsx`**
   - Load FFmpeg.wasm lazily (large binary, ~30MB)
   - Fetch the output video from `/api/files/{id}/output.mp4`
   - Render a simple trim UI: start/end slider over video timeline
   - On "Apply Trim", run: `ffmpeg -i input.mp4 -ss START -to END -c copy output.mp4`
   - Download the result via an object URL

3. **Wire into job result page**
   - Replace disabled "Edit Video" button with `<VideoEditor jobId={id} />`
   - Show only when job status is `done`

### Notes
- FFmpeg.wasm requires `SharedArrayBuffer` (needs `Cross-Origin-Opener-Policy: same-origin`
  and `Cross-Origin-Embedder-Policy: require-corp` headers)
- Add these to `next.config.ts` headers for the job page route
- First load is slow (~30MB WASM binary) — show a loading indicator
- For more advanced editing (split, overlay, effects), consider Remotion for
  programmatic video generation instead

### Alternative: Server-side editing
Use the existing FastAPI backend + FFmpeg (already installed) — add a
`POST /api/jobs/{id}/trim` endpoint that runs FFmpeg trim server-side.
Simpler than WASM, no header requirements, but requires a server round-trip.
