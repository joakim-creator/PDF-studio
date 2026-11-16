# Versionering och release

## Versionsnummer

Formatet är `<major>.<minor>.<rättning>`.

Under bygget löper minor-siffran med fasnumret: `0.1.0` när fas 1 är klar, `0.2.0`
när fas 2 är det. `1.0.0` sätts när allt i specifikationens avsnitt 8 finns **och
produkten används skarpt**. Därefter gäller vanlig semantisk versionering.

Räkna med att en fas tillkommer efter att produkten börjat användas på riktigt. Den
sortens fas syns inte i en plan, bara i användning — planera för den i stället för
att bli överraskad.

## Att göra ett släpp

Rutinen finns också som skill: skriv `/slapp`.

1. Alla uppgifter i fasen är `KLAR` i [BACKLOG.md](../BACKLOG.md).
2. `npm run verify` (lint + typkontroll + prov) går igenom.
3. Migrationer som ingår är körda i **både dev och prod** och står i
   [databasandringar.md](databasandringar.md) med återställning.
4. Flytta posterna i `CHANGELOG.md` från `[Ej släppt]` till en ny versionsrubrik
   med datum.
5. Höj versionen i `package.json`.
6. Commit: `chore(release): v<version>`
7. Tagga: `git tag -a v<version> -m "<vad släppet innehåller>"`
8. Driftsätt enligt [driftsattning.md](driftsattning.md).

Taggen är återställningspunkten. Går något fel senare ska det alltid gå att gå
tillbaka till senaste taggen och veta exakt vad som fanns där — både i koden och i
databasen.

## Commit-meddelanden

Formatet är `<typ>(<omfång>): <beskrivning> [<uppgifts-ID>]`.

```
feat(schema): passloggning med förifyllda värden [F2-03]
fix(mat): felaktig summering över midnatt [F4-04]
db(schema): tabeller för träning [F0-04]
sec(webhook): tak för antal anrop per token [U-022]
```

**Typer:** `feat`, `fix`, `db` (migration), `refactor`, `test`, `docs`, `chore`,
`sec` (säkerhetsrättning).

Uppgifts-ID:t binder ihop kedjan: backlogg → commit → changelog → tagg. En rad kod
ska alltid gå att spåra till en uppgift, och en uppgift till ett beslut.

## Grenar (som i PE Portal, B-032/B-033 där)

- `main` = produktionen. Flyttas bara vid milstolpe (0.1.0, 0.2.0, 1.0.0) eller brådskande rättning, och släpps
  för hand med arbetsflödet **release** (skriv `SLAPP`).
- `dev` = dev-miljön. En push till `dev` kör verify och, när den är grön, läggs ut i dev automatiskt (`deploy-dev`).
- Uppgiftsgrenar `fas-<n>/<uppgifts-id>-<kort-namn>` grenas från `dev` och slås ihop dit (`--ff-only`) när verify
  är grön. **Uppgiftsgrenen hålls lokal** — bara `dev` laddas upp, så att varje uppgift ger en CI-körning.
- Brådskande rättningar grenas från `main` och slås sedan ihop även till `dev`.

```bash
git add <filer> && git commit -m "<typ>(<omfång>): <beskrivning> [<uppgifts-id>]"
git checkout dev && git merge --ff-only <uppgiftsgren> && git push origin dev && git branch -d <uppgiftsgren>
```

Commit-meddelanden skrivs **utan å/ä/ö**. Fråga systemägaren före commit och push.

## CI och utläggning

- `.github/workflows/verify.yml`: verify vid varje push och PR, databasen som tjänst, samma kommando som lokalt med
  kravet att databasproven körs. Jobbet `deploy-dev` körs bara vid push till `dev`, efter gröna prov, när variabeln
  `DEV_HOST` finns.
- `.github/workflows/release.yml`: `workflow_dispatch` från `main` med bekräftelsen `SLAPP`; prov → migrationer →
  kod → hälsokontroll (`/health`) → automatisk återgång till föregående version om något fallerar.
- Servern nås av GitHub som användaren `deploy`, låst till kommandona `status`/`deploy` (`command=` i
  authorized_keys). Ändras utläggningsskripten måste installationen köras om på servern.
- `concurrency` på utläggningsjobben. `.gitattributes` med `eol=lf` för `*.sh`, `*.service`, `*.conf`, `*.sql`, `*.yml`.
- Förlagor: `pe-portal/scripts/verify.py`, `.github/workflows/`, `deploy/` (ci_write_key.sh,
  install_deploy_access.sh, pe-deploy.sh, pe-deploy-root.sh).

## Regler som inte förhandlas

- **Committa aldrig hemligheter.** Blir en nyckel exponerad ska den **roteras**
  omedelbart — det räcker inte att ta bort den ur historiken.
- **Migrationer ändras aldrig i efterhand.**
- **Databasen före koden.** Alltid.
- **`main` taggas vid varje fasavslut**, även om ingenting driftsätts. Taggen är
  billig och är det enda som gör "gå tillbaka till hur det var" möjligt.
