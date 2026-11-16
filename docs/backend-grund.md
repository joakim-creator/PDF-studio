# Backend-grund — det som ska finnas från början

Det här är det som egengranskningen av PE Portal (2026-10-17) visade saknades i ett system som annars var
välbyggt, och som sedan byggdes in på en kväll. Nästa system ska ha det från Fas 0, inte efter en granskning.
Varje punkt har en referensfil i `pe-portal` som går att kopiera eller läsa som förlaga. Oberoende av ramverk —
där det står Flask gäller motsvarigheten i det ramverk som används.

Uppgifterna finns som F0-10–F0-19 i [BACKLOG.md](../BACKLOG.md). Hur de provas står under varje punkt: **ett prov
som inte setts falla är inte ett prov** — bryt regeln i en kopia och se vakten bli röd.

---

## 1. Bakom en proxy: lita på exakt en

Gunicorn/Node bakom Nginx ser `127.0.0.1` som avsändare för alla anrop. Allt som räknar per klient — spärren mot
inloggningsförsök, taket på en publik sida — räknar då hela bolaget som en klient. Tio sidvisningar av `/login`
per minut gav "För många försök" åt alla. HSTS och `is_secure` blir också fel.

- Läs klientens adress och protokoll ur `X-Forwarded-For`/`X-Forwarded-Proto`, men bara från **en** betrodd proxy
  (`ProxyFix(x_for=1, x_proto=1)` i Flask). Appen lyssnar bara på localhost, så huvudena kan inte komma från någon
  annan.
- Nginx sätter huvudena och dessutom `X-Request-ID $request_id` (punkt 3).
- **Prov:** tolv anrop med olika `X-Forwarded-For` och samma `REMOTE_ADDR` ska ge tolv 200; samma adress elva gånger
  ska ge 429 på den elfte.
- Referens: `pe-portal/app.py` (ProxyFix), `tests/test_proxy.py`, `deploy/dev/nginx-dev.conf`.

## 2. Spärr per konto, inte bara per adress

En spärr per IP skyddar inte när adressen är delad (kontoret, mobilnätet) och låser ute fel personer.

- `failed_logins` och `locked_until` på kontot: fem fel (lösenord eller engångskod) låser i 15 minuter; rätt
  inloggning nollar. Meddelandet säger hur länge.
- Referens: `pe-portal/auth.py` (`_failed`, `_locked_message`), `tests/test_totp.py`.

## 3. Ärendenummer, logg, felsida, hälsosida, felrapportering

Ett fel i produktion ska synas utan att någon läser journalen, och den som felsöker (en människa eller en AI) ska
kunna följa ett anrop från Nginx-loggen till felrapporten.

- **Ärendenummer** (`X-Request-ID`) på varje anrop: Nginx eget används när det finns, annars skapas ett. Står i
  svaret, i varje loggrad, på felsidan ("ange detta nummer när du felanmäler") och i felrapporten.
- **Loggrad per anrop:** metod, adress, status, tid, bolag, användare, ärendenummer. Till stderr → journald.
- **Felsidan** är fristående (visas även när databasen är nere) och visar inga interna detaljer.
- **`/health`** är publik, svarar `ok`/`fel` per del (masterdatabas, bolagsdatabas, migrationer) utan detaljer;
  driftsättningsskriptet och leverantörens uptime-övervakning anropar den.
- **Felrapportering** (GlitchTip — samma bibliotek som Sentry, ingen amerikansk leverantör): bara aktiv med
  `GLITCHTIP_DSN`, aldrig i proven; rapporten **tvättas** (inga kakor, formulärdata, huvuden, frågesträngar eller
  lokala variabler — bara stack, adress, metod, bolag, ärendenummer, användarnamn); **tak per timme i koden** och
  händelsetak på kontot (två lager).
- **Prov:** svaret bär ett ärendenummer; ett framkallat 500 loggas med stack och ärendenummer och visar sidan;
  `/health` ger 503 när bolagets databas inte nås; felrapporten saknar kakor och formulärdata; taket per timme
  håller. En egen transport i proven **måste ärva `Transport`**, annars går anropet ut på nätet.
- Referens: `pe-portal/core/observability.py`, `templates/error.html`, `tests/test_drift_logg.py`,
  `docs/Freja/driftsattning.md` steg 17.

## 4. Säkerhetskopiering och återställningsprov

Leverantörens automatiska backup räcker inte: den täcker inte filerna på servern, och ingen vet att återställningen
fungerar förrän den provats.

- Ett skript (cron, nattligen) som tar `pg_dump` av **varje** databas via appen (lösenordet i miljön, aldrig på
  kommandoraden), packar hela filmappen, och laddar upp till en **egen backup-hink** via en förhandssignerad länk
  från appen (`curl --upload-file`, inget i minnet). Lokala kopior gallras efter 30 dagar; hinkens livscykelregel
  (90 dagar) är taket på kontot.
