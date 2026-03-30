### HyperSwap Repo State and Donors

### Live Source Status
- HyperSwap is not present in the checked-in `.py` files that currently define swapper behavior:
  - `app/ui/widgets/swapper_layout_data.py`
  - `app/processors/models_data.py`
  - `app/processors/models_processor.py`
  - `app/processors/face_swappers.py`
  - `app/processors/workers/frame_worker.py`
- This means HyperSwap `512` work is blocked on one prerequisite:
  - restore or verify base HyperSwap support in live source first

### Local Donor Bundle Already In Repo
- The repo already contains a prior donor bundle:
  - `jobs/Features/Hyperswap-Support/Implenentation_Plan.md`
  - `jobs/Features/Hyperswap-Support/source-mirror/app/processors/models_data.py`
  - `jobs/Features/Hyperswap-Support/source-mirror/app/processors/models_processor.py`
  - `jobs/Features/Hyperswap-Support/source-mirror/app/processors/face_swappers.py`
  - `jobs/Features/Hyperswap-Support/source-mirror/app/processors/workers/frame_worker.py`
  - `jobs/Features/Hyperswap-Support/source-mirror/app/ui/widgets/swapper_layout_data.py`

### What The Donor Bundle Says
- HyperSwap was previously planned as:
  - `Hyperswap256 Version A`
  - `Hyperswap256 Version B`
  - `Hyperswap256 Version C`
- The donor bundle includes:
  - ArcFace mapping entries targeting `Inswapper128ArcFace`
  - model registry entries for three `256` ONNX files
  - thin `ModelsProcessor` wrappers
  - `FaceSwappers` latent and inference methods
  - `FrameWorker` latent-selection and runtime branches
  - UI option entries for model selection
- The donor runtime pattern is a fixed `256x256` model path, which matches the shape needed for a later `256 -> 512` extension by mirroring `InStyleSwapper256`

### Cache and Workspace Signals
- Additional HyperSwap signals exist in non-authoritative files:
  - `app/processors/workers/__pycache__/frame_worker.cpython-312.pyc`
  - `app/processors/__pycache__/models_processor.cpython-312.pyc`
  - `last_workspace.json`
  - completed job JSON files under `jobs/completed/`
- These signals are useful because they show HyperSwap was used locally, but they are not a substitute for checked-in source.

### Planning Conclusion
- The safest path is:
  1. restore HyperSwap support in live source by mirroring the existing donor bundle
  2. add HyperSwap `512` mode by mirroring the live `InStyleSwapper256` `512` pattern
  3. add HyperSwap auto-resolution later by mirroring the live `Inswapper128` auto-resolution pattern

### Donor Usage Rule
- Use the donor bundle for naming, placement, and model-family assumptions.
- Use the current target files for exact branch placement, toggle structure, runtime shape, and code style.
- If donor material conflicts with current live source style, current live source wins.
