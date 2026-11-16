---
name: git-ci-arbetssatt
description: >
  Sätter upp och följer PE Portals arbetssätt med git, GitHub och CI i ett projekt: grenarna main/dev/uppgiftsgrenar,
  ett verify-skript (lint + typkontroll + prov), GitHub Actions som kör verify vid varje push och lägger ut dev
  automatiskt, ett släpp till produktionen som startas för hand, och deploy-användare med låsta kommandon. Använd när
  användaren vill "sätta upp GitHub/CI som i PE Portal", "köra verify i workflow", "automatisk driftsättning till dev",
  "samma arbetssätt som pe-portal", eller när ett nytt projekt ska få grenmodell, commit-regler och CI.
---

# Git, verify och CI som i PE Portal

Förlagan är `C:\Users\JoakimHansson\Claude\pe-portal`. **Kopiera och anpassa filerna där i stället för att skriva nytt**,
läs dem först. Skriv på svenska. Användaren (Joakim) kör alla serverkommandon själv och vill ha ett steg i taget.

## Läge 1 — sätta upp i ett nytt projekt

Ta reda på först (fråga bara det som inte går att se i projektet): språk och ramverk, databas, var appen ska köras
(dev-server, prod-server), GitHub-repots namn, om det finns en dev-miljö redan.

Bygg sedan i den här ordningen, och visa varje steg innan nästa:

1. **Verify-skript** — ett kommando som kör hela kedjan och faller om något steg faller.
   Förlaga: `pe-portal/scripts/verify.py` (ruff → mypy → pytest, `--require-pg` fäller om databasproven skulle hoppas
   över, `--coverage` bara rapport). Byt stegen efter stacken (t.ex. `eslint` → `tsc --noEmit` → `vitest` för Node).
   Prov som kräver databas körs lokalt mot en Docker-container (se skriptets docstring) och **får aldrig hoppas över i CI**.
2. **CI: `.github/workflows/verify.yml`** — förlaga `pe-portal/.github/workflows/verify.yml`: körs vid varje push och PR,
   databasen som tjänst, samma verify-kommando som lokalt med kravet på databasproven. Jobbet `deploy-dev` körs bara
   vid push till `dev` med gröna prov och bara när variabeln `DEV_HOST` finns.
3. **Utläggning i dev** — `deploy-dev` loggar in via SSH som användaren `deploy`, som bara får köra ett låst kommando.
   Förlagor: `deploy/ci_write_key.sh` (skriver nyckel och värdnyckel från secrets/vars), `deploy/install_deploy_access.sh`
   (skapar `deploy`, låser nyckeln med `command=` i authorized_keys), `deploy/pe-deploy.sh` + `pe-deploy-root.sh`
   (hämtar grenen, kör migrationer **före** koden, startar om, hälsokontroll mot `/health`, återgång vid fel).
   Ändras skripten måste installationen köras om på servern — en push ändrar inte de installerade skripten.
4. **Släpp: `.github/workflows/release.yml`** — förlaga i pe-portal: `workflow_dispatch`, bara från `main`, användaren
   skriver `SLAPP` i rutan, proven körs först, sedan migrationer, kod, hälsokontroll, automatisk återgång.
5. **GitHub-inställningar** (användaren gör dem, ge exakta klick): secrets `DEV_DEPLOY_KEY`/`PROD_DEPLOY_KEY`,
   variabler `DEV_HOST`, `DEV_HOST_KEY`, `PROD_HOST`, `PROD_HOST_KEY`; skydd på `main` (kräver gröna `verify`).
   Nyckelparet skapas på användarens dator eller servern — **be aldrig om privata nycklar eller hemligheter i chatten**.
6. **Dokumentera i projektet:** avsnittet "Arbetssätt" i `CLAUDE.md` (texten nedan), manuella steg i
   `docs/driftsattning.md`, valet i beslutsloggen. Finns projektmallen (`C:\Users\JoakimHansson\Claude\Projektmall`)
   — använd dess dokument.

Prova kedjan på riktigt innan du säger klart: en push till en uppgiftsgren (bara verify), sedan en ihopslagning till
`dev` (verify + deploy-dev). Ett prov som aldrig setts falla bevisar inget — låt ett avsiktligt fel fälla CI en gång.

## Läge 2 — det dagliga arbetet (text att lägga i projektets CLAUDE.md)

- **Grenar:** `main` = produktionen, flyttas bara vid milstolpe eller brådskande rättning. `dev` = dev-miljön.
  Uppgiftsgrenar `fas-<n>/<uppgifts-id>-<kort-namn>` grenas från `dev` och slås ihop dit när de är gröna.
  Uppgiftsgrenen hålls lokal — bara `dev` laddas upp (en CI-körning per uppgift, som också lägger ut i dev).
  Brådskande rättningar grenas från `main` och slås sedan ihop även till `dev`.
- **Commit:** `<typ>(<omfång>): <beskrivning> [<uppgifts-id>]`, typer feat, fix, db, refactor, test, docs, chore, sec.
  **Utan å/ä/ö** i commit-meddelandet. Aldrig `git add -A` / `git add .` — lägg till filerna med namn.
  Committa aldrig hemligheter; en exponerad nyckel **roteras**.
- **Verify före ihopslagning:** verify-skriptet grönt lokalt, med databasproven. Kör en verify i taget.
- **Databasen före koden:** migration + dokumenterad återställning körs i dev, sedan prod, innan kod som förutsätter
  den når `main`. Migrationer ändras aldrig i efterhand — fel rättas med en ny.
- **Fråga alltid före commit och push.** Flödet när användaren säger ja:
  ```bash
  git add <filer> && git commit -m "<meddelande>"
  git checkout dev && git merge --ff-only <uppgiftsgren> && git push origin dev && git branch -d <uppgiftsgren>
  ```
  Säg sedan vad CI gör nu (verify, migration, utläggning) och vad användaren ska kontrollera i dev.
- **Släpp till produktionen** görs av användaren: GitHub → Actions → release → Run workflow från `main`, skriv `SLAPP`.
- **Servrar:** användaren kör kommandona själv via SSH. Ge ett eller två i taget, säg var de körs, vad som ska synas,
  risken och återgångsvägen före riskabla steg.

## Lärdomar att ta med

- Radslut: `.gitattributes` med `eol=lf` för `*.sh`, `*.service`, `*.conf`, `*.sql`, `*.yml` — skript från Windows
  går annars inte att köra på Linux, och migrationernas kontrollsummor ändras.
- Låt CI köra exakt samma kommando som lokalt; ett eget CI-kommando glider isär.
- `concurrency` på utläggningsjobben, så att två pushar inte lägger ut samtidigt.
- Hälsokontroll och automatisk återgång i utläggningen, inte bara "starta om och hoppas".
