# PDF-studio

Molnapp som ersätter Adobe Acrobat Pro och Foxit för att slå ihop, dela, kommentera och
exportera PDF:er, med AI-tolkning på svenska. Byggd från Projektmallen, med samma arbetssätt
som PE Portal.

- **Vad och varför:** [docs/projektspecifikation.md](docs/projektspecifikation.md)
- **Vad som görs nu:** [BACKLOG.md](BACKLOG.md)
- **Tekniska beslut:** [docs/beslutslogg.md](docs/beslutslogg.md)
- **Prototyp:** https://claude.ai/artifact/QWRAF2pJZjAypPx8vT44u1

## Köra lokalt (Windows)

```powershell
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
venv\Scripts\python -m flask --app app run --debug
```

Appen svarar på http://127.0.0.1:5000/health.

## Verify

Lint, typkontroll och prov i ett kommando:

```powershell
venv\Scripts\python scripts\verify.py
```

Databasproven kräver PostgreSQL (se `scripts/verify.py`). I CI körs de alltid.

## Vad som ligger var

| Fil | Roll |
|---|---|
| `CLAUDE.md` | Regler som laddas automatiskt varje session |
| `BACKLOG.md` | Enda källan till vad som ska göras och vad som är gjort |
| `CHANGELOG.md` | Vad varje släpp innehöll |
| `app.py` | Flask-appen (app factory) |
| `core/` | Det som alla moduler delar: ärendenummer, hälsosida |
| `scripts/verify.py` | Verify-kedjan |
| `.github/workflows/verify.yml` | CI vid varje push |
| `docs/` | Specifikation, beslut, migrationer, drift, versionering, lärdomar, backend-grund |
