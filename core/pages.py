"""
Sidorna efter inloggning (F1-03, F1-04 och gränssnittet för F1-05–F1-08), enligt prototypen
(https://claude.ai/artifact/QWRAF2pJZjAypPx8vT44u1).

Varje sida hämtar dokument via core.documents, som kontrollerar åtkomsten. Ett dokument användaren inte får se ger
404, samma som ett som inte finns.
"""

import re
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from core import documents, pdfops
from core.access import AccessDenied, get_document, visible_documents
from extensions import db
from models import Document

pages_bp = Blueprint('pages', __name__)

RECENT = 10
THUMB_DPI = 40
VIEW_DPI = (72, 110, 150)
SAFE_NAME = re.compile(r'[^\w .,()-]+', re.UNICODE)


def _user() -> Any:
    return current_user._get_current_object()  # type: ignore[attr-defined]


def handles_errors(view: Callable[..., ResponseReturnValue]) -> Callable[..., ResponseReturnValue]:
    """Åtkomstfel blir 404; användarfel blir ett meddelande och en ny visning av sidan man kom från."""
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> ResponseReturnValue:
        try:
            return view(*args, **kwargs)
        except AccessDenied:
            db.session.rollback()
            abort(404)
        except documents.DocumentError as error:
            db.session.rollback()
            flash(str(error), 'error')
            return redirect(request.referrer or url_for('pages.home'))
    return wrapper


def _pages(field: str = 'pages') -> list[int]:
    return [int(p) for p in request.form.getlist(field) if p.isdigit()]


@pages_bp.get('/')
@login_required
def home() -> ResponseReturnValue:
    query = request.args.get('q', '').strip()
    stmt = visible_documents(_user()).order_by(Document.created_at.desc())
    if query:
        stmt = stmt.where(Document.title.ilike(f'%{query}%'))
    recent = db.session.scalars(stmt.limit(RECENT)).all()
    rows = [(doc, documents.latest(doc)) for doc in recent]
    return render_template('home.html', rows=rows, query=query)


@pages_bp.post('/ladda-upp')
@login_required
@handles_errors
def upload() -> ResponseReturnValue:
    files = [f for f in request.files.getlist('files') if f and f.filename]
    if not files:
        raise documents.DocumentError('Välj minst en PDF att ladda upp.')
    created = [documents.upload(_user(), f.filename or '', f.read()) for f in files]
    db.session.commit()
    flash(f'{len(created)} {"fil uppladdad" if len(created) == 1 else "filer uppladdade"}. '
          'Originalet ändras aldrig.', 'success')
    if len(created) == 1:
        return redirect(url_for('pages.document', document_id=created[0].id))
    return redirect(url_for('pages.home'))


@pages_bp.get('/dokument/<int:document_id>')
@login_required
@handles_errors
def document(document_id: int) -> ResponseReturnValue:
    doc = get_document(_user(), document_id)
    history = documents.versions(_user(), document_id)
    shown = request.args.get('v', type=int) or history[-1].version_no
    version = next((v for v in history if v.version_no == shown), None)
    if version is None:
        abort(404)
    others = [d for d in db.session.scalars(visible_documents(_user()).order_by(Document.title)) if d.id != doc.id]
    return render_template('document.html', doc=doc, version=version, history=history, others=others,
                           latest=history[-1], thumb_dpi=THUMB_DPI)


@pages_bp.get('/dokument/<int:document_id>/v<int:version_no>/sida-<int:page>.png')
@login_required
@handles_errors
def page_image(document_id: int, version_no: int, page: int) -> ResponseReturnValue:
    dpi = request.args.get('dpi', type=int) or THUMB_DPI
    if dpi not in (THUMB_DPI, *VIEW_DPI):
        abort(400)
    _, data = documents.read(_user(), document_id, version_no)
    try:
        png = pdfops.render_png(data, page, dpi)
    except pdfops.PdfError:
        abort(404)
    response = Response(png, mimetype='image/png')
    response.headers['Cache-Control'] = 'private, max-age=3600'   # en version ändras aldrig
    return response


@pages_bp.get('/dokument/<int:document_id>/ladda-ner')
@login_required
@handles_errors
def download(document_id: int) -> ResponseReturnValue:
    version, data = documents.read(_user(), document_id, request.args.get('v', type=int))
    title = get_document(_user(), document_id).title
    name = SAFE_NAME.sub('_', title.removesuffix('.pdf')).strip() or 'dokument'
    suffix = '' if version.version_no == 1 else f' (version {version.version_no})'
    response = Response(data, mimetype='application/pdf')
    response.headers['Content-Disposition'] = f'attachment; filename="{name}{suffix}.pdf"'
    return response


