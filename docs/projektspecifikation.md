# Projektspecifikation

> Skrivs först och ändras medvetet. Backloggen bryter ner den här filen; går de isär
> är det specifikationen som gäller tills den ändras.
>
> Den fullständiga specifikationen med motiveringar, arkitekturbild och byggflöde finns i
> Claude-dokumentet *PDF-studio – projektspecifikation*
> (https://claude.ai/artifact/4DNXdeV4gNac2wJCkhh8Ut). Den här filen är sammanfattningen som
> följer koden; ändras något där ska det ändras här också.

## 1. Vad som byggs

En molnapp som ersätter Adobe Acrobat Pro och Foxit för att slå ihop, dela, kommentera och exportera PDF:er, med AI-tolkning och svensk podcast.

## 2. Vem det är för

Internt bruk i Joakims bolag, främst Pure Energy AB. Start med **8 användare och cirka
100 dokument i månaden**. Appen ska kunna säljas till andra bolag, så varje bolag har egna,
åtskilda data och konton från början.

Användarna är vana vid Office men inte vid PDF-verktyg. Det vanligaste ska gå på högst tre klick.

## 3. Vad som uttryckligen inte ingår

- Digital signering, sigill och certifikat i appen. Signering görs i externa system, till exempel
  Bella, via det öppna API:et.
- Att ändra befintlig text direkt i PDF:en (K15). Ersätts av export till Word.
- Tryckförberedande arbete (färgseparation, PDF/X, utfall). Beslut 2026-11-16: vi väntar.
- Skrivbordsprogram för Windows eller macOS.

## 4. Krav som styr tekniken

- **Region:** Azure, Sweden Central. All data i EU.
- **Personuppgifter:** fakturor, avtal och personnummer förekommer. Kryptering vid lagring och
  överföring, gallring, händelselogg, DPA med Anthropic och leverantören av talsyntes.
- **Plattform:** webbapp som fungerar fullt ut på mobil, med kameran som skanner.
- **Originalet rörs aldrig:** varje ändring blir en ny version.
- **Licenser:** inga AGPL-bibliotek, eftersom appen ska kunna säljas (inte PyMuPDF eller Ghostscript).
- **Kostnadstak:** cirka 500 kr i månaden för AI och talsyntes. Tak i koden 450 kr, på kontot 500 kr.
- **Öppet API** (REST, OpenAPI) förbereds från start.

## 5. Datamodell

Masterdatabasen har bara bolagsregistret (`tenants`). Varje bolag har en egen databas med
(B-006; definitionen finns i `models.py`):

| Tabell | Innehåll |
|---|---|
| `users` | Användare: Entra-id, eller lösenord och engångskod för reservkonton; inaktiveras, raderas aldrig |
| `user_permissions` | Uttryckliga tillägg, till exempel `dokument.radera` |
| `documents` | Ett dokument: titel, ägare, papperskorg, gallring |
| `document_versions` | En rad per version, aldrig ändrad: förälder, lagringsnyckel `<bolag>/documents/<uuid>.pdf`, sha256, sidor, storlek, källa |
| `document_shares` | Dokument som delats med en kollega |
| `annotations` | Kommentarer och markeringar per version och sida |
| `jobs` | Långa jobb (OCR, Word, Excel, podcast): status, kostnad, fel |
| `ai_usage` | Kostnad per AI-anrop, underlag för utgiftstaket |
| `audit_events` | Vem som gjorde vad och när |

## 6. Åtkomstregler

- En användare ser bara sitt bolags dokument.
- Inom bolaget ser alla dokument som delats med dem; egna dokument är privata tills de delas.
- Radering kräver tillägget `dokument.radera` och loggas. Administratör får inga tillägg automatiskt.

## 7. Externa beroenden

| Tjänst | Används till | Gräns och kostnad |
|---|---|---|
| Anthropic API, Claude Opus 5.5 (`claude-opus-5-5`) | Tolkning, OCR, frågor, manus | $4/$20 per miljon tokens in/ut; PDF upp till 600 sidor och 32 MB per anrop |
| Svensk talsyntes (väljs i lyssningstest: Azure AI Speech, ElevenLabs eller Google) | Podcast, fas 6 | Pris okänt tills valet är gjort |
| Microsoft Entra ID | Inloggning | Ingår i Microsoft 365 |
| Microsoft Graph | SharePoint och OneDrive, fas 7 | Ingår |
| Azure (App Service eller VM, PostgreSQL, Blob Storage) | Drift | Beräknas i fas 0 |
| GlitchTip (EU) | Felrapportering | Tak per timme i koden och på kontot |

## 8. Vad "klart" betyder

Version `1.0.0` sätts när faserna 0–4 är klara: K1–K6, K8 och K9 fungerar, mobilen med
kameraskanner fungerar, fem testanvändare klarar de fem nyckelflödena, produktionsgranskningen är
gjord, återställningsprovet har en rad, och appen används skarpt på Pure Energy.

## 9. Leveransordning

| Fas | Innehåll | Krav | Version |
|---|---|---|---|
| 0 Fundament | Projektmallens grund, Flask, Azure, CI | F0-01–F0-21 | 0.0.x |
| 1 Visa och sidor | Uppladdning, visning, slå ihop, dela, rotera, versioner | K1–K4 | 0.1.0 |
| 2 Kommentarer och bild | PDF-annoteringar, export till bild | K5–K6 | 0.2.0 |
| 3 AI och OCR | Frågor med sidhänvisning, sökbart textlager, utgiftstak | K8–K9 | 0.3.0 |
| 4 Mobil och skarp start | Kameraskanner, användartest, produktionsgranskning | MVP | 1.0.0 |
| 5 Word, Excel och API | Word-export, Excel-utdrag, komprimering, öppet API, Bella | K7, K11, K12 | 1.1.0 |
| 6 Svensk podcast | Talsyntes, manus för två röster, MP3 | K10 | 1.2.0 |
| 7 Samarbete och säkerhet | Dela med länk, maskering, kommandofält, SharePoint | K13, K14 | 1.3.0 |

## 10. Produktbeslut

| Datum | Beslut |
|---|---|
| 2026-11-16 | Ingen direkt textredigering i PDF; export till Word ersätter den (testet med PDF4QT tömde en faktura). |
| 2026-11-16 | Mobil med kameraskanner ingår i version 1. |
| 2026-11-16 | Tryckförberedande arbete väntar. |
| 2026-11-16 | Signering görs i Bella via API, inte i appen. |
| 2026-11-16 | Internt bruk först, men byggt för att kunna säljas. |
| 2026-11-16 | Grafisk profil: Pure Energy Design System, svart logotyp med orange +. |
