# Verification Checklist

Run through this before telling anyone a batch is ready. Size is the easiest thing to check and
the least informative.

## Per file

- [ ] Extension is `.docx` or `.pdf`
- [ ] Size ≤ 500,000 bytes
- [ ] Archive opens and every XML part parses (`.docx`), or the document opens (`.pdf`)
- [ ] Text retained — word-set diff against the source, not a character count
- [ ] Slide count equals page count (converted decks only; hidden slides legitimately drop)
- [ ] If images were recompressed and the graded content lives inside them, one image was
      extracted and read

## Per batch

- [ ] Every team accounted for; note any team with fewer files than expected
- [ ] No `.gdoc` / `.gsheet` / `.gslides` passed through as if it were a document
- [ ] No `~$*` lock file treated as a submission
- [ ] Team/submission ID prefixes unchanged, so files still map back to teams
- [ ] Originals still present and unmodified
- [ ] Consumed originals moved to the Trash, so the source folder shows only what still needs
      attention

## Known false alarms

- **Apparent text loss from theme GUIDs.** PowerPoint slide XML contains strings like
  `{CE2E32B3-B00B-4DCA-9D3A-E55D035EC2BE}`. Including them in a normalised comparison made two
  decks look like they had lost ~30% of their content when nothing was missing. Compare word
  sets, not normalised strings.
- **Leftover source files.** The pipeline is non-destructive, so `.html` and `.pptx` remain in
  the source folder after a completely successful run. This reads as a conversion failure and
  has been reported as a bug repeatedly. It is not one.

## Reporting

State what changed, what was deliberately left alone, and what could not be fixed. "68 of 70
under the cap" hides which two failed and why — list the exceptions by name, with size and
reason.