@pages_bp.post('/dokument/<int:document_id>/sidor')
@login_required
@handles_errors
def edit_pages(document_id: int) -> ResponseReturnValue:
    action = request.form.get('action', '')
    pages = _pages()
    operation: Callable[[bytes], bytes]
    if action in ('rotera-hoger', 'rotera-vanster'):
        degrees = 90 if action == 'rotera-hoger' else -90
        operation = lambda data: pdfops.rotate(data, pages, degrees)  # noqa: E731
        message = 'Sidorna är roterade.'
    elif action == 'ta-bort':
        operation = lambda data: pdfops.delete_pages(data, pages)  # noqa: E731
        message = 'Sidorna är borttagna.'
    elif action == 'tom-sida':
        after = request.form.get('after', type=int) or 0
        operation = lambda data: pdfops.insert_blank(data, after)  # noqa: E731
        message = 'En tom sida är infogad.'
    elif action == 'infoga':
        source_id = request.form.get('source', type=int) or 0
        after = request.form.get('after', type=int) or 0
        _, source = documents.read(_user(), source_id)
        chosen = pdfops.parse_ranges(request.form.get('source_pages', ''), pdfops.page_count(source)) \
            if request.form.get('source_pages', '').strip() else list(range(1, pdfops.page_count(source) + 1))
        operation = lambda data: pdfops.insert_from(data, source, after, chosen)  # noqa: E731
        message = 'Sidorna är infogade.'
    else:
        abort(400)
    version = documents.change(_user(), document_id, operation)
    db.session.commit()
    flash(f'{message} Sparat som version {version.version_no}; tidigare versioner finns kvar.', 'success')
    return redirect(url_for('pages.document', document_id=document_id))


@pages_bp.post('/dokument/<int:document_id>/aterstall/<int:version_no>')
@login_required
@handles_errors
def restore(document_id: int, version_no: int) -> ResponseReturnValue:
    version = documents.restore(_user(), document_id, version_no)
    db.session.commit()
    flash(f'Version {version_no} är återställd som version {version.version_no}.', 'success')
    return redirect(url_for('pages.document', document_id=document_id))


@pages_bp.route('/sla-ihop', methods=['GET', 'POST'])
@login_required
@handles_errors
def merge() -> ResponseReturnValue:
    if request.method == 'POST':
        chosen = sorted((request.form.get(f'pos-{doc_id}', type=int) or 999, doc_id) for doc_id in _pages('docs'))
        merged = documents.merge(_user(), [doc_id for _, doc_id in chosen],
                                 request.form.get('title', '').strip() or 'Ihopslagen.pdf')
        db.session.commit()
        flash('Filerna är ihopslagna till en ny fil. Originalen är oförändrade.', 'success')
        return redirect(url_for('pages.document', document_id=merged.id))
    docs = db.session.scalars(visible_documents(_user()).order_by(Document.created_at.desc())).all()
    return render_template('merge.html', rows=[(d, documents.latest(d)) for d in docs])


@pages_bp.route('/dela', methods=['GET'])
@login_required
def split_choose() -> ResponseReturnValue:
    docs = db.session.scalars(visible_documents(_user()).order_by(Document.created_at.desc())).all()
    return render_template('split_choose.html', rows=[(d, documents.latest(d)) for d in docs])


@pages_bp.route('/dela/<int:document_id>', methods=['GET', 'POST'])
@login_required
@handles_errors
def split(document_id: int) -> ResponseReturnValue:
    doc = get_document(_user(), document_id)
    version = documents.latest(doc)
    if request.method == 'POST':
        mode = request.form.get('mode', 'selected')
        if mode not in ('selected', 'range', 'each'):
            abort(400)
        created = documents.split(_user(), document_id, mode, request.form.get('ranges', ''), _pages())
        db.session.commit()
        flash(f'{len(created)} {"ny fil" if len(created) == 1 else "nya filer"} skapade. Originalet är oförändrat.',
              'success')
        target = created[0].id if len(created) == 1 else None
        return redirect(url_for('pages.document', document_id=target) if target else url_for('pages.home'))
    return render_template('split.html', doc=doc, version=version, thumb_dpi=THUMB_DPI)


@pages_bp.get('/kommer-snart/<string:feature>')
@login_required
def coming_soon(feature: str) -> ResponseReturnValue:
    names = {'kommentera': ('Kommentera', 'fas 2'), 'exportera': ('Exportera', 'fas 2 och 5'),
             'fraga-ai': ('Fråga AI', 'fas 3')}
    if feature not in names:
        abort(404)
    name, phase = names[feature]
    return render_template('coming_soon.html', name=name, phase=phase)
