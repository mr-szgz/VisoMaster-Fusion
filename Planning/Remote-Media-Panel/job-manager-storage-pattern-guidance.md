# Job Manager Storage Pattern Guidance

## Goal
Create a Remote Media panel that mirrors the Job Manager panel's control topology and persistence strategy so that users can create, edit, delete, refresh, and reconnect remote definitions the same way they manage saved jobs. A remote is a connection config, not a single media item. This document captures the subset of behaviors we want to copy before wiring any backend logic.

## Inherited behaviors worth copying
- **Button row layout**: the trio of `Save/Load/Delete` + `Refresh List` buttons shows affordances for persist/load flows. Remote panel equivalents should keep the visual grouping, but rename them to `Create Remote`, `Edit Remote`, `Delete Remote`, and `Refresh Remotes`.
- **List widget story**: the `jobQueueList` is a sortable list that hosts saved job entries. The remote list should reuse the same widget configuration (`QListWidget`, `sortingEnabled`, `acceptDrops` false), but each row represents a saved remote connection definition rather than a media file, and the list should stay single-select because remote management is one config at a time.
- **Bottom action zone**: reuse the lower two-button action bar as a template, but make it single-remote management instead of batch processing. The current shell should read as `Test Remote` + `Connect Remote`, not any all/selected or multi-select action set.
- **Persistence keys**: Job Manager saves workspace state via `save_current_workspace` and reloads with `load_saved_workspace`. Feature-add the same persistence group of controls (window state, saved remote definitions, selected remote id). Use new keys scoped to remote config data, not media records.
- **Grid layout scaffold**: copy the `QGridLayout` > `QVBoxLayout` > `QHBoxLayout` hierarchy used for Job Manager buttons and lists to keep spacing consistent with other left docks.

## Naming guidance
- All UI elements get `remote` or `Remote` prefixes where the Job Manager uses `job`. Examples: `remoteControlLayout`, `remoteConnectionsList`, `createRemoteButton`.
- Text strings should replace “Job” with “Remote”, “Remote Connection”, or “Remote Definition” so the user sees config-oriented wording rather than media-item wording.
- Persisted control keys and attribute names should follow camelCase `Remote` naming (e.g., `RemoteManagerScrollPosition`) to keep them distinct from job entries while reusing existing save/load hooks.

## Code references
- **UI layout**: `[app/ui/core/MainWindow.ui](/S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/core/MainWindow.ui#L1030)` (Job Manager dock markup).
- **Serialization logic**: `[app/ui/widgets/actions/save_load_actions.py](/S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/actions/save_load_actions.py#L600)` (window_state_data + job metadata sections).
- **Process/share buttons**: `[app/ui/widgets/actions/video_control_actions.py](/S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/actions/video_control_actions.py#L2569)` (theatre-mode layout manipulations illustrate how docks are hidden/shown but can be extended if the Remote panel needs to interact).

## Out of scope for this phase
- Do not wire up remote persistence backends or filesystem operations yet; focus purely on the UI shell that can later plug into the create/edit/delete/connect flow.
- Avoid duplicating job-specific business logic (swap processing, job queue state machine) until we have remote-specific requirements. The panel should be an empty shell with renamed/redesigned buttons.
- Do not add new data models or file formats yet; when persistence is added, it should describe remote connection configs rather than remote media items.
