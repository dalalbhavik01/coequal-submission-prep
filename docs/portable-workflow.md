# Portable Workflow

Paste this into any capable agent that has shell access and a filesystem. It is the skill
reduced to an operating prompt, for environments where you cannot install a skill folder.

---

You are preparing a folder of Canvas submission exports for upload to CoEqual.

**Limits.** CoEqual accepts only `.docx` and `.pdf`, and rejects any file over 500,000 bytes.
The cap is a hard reject, not a target. One upload set per assignment — never merge batches.

**Run the tool if it is available**, rather than writing your own:

```bash
python tools/prep_submissions.py <folder>
```

It writes validated copies to `<folder>/upload-ready/`, leaves originals untouched, and is safe
to re-run. If you do not have it, follow the ladder below by hand.

**Work diagnostically, not destructively.** Before compressing anything, find out what is
actually large. Word embeds multi-megabyte font subsets, so a 1.7 MB file can be 15 KB of text
wrapped in 3.2 MB of fonts — compressing its images would destroy quality for no reason. Profile
each oversized file by summing the bytes under `/media/` versus `/fonts/` versus the XML.

**Apply the cheapest fix first and stop as soon as the file is under the cap:**

1. Strip embedded fonts (`.docx`/`.pptx`) or losslessly re-save (`.pdf`). Fonts are cosmetic;
   dropping them changes nothing about the content.
2. Recompress embedded images, stepping down through quality tiers. After rewriting a PDF,
   render the page before and after and compare — reject the rewrite if the page visibly
   changed rather than shipping it.
3. As a last resort, flatten pages to JPEG and re-insert the text as an invisible layer, so the
   page looks identical and the text still extracts.

**Route by type.** `.html`/`.txt` are Canvas text-box entries and convert to `.docx`. `.pptx`
exports to PDF via PowerPoint or Keynote — never rebuild a deck from extracted text. `.gdoc`,
`.gsheet` and `.gslides` are ~180-byte link stubs with no content: they cannot be fixed, and one
reaching you is always a failed submission. Files containing `~$` are Office lock files, not
submissions.

**Verify, do not assume.** Confirm text survived with a word-set diff, that slide count equals
page count for converted decks, and — when the graded artefact is a screenshot of charts or
statistical output — extract one image and actually read it. A smaller file is not a surviving
file.

**Report per-file.** Name anything you could not fix and say what its best achievable size was,
so the user can decide. A pristine oversized original often beats a degraded one that still
fails the cap. Name every `.gdoc` and every missing deliverable; those need a human.

**Never publish or commit student data.** These folders hold real names, grades and written work.
