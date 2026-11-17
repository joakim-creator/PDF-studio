"""
Sidoperationer på PDF-filer (F1-05, F1-06, F1-07). Rena funktioner: bytes in, bytes ut — inget i databasen.

pikepdf (qpdf, MPL-2.0) för att slå ihop, dela, rotera, ta bort och infoga; pypdfium2 (PDFium, Apache/BSD) för att
rendera sidor till bild. Inga AGPL-bibliotek (B-003). Sidnummer är 1-baserade, som användaren ser dem.
"""

import io
import re

import pikepdf

PDF_MAGIC = b'%PDF-'
RANGE_RE = re.compile(r'^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$')


class PdfError(ValueError):
    """Filen eller önskemålet går inte att genomföra. Meddelandet visas för användaren."""


def _open(data: bytes) -> pikepdf.Pdf:
    if not data.startswith(PDF_MAGIC):
        raise PdfError('Filen är inte en PDF.')
    try:
        return pikepdf.open(io.BytesIO(data))
    except pikepdf.PasswordError:
        raise PdfError('PDF:en är lösenordsskyddad. Ta bort skyddet och ladda upp den igen.') from None
    except pikepdf.PdfError:
        raise PdfError('PDF:en är skadad och går inte att öppna.') from None


def _save(pdf: pikepdf.Pdf) -> bytes:
    out = io.BytesIO()
    pdf.save(out, deterministic_id=True)
    return out.getvalue()


def page_count(data: bytes) -> int:
    with _open(data) as pdf:
        count = len(pdf.pages)
    if count == 0:
        raise PdfError('PDF:en har inga sidor.')
    return count


def _check_pages(pages: list[int], count: int) -> None:
    if not pages:
        raise PdfError('Välj minst en sida.')
    wrong = [p for p in pages if p < 1 or p > count]
    if wrong:
        raise PdfError(f'Sidan {wrong[0]} finns inte (dokumentet har {count} sidor).')


def parse_ranges(text: str, count: int) -> list[int]:
    """'1-3, 5' → [1, 2, 3, 5]. Ordningen bevaras; dubbletter tas bort."""
    pages: list[int] = []
    for part in [p for p in text.split(',') if p.strip()]:
        match = RANGE_RE.match(part)
        if not match:
            raise PdfError(f'”{part.strip()}” är inte ett sidnummer eller intervall, till exempel 1-3, 5.')
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if last < first:
            raise PdfError(f'Intervallet {first}-{last} går baklänges.')
        pages += [p for p in range(first, last + 1) if p not in pages]
    _check_pages(pages, count)
    return pages


def merge(files: list[bytes]) -> bytes:
    if len(files) < 2:
        raise PdfError('Välj minst två filer att slå ihop.')
    out = pikepdf.new()
    for data in files:
        with _open(data) as pdf:
            out.pages.extend(pdf.pages)
    return _save(out)


def extract(data: bytes, pages: list[int]) -> bytes:
    with _open(data) as pdf:
        _check_pages(pages, len(pdf.pages))
        out = pikepdf.new()
        for number in pages:
            out.pages.append(pdf.pages[number - 1])
        return _save(out)


def split_each(data: bytes) -> list[bytes]:
    return [extract(data, [n]) for n in range(1, page_count(data) + 1)]


def rotate(data: bytes, pages: list[int], degrees: int) -> bytes:
    if degrees % 90:
        raise PdfError('Sidor kan bara roteras i steg om 90 grader.')
    with _open(data) as pdf:
        _check_pages(pages, len(pdf.pages))
        for number in pages:
            pdf.pages[number - 1].rotate(degrees, relative=True)
        return _save(pdf)


def delete_pages(data: bytes, pages: list[int]) -> bytes:
    with _open(data) as pdf:
        _check_pages(pages, len(pdf.pages))
        if len(set(pages)) >= len(pdf.pages):
            raise PdfError('Det går inte att ta bort alla sidor.')
        for number in sorted(set(pages), reverse=True):
            del pdf.pages[number - 1]
        return _save(pdf)


def insert_blank(data: bytes, after: int) -> bytes:
    """En tom sida efter sidan `after` (0 = först), i samma storlek som sidan bredvid."""
    with _open(data) as pdf:
        if after < 0 or after > len(pdf.pages):
            raise PdfError(f'Sidan {after} finns inte (dokumentet har {len(pdf.pages)} sidor).')
        neighbour = pdf.pages[max(after - 1, 0)]
        box = pikepdf.Rectangle(neighbour.mediabox)   # samma storlek som sidan bredvid
        blank = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=box.as_array(), Resources=pikepdf.Dictionary())
        pdf.pages.insert(after, pikepdf.Page(pdf.make_indirect(blank)))
        return _save(pdf)


def insert_from(data: bytes, other: bytes, after: int, pages: list[int]) -> bytes:
    """Sidorna `pages` ur `other`, infogade efter sidan `after` (0 = först)."""
    with _open(data) as pdf, _open(other) as source:
        if after < 0 or after > len(pdf.pages):
            raise PdfError(f'Sidan {after} finns inte (dokumentet har {len(pdf.pages)} sidor).')
        _check_pages(pages, len(source.pages))
        for offset, number in enumerate(pages):
            pdf.pages.insert(after + offset, source.pages[number - 1])
        return _save(pdf)


def render_png(data: bytes, page: int, dpi: int = 72) -> bytes:
    """Sidan som PNG. 72 dpi för miniatyrer, 150 eller 300 för export (F2-03)."""
    import pypdfium2 as pdfium
    if not data.startswith(PDF_MAGIC):
        raise PdfError('Filen är inte en PDF.')
    doc = pdfium.PdfDocument(data)
    try:
        _check_pages([page], len(doc))
        image = doc[page - 1].render(scale=dpi / 72).to_pil()
        out = io.BytesIO()
        image.save(out, format='PNG')
        return out.getvalue()
    finally:
        doc.close()


def search(data: bytes, query: str) -> list[int]:
    """Sidorna (1-baserade) där texten förekommer, utan hänsyn till versaler. Skannade sidor hittas efter OCR (F3-05)."""
    import pypdfium2 as pdfium
    needle = ' '.join(query.split()).casefold()
    if not needle:
        return []
    doc = pdfium.PdfDocument(data)
    try:
        return [n for n in range(1, len(doc) + 1)
                if needle in ' '.join(str(doc[n - 1].get_textpage().get_text_bounded()).split()).casefold()]
    finally:
        doc.close()


def text(data: bytes, page: int) -> str:
    """Sidans text (för prov och sökning). Skannade sidor ger tom text tills OCR finns (F3-05)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(data)
    try:
        return str(doc[page - 1].get_textpage().get_text_bounded())
    finally:
        doc.close()
