# Beslutslogg

Tekniska beslut som fattas under arbetets gång, och **varför** de togs.
Produktbesluten står i [projektspecifikationen](projektspecifikation.md).

Ett beslut ändras inte i efterhand — det ersätts av ett nytt som hänvisar tillbaka.
Då syns det i loggen att något ändrades och varför, i stället för att historien
skrivs om. Ett ersatt beslut som står kvar är inte pinsamt; det är den enda
kvarvarande förklaringen till varför den uppenbara lösningen inte fungerade.

**Status:** `GÄLLER` · `ERSATT AV B-xxx` · `ÅTERTAGET`

---

## B-001 — Flask som ramverk för API:et

**Datum:** 2026-11-16 · **Status:** GÄLLER

FastAPI och Flask var båda möjliga. PE Portal är byggd i Flask, och Projektmallens
referensfiler (proxy, ärendenummer, inloggning med engångskod, händelselogg, backup,
provfixtur) är skrivna för Flask.

**Beslut:** Flask 3 med Flask-SQLAlchemy, samma versioner som PE Portal. Det öppna
API:et beskrivs med OpenAPI via ett Flask-tillägg (APIFlask eller motsvarande, väljs i fas 5).

**Konsekvens:** referensfilerna kan kopieras rakt av, och alla projekt har samma teknik.
Tunga jobb (OCR, Word, podcast) körs i en jobbkö i stället för asynkront i webbprocessen.

## B-002 — Azure, Sweden Central

**Datum:** 2026-11-16 · **Status:** ERSATT AV B-010

Företaget använder redan Microsoft 365 och Entra ID.

**Beslut:** drift i Azure, region Sweden Central. Vilka Azure-tjänster (App Service eller VM,
Azure Database for PostgreSQL, Blob Storage) som används bestäms i F0-20 när kostnaden är räknad.

**Konsekvens:** inloggning och Microsoft Graph fungerar med samma konton. PE Portal kör inte i
Azure, så utläggningsskripten därifrån måste anpassas.

## B-003 — Inga AGPL-bibliotek

**Datum:** 2026-11-16 · **Status:** GÄLLER

Appen ska kunna säljas till andra bolag. AGPL kräver att koden blir öppen eller att en licens köps.

**Beslut:** pikepdf (qpdf) för sidhantering, pypdfium2 (PDFium) för rendering till bild,
pdf.js och pdf-lib i webbläsaren, python-docx för Word. Inte PyMuPDF eller Ghostscript.

**Konsekvens:** PyMuPDFs bekväma API för textlager måste ersättas, till exempel med pikepdf
och en egen textlagerskrivare i fas 3. Varje nytt beroende licenskontrolleras innan det läggs till.

## B-004 — En databas per bolag

**Datum:** 2026-11-16 · **Status:** GÄLLER

Appen ska kunna säljas, och bolagens dokument får aldrig blandas.

**Beslut:** masterdatabas för bolag, användare och roller, och en PostgreSQL-databas per bolag,
som i PE Portal. Lagringsnycklar `<bolag>/<område>/<uuid>.<ändelse>`.

**Konsekvens:** migrationer körs mot varje bolagsdatabas, och proven måste visa att ett bolag
inte ser ett annat bolags data.

## B-006 — Användarna ligger i bolagens databaser

**Datum:** 2026-11-16 · **Status:** GÄLLER

Specifikationen sade först att masterdatabasen skulle ha bolag, användare och roller.
PE Portal har användarna i varje bolags egen databas, och det håller isär bolagen helt.

**Beslut:** masterdatabasen har bara bolagsregistret (`tenants`, med Entra-katalogens id).
Användare, tillägg och allt annat ligger i bolagets databas.

**Konsekvens:** en person som arbetar i två bolag har två konton. Vid inloggning slås bolaget
upp via Entra-katalogens id innan användaren kan hittas (F0-13).

## B-007 — En adress för alla bolag; bolaget väljs vid inloggningen

**Datum:** 2026-11-17 · **Status:** GÄLLER

PE Portal har en domän per bolag. PDF-studio ska kunna säljas till många bolag, och en
domän per bolag kräver ett DNS- och certifikatsteg för varje ny kund.

**Beslut:** en adress för alla. Med Microsoft hittas bolaget via katalogens id i
inloggningen (Entra-appen tar emot flera organisationer). Med reservkonto anger man
bolaget i formuläret. Sessionen bär bolagets id och användarnamnet och är signerad.

**Konsekvens:** inget DNS-steg per kund. Ett felstavat bolag ger samma fel som fel
lösenord, så inga bolagsnamn går att gissa fram.

## B-008 — Förslag: en Ubuntu-server per miljö i Azure, PostgreSQL som tjänst

**Datum:** 2026-11-17 · **Status:** ERSATT AV B-010

