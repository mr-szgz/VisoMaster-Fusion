### UI-Only Remote Import Panel + Provider Abstraction (GraphQL-First)

### Summary
- Add a new dock panel named `Import Videos/Images`, with the same show/hide checkbox behavior as existing panels.
- Keep this phase strictly UI-only: no remote calls and no import into existing target media.
- Add a generic provider interface plus a first GraphQL provider implementation scaffold.

### Implementation Changes
- UI shell:
  - Update [MainWindow.ui](S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/core/MainWindow.ui) to add `ImportMediaCheckBox` in `panelVisibilityCheckBoxLayout`.
  - Add new `QDockWidget` (`import_Media_DockWidget`) titled `Import Videos/Images` in the left dock area, matching existing dock sizing/features.
  - Panel structure:
    - Top tabs: `Browser`, `Settings`.
    - `Browser` contains media-separated tabs: `Videos`, `Images`, `Saved Videos`, `Saved Images`.
    - Each browser tab has search input, action button, and `QListWidget` placeholder.
    - `Settings` contains provider selector (`GraphQL` enabled), endpoint field, and query editors for video query, image query, and saved-searches query.
  - Regenerate [main_window.py](S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/core/main_window.py) using the existing UI conversion script.

- Behavior wiring (copy existing patterns):
  - In [main_ui.py](S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/main_ui.py), wire `ImportMediaCheckBox.toggled` to a new show/hide handler in [layout_actions.py](S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/actions/layout_actions.py), mirroring existing panel handlers.
  - Add UI-only handlers in a new `remote_import_actions` module for search buttons and tab actions; handlers validate required fields and return non-blocking “UI-only mode” feedback.
  - Reuse existing placeholder setup pattern for new remote result list widgets.

- Persistence and compatibility:
  - Add `ImportMediaCheckBox` into theatre-mode state capture/restore in [layout_actions.py](S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/actions/layout_actions.py).
  - Persist/restore checkbox state in [save_load_actions.py](S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/actions/save_load_actions.py) under `window_state_data`.
  - Persist remote settings in `main_window.control` with keys:
    - `RemoteImportProvider`
    - `RemoteImportGraphQLEndpoint`
    - `RemoteImportVideoQuery`
    - `RemoteImportImageQuery`
    - `RemoteImportSavedSearchesQuery`
  - Initialize default values during widget initialization so old workspaces remain loadable without errors.

- Provider abstraction:
  - Add `app/processors/remote_providers/` package with:
    - `types.py` for shared dataclasses/types (`RemoteMediaItem`, `RemoteSavedSearch`, `RemoteSearchResult`, config model, media-type enum).
    - `base.py` with abstract `RemoteMediaProvider` interface:
      - `provider_id()`
      - `validate_config(config)`
      - `search_videos(...)`
      - `search_images(...)`
      - `list_saved_searches(...)`
    - `graphql_provider.py` implementing the abstract interface with UI-only-safe behavior (validation implemented, deterministic empty results for search/list methods).
    - `registry.py` for provider lookup (`graphql` mapped, future providers pluggable).

### Test Plan
- Automated:
  - Unit tests for provider interface/registry and GraphQL provider UI-only behavior.
  - Unit tests for workspace save/load to verify new checkbox state and remote control keys are preserved.
- Manual:
  - Verify checkbox toggles panel visibility correctly.
  - Verify theatre mode saves/restores new panel state with existing panels.
  - Verify workspace save/load restores panel visibility plus endpoint/query settings.
  - Verify all browser tabs render and stay responsive with empty placeholders.

### Public Interface Additions
- New remote provider API package: `app/processors/remote_providers`.
- New persisted workspace/control keys listed above.

### Assumptions (Locked)
- UI-only means no network calls and no import into existing target media in this phase.
- `ImportMediaCheckBox` defaults to checked (`True`) to match current panel default behavior.
- Provider selector is present now, but only `GraphQL` is enabled.
- Images and videos remain separated in UI and provider API contracts.
