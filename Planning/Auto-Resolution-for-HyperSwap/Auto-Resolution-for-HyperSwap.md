### Auto-Resolution for HyperSwap

### Summary
- Ultimate goal: mirror the existing `Inswapper128` auto-resolution behavior for HyperSwap while following current VisoMaster Fusion naming, branch placement, and control-flow patterns literally.
- Recommended delivery order: first add a single `512` mode for HyperSwap by mirroring the existing `InStyleSwapper256 -> 512` path, then add HyperSwap auto-resolution later by mirroring the existing `Inswapper128` resolution-selection logic.
- Hard rule for implementation: no helper extraction, no new abstractions, no dependency additions, no opportunistic cleanup, and no unrelated file edits.

### Current Source Facts
- Live checked-in source already contains the full `Inswapper128` resolution system:
  - UI resolution selector and auto toggle in `app/ui/widgets/swapper_layout_data.py`
  - aligned face preparation in `app/processors/workers/frame_worker.py`
  - `dim` selection and auto-resolution thresholds in `app/processors/workers/frame_worker.py`
  - tiled runtime inference around the fixed `128x128` model in `app/processors/workers/frame_worker.py`
- Live checked-in source already contains the `InStyleSwapper256` `512` pattern:
  - per-model `512 Resolution` toggles in `app/ui/widgets/swapper_layout_data.py`
  - `dim = 2` or `dim = 4` selection in `app/processors/workers/frame_worker.py`
  - tiled runtime inference that turns the `256` base model into a `512` working path in `app/processors/workers/frame_worker.py`
  - fixed `256x256` base inference entrypoint in `app/processors/face_swappers.py`
- Live checked-in source does not currently expose HyperSwap in the checked-in `.py` files:
  - no HyperSwap model options in `app/ui/widgets/swapper_layout_data.py`
  - no HyperSwap model registry entries in `app/processors/models_data.py`
  - no HyperSwap wrappers in `app/processors/models_processor.py`
  - no HyperSwap runtime methods in `app/processors/face_swappers.py`
  - no HyperSwap branches in `app/processors/workers/frame_worker.py`
- HyperSwap donor material does exist elsewhere in the repo:
  - `jobs/Features/Hyperswap-Support/Implenentation_Plan.md`
  - `jobs/Features/Hyperswap-Support/source-mirror/...`
  - `last_workspace.json`, completed job files, and compiled caches also reference HyperSwap variants

### Why This Feature Is Feasible
- `Inswapper128` proves the app already supports multi-resolution behavior through in-code aligned-face scaling plus tiled inference around a fixed-size base model.
- `InStyleSwapper256` proves a `256` base model can gain a `512` mode without new weights by reusing the aligned `512` face crop and splitting it into `256` tiles during runtime.
- The HyperSwap donor bundle under `jobs/Features/Hyperswap-Support/` already points to a `Hyperswap256 Version A/B/C` model family, which makes the `InStyleSwapper256` pattern the closest safe donor for a first `512` mode.

### Source-of-Truth Rule
- Treat the checked-in `.py` files as authoritative for what exists today.
- Treat `jobs/Features/Hyperswap-Support/` as donor/reference material for how HyperSwap was previously planned or mirrored.
- Treat `.pyc`, `last_workspace.json`, and saved jobs as signals only, not as implementation truth.

### Recommended Architecture
- Phase 0: restore or verify live HyperSwap support.
  - If HyperSwap is intended to exist in this branch, first re-land it into the checked-in `.py` source using the donor bundle under `jobs/Features/Hyperswap-Support/` as the mirror reference.
  - Do not build `512` mode on top of cache-only or workspace-only references.
- Phase 1: add HyperSwap `512` mode only.
  - Mirror the existing `Inswapper128` control shape for HyperSwap UI, but duplicate it per HyperSwap variant because the current layout data pattern uses one `requiredSelectionValue` per control.
  - Preferred first-pass selector options: `256` and `512`.
  - Do not expose `128` or `384` in the HyperSwap selector until those paths actually exist in live runtime code.
  - Mirror the existing `InStyleSwapper256` `dim` selection shape in `FrameWorker`.
  - Mirror the existing tiled `InStyleSwapper256` runtime branch in `FrameWorker`.
  - Keep HyperSwap base inference fixed at `256x256`.
- Phase 2: add HyperSwap auto-resolution.
  - Reuse the same duplicated-per-variant HyperSwap selector structure from Phase 1.
  - Mirror the existing `Inswapper128` auto-selection UI and `FrameWorker` decision flow.
  - Limit HyperSwap auto mode to the resolutions HyperSwap actually supports in live code.
  - Do not clone the full `128/256/384/512` matrix unless those modes truly exist for HyperSwap.

### Pattern Selection
- UI donor pattern to mirror first: `Inswapper128`.
  - Reason: the end goal is an Inswapper-like resolution control surface, not a temporary HyperSwap-only toggle.
  - Reason: copying that control shape now avoids another UI churn later.
  - Reason: the current layout-data gating pattern strongly favors duplicated per-model controls.
- Runtime donor pattern to mirror first: `InStyleSwapper256` `512` mode.
  - Reason: same base size class (`256 -> 512`)
  - Reason: same tile-size class (`256` tiles)
  - Reason: lowest-risk runtime path with the smallest change surface
- Auto-resolution donor pattern to mirror second: `Inswapper128`.
  - Reason: needed only after HyperSwap has more than one working resolution in live source
  - Reason: should reuse existing naming and branch placement after the `256/512` path is stable

### Files Expected To Change When Implemented
- `app/ui/widgets/swapper_layout_data.py`
  - HyperSwap model options, then duplicated Inswapper-style HyperSwap resolution selectors, then later duplicated HyperSwap auto-resolution toggles
- `app/processors/models_data.py`
  - HyperSwap ArcFace mapping and model registry entries, if HyperSwap is not already restored in live source
- `app/processors/models_processor.py`
  - thin HyperSwap wrappers, if missing
- `app/processors/face_swappers.py`
  - HyperSwap model registration and fixed `256x256` inference entrypoint, if missing
- `app/processors/workers/frame_worker.py`
  - HyperSwap latent selection branch, `dim` selection branch, and tiled runtime branch

### Acceptance Criteria
- HyperSwap A/B/C exists in checked-in `.py` source, not only in donor docs or caches.
- HyperSwap `512` mode reuses the existing aligned-face preparation and tiled runtime structure already used for `InStyleSwapper256`.
- HyperSwap UI follows the Inswapper-style selector pattern instead of introducing a separate ad hoc toggle-only control if a selector can be landed cleanly.
- Later HyperSwap auto mode reuses the existing `Inswapper128` resolution-selection pattern instead of introducing new abstractions.
- New code stays adjacent to the matching existing model branches and uses the same naming style.
- No unrelated files are changed.

### Non-Goals
- No generalized multi-model resolution framework
- No helper extraction for shared tile logic
- No speculative HyperSwap `128` or `384` modes
- No refactor of `Inswapper128` or `InStyleSwapper256`
- No changes outside the HyperSwap feature surface
