# Batch Integrity

Per-file checks catch files that broke. Batch-level checks catch files that were never there,
or that belong to a different assignment — and those are the ones that change grades. Run these
*before* uploading, because afterwards they are expensive to unwind.

Canvas names every export `<team>_<userid>_<submissionid>_<title>`, so the leading number gives
you the team for free. Everything below is a few lines of parsing over that.

## Does every team have the expected number of files?

Count files per team, take the modal count, and flag every deviation **in both directions**.

- **Below the mode — a missing deliverable.** This is the costly one. If an assignment expects
  a technical document *and* a slide deck, a team with one file scores zero on whichever
  criterion the missing file covers. Nothing about the remaining file looks wrong, so it passes
  every per-file check cleanly.
- **Above the mode — a duplicate or an individual make-up submission.** Usually benign (a
  student who missed the group session submitting separately), but worth confirming rather than
  grading twice.

Observed in a real batch of 36 teams at two files each: one team had submitted no technical
documentation, and another's second file was a 165-byte Office lock file rather than a deck.
Both lost a full criterion. Neither was visible without counting.

## Does the batch match the assignment's scope?

A folder of submissions does not announce which course section it came from, and merging two
Canvas downloads is an easy mistake. Before uploading, confirm the batch size matches the
assignment's group count.

When it does not, scan the extracted text for section or cohort markers — course codes,
section numbers, cohort names. Teams usually put them on the title page.

Observed: a batch of 36 teams uploaded against an assignment configured for 18 groups of one
section. Scanning the documents showed every team numbered 18 or below naming one section, and
every team above it naming another — a clean split into two sections of 18, completely
invisible from the filenames. Uploading as-is would have put a second section's work into the
wrong assignment.

## Are there duplicates within a team?

Two files with the same team prefix and near-identical content usually means a resubmission that
Canvas kept both copies of. Grade the later `submissionid`, not both.

## Report before uploading

Say which teams deviate from the expected file count and in which direction, and whether the
batch size matches the assignment. These need a human decision — a missing deliverable might be
an upload failure worth chasing rather than a zero, and only the instructor knows which.

Do not silently proceed. A batch that uploads cleanly and is quietly wrong is worse than one
that stops and asks.
