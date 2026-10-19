# Pipeline

The order matters. Each step is more destructive than the last, so the pipeline stops as soon as
a file is under the cap.

## Limits

- **500,000 bytes** per file. A hard reject, not a target — do not propose uploading anyway.
- **`.docx` and `.pdf` only.**
- One upload set per assignment. Never merge batches: a reflection (one file per team) and a
  group assignment (two files per team) are separate CoEqual assignments even when the teams
  are identical.

## Step 1 — strip embedded fonts (lossless)

Word stores font subsets in `word/fonts/*.odttf`, PowerPoint in `ppt/fonts/*.fntdata`. They are
purely cosmetic: dropping them makes the application render the same named fonts from the
system instead. Nothing about the content changes.

To remove them cleanly, delete the font parts *and* every reference to them, or the file will
not open:

- the font parts themselves
- `<w:embedRegular|embedBold|embedItalic|embedBoldItalic>` in `word/fontTable.xml`
- `<p:embeddedFontLst>` in `ppt/presentation.xml`
- the font relationships in `word/_rels/fontTable.xml.rels` / `ppt/_rels/presentation.xml.rels`
- the `odttf` / `fntdata` defaults in `[Content_Types].xml`
- `<w:embedTrueTypeFonts|embedSystemFonts|saveSubsetFonts>` in `word/settings.xml`

This alone routinely resolves the majority of oversized Word files. Observed: 1.67 MB → 11.7 KB,
2.4 MB → 452 KB, 876 KB → 23 KB, all with text byte-identical afterwards.

**Profile before acting.** Sum the bytes under `/media/` versus `/fonts/` versus the XML. If a
file is 90% fonts, compressing its images is wasted damage.

## Step 2 — recompress images (guarded)

Downsample by maximum dimension and re-encode, stepping down through quality tiers and stopping
at the first tier under the cap.

Two things that are easy to get wrong:

- **PNG screenshots of UI beat JPEG.** Palette-quantising a screenshot to 256 colours preserves
  text far better than JPEG at an equivalent size, because JPEG rings around high-contrast
  glyph edges. Try both and keep whichever is smaller *at acceptable quality*.
- **In PDFs, rewrite the image XObject streams directly.** pypdf's `page.images[].replace()`
  can silently do nothing. When rewriting, resolve **ICCBased** colorspaces via the `/N` entry
  in the ICC stream, or a large share of images get skipped as "unknown colorspace". Composite
  any `/SMask` onto white before re-encoding, otherwise transparency becomes a black box.

**The render guard.** After rewriting a PDF, render the page before and after and measure pixel
drift. Reject anything above a tolerance of ~3.0 and fall back rather than shipping it. This
guard exists because two bugs shipped silently without it: a stream rewrite that corrupted pages
at drift 55–93, and a dropped soft mask that passed a loose tolerance at drift 8.4.

## Step 2b — lossless polish (before giving up)

Between recompressing images and flattening, there is a free rung worth taking: Flate-compress
any stream that is still stored uncompressed, and deduplicate identical objects. Logos and
headers repeat on every page and often sit in the file many times over.

This changes nothing visible and pulled two files under the cap in a real batch without touching
image quality. Try it before accepting any further loss.

## Step 3 — flatten (last resort)

When a file still will not fit, flatten the pages to JPEG and re-insert the text as an
**invisible layer in a base-14 font**. The page looks the same and the text still extracts,
which is what a grader actually reads. Plain rasterising would make the document ungradeable.

## When to stop

If a PDF's bulk is content streams rather than images, no amount of image downsampling will get
it under the cap. Leave the pristine original, report the best achievable size, and let the user
decide. Degrading a file that still fails the cap is pure loss.

## Properties worth preserving

- **Non-destructive** — originals stay put; output goes to a separate folder.
- **Idempotent** — re-running over prepared files is a no-op.
- **Named consistently** — Canvas encodes `<team>_<userid>_<submissionid>_<title>`. Keep the
  prefix intact; it is the only reliable mapping back to a team.
