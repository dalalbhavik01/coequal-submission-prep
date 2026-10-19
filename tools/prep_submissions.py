#!/usr/bin/env python3
"""Prepare downloaded Canvas submissions for upload to CoEqual.

CoEqual accepts only .docx / .pdf and caps each file at 500 KB. Canvas exports
routinely break both rules: Word embeds multi-megabyte font subsets, and
text-entry submissions come down as .html.

This reads a submissions folder and writes a clean, validated set to an output
folder, leaving the originals untouched. It is idempotent -- re-running over
already-prepared files is a no-op.

    python tools/prep_submissions.py ~/Downloads/submissions

Fixes applied, cheapest first, only as far as needed to get under the cap:
  .docx  strip embedded fonts -> recompress embedded images
  .pdf   lossless re-save     -> downsample embedded images
  .html  convert to .docx (pandoc if installed, else a built-in converter)
  .pptx  export to .pdf via Microsoft PowerPoint, then compress as a .pdf
"""

from __future__ import annotations

import argparse
import io
import re
import shutil
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_LIMIT = 500_000
DOC_EXTS = {".docx", ".pdf"}
CONVERTIBLE = {".html", ".htm", ".txt"}
SLIDES = {".pptx", ".ppt"}

# --- .docx: embedded fonts -------------------------------------------------
# Word stores font subsets in word/fonts/*.odttf. They are purely cosmetic --
# dropping them makes Word render the same named fonts from the system.
FONT_PART = "word/fonts/"
RE_EMBED = re.compile(rb"<w:embed(?:Regular|Bold|Italic|BoldItalic)\b[^>]*/>")
RE_SETTING = re.compile(rb"<w:(?:embedTrueTypeFonts|embedSystemFonts|saveSubsetFonts)\b[^>]*/>")
RE_FONT_REL = re.compile(rb'<Relationship\b[^>]*relationships/font"[^>]*/>')
RE_ODTTF_CT = re.compile(rb'<Default\b[^>]*Extension="odttf"[^>]*/>')


def docx_text(path: Path) -> str:
    """Body + table text, used to prove a rewrite changed nothing that matters."""
    import docx

    d = docx.Document(str(path))
    body = "\n".join(p.text for p in d.paragraphs)
    tables = "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
    return body + tables


def recode_docx_image(data: bytes, suffix: str, max_dim: int, quality: int):
    """Return (new_bytes, new_suffix) or None.

    Screenshots stored as PNG dominate these documents and palette-quantising
    them barely helps, so an opaque PNG is re-encoded as JPEG. That changes the
    part's extension, which drives the package content type -- the caller must
    rename the part and repoint every relationship at it.
    """
    from PIL import Image

    fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}.get(suffix.lower())
    if not fmt:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        # Screenshots pasted from the clipboard carry an alpha channel that is
        # fully opaque. Only keep PNG when transparency is actually USED --
        # otherwise every screenshot is locked into PNG and never shrinks.
        if img.mode in ("RGBA", "LA"):
            alpha = img.getchannel("A")
            if alpha.getextrema()[0] == 255:
                img = img.convert("RGB")
        elif img.mode == "P" and "transparency" in img.info:
            img = img.convert("RGBA")
            if img.getchannel("A").getextrema()[0] == 255:
                img = img.convert("RGB")
        has_alpha = img.mode in ("RGBA", "LA")
        buf = io.BytesIO()
        if has_alpha:
            # Keep alpha (and therefore PNG) so nothing turns into a black box.
            img.save(buf, "PNG", optimize=True)
            new_suffix = ".png"
        else:
            img.convert("RGB").save(buf, "JPEG", quality=quality,
                                    optimize=True, progressive=True)
            new_suffix = ".jpeg"
    except Exception:
        return None
    out = buf.getvalue()
    return (out, new_suffix) if len(out) < len(data) else None


