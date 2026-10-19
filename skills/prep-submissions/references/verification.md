# Verification

Size is trivially checkable and tells you almost nothing. These checks tell you whether the
submission survived.

## Content retained

Extract text before and after and compare **word sets**, not character counts or normalised
strings. Formatting changes shift whitespace and punctuation constantly; vocabulary does not.

## Structure preserved

- Converted decks: **slide count must equal page count.** A mismatch means slides were dropped.
  (Exception: hidden slides do not export. Expected, not an error.)
- Archives: the zip must still open and every XML part must still parse.

## Legibility, by eye

When images were recompressed and the graded artefact lives inside them — statistical output,
charts, tables — **extract one image and read it.** A size reduction is not evidence that the
numbers are still readable. This takes a minute and is the only check that catches the failure
that actually matters.

Rough guide from real batches: screenshots of application UI remained fully legible at 700px
maximum dimension / quality 48, and parameter tables at 550px / quality 52. Treat these as
starting points to verify, not as settings to trust blindly.

## Two false alarms

**Theme GUIDs inflate "lost text".** PowerPoint slide XML contains theme GUID strings like
`{CE2E32B3-B00B-4DCA-9D3A-E55D035EC2BE}`. Normalising text that includes them made two decks
appear to lose ~30% of their content. A direct word-set diff showed zero missing words. Strip
markup-only tokens before comparing.

**Leftover source files look like failures.** Because the pipeline is non-destructive, the
source folder still contains `.html` and `.pptx` after a completely successful run. This reads
as "the conversion didn't work" and has been reported as a bug repeatedly. Move consumed
originals to the Trash (never `rm` — irreversible deletes are worse than clutter) and report
both folder counts side by side.

## Report per-file, not in aggregate

"68 of 70 under the cap" hides which two failed and why. List the exceptions by name with their
size and the reason, so the user can act on them.
