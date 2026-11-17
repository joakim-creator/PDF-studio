# Backlogg

Enda källan till vad som ska göras och vad som är gjort. Varje uppgift har ett ID
(`F<fas>-<nr>`) som används i commit-meddelanden, migrationsnamn och i
[CHANGELOG.md](CHANGELOG.md), så att en ändring alltid går att spåra tillbaka till
varför den gjordes.

**Status:** `TODO` · `PÅGÅR` · `KLAR` · `BLOCKERAD` · `STRUKEN`

Faserna följer avsnittet om leveransordning i
[projektspecifikationen](docs/projektspecifikation.md). En fas är klar först när alla
dess uppgifter är `KLAR` och versionen taggats enligt
[versionering.md](docs/versionering.md).

---

## Fas 0 — Fundament

Mål: ett körbart projekt med komplett datamodell, åtkomstkontroll och CI. Ingen
affärslogik. Fasen är klar när något går att köra och pröva.

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F0-01 | Repo, `.gitignore`, `.env.example` | KLAR | joakim-creator/PDF-studio (publikt), grenarna `main` och `dev` |
| F0-02 | Spårbarhetsdokument på plats | KLAR | Specifikation, backlogg fas 0–7, beslut B-001–B-008 |
| F0-03 | Projektuppsättning (ramverk, språk, formatering) | KLAR | Flask-fabrik, ärendenummer, `/health`, ruff och mypy |
| F0-04 | Datamodell: tabeller | KLAR | Master: `tenants`. Bolag: 9 tabeller i `models.py`. Migrationer `202611162200_baslinje` med återställning R-001, R-002 |
| F0-05 | Index och villkor | KLAR | Index på varje FK, villkor för versioner, sidor, typer och belopp; vaktprov |
| F0-06 | Åtkomstkontroll på samtliga tabeller | KLAR | `core/access.py`: egna och delade dokument, inaktiverade ser inget, radering kräver tillägg; bolag skiljs av databasen |
| F0-07 | `seed.sql` med testdata — **rader i varje delad tabell** | KLAR | `tests/seed.py` (som i PE Portal), vaktprov att varje tabell har seed |
| F0-08 | Testuppsättning + vaktprov för schema och åtkomst | KLAR | SQLite-mall plus PostgreSQL per prov; 35 prov, varje vakt sedd falla |
| F0-09 | Verify-skript (lint, typkontroll, prov i ett kommando; fäller om databasproven hoppas över) och CI `verify.yml` vid varje push — **och beroendeskanning** (`pip-audit`/`npm audit`) | KLAR | Databasproven körs lokalt mot Docker och krävs i CI (`--require-pg`). versionering.md "CI och utläggning" |
| F0-10 | Bakom proxy: lita på exakt en (`X-Forwarded-For`/`-Proto`), ärendenummer `X-Request-ID` från Nginx | KLAR | `core/security.py`, ProxyFix med en betrodd proxy. Nginx-raderna kommer med servern i F0-20. [backend-grund.md](docs/backend-grund.md) 1 |
| F0-11 | Ärendenummer, loggrad per anrop, felsida utan detaljer, `/health`, felrapportering (GlitchTip) med tvätt och timtak | PÅGÅR | Koden klar: felsida, `/health` mot master och alla bolag med migrationsstatus, tvättad rapport, tak 50/timme. Kvar: GlitchTip-konto och larm (driftsattning.md steg 2). backend-grund 3 |
| F0-12 | Backupskript (alla databaser + filer → egen hink), kontroll av återställd databas, **återställningsprov med datum** | TODO | backend-grund 4 |
| F0-13 | Inloggning: SSO som huvudväg; lokala konton med lösenord **och** engångskod, 12 tecken, spärr per konto, inloggningslogg | PÅGÅR | Koden klar och provad: `core/auth.py`, `core/session.py`, `core/totp.py`, migration `202611170200_inloggning`, Microsoft mot låtsasklient. Kvar: appregistrering i Entra och ett skarpt prov (driftsattning.md steg 1). backend-grund 2, 6 |
| F0-14 | Konton inaktiveras i stället för att raderas; pågående session upphör | KLAR | `core/accounts.py` och `core/session.py`: ett inaktiverat konto tappar sin session vid nästa anrop. backend-grund 5 |
| F0-15 | Händelselogg (`audit_events`) och tillägg för destruktiva åtgärder; administratör får inga tillägg automatiskt | KLAR | `core/audit.py`, `core/accounts.py`: tillägg delas ut uttryckligen, ingen ger sig själv något, allt loggas. backend-grund 7 |
| F0-16 | GDPR: förteckning utan "bestäms senare", gallringsregel som kod med torrkörning, roll som beslutar, registerutdrag | KLAR | `docs/GDPR.md` (tiderna är systemägarens förslag, beslutas i F4-03), `core/retention.py`, `flask gdpr-kandidater`, `flask gdpr-utdrag`, tillägget `gdpr.besluta`. Tömning av filer byggs med lagringen (F1-01). backend-grund 10 |
| F0-17 | Främmande nycklar på i proven; radlås läser om; säkerhetshuvuden; index på FK-kolumner | KLAR | FK och index (F0-04); `core/locking.py` låser och läser om, provat med två sessioner i PostgreSQL; säkerhetshuvuden med CSP i rapportläge. backend-grund 9, 12 |
| F0-18 | Modulgränser som vaktprov (beroendematris); kärnan importerar aldrig en modul | KLAR | Vaktprov i `tests/test_vakt.py`; matrisen står i provets beskrivning. backend-grund 11 |
| F0-19 | Provfixtur från mallfil: schema + seed byggs en gång per körning, varje prov kopierar filen; mål under 0,2 s per prov och hela verify under 5 min | KLAR | 35 prov på 1,4 s (2026-11-16) | backend-grund 13 |
| F0-20 | Grenarna `main`/`dev`, `deploy-dev` vid push till `dev`, deploy-användare låst till `status`/`deploy`, migrationer före koden, hälsokontroll och återgång | PÅGÅR | Filerna klara och provade: `deploy/`, jobbet `deploy-dev`, `wsgi.py`, `db-status`, `db-migrate`, `backup-dump`; servern lägger bara ut den provade commiten. Kvar: servern i Azure och ett skarpt prov (driftsattning.md steg 5–6). versionering.md |
| F0-21 | Släpp till produktionen: `release.yml` (bara `main`, `SLAPP`), skydd på `main` (kräver grön verify) | PÅGÅR | `release.yml` klar och provad (bara `main`, `SLAPP`, prov först, provad commit). Kvar: produktionsservern och skydd på `main` i GitHub (steg 6). versionering.md |

