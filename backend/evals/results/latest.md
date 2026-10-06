# Quality eval: zh → en, FLEURS test, 50 clips

Run 2026-10-06 22:24 UTC. Lower CER is better; chrF++ and BLEU are 0–100, higher is better.

## Speech recognition

| Model | CER | Speed | Audio |
| --- | --- | --- | --- |
| large-v3 | 9.0% | 4.9× real time | 9.6 min |
| large-v3-turbo | 9.1% | 17.1× real time | 9.6 min |

## Translation (reference transcripts in)

| Model | chrF++ | BLEU | Segments/s | Untranslated |
| --- | --- | --- | --- | --- |
| qwen3:8b | 52.33 | 24.47 | 0.31 | 0 |

## Full pipeline (speech → translation)

large-v3 → qwen3:8b: chrF++ 49.73, BLEU 20.45 (vs 52.33 from perfect transcripts)
