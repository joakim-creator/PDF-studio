"""Små PDF:er för proven: varje sida har en text ("A1", "A2" …) och en storlek, så att ordningen går att pröva."""

import io

import pikepdf

A4 = (595, 842)
LETTER = (612, 792)


def make(label: str, pages: int = 2, size: tuple[int, int] = A4, password: str | None = None) -> bytes:
    pdf = pikepdf.new()
    font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                BaseFont=pikepdf.Name.Helvetica))
    for n in range(1, pages + 1):
        content = pdf.make_stream(f'BT /F1 24 Tf 72 {size[1] - 100} Td ({label}{n}) Tj ET'.encode())
        page = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, *size], Contents=content,
                                  Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)))
        pdf.pages.append(pikepdf.Page(page))
    out = io.BytesIO()
    if password:
        pdf.save(out, encryption=pikepdf.Encryption(owner=password, user=password))
    else:
        pdf.save(out)
    return out.getvalue()


def texts(data: bytes) -> list[str]:
    """Texten på varje sida, i ordning."""
    from core import pdfops
    return [pdfops.text(data, n).strip() for n in range(1, pdfops.page_count(data) + 1)]


def sizes(data: bytes) -> list[tuple[int, int]]:
    with pikepdf.open(io.BytesIO(data)) as pdf:
        return [(int(p.mediabox[2]), int(p.mediabox[3])) for p in pdf.pages]


def rotations(data: bytes) -> list[int]:
    with pikepdf.open(io.BytesIO(data)) as pdf:
        return [int(p.obj.Rotate) if '/Rotate' in p.obj else 0 for p in pdf.pages]  # type: ignore[arg-type]
