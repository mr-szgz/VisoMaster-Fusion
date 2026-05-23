---
name: keepachangelog
description: Maintain and validate `CHANGELOG.md` using the Keep a Changelog format and Semantic Versioning. Use when adding entries to the Unreleased section, preparing a release section with a date, or checking that headings and sections follow Keep a Changelog conventions.
---

# Keep a Changelog

Follow this workflow to update `CHANGELOG.md` in this repo.

## Workflow

1. Review keepachangelog skill
2. Open `CHANGELOG.md` and keep the existing top matter intact.
3. Add new entries under `## [Unreleased]` in the appropriate category:
   `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
4. Use bullet points and match existing style:
   short, concrete, past-tense phrases; backtick CLI flags; include a scope in parentheses when helpful (for example `(arcfaces)`).
5. Keep section order consistent and avoid empty category headings unless they already exist.
6. When releasing:
   - Move all Unreleased entries into a new version section.
   - Format the heading as `## [X.Y.Z] - YYYY-MM-DD`.
   - Insert the new version section directly below `## [Unreleased]`.
   - Leave `## [Unreleased]` present (empty or with only headings, following existing style).

## Validation Checklist

- `## [Unreleased]` remains the first section.
- Version sections are in descending order (latest first).
- Dates use `YYYY-MM-DD`.
- Categories are standard Keep a Changelog headings.
- Bullets are consistent with existing phrasing and punctuation.

## User-Facing References

If a user asks for the rules, examples, or source material, provide short, relevant snippets from these references. Offer the file path and, if requested, show the file tree under `references/`.

Only paste larger sections when the user explicitly asks for the full file content.

## Notes

- Do not invent new categories.
- Do not rename existing headings unless requested.
- Preserve links and references if they are present at the end of the file.
