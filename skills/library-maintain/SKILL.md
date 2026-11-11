---
name: library-maintain
description: Search and inspect an Embodied Paper Notes repository, resolve quality issues, preserve human annotations, and perform requested Git synchronization. Use for library upkeep and existing-note corrections, not new literature discovery or automatic deletion.
---

# Maintain the local research library

Use the repository selected by `embodied-notes` or `epn --root PATH`. Inspect `get_capabilities` and tool schemas once. Generated paper notes, human annotations, raw caches and website artifacts have different roles; do not treat them as interchangeable copies.

## Find and inspect

Use `search_library` for queries and `read_paper_note` for exact records. Run `inspect_library` for quality/duplicate candidates and `check_library` for structural/evidence validation. A warning is a finding to evaluate, not permission to delete or overwrite a note. Compare stable identifiers and versions before calling two titles duplicates.

For a correction, read the current note and its evidence. Update generated conclusions through `prepare_paper` and `commit_paper_summary`, preserving `locked_tags` and checking coverage. A new source version must remain distinguishable from the previously read version. Reprepare and reconcile if a revision check fails; never suppress the conflict by guessing a replacement revision.

## Human annotations

Human text lives in `content/annotations/`. When the user explicitly requests an annotation edit, call `read_annotation`, prepare the smallest change, then `update_annotation` with the exact revision token required by the tool. Verify the returned content/revision. On a conflict, reread and merge only the requested change. Regenerating an AI summary does not authorize annotation edits.

## Queue and synchronization

- Inspect `list_queue` and use `update_queue` only for task-relevant status changes, copying the returned queue `paper_id` and whole-queue `revision`. A saved candidate is not a fully read paper; failed ingestion must not be marked complete.
- For requested Git synchronization, inspect `git status` and the current branch/remote first. Fetch remote state and review divergence before merging. Preserve uncommitted edits, resolve same-note conflicts using both versions, and run validation before publishing. Avoid force-push, resets or automatic conflict winners.
- A note-writing request alone does not authorize pushing a repository. Honor any already-authorized automatic publication workflow without adding a new approval gate.
- Keep credentials, PDF/text caches and generated site output out of commits. Inspect the actual diff; Git ignore rules do not remove a secret already tracked.

Return what was repaired, what remains unresolved, and the validation/synchronization result. If a repair needs destructive merging or removal outside the user's request, present the concrete affected records before proceeding.
