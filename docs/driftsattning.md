# Driftsättning och manuella steg

## Miljöer

| Miljö | Namn | Adress | Referens |
|---|---|---|---|
| Utveckling | `pe-portal-dev` (DigitalOcean FRA1, delas med PE Portal), tjänsten `pdf-studio-dev`, port 8010 | `https://<dev-domän>` | B-010 |
| Produktion | Egen droplet, Basic 2 GB (12 USD/månad), tjänsten `pdf-studio`, port 8010 | Bestäms i F4-04 | B-010 |

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

Gratis — Entra-registreringen kostar inget och kräver ingen Azure-prenumeration. Appen registreras för **en
organisation**, Pure Energys katalog, som PE Portal (B-011). Ett andra bolag kräver ett nytt beslut.

1. Entra-administrationscentret (entra.microsoft.com) → Identitet → Program → Appregistreringar → **Ny registrering**.
   Namn `PDF-studio`; kontotyper **Endast konton i den här organisationskatalogen (en klientorganisation)**;
   omdirigerings-URI, plattform **Webb**: `https://<dev-domän>/auth/microsoft/callback`.
   Lägg sedan till `http://localhost:5055/auth/microsoft/callback` (lokalt) under Autentisering, och
   produktionens adress när den finns.
2. Översikten visar **Program-id (klient)** → `ENTRA_CLIENT_ID` och **Katalog-id (klientorganisation)** →
   `ENTRA_TENANT_ID`. Inget av dem är hemligt.
3. **Certifikat och hemligheter** → ny klienthemlighet, giltig 24 månader (anteckna slutdatumet här: ____).
   Värdet visas bara en gång — lägg det direkt i miljöfilen som `ENTRA_CLIENT_SECRET` (lokalt i `.env`, på servern
   i `/etc/pdf-studio/dev.env`), aldrig i chatten eller i repot.
4. Behörigheter: bara `openid`, `profile`, `email` (standard). Inget administratörsmedgivande behövs.
5. Bolaget knyts till katalogen: `flask --app app bolag-skapa <slug> <namn> --databas <url> --entra-katalog
   <katalog-id>` (samma id som `ENTRA_TENANT_ID`).
6. Användarna läggs upp med e-postadressen (`konto-skapa ... --epost`); Microsoft-kontot binds vid första
   inloggningen. Ingen skapas automatiskt.
7. Prova: logga in med Microsoft i dev och se raden `microsoft ok` i inloggningsloggen. Ett konto från en annan
   organisation ska nekas.

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

1. PE Portals backup-hink i Spaces (privat, livscykelregel 90 dagar), egen mapp `pdf-studio/` (B-010);
   `BACKUP_SPACES_BUCKET` i miljön.
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

### 5. Servern på DigitalOcean (F0-20)

Beslut B-010. Dev körs på `pe-portal-dev` **bredvid PE Portal**, produktionen på en egen droplet. Kör kommandona som
root via SSH, **ett block i taget**, och läs utdata innan nästa. Inget här rör PE Portals användare (`deploy`,
`www-data`), port (8000), databaser eller Nginx-block.

**5a. Växlingsfil, 2 GB** (servern har ingen; två appar delar 2 GB minne).
Risk: låg. Återgång: `swapoff /swapfile; rm /swapfile` och ta bort raden i `/etc/fstab`.
```
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab && free -h
```

**5b. Systemanvändaren och filmappen.** Risk: ingen för PE Portal. Återgång: `userdel pdfstudio; rm -r /var/lib/pdf-studio`.
```
useradd --system --home-dir /var/lib/pdf-studio --shell /usr/sbin/nologin pdfstudio
install -d -o pdfstudio -g pdfstudio -m 750 /var/lib/pdf-studio /var/lib/pdf-studio/filer
```

**5c. Databaserna** i serverns PostgreSQL, med en egen roll som inte är ägare till PE Portals databaser. Lösenordet
skapas på servern och visas inte. Återgång: `dropdb` för de två och `DROP ROLE pdfstudio`.
```
PW=$(openssl rand -hex 24); sudo -u postgres psql -c "CREATE ROLE pdfstudio LOGIN PASSWORD '$PW'"
sudo -u postgres createdb -O pdfstudio pdfstudio_master && sudo -u postgres createdb -O pdfstudio pdfstudio_pureenergy
```
Skriv miljöfilen i samma skal, så att `$PW` finns kvar (5d).

