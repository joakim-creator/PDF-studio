"""Sidorna efter inloggning. Startsidan byggs ut enligt prototypen i F1-03."""

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

pages_bp = Blueprint('pages', __name__)


@pages_bp.get('/')
@login_required
def home() -> ResponseReturnValue:
    return render_template('home.html', user=current_user)
