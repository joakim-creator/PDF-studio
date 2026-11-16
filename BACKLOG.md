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
| F0-01 | Repo, `.gitignore`, `.env.example` | PÅGÅR | Lokalt repo klart; GitHub-repo saknas |
| F0-02 | Spårbarhetsdokument på plats | KLAR | Specifikation, backlogg fas 0–7, beslut B-001–B-005 |
| F0-03 | Projektuppsättning (ramverk, språk, formatering) | KLAR | Flask-fabrik, ärendenummer, `/health`, ruff och mypy |
| F0-04 | Datamodell: tabeller | TODO | |
| F0-05 | Index och villkor | TODO | |
| F0-06 | Åtkomstkontroll på samtliga tabeller | TODO | |
| F0-07 | `seed.sql` med testdata — **rader i varje delad tabell** | TODO | Utan rader sover åtkomstproven |
| F0-08 | Testuppsättning + vaktprov för schema och åtkomst | TODO | |
| F0-09 | Verify-skript (lint, typkontroll, prov i ett kommando; fäller om databasproven hoppas över) och CI `verify.yml` vid varje push — **och beroendeskanning** (`pip-audit`/`npm audit`) | PÅGÅR | Grön lokalt och sedd falla; CI körs först när GitHub-repot finns. | versionering.md "CI och utläggning" |
| F0-10 | Bakom proxy: lita på exakt en (`X-Forwarded-For`/`-Proto`), ärendenummer `X-Request-ID` från Nginx | TODO | [backend-grund.md](docs/backend-grund.md) 1 |
| F0-11 | Ärendenummer, loggrad per anrop, felsida utan detaljer, `/health`, felrapportering (GlitchTip) med tvätt och timtak | TODO | backend-grund 3 |
| F0-12 | Backupskript (alla databaser + filer → egen hink), kontroll av återställd databas, **återställningsprov med datum** | TODO | backend-grund 4 |
| F0-13 | Inloggning: SSO som huvudväg; lokala konton med lösenord **och** engångskod, 12 tecken, spärr per konto, inloggningslogg | TODO | backend-grund 2, 6 |
| F0-14 | Konton inaktiveras i stället för att raderas; pågående session upphör | TODO | backend-grund 5 |
| F0-15 | Händelselogg (`audit_events`) och tillägg för destruktiva åtgärder; administratör får inga tillägg automatiskt | TODO | backend-grund 7 |
| F0-16 | GDPR: förteckning utan "bestäms senare", gallringsregel som kod med torrkörning, roll som beslutar, registerutdrag | TODO | backend-grund 10 |
| F0-17 | Främmande nycklar på i proven; radlås läser om; säkerhetshuvuden; index på FK-kolumner | TODO | backend-grund 9, 12 |
| F0-18 | Modulgränser som vaktprov (beroendematris); kärnan importerar aldrig en modul | TODO | backend-grund 11 |
| F0-19 | Provfixtur från mallfil: schema + seed byggs en gång per körning, varje prov kopierar filen; mål under 0,2 s per prov och hela verify under 5 min | TODO | backend-grund 13 |
| F0-20 | Grenarna `main`/`dev`, `deploy-dev` vid push till `dev`, deploy-användare låst till `status`/`deploy`, migrationer före koden, hälsokontroll och återgång | TODO | versionering.md, driftsattning.md steg 5 |
| F0-21 | Släpp till produktionen: `release.yml` (bara `main`, `SLAPP`), skydd på `main` (kräver grön verify) | TODO | versionering.md |

## Fas 1 — Visa och sidor (0.1.0)

Mål: flödena Slå ihop och Dela fungerar som i prototypen. Krav K1–K4.

| ID | Uppgift | Status | Anteckning |
|---|---|---|---|
| F1-01 | Uppladdning till Blob Storage, filtyp kontrolleras på innehållet, gräns 32 MB | TODO | backend-grund 12 |
| F1-02 | `documents` och `document_versions`; originalet rörs aldrig | TODO | |
| F1-03 | Startsidan enligt prototypen: uppladdning, fem uppgifter, senaste dokument | TODO | |
| F1-04 | Visning med pdf.js: miniatyrer, zoom, sök | TODO | K1 |
| F1-05 | Slå ihop med pikepdf, ordning, namn på ny fil | TODO | K2 |
| F1-06 | Dela: markerade sidor, en fil per sida, intervall | TODO | K3 |
| F1-07 | Rotera, ta bort och infoga sidor (även tom sida och sidor från annan fil) | TODO | K4 |
| F1-08 | Versionshistorik och återställning av en version | TODO | |

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
