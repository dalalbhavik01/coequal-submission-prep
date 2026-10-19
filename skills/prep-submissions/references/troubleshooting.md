# Troubleshooting

## Converting .pptx to PDF on macOS

**Keynote is the reliable path.**

```applescript
tell application "Keynote"
  set d to open POSIX file "/path/to/deck.pptx"
  export d to POSIX file "/path/to/deck.pdf" as PDF
  close d saving no
end tell
```

Fidelity is high — layout, colour, typography and multi-column structure all survive.

Two gotchas:

- **Let Keynote warm up.** The first few files in a cold loop fail and then succeed on retry.
  Launch it, pause, then iterate; retry failures once before reporting them.
- **Keynote re-encodes images**, so an exported PDF can be *larger* than the compressed source.
  Re-run the compression ladder afterwards.

**Microsoft PowerPoint's AppleScript route is unreliable.** `save as PDF` returns AppleEvent
timeout (-1712) when a first-run or sign-in dialog is blocking automation — and nothing on the
terminal tells you that is why. It has worked historically, so try it if you like, but do not
burn time debugging it; switch to Keynote.

**Never rebuild a deck from extracted text.** Decks are graded on visual communication. A
text-only reconstruction scores the wrong thing.

## Converting .html

Canvas text-box entries arrive as `<n>_<id>_text.html`. These are real content and convert
cleanly to `.docx` via pandoc, or to PDF via headless Chrome:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --no-pdf-header-footer \
  --user-data-dir=/tmp/profile-N --print-to-pdf=out.pdf "file:///path/in.html"
```

Chrome's headless mode often does not exit cleanly — it writes the PDF and then hangs. Check for
the output file rather than waiting on the process, and give each invocation its own
`--user-data-dir` or concurrent runs will block on the profile lock.

## Environment limits seen in the field

Do not assume the usual toolchain is present. On a stock macOS machine you may find **no
LibreOffice, no ghostscript, no ImageMagick, no qpdf**. Check before planning around them.

System Python may be old enough to matter — 3.9 cannot run scripts using
`tempfile.TemporaryDirectory(ignore_cleanup_errors=...)`, which rules out some helper tooling.

Generally available and sufficient: Pillow, pypdf/PyMuPDF, openpyxl, `sips`, `qlmanage`,
Keynote, headless Chrome.
