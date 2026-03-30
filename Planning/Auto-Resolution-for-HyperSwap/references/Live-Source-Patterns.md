### Live Source Patterns

### `Inswapper128` UI Pattern
- File: `app/ui/widgets/swapper_layout_data.py`
- Relevant snapshot:
  - `SwapperResSelection` exposes `128`, `256`, `384`, `512`
  - `SwapperResAutoSelectEnableToggle` is scoped to `Inswapper128`
  - `InStyleResAEnableToggle`, `InStyleResBEnableToggle`, and `InStyleResCEnableToggle` already show the per-model `512` toggle pattern used by `InStyleSwapper256`
  - current layout-data structure scopes controls through a single `requiredSelectionValue`, which makes duplicated per-model controls the safest mirror pattern for HyperSwap A/B/C
- Useful line range from the current snapshot:
  - `25-64`

### Aligned Face Preparation Pattern
- File: `app/processors/workers/frame_worker.py`
- Relevant snapshot:
  - `original_face_512` is created through `kgm.warp_affine(...)`
  - `original_face_384`, `original_face_256`, and `original_face_128` are created through resize transforms
- Useful line range from the current snapshot:
  - `2628-2650`

### `Inswapper128` Resolution Selection Pattern
- File: `app/processors/workers/frame_worker.py`
- Relevant snapshot:
  - when auto-resolution is enabled, `tform.scale` selects `dim = 1/2/3/4`
  - the selected `dim` maps to `original_face_128`, `original_face_256`, `original_face_384`, or `original_face_512`
- Useful line range from the current snapshot:
  - `2792-2817`

### `Inswapper128` Runtime Tiling Pattern
- File: `app/processors/workers/frame_worker.py`
- Relevant snapshot:
  - tiles are cut from the aligned face with `input_face_affined[j::dim, i::dim]`
  - outputs are written back with the same strided coordinates
  - the same branch shape handles normal mode and `Mode 2`
  - there is a batched path present in source, but `_use_batched` is currently hard-set to `False`, so the active path is sequential
- Useful line ranges from the current snapshot:
  - `3100-3166`
  - `3168-3200`

### `Inswapper128` Fixed Base Inference Pattern
- File: `app/processors/face_swappers.py`
- Relevant snapshot:
  - the live source binds `target` as `(1, 3, 128, 128)`
  - the custom provider path also captures a `(1, 3, 128, 128)` example tensor
  - `run_inswapper_batched(...)` is explicitly described as `pixel-shift resolution mode`
- Useful line ranges from the current snapshot:
  - `536-613`
  - `623-700`

### `InStyleSwapper256` `512` UI Pattern
- File: `app/ui/widgets/swapper_layout_data.py`
- Relevant snapshot:
  - one `512 Resolution` toggle per model variant
  - each toggle is controlled by `parentSelection` plus `requiredSelectionValue`
- Useful line range from the current snapshot:
  - `42-64`

### `InStyleSwapper256` `dim` Selection Pattern
- File: `app/processors/workers/frame_worker.py`
- Relevant snapshot:
  - `dim = 4` and `input_face_affined = original_face_512` when the per-model `512` toggle is enabled
  - otherwise `dim = 2` and `input_face_affined = original_face_256`
- Useful line range from the current snapshot:
  - `2820-2861`

### `InStyleSwapper256` Runtime Tiling Pattern
- File: `app/processors/workers/frame_worker.py`
- Relevant snapshot:
  - `dim_res = dim // 2`
  - for the `512` path this yields a `2 x 2` tile grid of `256x256` model inputs
  - runtime structure matches the `Inswapper128` branch style:
    - `tile_inputs`
    - `tile_outputs`
    - `tile_coords`
    - `Mode 2`
    - normal mode
- Useful line range from the current snapshot:
  - `3237-3305`

### `InStyleSwapper256` Fixed Base Inference Pattern
- File: `app/processors/face_swappers.py`
- Relevant snapshot:
  - `run_iss_swapper(...)` binds `target` and `output` as `(1, 3, 256, 256)`
  - this is the base pattern to mirror if HyperSwap is also a fixed `256x256` model
- Useful line range from the current snapshot:
  - `707-750`

### Thin Wrapper and Registry Pattern
- Files:
  - `app/processors/models_processor.py`
  - `app/processors/models_data.py`
- Relevant snapshot:
  - `ModelsProcessor` uses thin wrappers for `calc_swapper_latent_iss(...)` and `run_iss_swapper(...)`
  - `models_data.py` maps `InStyleSwapper256` variants to `Inswapper128ArcFace`
  - `models_data.py` registers one model entry per variant
- Useful line ranges from the current snapshot:
  - `app/processors/models_processor.py:1761-1771`
  - `app/processors/models_data.py:61-116`
