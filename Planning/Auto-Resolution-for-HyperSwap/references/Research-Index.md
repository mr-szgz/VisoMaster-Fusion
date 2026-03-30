### Research Index

### Source-of-Truth Order
1. Checked-in live `.py` source under `app/`
2. Local donor bundle under `jobs/Features/Hyperswap-Support/`
3. Cache and state artifacts:
   - `app/processors/workers/__pycache__/frame_worker.cpython-312.pyc`
   - `app/processors/__pycache__/models_processor.cpython-312.pyc`
   - `last_workspace.json`
   - completed job JSON files

### Key Findings
- `Inswapper128` already has a full multi-resolution system in live source.
- `InStyleSwapper256` already has a `512` mode in live source.
- HyperSwap is not currently exposed in the checked-in `.py` files.
- HyperSwap donor material already exists elsewhere in the repo and can be used as a mirror reference.
- The safest first HyperSwap extension is to mirror the current `InStyleSwapper256` `512` pattern, not the full `Inswapper128` auto-resolution matrix.

### Reference Docs In This Folder
- `Live-Source-Patterns.md`
  - snapshot of the current checked-in `Inswapper128` and `InStyleSwapper256` patterns that matter for this feature
- `HyperSwap-Repo-State-and-Donors.md`
  - snapshot of the current HyperSwap gap in live source plus the local donor material already present in the repo

### Files Worth Reading First During Implementation
- `app/ui/widgets/swapper_layout_data.py`
- `app/processors/face_swappers.py`
- `app/processors/models_processor.py`
- `app/processors/models_data.py`
- `app/processors/workers/frame_worker.py`
- `jobs/Features/Hyperswap-Support/Implenentation_Plan.md`
- `jobs/Features/Hyperswap-Support/source-mirror/...`