## Fas 1 — Visa och sidor (0.1.0)

Mål: flödena Slå ihop och Dela fungerar som i prototypen. Krav K1–K4.

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F1-01 | Uppladdning till Blob Storage, filtyp kontrolleras på innehållet, gräns 32 MB | KLAR | `core/storage.py` (lokalt och Azure Blob, provat mot Azurite i CI), `core/documents.py`: filtyp på innehållet, 32 MB. Formuläret kommer med F1-03 |
| F1-02 | `documents` och `document_versions`; originalet rörs aldrig | KLAR | Originalet rörs aldrig: varje ändring är en ny version med förälder, under radlås |
| F1-03 | Startsidan enligt prototypen: uppladdning, fem uppgifter, senaste dokument | TODO | |
| F1-04 | Visning med pdf.js: miniatyrer, zoom, sök | TODO | K1 |
| F1-05 | Slå ihop med pikepdf, ordning, namn på ny fil | PÅGÅR | Logiken klar och provad (`core/pdfops.py`, `documents.merge`). Kvar: sidan |
| F1-06 | Dela: markerade sidor, en fil per sida, intervall | PÅGÅR | Logiken klar och provad (markerade, intervall, en per sida). Kvar: sidan |
| F1-07 | Rotera, ta bort och infoga sidor (även tom sida och sidor från annan fil) | PÅGÅR | Logiken klar och provad (rotera, ta bort, tom sida, sidor ur annan fil). Kvar: sidan |
| F1-08 | Versionshistorik och återställning av en version | PÅGÅR | Logiken klar och provad; återställning blir en ny version (migration `202611170400_aterstall_version`). Kvar: sidan |