- Ett kommando som kontrollerar en återställd databas mot koden (`flask db-status --url <databas>`).
- **Återställningsprovet** som rutin med tabell (datum, kopia, databas återläst, filer, kontroll, tid, utförd av) —
  en gång före lansering, sedan vid varje milstolpe. Mål: högst ett dygns dataförlust, återställning inom två
  timmar. Go-live-kriteriet är uppfyllt först när tabellen har en rad.
- **Prov:** länken är en signerad PUT till backup-hinken utan hemligheten i adressen; pg_dump-kommandot lämnar
  lösenordet i miljön; skriptet tar hela filmappen och gallrar.
- Referens: `pe-portal/deploy/backup.sh`, `core/backup.py`, `tests/test_backup.py`, `docs/Freja/driftsattning.md`
  steg 18.

## 5. Inaktivera, radera aldrig konton

Ett fyrtiotal kolumner (`created_by`, `updated_by` …) pekar på kontot — det är spårbarheten. En hård radering ger
500 i PostgreSQL så snart kontot skapat något, och raderas den ändå försvinner "vem gjorde vad".

- `active`-flagga på kontot; inaktiverad nekas alla inloggningsvägar och tappar pågående session (`load_user`);
  listor över vem som kan få roller visar bara aktiva.
- **Prov med främmande nycklar påslagna** (punkt 9): att radera ett konto som skapat en rad ska falla.
- Referens: `pe-portal/core/portal.py` (`user_active`), `app.py` (`load_user`), `tests/test_anvandare.py`.

## 6. Lokala konton: lösenord och engångskod, 12 tecken, inloggningslogg

SSO (Microsoft Entra) är huvudvägen; lokala konton är reserv och för externa konsulter — och de är det svagaste
stället om de bara har ett lösenord.

- Engångskod (TOTP, RFC 6238 — standardbiblioteket räcker, ~40 rader) efter lösenordet. Appen registreras vid
  första inloggningen (nyckel och `otpauth://`-länk visas en gång); hemligheten sparas **krypterad** (Fernet, nyckel
  i miljön eller härledd ur `SECRET_KEY`); administratören återställer vid tappad telefon; Mitt konto kan byta app.
- Nya lösenord minst 12 tecken, en konstant på ett ställe.
- **Inloggningslogg**: varje försök (användarnamn även okända, metod, utfall, klientens adress, tid), sida för
  administratören.
- **Proven loggar in i två steg som i drift** — ingen bakdörr i koden för provens skull. En hjälpfunktion läser
  nyckeln ur databasen som användaren läser den på skärmen.
- **Prov:** RFC 6238:s testvektorer; koden krävs även för admin; fem fel låser; återställningen loggas.
- Referens: `pe-portal/core/totp.py`, `auth.py`, `tests/conftest.py` (`local_login`), `tests/test_totp.py`.

## 7. Händelselogg och tillägg för destruktiva åtgärder

Radering av affärsdata ska kräva ett uttryckligt tillägg (inte följa av en roll) och lämna en rad: vem, vad, när.

- En gemensam tabell `audit_events` (användare, område, åtgärd, beskrivning, tid) och en hjälpfunktion
  `audit.log(område, åtgärd, beskrivning)`; sida under Inställningar. Fler händelser (prisändringar på rader)
  loggas där senare.
- Tillägg per moment (`crm.radera`, `freja.makulera` …) delas ut uttryckligen; administratör får dem inte
  automatiskt; knapparna visas bara med tillägget; nekad sida säger vilket tillägg som krävs.
- **Prov:** utan tillägget 403 och inga rader ändrade; med tillägget raderat och loggat; knappen syns bara med
  tillägget.
- Referens: `pe-portal/core/audit.py`, `core/permissions.py`, `modules/crm/routes.py` (`_require_delete`),
  `tests/test_radera_crm.py`.

## 8. Originalhandlingar fryses

En utskrift som räknas som handling (kontantfaktura, kvitto, avtal) får inte byggas från registren vid
utskriftstillfället — ändras kunden eller företagsuppgifterna visar den något annat än vad som lämnades ut.

- Spara det som stod på handlingen (säljare, kund, rader, belopp) som JSON på underlaget när den skapas; utskriften
  läser kopian. Före det: arbetskopia märkt PRELIMINÄR. Inga interna uppgifter i kopian (inpris, anteckningar).
- **Prov:** ändra namn, adress, kundtyp, företagsuppgifter och ett radpris efter att handlingen skapats — utskriften
  visar originalet.
- Referens: `pe-portal/modules/freja/cash_invoice.py`, `tests/test_kontantfaktura_frusen.py`.

## 9. Främmande nycklar på i proven; radlås läser om

- **SQLite upprätthåller inte främmande nycklar om man inte ber om det.** Två prov raderade rader och lämnade
  föräldralösa barn utan att något föll; PostgreSQL hade stoppat det. `PRAGMA foreign_keys=ON` på varje
  SQLite-anslutning från dag ett. Ett grönt prov mot en databas som inte kontrollerar reglerna bevisar inget om
  reglerna.
