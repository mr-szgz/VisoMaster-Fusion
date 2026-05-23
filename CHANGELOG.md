# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.
Entries before this file was added were backfilled from git tags and version bump commits.

## [Unreleased]

### Changed

- Adjusted camera gaze lock behavior

## [3.4.1] - 2026-05-16

### Changed

- Showed more commits on the launcher rollback page
- Reduced card context menu handle usage

### Fixed

- Fixed workspace autosave for marker recordings

## [3.4.0] - 2026-05-16

### Added

- Added camera gaze lock controls
- Added a face compare keybind

### Changed

- Split eye calculations to simplify follow-on processing
- Separated video encoding into its own module
- Tweaked frame editing behavior and reduced memory use

### Fixed

- Cleaned up failed engine creation paths
- Added `.timing` cleanup to ONNX probe retries

## [3.3.1] - 2026-05-14

### Fixed

- Improved webcam reliability

## [3.3.0] - 2026-05-14

### Added

- Added a job-level `force_recognition_in_batch` flag

### Changed

- Optimized sequential detection behavior

## [3.2.3] - 2026-05-14

### Changed

- Reduced memory use during recent processing paths

### Fixed

- Fixed batch processing regressions
- Fixed input face loading issues

## [3.2.2] - 2026-05-13

### Fixed

- Fixed detection stability issues

## [3.2.1] - 2026-05-12

### Changed

- Adjusted degenerate handling for the 478-point landmark model

## [3.2.0] - 2026-05-12

### Added

- Added GPU selection support for multi-GPU systems

## [3.1.2] - 2026-05-11

### Added

- Added Auto Mouth options to exclude upper teeth and show mouth outlines

### Changed

- Pinned ONNX Runtime GPU to the stable CUDA 13 build
- Backfilled the patch-version release path

### Fixed

- Fixed detector input size resolution in batch detection

## [3.1.0] - 2026-05-10

### Added

- Added Mouth Fit & Align occlusion support for the original face

### Changed

- Hardened model unload safeguards and reduced memory pressure
- Improved feed video dirty-state handling

### Fixed

- Fixed stop-processing behavior
- Fixed degenerate 5-point alignment edge cases

## [3.0.9] - 2026-05-09

### Removed

- Removed the redundant `Start.bat` path from the portable release flow

## [3.0.8] - 2026-05-09

### Changed

- Refreshed the README and download guidance

## [3.0.7] - 2026-05-08

### Fixed

- Fixed webcam loading

## [3.0.6] - 2026-05-08

### Fixed

- Kept tracking landmarks aligned when detailed 203-point and 478-point detections refine a face

## [3.0.5] - 2026-05-08

### Fixed

- Applied a broad batch of stability and processing fixes

## [3.0.4] - 2026-05-08

### Fixed

- Fixed portable launcher dependency updates

## [3.0.3] - 2026-05-08

### Changed

- Moved launcher script sources into `scripts/`

### Fixed

- Fixed CUDA 13 ONNX Runtime nightly index handling

## [3.0.2] - 2026-05-08

### Added

- Added start scripts under `app/scripts`

## [3.0.1] - 2026-05-08

### Changed

- Updated ONNX Runtime GPU to a CUDA 13 nightly build

## [3.0.0] - 2026-05-06

### Changed

- Switched the runtime and dependency stack to CUDA 13 packages
- Updated launcher and README guidance for the new runtime layout
- Refined portable launcher self-update behavior

### Fixed

- Reduced high CPU load introduced by the runtime transition
- Corrected launcher and README inconsistencies around the portable flow

## [2.1.2] - 2026-05-05

### Changed

- Continued validating the automated version bump workflow

## [2.1.1] - 2026-05-05

### Changed

- Refreshed documentation for the `2.0.0` release
- Restricted automated version bumps to the `dev` branch

### Fixed

- Fixed version bump workflow permissions

## [2.1.0] - 2026-05-02

### Added

- Added an option to preserve the source directory structure in outputs

### Changed

- Optimized media loading for large directories and sorted loads more predictably

### Fixed

- Fixed restored media ordering on startup
- Fixed workspace restore for selected faces, toggles, and assignments
- Fixed duplicate embedding IDs that could make later batch jobs skip swaps

## [2.0.1] - 2026-05-02

### Added

- Added theatre fullscreen mode and recording stop confirmation
- Added Arc Similarity controls and clear-all actions in face and embedding panels
- Added auto source quality matching

### Changed

- Refined collapsible parameter sections, media thumbnails, path controls, and folder shortcuts
- Added tracked `version.json` versioning metadata

### Fixed

- Fixed stale target video previews and webcam restore issues
- Fixed issue scanner state, warning noise, and marker-resolved behavior
- Fixed KPS resize and tracking edge cases
- Fixed batch progress stop-confirm races
- Disabled detection when no target face is active

## [2.0.0] - 2026-04-19

### Added

- Added ByteTrack-based face tracking, issue scan and frame review tools, and output clustering controls
- Added Re-Age, Auto Mouth, Mouth Fit & Align, and other face editing refinements
- Added Windows11-Dark theming, theatre mode refinements, and broader user documentation

### Changed

- Reworked the portable launcher, versioning preparation, and workspace persistence flow
- Expanded VR and playback pipelines with tiled detection, better fullscreen behavior, and stronger caching

### Fixed

- Fixed skipped-frame audio rebuilds, batch stop-confirmation races, and multiple workspace restore bugs
- Fixed detector input sizing, landmark stability, VR edge cases, and a wide set of UI regressions

## [1.0.0] - 2025-11-04

### Added

- Launched VisoMaster Fusion as a combined fork of the experimental, job manager, and VR180 variants
- Added a portable Windows launcher, uv-managed environment setup, and virtual camera output
- Added audio preview playback, improved workspace persistence, and early Ref-LDM and VR workflow support

### Changed

- Shifted the portable stack toward Python 3.11, CUDA 12.9, and bundled FFmpeg handling
- Reworked job management, recognition model loading, and launcher self-update behavior

### Fixed

- Fixed model loading and unloading across TensorRT, restorers, landmarks, and denoiser paths
- Fixed VR detection and memory spikes, portable setup issues, and last-workspace restoration after job runs
