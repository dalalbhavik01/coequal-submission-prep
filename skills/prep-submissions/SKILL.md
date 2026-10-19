---
name: prep-submissions
description: Prepare downloaded Canvas submissions for upload to CoEqual — convert .html text entries and .pptx decks to accepted formats, strip Word font bloat, compress under CoEqual's 500 KB cap, and validate every output. Use this whenever the user mentions preparing, converting, compressing, shrinking, or fixing a folder of student submissions; when CoEqual rejects files as too large or the wrong format; when a Canvas bulk download contains .pptx, .html, or .gdoc files; when the user asks to "make these upload ready"; or when they write \prep-submissions.
---

# Prep Submissions

Turn a Canvas bulk-download folder into a set of files CoEqual will actually accept, without
damaging the content being graded.

## Why this is not just "compress the files"

CoEqual accepts **only `.docx` and `.pdf`**, and caps each file at **500,000 bytes**. Canvas
routinely breaks both rules. Two things make this harder than it sounds:

1. **The bulk of a file is usually not the content.** Word embeds multi-megabyte font subsets;
   a 1.7 MB submission can be 15 KB of text wrapped in 3.2 MB of fonts. Compressing images on a
   file like that destroys quality for no reason.
2. **The thing being graded often lives inside the images.** Statistical output, charts and
   model tables arrive as screenshots. Compress too hard and the p-values become unreadable —
   you have technically met the size cap and ruined the submission.

So the work is diagnostic before it is destructive: find out *what* is big, then apply the
cheapest fix that clears the cap.

## Run the tool, don't rebuild it

`tools/prep_submissions.py` implements this whole pipeline, including guards that took real
breakage to discover. Reach for it first:

```bash
python tools/prep_submissions.py ~/Downloads/submissions
```

It reads a folder, writes validated copies to `<folder>/upload-ready/`, leaves the originals
untouched, and is idempotent — re-running over prepared files is a no-op.

Useful flags: `-o/--out` for a different output folder, `--limit` to change the byte cap.

Extend the tool when it is missing something. Writing a parallel one-off script means
re-discovering the same bugs — a stream rewrite that corrupted pages, and a dropped soft mask
that turned a logo into a black box, both of which now have guards.

## The escalation ladder

Apply the cheapest, least destructive fix first and **stop the moment the file is under the
cap**. Most files never reach step 3.

| Step | Fix | Cost |
|---|---|---|
| 1 | Strip embedded fonts (`.docx`) / lossless re-save (`.pdf`) | None — fonts are cosmetic |
| 2 | Recompress embedded images | Guarded; rejected if the page visibly changes |
| 3 | Flatten pages to JPEG, re-insert text as an invisible layer | Last resort; page looks identical and text still extracts |

Full detail, including the per-format routing and the render-drift guard, is in
[references/pipeline.md](references/pipeline.md). Read it before changing any compression
behaviour.

## Format routing

| Input | What it is | Treatment |
|---|---|---|
| `.docx` | accepted | strip fonts → recompress images |
| `.pdf` | accepted | lossless re-save → downsample images |
| `.html` / `.txt` | Canvas text-box entry | convert to `.docx` |
| `.pptx` | slide deck | export to PDF, then run the PDF ladder |
| `.gdoc` / `.gsheet` / `.gslides` | **a link stub, not a document** | cannot be fixed — see below |
| `~$*.pptx` | Office lock file, ~165 bytes | not a submission; exclude it |

A `.gdoc` is roughly 180 bytes of JSON holding a Drive document ID. There is no content to
convert and no tooling fix. **A `.gdoc` reaching you is always a failed submission** — report it
and ask for the student to re-export as PDF. Do not spend effort trying to resolve it.

Converting `.pptx` has a platform wrinkle worth knowing before you debug it:
[references/troubleshooting.md](references/troubleshooting.md).

## Check the batch, not just the files

A file that converted cleanly can still be the wrong file, or the only file where two were
expected. Before uploading, count files per team using the `<team>_` prefix Canvas puts on every
export, and confirm the batch size matches the assignment's group count.

The two failures this catches are both invisible to per-file checks: a team missing a
deliverable entirely (which scores zero on whatever criterion it covered), and a batch that
merges two course sections into an assignment configured for one. Both have happened; both are
cheap to detect and expensive to unwind after upload.

See [references/batch-integrity.md](references/batch-integrity.md).

## Never publish student data

These folders hold real names, grades and written work. The repository `.gitignore` excludes
`submissions/`, `outputs/`, `grades/`, `upload-ready/` and every document extension. Keep it
that way. Do not commit a submission, a grade export, or a sample file "for testing", and do not
paste student content into an issue or a public page.

## Verify before reporting

Size is the easiest thing to check and the least important. Confirm the content survived:

- **Text retained** — extract before and after and diff the word sets.
- **Slide count equals page count** for every converted deck.
- **Legibility, by looking** — when images were recompressed, extract one and actually read it.
  If the numbers in a screenshot are the graded artefact, a size figure is not evidence.

Two false alarms waste real time; both are described in
[references/verification.md](references/verification.md).

## Report honestly

State what changed, what was left alone, and what could not be fixed. In particular:

- Name any file that **cannot** reach the cap without damage, and say what its best achievable
  size was, so the user can decide. A pristine oversized original often beats a degraded one
  that still fails the cap.
- Name every `.gdoc` and every missing deliverable. These need a human, not a retry.
- Say where the originals went. The tool leaves them in place, which means the source folder
  still shows `.html` and `.pptx` after a successful run. Those are consumed inputs, not
  failures — but they read as failures. Move them to the Trash (never `rm`) and report both
  folder counts side by side so the distinction is visible.

## References

- [references/pipeline.md](references/pipeline.md) — the ladder, per-format rules, the guards
- [references/verification.md](references/verification.md) — what to check and the known false alarms
- [references/batch-integrity.md](references/batch-integrity.md) — missing deliverables, merged sections, duplicates
- [references/troubleshooting.md](references/troubleshooting.md) — platform quirks and environment limits