**5d. Miljöfilen** `/etc/pdf-studio/dev.env` (root, `chmod 600`). Variablerna står i tabellen nedan; för dev:
```
install -d -m 700 /etc/pdf-studio
cat > /etc/pdf-studio/dev.env <<EOF
PDF_ENV=dev
SECRET_KEY=$(openssl rand -hex 32)
TOTP_KEY=$(python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
MASTER_DATABASE_URL=postgresql://pdfstudio:$PW@127.0.0.1:5432/pdfstudio_master
STORAGE_MODE=local
STORAGE_FOLDER=/var/lib/pdf-studio/filer
EOF
chmod 600 /etc/pdf-studio/dev.env; unset PW
```
Entra-värdena (steg 1) läggs till med en editor när registreringen finns.

**5e. Koden.** Risk: ingen för PE Portal. Återgång: `rm -r /var/www/pdf-studio`.
```
git clone https://github.com/joakim-creator/PDF-studio.git /var/www/pdf-studio
cd /var/www/pdf-studio && git checkout dev && python3 -m venv venv && venv/bin/pip install -q -r requirements.txt
```

**5f. Schemat, bolaget och första kontot.** Bolagets databas-URL är masterns med `pdfstudio_pureenergy` i stället
för `pdfstudio_master`.
```
cd /var/www/pdf-studio && set -a && . /etc/pdf-studio/dev.env && set +a
venv/bin/flask --app app db-migrate --yes
venv/bin/flask --app app bolag-skapa pureenergy "Pure Energy" --databas '<bolagets url>' --entra-katalog <katalog-id>
venv/bin/flask --app app db-migrate --yes && venv/bin/flask --app app db-status
```
Nödkontot: `konto-skapa` (steg 4). Lösenordet skrivs in på servern, aldrig i chatten.

**5g. Tjänsten och Nginx.** DNS först: en A-post för `<dev-domän>` till adressen för `pe-portal-dev`.
Risk: `nginx -t` måste vara grönt före omladdningen, annars påverkas PE Portal. Återgång: ta bort länken i
`sites-enabled`, `systemctl reload nginx`, `systemctl disable --now pdf-studio-dev`.
```
cp deploy/pdf-studio.service /etc/systemd/system/pdf-studio-dev.service && systemctl daemon-reload
systemctl enable --now pdf-studio-dev && curl -s -H 'Host: <dev-domän>' http://127.0.0.1:8010/health
sed 's/DOMÄN/<dev-domän>/' deploy/nginx.conf > /etc/nginx/sites-available/pdf-studio
ln -s /etc/nginx/sites-available/pdf-studio /etc/nginx/sites-enabled/pdf-studio && nginx -t
systemctl reload nginx && certbot --nginx -d <dev-domän>
```
`nginx-default.conf` installeras **inte** på dev — PE Portal har redan ett `default_server`.

**5h. Prova:** `curl -s https://<dev-domän>/health` ger `"status": "ok"`, och PE Portal svarar som förut.

**Produktionen (F4-04).** DigitalOcean → Create → Droplet: Ubuntu 24.04 LTS, Frankfurt (FRA1), Basic, Regular,
**2 GB / 1 vCPU, 12 USD/månad**, SSH-nyckel, DigitalOceans backup avstängd (egen backup, steg 3). Cloud Firewall: 22
bara från din adress, 80 och 443 öppna. Först:
```
apt install -y postgresql-16 nginx python3.12-venv git certbot python3-certbot-nginx
cp deploy/nginx-default.conf /etc/nginx/sites-available/default
```
Därefter 5a–5h med `prod.env`, `PDF_ENV=prod`, tjänsten `pdf-studio` och grenen `main`.

**Blockerar:** F0-20

### 6. GitHub och automatisk utläggning (F0-20, F0-21)

1. Repo på GitHub (`joakim-creator/PDF-studio`); grenarna `main` och `dev`. Skydd på `main`: kräver grön `verify`.
2. På servern: `bash deploy/install_deploy_access.sh dev <dev-domän>`. Skriptet skapar användaren `pdfdeploy`
   (inte `deploy` — den är PE Portals, och dess nyckel skulle skrivas över), som bara får köra `status` och
   `deploy <commit>`, och skriver ut nyckeln **en gång** — den går bara in i GitHub, aldrig i chatten.
   `DEV_HOST` är samma server som PE Portals dev, men nyckeln är en annan.
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
| `MASTER_DATABASE_URL` | Serverns PostgreSQL, databasen `pdfstudio_master`, rollen `pdfstudio` (steg 5c) | Nej |
| `TOTP_KEY` | Egen Fernet-nyckel för engångskoderna | Nej |
| `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_TENANT_ID` | Appregistreringen (steg 1). Med `ENTRA_TENANT_ID` godtas bara den katalogen (B-011) | Nej |
| `STORAGE_MODE`, `STORAGE_FOLDER` | `local` och `/var/lib/pdf-studio/filer` (B-010) | Nej |
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
