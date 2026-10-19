# Troubleshooting

## Converting .pptx to PDF on macOS

**Microsoft PowerPoint is the primary path and the one the tool uses.** Its native export
preserves layout, type and colour exactly, which matters because decks are graded on visual
communication.

```applescript
tell application "Microsoft PowerPoint"
  open POSIX file "/path/to/deck.pptx"
  save active presentation in POSIX file "/path/to/deck.pdf" as save as PDF
  close active presentation saving no
end tell
```

Two AppleScript errors come up, and they mean different things:

- **`-1712` (AppleEvent timed out)** — a first-run, licence or sign-in dialog is blocking
  automation. Nothing in the terminal says so. Open PowerPoint manually once, dismiss whatever
  it is asking, and re-run. This resolves it; it is not a reason to abandon PowerPoint.
- **`-50` (Parameter error)** — the input is not a real presentation. Usually an Office lock
  file (`~$*.pptx`) that slipped through, or a truncated upload.

**Keynote is a verified fallback** if PowerPoint is unavailable:

```applescript
tell application "Keynote"
  set d to open POSIX file "/path/to/deck.pptx"
  export d to POSIX file "/path/to/deck.pdf" as PDF
  close d saving no
end tell
```

Fidelity is high — layout, colour, typography and multi-column structure all survive. Two quirks
of its own: let it warm up, because the first few files in a cold loop fail and then succeed on
retry; and it re-encodes images, so an exported PDF can be *larger* than the compressed source,
which means re-running the compression ladder afterwards.

**Never rebuild a deck from extracted text.** A text-only reconstruction scores the wrong thing.

## Converting .html

Canvas text-box entries arrive as `<n>_<id>_text.html`. These are real content and convert
cleanly to `.docx` via pandoc, which is what the tool uses when pandoc is installed; it falls
back to a built-in converter otherwise.

To produce a PDF instead, headless Chrome works:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --no-pdf-header-footer \
  --user-data-dir=/tmp/profile-N --print-to-pdf=out.pdf "file:///path/in.html"
```

Chrome's headless mode often does not exit cleanly — it writes the PDF and then hangs. Check for
the output file rather than waiting on the process, and give each invocation its own
`--user-data-dir`, or concurrent runs block on the profile lock.

## Environment limits seen in the field

Do not assume the usual toolchain is present. On a stock macOS machine you may find **no
LibreOffice, no ghostscript, no ImageMagick, no qpdf**. Check before planning around them — this
is why the pipeline is built on PyMuPDF and Pillow rather than shelling out to converters.

System Python may be old enough to matter: 3.9 cannot run code using
`tempfile.TemporaryDirectory(ignore_cleanup_errors=...)`, which rules out some helper tooling.

Install dependencies into a virtual environment rather than system-wide:

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
```