- **`SELECT … FOR UPDATE` låser raden men uppdaterar inte ett objekt sessionen redan läst.** Den andra av två
  samtidiga faktureringar såg "Utförd" fast raden nyss blivit "Fakturerad". Läs om efter låset
  (`populate_existing()` i SQLAlchemy) och pröva med två sessioner mot riktig PostgreSQL.
- Referens: `pe-portal/core/db_routing.py`, `modules/freja/invoicing.py` (`send_order`),
  `tests/test_fakturering_samtidigt.py`.

## 10. GDPR-grunden i koden, inte bara i dokumentet

- Förteckningen (`docs/GDPR.md`) uppdateras vid varje ny uppgift om personer — och den ska inte ha "bestäms senare"
  vid lansering.
- En **regel** för gallring som kod (t.ex. "prövas 36 månader efter senaste aktivitet") med en kandidatlista och
  ett kommando för torrkörning; en **roll** (GDPR-ansvarig) som beslutar per post; **registerutdrag** som ett
  kommando som samlar allt om en person som JSON.
- Referens: `pe-portal/core/retention.py`, `app.py` (`gdpr-kandidater`, `gdpr-utdrag`), `tests/test_gdpr.py`,
  `docs/GDPR.md`, `docs/GDPR-RUTINER.md`.

## 11. Modulgränser som vakt, inte som mappstruktur

Moduler importerar varandra, och kärnan importerar moduler, utan att något faller. Nästa modul blir dyrare för
varje sådan genväg.

- Skriv beroendematrisen (vilken modul får importera vad; kärnan importerar aldrig en modul) i arkitekturdokumentet
  **och** som ett vaktprov som läser importerna. Delade begrepp (kunder, inventarier, användare) ligger i kärnan och
  refereras via id.
- Det som en modul behöver från en annan går via en funktion modulen registrerar (krok), aldrig via en annan moduls
  privata vyfunktioner.

## 12. Övrigt att ha med från början

- **Säkerhetshuvuden**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, CSP i
  rapportläge först.
- **Filuppladdning**: typen kontrolleras på innehållet (första byten), aldrig på ändelsen; nyckel
  `<bolag>/<område>/<uuid>.<ändelse>`; filnamnet bara i databasen; privat hink med signerade länkar.
- **Beroendeskanning** (`pip-audit`, `npm audit`) som steg i CI; varje paket som används direkt står i
  requirements (inte bara som transitivt beroende).
- **Index på FK-kolumner** som joinas — en migration med `CREATE INDEX` innan datan växer.
- **Släppet bundet till den provade commiten**: servern tar emot commit-id från CI och vägrar om grenen pekar
  någon annanstans; `pip freeze` sparas före installation så att återgången återställer beroendena.
- **Tid**: UTC i databasen, lokal tid i gränssnittet, `timestamptz`; schematider (planering) är lokala klockslag
  och ska sägas vara det.
- **Pengar**: `numeric`, aldrig flyttal.

## 13. Provsviten ska gå på minuter, inte kvartar

En provsvit som tar en kvart körs före ihopslagning; en som tar tre minuter körs efter varje steg. Skillnaden
avgör hur långt det är mellan ett fel och dess orsak.

- **Fixturen är ofta dyrare än proven.** I PE Portal byggde varje prov 72 tabeller i en ny SQLite-fil, fyllde seeden
  och loggade in med scrypt: ca 1 s per prov, medan själva provet tog under 50 ms. 750 prov gav 13 minuter.
- **Bygg schemat och seeden en gång per körning till en mallfil** och låt varje prov kopiera filen (några
  tusendelar). Mallen byggs färsk vid varje körning utifrån modellerna och seeden — ingenting sparas i projektet,
  och nya tabeller följer med utan handpåläggning. Det som i seeden bär bolagets namn (lagringsnycklar) byts efter
  kopieringen. En mall med seed och en utan. Resultat: 13 min → 3 min.
- **Vaktprov för mallen:** kopian har samma radantal per tabell som en databas byggd från grunden, alla modellernas
  tabeller finns, och en ändring i ett provbolag syns inte i ett annat.
- **Mät innan du gissar varför något blev långsamt** (`pytest --durations=20`, och jämför gammal och ny kodbas
  ensamma på maskinen). Två sessioner som kör verify samtidigt på samma disk gör båda dubbelt så långsamma — kör
  en i taget.
- Det enda som inte längre är per prov är datumet: seeden räknar från "i dag" när mallen byggs, så en körning över
  midnatt kan ge en datumskillnad i enstaka prov.
- Referens: `pe-portal/tests/conftest.py` (`_template`, `make_tenant`), `tests/test_provmall.py`,
  `docs/Freja/lardomar.md` (2026-10-19).
