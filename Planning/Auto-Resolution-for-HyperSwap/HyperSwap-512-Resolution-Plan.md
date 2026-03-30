### HyperSwap 512 Resolution Plan

### Scope
- Add one extra runtime mode for HyperSwap: `512`.
- Keep HyperSwap base inference at `256x256`.
- Do not add HyperSwap auto-resolution in this pass.
- Do not add helpers, abstractions, or unrelated cleanup.

### Preconditions
- HyperSwap support must exist in the checked-in `.py` source before `512` work starts.
- If HyperSwap is missing from live source, restore it first by mirroring the donor bundle under `jobs/Features/Hyperswap-Support/`.
- Use donor material as a placement and naming reference only; current target file style still wins.

### Recommended Pattern To Mirror
- UI donor: existing `Inswapper128` resolution selector pattern, duplicated per HyperSwap variant.
- Runtime donor: existing `InStyleSwapper256` `512` mode.
- Reason:
  - the desired end-state UI is Inswapper-like, so copying that surface now reduces future churn
  - the current layout schema appears to expect one `requiredSelectionValue` per control, which makes duplicated per-variant controls the clean pattern
  - the runtime path is still closest to `InStyleSwapper256` because HyperSwap is a `256` base model family
  - same `256` tile size
  - same `dim = 2` default and `dim = 4` extended path

### Implementation Strategy
- UI pattern:
  - do not use a one-item `512`-only dropdown; it loses the explicit base-resolution choice and is weaker than the Inswapper pattern
  - mirror the Inswapper selector structure, but duplicate it per HyperSwap variant because the current layout pattern is single-model scoped
  - preferred first-pass controls:
    - `HyperSwapResASelection`
    - `HyperSwapResBSelection`
    - `HyperSwapResCSelection`
  - preferred first-pass option list for each selector:
    - `256`
    - `512`
  - if auto toggle is deferred to the later feature pass, keep this document scoped to selector-only manual resolution choice
- Latent and aligned-face selection pattern:
  - mirror the existing `InStyleSwapper256` branch in `get_affined_face_dim_and_swapping_latents(...)`
  - when the selected HyperSwap variant resolution is `512`:
    - `dim = 4`
    - `input_face_affined = original_face_512`
  - otherwise:
    - `dim = 2`
    - `input_face_affined = original_face_256`
- Runtime pattern:
  - mirror the existing `InStyleSwapper256` branch in `get_swapped_and_prev_face(...)`
  - keep `dim_res = dim // 2`
  - for `512` mode this gives a `2 x 2` tile grid of `256x256` inputs
  - reassemble the output using the same `tile_inputs`, `tile_outputs`, `tile_coords`, `Mode 2`, and normal-mode structure already present for `InStyleSwapper256`
- Base inference pattern:
  - keep HyperSwap base inference fixed to `256x256`
  - mirror the shape and placement of `run_iss_swapper(...)`
  - do not invent a separate `512` ONNX model unless one already exists and is explicitly intended

### Proposed File-by-File Plan
1. `app/ui/widgets/swapper_layout_data.py`
- Ensure HyperSwap A/B/C model options exist.
- Add duplicated HyperSwap A/B/C resolution selectors mirroring the Inswapper control structure as closely as the current layout schema allows.
- Keep selector naming and placement consistent with the current `Swapper` block.
- First-pass selector options should be `256` and `512` only.

2. `app/processors/workers/frame_worker.py`
- Add HyperSwap latent and `dim` selection branch beside the existing model branches.
- Mirror the `InStyleSwapper256` `dim` check shape, but read from the HyperSwap selector value instead of an on/off toggle.
- Add HyperSwap tiled runtime branch by copying the `InStyleSwapper256` branch structure and swapping only the model-specific names/calls.

3. `app/processors/face_swappers.py`
- Only if HyperSwap is missing:
  - add HyperSwap A/B/C to `self.swapper_models`
  - add `calc_swapper_latent_hyperswap256(...)`
  - add `run_hyperswap256(...)`
- Keep method naming in the same style as `calc_swapper_latent_iss(...)` and `run_iss_swapper(...)`.

4. `app/processors/models_processor.py`
- Only if HyperSwap is missing:
  - add `calc_swapper_latent_hyperswap256(...)`
  - add `run_hyperswap256(...)`
- Keep these as thin pass-through wrappers only.

5. `app/processors/models_data.py`
- Only if HyperSwap is missing:
  - add ArcFace mapping entries for HyperSwap A/B/C
  - add model registry entries for the three HyperSwap ONNX files

### Validation Plan
- Parse-check all changed Python files.
- Manual UI verification:
  - HyperSwap A/B/C appears in the swapper selector.
  - only the matching HyperSwap resolution selector is shown for the chosen variant.
  - each HyperSwap selector offers `256` and `512`.
- Manual runtime verification:
  - HyperSwap `256` path still works unchanged.
  - HyperSwap `512` path uses the aligned `512` face and tiled `256` inference.
  - `Mode 2` behavior follows the same control flow as the current `InStyleSwapper256` branch.
- Regression spot check:
  - `Inswapper128` resolution controls unchanged.
  - `InStyleSwapper256` `512` behavior unchanged.

### Risks
- Largest blocker: checked-in source currently lacks HyperSwap while donor docs and cache artifacts indicate prior work.
- HyperSwap model IO names may differ from the donor bundle and must be verified against the live ONNX registration path before implementation.
- If HyperSwap model assets are not present in the current branch, runtime validation cannot complete until the base model registration is restored.

### Exit Condition
- HyperSwap gains a narrow `512` extension that mirrors the current `InStyleSwapper256` pattern exactly.
- Auto-resolution remains out of scope for this pass.
- No unrelated files or abstractions are introduced.
