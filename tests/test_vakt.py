"""
Vaktprov (F0-08): regler som läser schemat och koden och faller vid återfall, så att de inte kan glömmas bort.
"""

import re
from pathlib import Path

from flask import Flask
from sqlalchemy import DateTime, Numeric, Table

from core.migrations import KINDS, discover, file_checksum
from extensions import db
from tests.seed import seed_all

ROOT = Path(__file__).resolve().parent.parent
CHECKSUMS = ROOT / 'migrations' / 'checksums.txt'
AGPL_PACKAGES = ('pymupdf', 'fitz', 'ghostscript', 'pymupdfb', 'pdf2docx')


def _all_tables(app: Flask) -> list[Table]:
    with app.app_context():
        return [*db.metadata.sorted_tables, *db.metadatas['master'].sorted_tables]


def _covered(table: Table, column: str) -> bool:
    """En kolumn är indexerad om något index eller villkor (primärnyckel, unik) börjar med den."""
    if list(table.primary_key.columns)[0].name == column:
        return True
    leading = [list(ix.columns)[0].name for ix in table.indexes]
    leading += [list(c.columns)[0].name for c in table.constraints if hasattr(c, 'columns') and list(c.columns)
                and c.__class__.__name__ == 'UniqueConstraint']
    return column in leading


def test_varje_frammande_nyckel_har_ett_index(app: Flask) -> None:
    missing = [f'{t.name}.{fk.parent.name}' for t in _all_tables(app) for fk in t.foreign_keys
               if not _covered(t, fk.parent.name)]
    assert missing == []


def test_pengar_ar_numeric_och_tid_ar_timestamptz(app: Flask) -> None:
    wrong = []
    for t in _all_tables(app):
        for c in t.columns:
            if c.name.startswith('cost') and not isinstance(c.type, Numeric):
                wrong.append(f'{t.name}.{c.name} är inte numeric')
            if isinstance(c.type, DateTime) and not c.type.timezone:
                wrong.append(f'{t.name}.{c.name} saknar tidszon')
    assert wrong == []


def test_seeden_fyller_varje_tabell() -> None:
    """Åtkomstprov utan rader passerar både "syns" och "syns inte" — varje bolagstabell ska ha seed."""
    source = Path(seed_all.__code__.co_filename).read_text(encoding='utf-8')
    with_seed = set(re.findall(r'\b([A-Z][A-Za-z]+)\(', source))
    import models
    tables = {name for name, obj in vars(models).items()
              if isinstance(obj, type) and getattr(obj, '__tablename__', None)}
    assert tables - with_seed == set()


def test_varje_migration_har_aterstallning_och_ar_last() -> None:
    locked = {}
    for line in CHECKSUMS.read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            name, digest = line.split()
            locked[name] = digest
    files = {}
    for kind in KINDS:
        for m in discover(kind):   # kastar om en återställningsfil saknas
            for path in (m.path, m.down_path):
                files[f'{kind}/{path.name}'] = file_checksum(path)
    assert files == locked, 'En migration har ändrats eller saknas i checksums.txt — en körd migration ändras aldrig'


def test_varje_migration_har_en_dokumenterad_aterstallning() -> None:
    doc = (ROOT / 'docs' / 'databasandringar.md').read_text(encoding='utf-8')
    missing = [f'{kind}/{m.label}' for kind in KINDS for m in discover(kind) if m.label not in doc]
    assert missing == []


def test_inga_agpl_bibliotek() -> None:
    names = []
    for req in ('requirements.txt', 'requirements-dev.txt'):
        for line in (ROOT / req).read_text(encoding='utf-8').splitlines():
            name = re.split(r'[=<>;\s\[]', line.strip(), maxsplit=1)[0].lower()
            if name and not name.startswith('#'):
                names.append(name)
    assert [n for n in names if n in AGPL_PACKAGES] == []


def test_gdpr_forteckningen_tar_upp_varje_tabell_och_ar_beslutad(app: Flask) -> None:
    doc = (ROOT / 'docs' / 'GDPR.md').read_text(encoding='utf-8')
    with app.app_context():
        tables = [t.name for t in db.metadata.sorted_tables]
    assert [t for t in tables if f'`{t}`' not in doc] == []
    assert re.findall(r'bestäms senare|TBD|\?\?\?', doc, re.IGNORECASE) == []


def _app_sources() -> dict[Path, str]:
    return {p: p.read_text(encoding='utf-8') for p in ROOT.rglob('*.py')
            if 'venv' not in p.parts and 'tests' not in p.parts}


def test_karnan_importerar_aldrig_en_modul() -> None:
    """Beroendematrisen (backend-grund 11): core → models, extensions. Moduler (modules/, från fas 1) får importera
    core, aldrig tvärtom och aldrig varandras privata delar."""
    pattern = re.compile(r'^\s*(from|import)\s+modules\b', re.MULTILINE)
    offenders = [str(p.relative_to(ROOT)) for p, src in _app_sources().items()
                 if p.parent.name == 'core' and pattern.search(src)]
    assert offenders == []


def test_radlas_tas_bara_via_lock() -> None:
    """`with_for_update` utan omläsning ger gamla värden (backend-grund 9). Bara core/locking.py får låsa."""
    offenders = [str(p.relative_to(ROOT)) for p, src in _app_sources().items()
                 if 'with_for_update' in src and p != ROOT / 'core' / 'locking.py']
    assert offenders == []


def test_pdfium_anvands_bara_genom_laset() -> None:
    """PDFium är inte trådsäkert; samtidiga renderingar fällde processen (core/pdfops.py, `_pdfium`)."""
    uses = [(str(p.relative_to(ROOT)), src.count('pdfium.PdfDocument(')) for p, src in _app_sources().items()
            if 'pdfium.PdfDocument(' in src]
    assert uses == [(str(Path('core') / 'pdfops.py'), 1)]
    src = (ROOT / 'core' / 'pdfops.py').read_text(encoding='utf-8')
    block = src[src.index('def _pdfium('):src.index('def render_png(')]
    assert block.index('with _PDFIUM_LOCK:') < block.index('pdfium.PdfDocument(')


def test_konton_raderas_aldrig() -> None:
    pattern = re.compile(r'session\.delete\(\s*\w*user\w*\s*\)|delete\(User\)', re.IGNORECASE)
    offenders = [str(p.relative_to(ROOT)) for p, src in _app_sources().items() if pattern.search(src)]
    assert offenders == []


def test_dokument_hamtas_bara_via_atkomstkontrollen() -> None:
    """Alla frågor mot Document går via core.access, så att ingen sida glömmer vem som får se vad."""
    # Gallringen prövar bolagets alla dokument, men lämnar aldrig ut innehållet (core/retention.py).
    allowed = {ROOT / 'core' / 'access.py', ROOT / 'models.py', ROOT / 'core' / 'retention.py'}
    pattern = re.compile(r'select\(Document\b|Document\.query|query\(Document\b')
    offenders = [str(p.relative_to(ROOT)) for p in ROOT.rglob('*.py')
                 if 'venv' not in p.parts and 'tests' not in p.parts and p not in allowed
                 and pattern.search(p.read_text(encoding='utf-8'))]
    assert offenders == []