B-002 lämnade öppet vilka Azure-tjänster som används. PE Portals utläggning (SSH till en
server, migrationer före koden, hälsokontroll, återgång) är provad i drift och kan
användas nästan oförändrad på en vanlig Linux-server.

**Förslag:** en virtuell Ubuntu-server per miljö (B2s) med Nginx och gunicorn, och Azure
Database for PostgreSQL (flexibel server, B1ms) i Sweden Central. Skripten i `deploy/` och
stegen i driftsattning.md (steg 5–6) är skrivna för det.

**Konsekvens:** samma arbetssätt som PE Portal. Alternativet App Service kräver ett annat
utläggningsflöde och räknas på innan det väljs. Kostnaden i kronor per månad ska
hämtas ur Azures priskalkylator innan beslutet.

## B-009 — Sidbilderna renderas på servern i första steget

**Datum:** 2026-11-17 · **Status:** GÄLLER

Specifikationen nämner pdf.js för visningen. pdf.js måste antingen laddas från ett CDN
(extern part i varje sidvisning, och CSP:n behöver öppnas) eller läggas i repot.

**Beslut:** miniatyrer och sidbilder renderas på servern med pypdfium2 (PDFium) och
skickas som PNG. Ingen JavaScript från tredje part. pdf.js tas in när zoom och
textmarkering i vyn byggs (F1-04, F2-01), och då i repot med låst version.

**Konsekvens:** sidorna fungerar utan JavaScript och med strikt CSP. Varje sidbild kostar
en rendering på servern; den cachas i webbläsaren eftersom en version aldrig ändras.

## B-010 — DigitalOcean i Frankfurt: dev på PE Portals dev-server, egen server för produktionen

**Datum:** 2026-11-17 · **Status:** GÄLLER · ersätter B-002 och B-008

Kostnaden i Azure räknades ur Azures prislista (SEK, 2026-11-17): cirka 220 kr per månad för
dev och cirka 530 kr per månad för produktionen (virtuell server, PostgreSQL som tjänst, disk,
fast adress, lagring). PE Portal kör redan på DigitalOcean i Frankfurt, och servern
`pe-portal-dev` (2 GB minne, 50 GB disk) hade 1,3 GB ledigt minne och 44 GB ledig disk.
Inloggningen med Microsoft kräver inte Azure — Entra-registreringen är gratis (B-011).

**Beslut:**

- **Dev** körs på `pe-portal-dev`, bredvid PE Portal. Ingen extra kostnad. Egen
  systemanvändare (`pdfstudio`), egen port (8010), egen deploy-användare (`pdfdeploy`) och
  egna databaser i serverns PostgreSQL. En växlingsfil på 2 GB läggs till.
- **Produktionen** får en egen droplet, Basic 2 GB / 1 vCPU, **12 USD per månad**
  (digitalocean.com/pricing/droplets, 2026-11-17), med PostgreSQL och filerna lokalt på servern.
- **Backup** dumpas före varje migration och varje natt, och kopieras till PE Portals
  backup-bucket i Spaces under en egen mapp. Backup finns först när återställningen är provad (F0-12).

**Konsekvens:** utläggningen från PE Portal används nästan oförändrad. Filerna lagras lokalt
(`STORAGE_MODE=local`); Azure Blob-stödet i koden ligger kvar men används inte. Datan ligger i
Tyskland (EU), inte i Sverige. Blir dev-servern trång flyttas PDF-studio till en egen droplet
(12 USD). En kraschad process på dev drabbar inte PE Portal, men minnet delas.

## B-011 — Microsoft-inloggning för en organisation, som PE Portal (B-055)

**Datum:** 2026-11-17 · **Status:** GÄLLER

B-007 sade att Entra-appen skulle ta emot flera organisationer. Så länge bara Pure Energys
katalog används är det en onödig öppning: vem som helst med ett Microsoft-konto kan nå
inloggningen, och appen måste lita på att bolagsregistret stoppar dem.

**Beslut:** Entra-appen registreras för en organisation (single-tenant), som PE Portal.
Med `ENTRA_TENANT_ID` satt loggar appen in mot just den katalogen och nekar en inloggning
vars katalog-id är ett annat. Adressen är fortfarande en för alla (B-007 i övrigt gäller).

**Konsekvens:** gratis, och samma uppsättning som PE Portal. När ett andra bolag ska in
ändras registreringen till flera organisationer och `ENTRA_TENANT_ID` tas bort — ett nytt beslut.

## B-005 — Claude Opus 5.5 för all AI-tolkning

**Datum:** 2026-11-16 · **Status:** GÄLLER

**Beslut:** `claude-opus-5-5` via Anthropics Python-SDK. PDF:er skickas som dokumentblock, så att
text i bilder tolkas utan separat OCR-motor. Promptcache för följdfrågor.

**Konsekvens:** kostnaden mäts per anrop från dag ett (tabellen `ai_usage`) och stoppas av
utgiftstaket på 450 kr i koden och 500 kr på kontot.
