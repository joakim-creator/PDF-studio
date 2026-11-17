# GDPR — personuppgifter i PDF-studio

Förteckning över vilka personuppgifter appen sparar, varför, var de finns och hur länge de sparas (F0-16).
**Uppdateras när en ny uppgift om personer tillkommer** — en ny tabell, ett nytt fält eller en ny extern tjänst.
Vaktprovet `tests/test_vakt.py` faller om en tabell i bolagsdatabasen saknas här eller om en gallringstid inte
är satt.

- **Personuppgiftsansvarig:** varje bolag för sina egna dokument och användare (först Pure Energy AB).
- **Systemägare:** Joakim Hansson.
- **GDPR-ansvarig:** den som har tillägget `gdpr.besluta` i bolaget. Det delas ut uttryckligen; administratör får
  det inte automatiskt.

Tiderna nedan är systemägarens förslag 2026-11-16. De beslutas av GDPR-ansvarig senast i produktionsgranskningen
(F4-03), och ändras då både här och i `core/retention.py`.

---

## Principer

- **Bara det som behövs.** Ett fält om en person läggs till först när ett arbetsmoment behöver det.
- **Data i EU.** Azure, Sweden Central (B-002). Varje bolag har en egen databas (B-004).
- **Dokumentens innehåll** kan handla om andra än användarna (fakturor, avtal). Det ägs av bolaget som laddade upp
  dem och gallras med dokumentet.
- **AI:** dokument skickas till Anthropic för tolkning (B-005) enligt personuppgiftsbiträdesavtal; de används inte
  för att träna modeller. Frågornas text sparas inte i appen, bara kostnaden.

## Register per tabell

| Tabell | Vem | Uppgifter | Varför (ändamål · grund) | Gallring |
|---|---|---|---|---|
| `users` | Användare (anställda, konsulter) | Användarnamn, namn, e-post, Microsoft-id, lösenordshash och engångskod för reservkonton, inloggningsförsök | Inloggning och behörighet · avtal (anställning, uppdrag) | Inaktiveras när personen slutar; raden finns kvar för spårbarheten (vem gjorde vad). E-post och Microsoft-id töms 24 månader efter inaktivering (byggs med inloggningen, F0-13) |
| `login_events` | Användare och de som försöker logga in | Användarnamn (även okända), metod, utfall, klientens IP-adress, tid | Säkerhet: upptäcka och stoppa försök att gissa lösenord · berättigat intresse | 12 månader |
| `user_permissions` | Användare | Vilka tillägg personen har och vem som gav dem | Behörighet · avtal | Tas bort när tillägget dras in; ändringen står i händelseloggen |
| `documents` | Användare (ägare) och personer i dokumenten | Titel, ägare, tider | Själva tjänsten · avtal/berättigat intresse | Papperskorgen töms efter 7 dagar. Dokument utan aktivitet i 24 månader prövas av GDPR-ansvarig: gallra, eller behåll med angiven anledning och ny prövning efter 24 månader |
| `document_versions` | Personer i dokumenten | Filerna (PDF) med allt innehåll, vem som skapade versionen | Själva tjänsten, originalet rörs aldrig · avtal | Med dokumentet |
| `document_shares` | Användare | Vem ett dokument delats med, av vem | Samarbete · avtal | Med dokumentet |
| `annotations` | Användare och personer som nämns | Kommentarer och markeringar med författare | Granskning av dokument · avtal | Med dokumentet |
| `jobs` | Användare | Vem som beställde OCR, Word, podcast med mera, kostnad, felmeddelande | Köa långa uppgifter, kostnadsuppföljning · berättigat intresse | Med dokumentet |
| `ai_usage` | Användare | Vem, när, modell, antal tokens, kostnad (inte frågans text) | Utgiftstaket och kostnadsuppföljning · berättigat intresse | 24 månader |
| `audit_events` | Användare och de som nämns i en händelse | Vem gjorde vad och när | Spårbarhet och säkerhet · berättigat intresse | 36 månader |

Masterdatabasen (`tenants`) innehåller bolag, inga personer.

## Gallring och beslut

Regeln finns som kod i `core/retention.py` och ändrar ingenting av sig själv.

```bash
flask --app app gdpr-kandidater --tenant <slug>
```

visar vad som står på tur (torrkörning). GDPR-ansvarig beslutar per dokument med `core.retention.decide`:
*gallra* (dokumentet flyttas till papperskorgen och töms efter 7 dagar) eller *behåll* (kräver en anledning, ny
prövning efter 24 månader). Varje beslut står i händelseloggen. Själva tömningen av filer byggs när lagringen finns
(F1-01).

## Registerutdrag (artikel 15)

```bash
flask --app app gdpr-utdrag <användarnamn> --tenant <slug>
```

ger allt appen har om en användare som JSON: kontot, tilläggen, dokumenten personen äger eller fått delade,
kommentarerna, jobben, AI-kostnaderna och händelserna. Lösenordshash och engångskod lämnas inte ut, bara att de
finns.

**Begränsning:** en person som bara förekommer *i* ett dokument (till exempel på en faktura) hittas inte av
utdraget. Ett sådant utdrag görs genom sökning i dokumentens text, som finns när OCR-lagret är byggt (F3-05).
