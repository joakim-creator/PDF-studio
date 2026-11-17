# Arbetsregler

Läses automatiskt varje session. Håll den kort — det som står här ska vara sant och
gälla alltid. Regler som bara gäller ibland hör hemma i `docs/`, inte här.

## Projektet

PDF-studio: molnapp för PDF (slå ihop, dela, kommentera, exportera, AI). Python 3.12, Flask 3,
PostgreSQL med en databas per bolag, DigitalOcean Frankfurt (B-010). Förlaga för kod: `C:\Users\JoakimHansson\Claude\pe-portal`.

- **Inga AGPL-bibliotek** (inte PyMuPDF, inte Ghostscript). Licenskontrollera varje nytt beroende ([B-003](docs/beslutslogg.md)).
- **Originalet rörs aldrig.** Varje ändring av ett dokument blir en ny version.
- **AI:** `claude-opus-5-5`, kostnaden loggas per anrop och stoppas av utgiftstaket.
- Grafisk profil: Pure Energy Design System, svart logotyp med orange +. Prototyp: https://claude.ai/artifact/QWRAF2pJZjAypPx8vT44u1

Varje regel nedan finns för att den kostade något. Referenserna pekar på
[lärdomarna](docs/lardomar.md).

## Miljön

- Terminalen är **PowerShell 5.1**. `&&` finns inte — separera med `;` eller
  `if ($?) { ... }`. Kör `npx.cmd`, inte `npx`.
- Git-kommandon körs **från projektmappen**, aldrig från hemkatalogen.

## Innan något körs skarpt

- **Databasen före koden.** En migration som en driftsatt kodrad förutsätter körs
  *innan* koden slås ihop. Aldrig samtidigt, aldrig efter.
- **Varje migration har en dokumenterad återställning** i
  [databasandringar.md](docs/databasandringar.md) *innan* den körs. Ingen återställning,
  ingen körning.
- **Migrationer ändras aldrig i efterhand.** En körd migration är historik. Fel rättas
  med en ny migration.
- **Verify-skriptet** (lint + typkontroll + prov i ett kommando) ska vara grönt, med databasproven, innan
  sammanslagning till `dev` eller `main`. CI kör samma kommando och tillåter inte att databasproven hoppas över.
- Vid produktionsändringar: **ett steg i taget**, invänta bekräftelse mellan stegen.

## Git och CI (som i PE Portal — skillen `git-ci-arbetssatt`, [versionering.md](docs/versionering.md))

- **Grenar:** `main` = produktionen, `dev` = dev-miljön, uppgiftsgrenar `fas-<n>/<uppgifts-id>-<kort-namn>` från `dev`.
  Uppgiftsgrenen hålls lokal — bara `dev` laddas upp. Push till `dev` med gröna prov läggs ut i dev automatiskt.
- **Fråga alltid före commit och push.** Commit-meddelanden utan å/ä/ö.
- **Produktionen släpps för hand** av systemägaren: GitHub → Actions → release från `main`, skriv `SLAPP`.
- Serverkommandon körs av systemägaren via SSH: ett eller två i taget, med risk och återgångsväg.

## Hemligheter

- **Aldrig `git add -A`.** Lägg till namngivna filer. Inget undantag.
- Temporära filer, skript och datautdrag hör hemma **utanför repot**.
- Maskera nycklar och tokens i all utdata, även i felmeddelanden och loggar.
- En exponerad nyckel är komprometterad. Den **roteras** — att ta bort den ur
  historiken räcker inte.

## Prov

- **Ett prov du inte sett falla är inte ett prov.** Bryt det avsiktligt och se
  det bli rött innan du litar på att det är grönt.
- Ett prov som prövar åtkomst kräver **data i tabellen**. Utan rader passerar både
  "syns" och "syns inte", och sviten sover.
- Ett prov får aldrig radera data som andra prov förutsätter, och ska städa både
  underliggande och härledda tabeller.
- Påståenden av typen `antal > 0` passerar på skräp från förra körningen. Pröva det
  faktiska värdet.
- Regler som inte kan glömmas bort skrivs som **vaktprov** — ett prov som läser
  schemat eller koden och faller vid återfall. Se `tests/`-konventionen i
  [lardomar.md](docs/lardomar.md).
- **Provsviten ska gå på minuter.** Schemat och seeden byggs en gång per körning till en
  mallfil som varje prov kopierar — inte från grunden per prov. Blir sviten långsam: mät
  (`--durations`) innan du gissar, och kör en verify i taget ([backend-grund.md](docs/backend-grund.md) 13).

## Backend (från PE Portals egengranskning 2026-10-17 — [backend-grund.md](docs/backend-grund.md))

- **Bakom en proxy litar appen på exakt en** (`X-Forwarded-For`/`-Proto` från Nginx). Utan det räknar varje
  spärr per klient hela bolaget som en.
- **Varje anrop har ett ärendenummer** som står i loggen, på felsidan och i felrapporten. Fel i produktion ska
  ge ett larm, inte vänta på att någon läser journalen.
- **Konton inaktiveras, raderas aldrig.** Det som pekar på kontot är spårbarheten.
- **Destruktiva åtgärder kräver ett tillägg och lämnar en loggrad** (vem, vad, när). Administratör får inga
  tillägg automatiskt.
- **Lokala konton: lösenord och engångskod, minst 12 tecken, spärr per konto.** Proven loggar in i två steg som
  i drift — ingen bakdörr för provens skull.
- **Främmande nycklar ska upprätthållas i proven** (SQLite: `PRAGMA foreign_keys=ON`). Ett grönt prov mot en databas
  som inte kontrollerar reglerna bevisar inget om reglerna.
- **Ett radlås läser om objektet.** `FOR UPDATE` uppdaterar inte det sessionen redan läst.
- **En handling som lämnas ut fryses** när den skapas; utskriften läser kopian, inte registren.
- **Backup finns först när återställningen är provad** — datum i tabellen i driftsattning.md.
- **Hemligheter i databasen (OAuth-nycklar, TOTP) är krypterade**; nyckeln i miljön.

## Ändringar i kod

- **Skriptade ersättningar över större block räknar identifierare före och efter.**
  Ett `sed`-spann som råkar täcka en rad för mycket tar bort funktioner tyst.
- Efter en större omskrivning: kör bygget. Oanvänd import är ofta det enda spåret
  efter något som försvunnit.

## Påståenden

- **Säg inte att något är fallet utan att ha kört kommandot som visar det.** Ett
  kommando som ger tomt svar betyder inte alltid att det är tomt.
- Siffror i dokument hämtas ur källan vid skrivtillfället, aldrig ur minnet.
- Rekommendera ingen ändring vars kostnad inte är räknad på.

## Vid oklar indata

Gör indatan entydig hellre än att bygga en smartare gissare. Tre allt mer
avancerade tolkningar av tvetydig data slog fel; en inställning i källan löste det.
