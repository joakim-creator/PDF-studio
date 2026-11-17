"""
Proxy och säkerhetshuvuden (F0-10, F0-17; backend-grund 1 och 12). Förlaga: pe-portal/app.py.

- **Exakt en betrodd proxy.** Appen lyssnar bara på localhost bakom Nginx, som sätter `X-Forwarded-For` och
  `X-Forwarded-Proto`. ProxyFix litar på den sista adressen i kedjan och ingen annan — utan det ser varje anrop ut att
  komma från 127.0.0.1, och en spärr per klient räknar hela bolaget som en.
- **Säkerhetshuvuden** på varje svar. CSP står i rapportläge tills sidorna finns; HSTS bara när anropet kom över https.
"""

from flask import Flask, Response, request
from werkzeug.middleware.proxy_fix import ProxyFix

CSP = "default-src 'self'; img-src 'self' data: blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"


def init_app(app: Flask) -> None:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # type: ignore[method-assign]

    @app.after_request
    def _security_headers(response: Response) -> Response:
        headers = response.headers
        headers.setdefault('X-Frame-Options', 'DENY')
        headers.setdefault('X-Content-Type-Options', 'nosniff')
        headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        headers.setdefault('Content-Security-Policy-Report-Only', CSP)
        if request.is_secure:
            headers.setdefault('Strict-Transport-Security', 'max-age=31536000')
        return response
