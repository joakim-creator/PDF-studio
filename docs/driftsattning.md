# Driftsättning och manuella steg

## Miljöer

| Miljö | Namn | Adress | Referens |
|---|---|---|---|
| Utveckling | | | |
| Produktion | | | |

Migrationer körs **alltid mot dev först**. Produktion rörs bara av migrationer som
redan gått igenom dev och står i [databasandringar.md](databasandringar.md).

**Nginx måste skicka klientens adress och protokoll** (`X-Forwarded-For`, `X-Forwarded-Proto`) och ett
ärendenummer (`X-Request-ID $request_id`); appen litar på exakt en proxy. Utan huvudena räknar spärren mot
inloggningsförsök alla användare som en klient. Kontrollera med `grep -n proxy_set_header /etc/nginx/sites-enabled/*`.

## Manuella steg

Sådant som kräver inloggning och inte kan automatiseras. Numrera dem och notera
vilken backloggpost de blockerar, så att det syns när något står stilla i väntan på
ett konto.

### 1. Microsoft-inloggning (Entra ID) (F0-13)

PDF-studio är en app för **flera organisationer** (varje bolag har sin egen Entra-katalog), så
registreringen görs en gång, i den katalog som äger appen.

1. Entra-administrationscentret → Identitet → Program → Appregistreringar → **Ny registrering**.
   Namn `PDF-studio`; kontotyper **Konton i alla organisationskataloger (flera klientorganisationer)**;
   omdirigerings-URI (webb) `https://<dev-domän>/auth/microsoft/callback`. Lägg till samma för prod senare.
2. Under **Certifikat och hemligheter**: ny klienthemlighet. Värdet visas bara en gång — lägg det direkt i
   dev-miljöns miljöfil som `ENTRA_CLIENT_SECRET`, aldrig i chatten eller i repot. Programmets (klientens)
   id blir `ENTRA_CLIENT_ID`.
3. Behörigheter: bara `openid`, `profile`, `email` (standard). Inga administratörsmedgivanden behövs.
4. För varje bolag: katalogens id (Entra → Översikt → Klientorganisations-id) läggs in med
   `flask --app app bolag-skapa <slug> <namn> --databas <url> --entra-katalog <id>`. Första gången någon i
   en annan organisation loggar in godkänner deras administratör appen.
5. Användarna läggs upp med e-postadressen (`konto-skapa ... --epost`); Microsoft-kontot binds vid första
   inloggningen. Ingen skapas automatiskt.
6. Prova: logga in med Microsoft i dev, och se raden `microsoft ok` i inloggningsloggen.

**Blockerar:** F0-13 (skarpt prov)

### 2. Felrapportering och hälsokontroll (F0-11)

1. GlitchTip (hyrd i EU eller egen drift): organisation, ett projekt per miljö, DSN till miljöfilen
   (`GLITCHTIP_DSN`). Händelsetak på projektet (taket på kontot); `ERROR_REPORT_HOURLY_MAX` är taket i koden.
2. Larm per nytt och återkommande fel till e-post och Teams (Incoming Webhook).
3. Uptime-kontroll hos leverantören mot `https://<domän>/health`, larm vid annat än 200.
4. Prova: framkalla ett fel i dev och se ärendet i GlitchTip med samma ärendenummer som felsidan visar.

**Läsa loggen:** `journalctl -u <tjänst> -n 200`; sök ett ärende med `journalctl -u <tjänst> | grep <ärendenummer>`.

### 3. Säkerhetskopiering och återställningsprov (F0-12)

**Mål:** högst ett dygns dataförlust, återställning inom två timmar.

1. Egen backup-hink (privat) med livscykelregel (90 dagar); `BACKUP_SPACES_BUCKET` i miljön.
2. Backupskriptet installerat och cron kl 03 (`0 3 * * * /usr/local/sbin/<app>-backup >> /var/log/<app>-backup.log 2>&1`).
   Prova för hand: loggen slutar med `KLART` och visar en uppladdning per fil.
3. **Återställningsprovet** på dev mot en kopia — före lansering och vid varje milstolpe: ny tom databas, `pg_restore`,
   kontroll mot koden (`db-status --url`), packa upp filerna och öppna en, räkna rader mot källan, städa.
   Leverantörens egen backup (prod) provas separat (*Restore to new cluster*).

| Datum | Kopia | Databas återläst | Filer | Kontroll mot koden | Tid | Utförd av |
|---|---|---|---|---|---|---|
| | | | | | | |

### 4. Nödkontot (F0-13)

Lokala konton loggar in med lösenord (minst 12 tecken) och engångskod från en autentiseringsapp. Registrera
appen för nödkontot direkt efter driftsättningen, så att nödinloggningen är provad innan den behövs — anteckna
datum här: ____. Tappad telefon: administratören återställer appen. Fem fel låser kontot i 15 minuter;
inloggningsloggen visar försöken.

### 5. Servern i Azure (F0-20)

Förslag (B-008): en Ubuntu-server per miljö, med PostgreSQL som Azure-tjänst — samma upplägg som PE Portal, så att
skripten i `deploy/` gäller som de är.