## Fas 2 — Kommentarer och bild (0.2.0)

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F2-01 | `annotations`: markera, stryk under, fritext, kommentar, frihand, stämpel | TODO | K5 |
| F2-02 | Annoteringar skrivs som PDF-annoteringar (pdf-lib eller pikepdf) | TODO | Prov: öppnas i Adobe och Foxit |
| F2-03 | Export av sidor till PNG och JPG, 150/300 dpi (pypdfium2) | TODO | K6 |

## Fas 3 — AI och OCR (0.3.0)

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F3-01 | Jobbkö för långa uppgifter (`jobs`) | TODO | |
| F3-02 | Claude-klient: dokumentblock, citat, promptcache, kostnad per anrop i `ai_usage` | TODO | B-005 |
| F3-03 | Utgiftstak 450 kr i koden och 500 kr på kontot | TODO | driftsattning.md, Utgiftstak |
| F3-04 | Frågor och sammanfattning med sidhänvisning | TODO | K8 |
| F3-05 | Text i bild till osynligt textlager utan AGPL-bibliotek | TODO | K9, B-003 |
| F3-06 | Prov mot 20 riktiga dokument | TODO | |

## Fas 4 — Mobil och skarp start (1.0.0)

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F4-01 | Mobilvy och kameraskanner (foto till sökbar PDF) | TODO | |
| F4-02 | Användartest: fem nyckelflöden med fem användare | TODO | Grind 1 |
| F4-03 | Produktionsgranskning enligt `docs/produktionsgranskning.md` | TODO | |
| F4-04 | Produktion i Azure, återställningsprov med datum | TODO | |

## Fas 5 — Word, Excel och API (1.1.0)

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F5-01 | Export till Word: Claude tolkar strukturen, python-docx skriver | TODO | K7, Grind 2: 20 dokument |
| F5-02 | Utdrag till Excel med strukturerad utdata | TODO | K11 |
| F5-03 | Komprimering | TODO | K12 |
| F5-04 | Öppet API med OpenAPI-beskrivning och API-nycklar | TODO | |
| F5-05 | Skicka PDF till Bella för signering | TODO | |

## Fas 6 — Svensk podcast (1.2.0)

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F6-01 | Lyssningstest: Azure AI Speech, ElevenLabs, Google | TODO | |
| F6-02 | Manus för två värdar som strukturerad utdata, redigerbart | TODO | K10 |
| F6-03 | Inläsning och MP3 med kapitel (ffmpeg), gräns per månad | TODO | |

## Fas 7 — Samarbete och säkerhet (1.3.0)

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F7-01 | Dela med länk, utgångsdatum, kommentarer från kollegor | TODO | K13 |
| F7-02 | Maskering som tar bort texten på riktigt | TODO | K14 |
| F7-03 | Kommandofält (Ctrl+K) med bekräftelse före åtgärd | TODO | |
| F7-04 | SharePoint och OneDrive via Microsoft Graph | TODO | |

---

## Upptäckt under arbetet

Sådant som inte fanns i planen. Numreras `U-<nr>` löpande och stängs på samma sätt
som fasuppgifter.

Var noga med att notera **hur** felet upptäcktes. Ett fel som ingen signal fångade
är en lucka i proven, inte bara en bugg.

| ID | Uppgift | Upptäckt | Status |
|---|---|---|---|
| U-001 | | | TODO |
