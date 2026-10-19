# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added an optional processed-item limit to batch media processing, defaulting to 100 items, with saved settings and a stop report.
- Added a batch job-saving dialog with progress, cancellation, stop limits, target clearing, notification preferences, and detailed results.
- Added a "Check for New" job queue action that preserves existing entries and selection.
- Added a minimum frame count for saving skipped partial videos and live batch frame, rate, and item-progress reports.

### Changed

- Renamed the batch partial-video checkbox to "Save partial videos" without changing its behavior.
- Grouped the batch stop controls and notification checkbox between horizontal rules at the bottom of the options list.
- Kept batch dialogs nonmodal with independent minimize and restore behavior.
- Reset "Stop after current item" when opening processing dialogs while retaining other checkbox preferences.

### Fixed

- Reused saved job data during batch queue insertion and serviced UI events to avoid redundant JSON reads and an unresponsive final update.
- Preserved compatible model sessions and avoided competing preview processing during job transitions.
- Removed completed jobs without rebuilding the queue and retained final batch reports when intermediate notifications were suppressed.
- Saved skipped jobs with the current face parameters and output settings.