1. Azure-portalen → Virtuella datorer → Skapa: Ubuntu 24.04 LTS, region **Sweden Central**, storlek B2s
   (räcker för 8 användare), inloggning med SSH-nyckel. Öppna port 22 (bara från din adress), 80 och 443.
2. Azure Database for PostgreSQL – flexibel server, Sweden Central, version 16, minsta storleken (Burstable B1ms).
   Tillåt bara den virtuella servern i nätverket. Skapa databaserna `pdfstudio_master` och en per bolag.
3. På servern (som root, ett steg i taget):
   ```
   apt install -y nginx python3.12-venv git postgresql-client-16 certbot python3-certbot-nginx
   git clone https://github.com/joakim-creator/PDF-studio.git /var/www/pdf-studio
   cd /var/www/pdf-studio && git checkout dev && python3 -m venv venv && venv/bin/pip install -r requirements.txt
   install -d -m 700 /etc/pdf-studio   # miljöfilen /etc/pdf-studio/dev.env (Miljövariabler nedan), chmod 600
   cp deploy/pdf-studio.service /etc/systemd/system/pdf-studio-dev.service && systemctl daemon-reload
   cp deploy/nginx.conf /etc/nginx/sites-available/pdf-studio   # byt DOMÄN; länka till sites-enabled
   set -a; . /etc/pdf-studio/dev.env; set +a; venv/bin/flask --app app db-migrate
   systemctl enable --now pdf-studio-dev && certbot --nginx -d <domän>
   ```
4. Första bolaget och kontot: `flask --app app bolag-skapa ...` och `konto-skapa ...` (steg 1).
5. `curl -s https://<domän>/health` ska ge `"status": "ok"`.

**Blockerar:** F0-20

### 6. GitHub och automatisk utläggning (F0-20, F0-21)

1. Repo på GitHub (`joakim-creator/PDF-studio`); grenarna `main` och `dev`. Skydd på `main`: kräver grön `verify`.
2. På servern: `bash deploy/install_deploy_access.sh dev <domän>`. Skriptet skapar användaren `deploy`, som bara
   får köra `status` och `deploy <commit>`, och skriver ut nyckeln **en gång** — den går bara in i GitHub, aldrig i
   chatten.
3. GitHub → Settings → Secrets and variables → Actions: secrets `DEV_DEPLOY_KEY` (och `PROD_DEPLOY_KEY`),
   variabler `DEV_HOST`, `DEV_HOST_KEY` (och `PROD_HOST`, `PROD_HOST_KEY`). Utan `DEV_HOST` hoppas `deploy-dev` över.
4. Prova: push till `dev` → Actions visar `verify` och `deploy-dev` gröna, och dev svarar 200 på `/health`.
   Låt ett avsiktligt fel fälla verify en gång innan kedjan räknas som klar.
5. Prod: Actions → release → Run workflow från `main`, skriv `SLAPP`. Servern lägger bara ut den commit som
   proven kördes på. Första gången: se att återgången fungerar.

**Blockerar:** F0-20, F0-21

## Miljövariabler

Sätts i driftsmiljön med **produktionens** värden — aldrig utvecklingens.

| Variabel | Källa | Exponeras mot klienten |
|---|---|---|
| `SECRET_KEY` | Slumpad, `python -c "import secrets; print(secrets.token_urlsafe(48))"` | Nej |
| `MASTER_DATABASE_URL` | Azure PostgreSQL, databasen `pdfstudio_master` | Nej |
| `TOTP_KEY` | Egen Fernet-nyckel för engångskoderna | Nej |
| `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` | Appregistreringen (steg 1) | Nej |
| `GLITCHTIP_DSN`, `ERROR_REPORT_HOURLY_MAX` | GlitchTip (steg 2) | Nej |
| `PDF_ENV` | `dev` eller `prod` (syns i felrapporterna) | Nej |
| `TENANT_POOL_SIZE`, `MASTER_POOL_SIZE` | Anslutningar per process (standard 4 och 2) | Nej |

Variabler som exponeras mot klienten ska vara ofarliga att exponera. Skyddet ligger
i åtkomstkontrollen på servern, inte i att nyckeln är svår att hitta.

## Utgiftstak

Varje tjänst som kostar per anrop ska ha **två spärrar**: ett tak i den egna koden
och ett tak på kontot hos leverantören. Appens tak är första försvaret; kontots är
det som inte kan gå sönder på grund av en bugg.

| Tjänst | Tak i koden | Tak på kontot |
|---|---|---|
| | | |

## Efter driftsättning

Gå igenom på riktig enhet, inte bara i utvecklingsläge:

- [ ] Inloggning och utloggning
- [ ] Det vanligaste flödet, från början till slut
- [ ] Något som skriver till databasen, och att värdet syns efteråt
- [ ] Kamera, fil eller annan enhetsfunktion som används
- [ ] En andra användare ser bara sitt eget
- [ ] `/health` svarar `ok`; ett framkallat fel ger ett larm med ärendenummer
- [ ] Nödkontot kan logga in med lösenord och engångskod
- [ ] Återställningsprovet har en rad med datum i tabellen ovan

Punkten om den andra användaren är den som oftast avslöjar något.
