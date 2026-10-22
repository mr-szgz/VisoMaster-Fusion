# ByteTrack landmark downstream execution order

This list traces the downstream consumers of landmarks returned by the application's ByteTrack integration in the standard video/webcam path. It includes direct landmark consumers and indirect consumers of the aligned face crops, masks, and swapped images derived from those landmarks. ByteTrack tracks bounding boxes; the application associates those boxes with detection landmarks. Optional stages run only when enabled, and configurable stages appear at their supported execution positions.

This is a source-code trace, not confirmation of a reproduced synchronization bug. References are repository-relative; line numbers reflect the code inspected on 2026-10-22.

1. **Recognition / identity filtering** — `app/processors/video_utils/sequential_detector.py:223`.
2. **Dense landmark refinement**, then **landmark smoothing** — `app/processors/video_utils/sequential_detector.py:383` and `:493`.
3. **Worker recognition → target matching → landmark adjustments** — `app/processors/workers/frame_worker_standard.py:375`; target matching and adjustments occur in the selected swap branch (`:456` / `:514` or `:611` / `:662`).
4. **Face alignment / cropping → pre-swap face shaping → swapping** — `app/processors/workers/frame_worker_pipeline.py:1858` onward.
5. **Profile-angle masks / segmentation safeguard angle calculation** — `app/processors/workers/frame_worker_pipeline.py:2268`.
6. **Expression restoration / Recast → face editor → face shaping**, when positioned at “Beginning” — `app/processors/workers/frame_worker_pipeline.py:2350`.
7. **First face restorer** — `app/processors/workers/frame_worker_pipeline.py:2449`.
8. **Occluder → FaceParser/mouth-region generation → CLIP mask → Restore Mouth/Eyes → XSeg/XSeg Mouth** — `app/processors/workers/frame_worker_pipeline.py:2465` onward; parser processing at `:2496`, Restore Mouth/Eyes at `:2571`, and XSeg at `:2640`.
9. **First-restorer automatic blending**, then **expression/editor/shaping** positioned after the first restorer — `app/processors/workers/frame_worker_pipeline.py:2742` and `:2803` onward.
10. **Second face restorer**, when not positioned at the end — `app/processors/workers/frame_worker_pipeline.py:2879`.
11. **Expression/editor/shaping** positioned after the second restorer — `app/processors/workers/frame_worker_pipeline.py:2913`.
12. **Auto Color → texture transfer → differencing → editor/shaping positioned after texture transfer → color corrections** — `app/processors/workers/frame_worker_pipeline.py:2978` onward; color corrections at `:3351`.
13. **Second face restorer**, when positioned at the end — `app/processors/workers/frame_worker_pipeline.py:3407`.
14. **Post-restorer mouth enhancement → ending FaceParser → ending color transfer → final blending/mask processing** — `app/processors/workers/frame_worker_pipeline.py:3441` onward.
15. **Face and mask placement back into the frame** — `app/processors/workers/frame_worker_pipeline.py:3768`.
16. **Makeup** — `app/processors/workers/frame_worker_standard.py:743` (or `:596` in the best-face branch).
17. **Landmark overlays → cropped-face comparison previews** — `app/processors/workers/frame_worker_standard.py:894` and `:915`.