def rewrite_docx(src: Path, dst: Path, *, strip_fonts: bool, image_budget: int | None,
                 max_dim: int = 1600, quality: int = 70) -> None:
    """Copy src -> dst, optionally dropping font parts and shrinking images."""
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        payload: dict[str, bytes] = {}
        renames: dict[str, str] = {}

        for item in zin.infolist():
            name = item.filename
            if strip_fonts and name.startswith(FONT_PART):
                continue
            data = zin.read(name)
            if image_budget and name.startswith("word/media/") and len(data) > image_budget:
                got = recode_docx_image(data, Path(name).suffix, max_dim, quality)
                if got:
                    data, new_suffix = got
                    if new_suffix != Path(name).suffix.lower():
                        new_name = str(Path(name).with_suffix(new_suffix))
                        renames[Path(name).name] = Path(new_name).name
                        name = new_name
            payload[name] = data

    # Repoint relationships at renamed parts and guarantee the content types.
    for name in list(payload):
        if name.endswith(".rels"):
            blob = payload[name]
            for old_base, new_base in renames.items():
                blob = blob.replace(old_base.encode(), new_base.encode())
            payload[name] = blob
        elif strip_fonts and name == "word/fontTable.xml":
            payload[name] = RE_EMBED.sub(b"", payload[name])
        elif strip_fonts and name == "word/settings.xml":
            payload[name] = RE_SETTING.sub(b"", payload[name])

    if "word/_rels/fontTable.xml.rels" in payload and strip_fonts:
        payload["word/_rels/fontTable.xml.rels"] = RE_FONT_REL.sub(
            b"", payload["word/_rels/fontTable.xml.rels"])

    ct = payload.get("[Content_Types].xml", b"")
    if strip_fonts:
        ct = RE_ODTTF_CT.sub(b"", ct)
    if renames and b'Extension="jpeg"' not in ct:
        ct = ct.replace(b"</Types>",
                        b'<Default Extension="jpeg" ContentType="image/jpeg"/></Types>')
    if ct:
        payload["[Content_Types].xml"] = ct

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
        for name, data in payload.items():
            zout.writestr(name, data)


def shrink_image(data: bytes, suffix: str, max_dim: int = 1600, quality: int = 70) -> bytes | None:
    """Re-encode an image in its ORIGINAL format, for use inside a .docx.

    The part name's extension drives the package content type, so switching
    PNG->JPEG here would produce a file Word rejects.
    """
    from PIL import Image

    fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}.get(suffix.lower())
    if not fmt:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt == "JPEG":
            img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        else:
            if img.mode in ("RGBA", "LA", "P"):
                img.save(buf, "PNG", optimize=True)
            else:
                img.convert("P", palette=Image.ADAPTIVE, colors=256).save(buf, "PNG", optimize=True)
    except Exception:
        return None
    out = buf.getvalue()
    return out if len(out) < len(data) else None


# Progressive image budgets for .docx, gentlest first. Each rung re-runs from
# the ORIGINAL file so artefacts never compound.
DOCX_LADDER = [(40_000, 1600, 75), (20_000, 1200, 65),
               (10_000, 1000, 55), (5_000, 800, 45),
               (3_000, 650, 35)]


def prep_docx(src: Path, dst: Path, limit: int) -> list[str]:
    notes: list[str] = []
    before = docx_text(src)

    shutil.copyfile(src, dst)
    if dst.stat().st_size > limit:
        rewrite_docx(src, dst, strip_fonts=True, image_budget=None)
        notes.append("stripped embedded fonts")
    for budget, max_dim, quality in DOCX_LADDER:
        if dst.stat().st_size <= limit:
            break
        rewrite_docx(src, dst, strip_fonts=True, image_budget=budget,
                     max_dim=max_dim, quality=quality)
        notes = [n for n in notes if not n.startswith("recompressed")]
        notes.append(f"recompressed images to {max_dim}px q{quality}")

    if docx_text(dst) != before:
        raise RuntimeError("text changed during rewrite")
    return notes


# --- .pdf ------------------------------------------------------------------
# Quality ladder, gentlest first. Each rung is applied to a FRESH copy of the
# original so artifacts never compound across attempts.
PDF_LADDER = [
    (2000, "PNG", 0),
    (1600, "JPEG", 80),
    (1200, "JPEG", 70),
    (1000, "JPEG", 60),
    (800, "JPEG", 50),
    (600, "JPEG", 40),
    (500, "JPEG", 35),
]
# Mean per-channel difference (0-255) between rendered original and rendered
# output. Honest recompression of these documents lands well under 1; anything
# above this has damaged something visible, so the rewrite is rejected.
RENDER_TOLERANCE = 3.0


def recode_for_pdf(data: bytes, max_dim: int, fmt: str, quality: int) -> bytes | None:
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        # Never flatten an image that carries its own alpha: JPEG has no alpha
        # channel and Pillow renders the transparent areas black.
        if fmt == "JPEG" and img.mode not in ("RGBA", "LA", "P"):
            img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
        elif img.mode in ("RGBA", "LA"):
            img.save(buf, "PNG", optimize=True)
        else:
            img.convert("P", palette=Image.ADAPTIVE, colors=256).save(buf, "PNG", optimize=True)
    except Exception:
        return None
    out = buf.getvalue()
    return out if len(out) < len(data) else None


def render_diff(a: Path, b: Path, dpi: int = 50) -> float:
    """Max over pages of the mean absolute pixel difference between two PDFs."""
    import numpy as np
    import pymupdf
    from PIL import Image

    da, db = pymupdf.open(a), pymupdf.open(b)
    worst = 0.0
    for i in range(min(da.page_count, db.page_count)):
        ia = Image.open(io.BytesIO(da[i].get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB")
        ib = Image.open(io.BytesIO(db[i].get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB")
        if ia.size != ib.size:
            ib = ib.resize(ia.size)
        worst = max(worst, float(np.abs(np.asarray(ia, float) - np.asarray(ib, float)).mean()))
    da.close()
    db.close()
    return worst


def pdf_text(doc) -> str:
    return "\n".join(doc[i].get_text() for i in range(doc.page_count))


# Last resort for PDFs whose bulk is embedded font data (PowerPoint exports).
# Each page becomes a JPEG, and the text is re-inserted as an INVISIBLE layer
# in a base-14 font that needs no embedding -- so the page looks the same and
# the text is still extractable, which is what the grader actually reads.
FLATTEN_LADDER = [(150, 70), (120, 60), (100, 55), (90, 50), (72, 45)]


def alnum(text: str) -> str:
    """Letters and digits only -- the content that must survive flattening."""
    return re.sub(r"[^0-9A-Za-z]", "", text)


def flatten_pdf(src: Path, dst: Path, dpi: int, quality: int) -> None:
    import pymupdf
    from PIL import Image

    old = pymupdf.open(src)
    new = pymupdf.open()
    try:
        for pno in range(old.page_count):
            page = old[pno]
            pix = page.get_pixmap(dpi=dpi)
            im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
            out_page = new.new_page(width=page.rect.width, height=page.rect.height)
            out_page.insert_image(out_page.rect, stream=buf.getvalue())
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not span["text"].strip():
                            continue
                        x0, y0, x1, y1 = span["bbox"]
                        try:
                            out_page.insert_text(
                                (x0, y1 - (y1 - y0) * 0.2), span["text"],
                                fontsize=max(1.0, span["size"]),
                                fontname="helv", render_mode=3)
                        except Exception:
                            pass
        new.save(dst, garbage=4, deflate=True)
    finally:
        new.close()
        old.close()


def prep_pdf(src: Path, dst: Path, limit: int) -> list[str]:
    import pymupdf

    notes: list[str] = []
    shutil.copyfile(src, dst)
    if dst.stat().st_size <= limit:
        return notes

    with pymupdf.open(src) as ref:
        pages, before_text = ref.page_count, pdf_text(ref)

    def finish(doc) -> None:
        """Save, then prove the result is the same document."""
        doc.save(dst, garbage=4, deflate=True, clean=True)
        doc.close()
        with pymupdf.open(dst) as out:
            if out.page_count != pages:
                raise RuntimeError("page count changed during rewrite")
            if pdf_text(out) != before_text:
                raise RuntimeError("text changed during rewrite")

    finish(pymupdf.open(src))
    notes.append("re-saved losslessly")
    if dst.stat().st_size <= limit:
        return notes

    for max_dim, fmt, quality in PDF_LADDER:
        doc = pymupdf.open(src)
        replaced = 0
        for pno in range(doc.page_count):
            page = doc[pno]
            for xref in {im[0] for im in page.get_images()}:
                try:
                    raw = doc.extract_image(xref)
                except Exception:
                    continue
                # A soft mask lives in its own xref. extract_image hands back
                # only the base image, so replacing it would strip the
                # transparency -- logos turn into solid black boxes. These are
                # small anyway; leave them alone.
                if raw.get("smask"):
                    continue
                smaller = recode_for_pdf(raw["image"], max_dim, fmt, quality)
                if not smaller:
                    continue
                # replace_image rebuilds the XObject dictionary (filter, colour
                # space, dimensions). Writing the stream directly would leave
                # those stale and render as garbage.
                try:
                    page.replace_image(xref, stream=smaller)
                    replaced += 1
                except Exception:
                    continue
        if not replaced:
            doc.close()
            continue
        finish(doc)
        drift = render_diff(src, dst)
        if drift > RENDER_TOLERANCE:
            # This rung damaged the page. Never ship it -- restore the original
            # and stop rewriting images; flattening below is the safe fallback.
            shutil.copyfile(src, dst)
            notes.append(f"image rewrite rejected (render diff {drift:.1f})")
            break
        if dst.stat().st_size <= limit:
            notes.append(f"downsampled images to {max_dim}px {fmt}"
                         f"{'' if fmt == 'PNG' else f' q{quality}'} (render diff {drift:.1f})")
            return notes

    # Still over: the remaining bulk is font data, which cannot be compressed.
    # Flatten to page images, keeping an invisible, extractable text layer.
    import pymupdf
    with pymupdf.open(src) as ref:
        want = alnum(pdf_text(ref))
    for dpi, quality in FLATTEN_LADDER:
        flatten_pdf(src, dst, dpi, quality)
        with pymupdf.open(dst) as out:
            if out.page_count != pages:
                raise RuntimeError("page count changed during flatten")
            if alnum(pdf_text(out)) != want:
                continue
        if dst.stat().st_size <= limit:
            notes.append(f"flattened to {dpi}dpi images, text layer preserved")
            return notes
    notes.append("flattened as far as quality allows")
    return notes


# --- .html / .txt ----------------------------------------------------------
class _Text(HTMLParser):
    """Minimal HTML -> (style, text) blocks; fallback when pandoc is absent."""

    SKIP = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[tuple[str, str]] = []
        self._buf: list[str] = []
        self._style = "Normal"
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._depth += 1
        elif tag in ("p", "li", "div", "br") or re.fullmatch(r"h[1-6]", tag):
            self._flush()
            if re.fullmatch(r"h[1-6]", tag):
                self._style = f"Heading {tag[1]}"
            elif tag == "li":
                self._style = "List Bullet"

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._depth = max(0, self._depth - 1)
        elif tag in ("p", "li", "div") or re.fullmatch(r"h[1-6]", tag):
            self._flush()

    def handle_data(self, data):
        if not self._depth:
            self._buf.append(data)

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if text:
            self.blocks.append((self._style, text))
        self._buf.clear()
        self._style = "Normal"

    def close(self):
        super().close()
        self._flush()


def convert_to_docx(src: Path, dst: Path) -> list[str]:
    if src.suffix.lower() != ".txt" and shutil.which("pandoc"):
        subprocess.run(
            ["pandoc", str(src), "-f", "html", "-t", "docx", "-o", str(dst)],
            check=True, capture_output=True,
        )
        return [f"converted {src.suffix} -> .docx (pandoc)"]

    import docx

    raw = src.read_text(encoding="utf-8", errors="replace")
    if src.suffix.lower() == ".txt":
        blocks = [("Normal", line.strip()) for line in raw.splitlines() if line.strip()]
    else:
        parser = _Text()
        parser.feed(raw)
        parser.close()
        blocks = parser.blocks
    out = docx.Document()
    for style, text in blocks:
        try:
            out.add_paragraph(text, style=style)
        except KeyError:
            out.add_paragraph(text)
    out.save(str(dst))
    return [f"converted {src.suffix} -> .docx (built-in)"]


# --- .pptx --------------------------------------------------------------
def convert_slides_to_pdf(src: Path, dst: Path) -> None:
    """Export a deck to PDF using Microsoft PowerPoint's own renderer.

    Decks are graded partly on visual communication, so reconstructing slides
    from extracted text would misrepresent the work. PowerPoint's native export
    preserves layout, type and colour exactly. Requires macOS + PowerPoint.
    """
    if not Path("/Applications/Microsoft PowerPoint.app").exists():
        raise RuntimeError("Microsoft PowerPoint is not installed; cannot convert slides")

    def esc(p: Path) -> str:
        return str(p.resolve()).replace("\\", "\\\\").replace('"', '\\"')

    script = (
        'tell application "Microsoft PowerPoint"\n'
        f'  open POSIX file "{esc(src)}"\n'
        '  delay 1\n'
        '  set thePres to active presentation\n'
        f'  save thePres in POSIX file "{esc(dst)}" as save as PDF\n'
        '  close thePres saving no\n'
        'end tell'
    )
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError(f"PowerPoint export failed: {r.stderr.strip()[:200]}")

    # Slide count must survive the export.
    import pymupdf
    from pptx import Presentation

    deck = Presentation(str(src))
    slides = len(deck.slides)
    hidden = sum(1 for sl in deck.slides if sl.element.get("show") == "0")
    pages = pymupdf.open(dst).page_count
    # Hidden slides are deliberately excluded from a PDF export.
    if pages != slides - hidden:
        raise RuntimeError(f"exported {pages} pages from {slides} slides ({hidden} hidden)")


# --- validation & driver ---------------------------------------------------
def validate(path: Path, limit: int) -> str:
    """Re-open the finished file the way a consumer would. Returns '' if OK."""
    size = path.stat().st_size
    ext = path.suffix.lower()
    if ext not in DOC_EXTS:
        return f"unsupported extension {ext}"
    if size > limit:
        return f"still {size:,} B, over the {limit:,} B cap"
    try:
        if ext == ".docx":
            import docx

            docx.Document(str(path))
        else:
            import pymupdf

            if pymupdf.open(str(path)).page_count < 1:
                return "PDF has no pages"
    except Exception as exc:
        return f"unreadable: {exc}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path, help="folder of downloaded Canvas submissions")
    ap.add_argument("-o", "--out", type=Path, help="output folder (default: <src>/upload-ready)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"max bytes per file (default {DEFAULT_LIMIT:,})")
    args = ap.parse_args()

    src_dir: Path = args.src.expanduser().resolve()
    out_dir: Path = (args.out or src_dir / "upload-ready").expanduser().resolve()
    if not src_dir.is_dir():
        print(f"error: {src_dir} is not a folder", file=sys.stderr)
        return 2

    files = sorted(
        p for p in src_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.resolve().parent != out_dir
    )
    if not files:
        print(f"error: no files in {src_dir}", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    rows, failures, skipped = [], [], []

    for src in files:
        ext = src.suffix.lower()
        dst = out_dir / (src.name if ext in DOC_EXTS
                         else src.stem + (".pdf" if ext in SLIDES else ".docx"))
        try:
            if ext == ".docx":
                notes = prep_docx(src, dst, args.limit)
            elif ext == ".pdf":
                notes = prep_pdf(src, dst, args.limit)
            elif ext in SLIDES:
                staged = out_dir / f".{src.stem}.staged.pdf"
                convert_slides_to_pdf(src, staged)
                notes = [f"exported {ext} -> .pdf (PowerPoint)"]
                notes += prep_pdf(staged, dst, args.limit)
                staged.unlink(missing_ok=True)
            elif ext in CONVERTIBLE:
                notes = convert_to_docx(src, dst)
            else:
                skipped.append((src.name, f"unsupported source type {ext}"))
                continue
            problem = validate(dst, args.limit)
            if problem:
                failures.append((dst.name, problem))
            rows.append((src.stat().st_size, dst.stat().st_size, dst.name, notes))
        except Exception as exc:
            failures.append((src.name, f"{type(exc).__name__}: {exc}"))

    rows.sort(key=lambda r: -r[1])
    print(f"\n  {'before':>10}  {'after':>10}  file / action")
    print("  " + "-" * 74)
    for before, after, name, notes in rows:
        flag = "  " if before == after else "->"
        print(f"  {before:>10,}  {after:>10,} {flag} {name[:58]}")
        for n in notes:
            print(f"  {'':>10}  {'':>10}     {n}")

    print(f"\n  {len(rows)} file(s) ready in {out_dir}")
    if rows:
        print(f"  largest {max(r[1] for r in rows):,} B / cap {args.limit:,} B"
              f"   total {sum(r[1] for r in rows):,} B")
    for name, why in skipped:
        print(f"  SKIPPED  {name}: {why}")
    for name, why in failures:
        print(f"  FAILED   {name}: {why}")
    if not failures and not skipped:
        print("  all files validated: .docx/.pdf only, every file under the cap, all readable")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
