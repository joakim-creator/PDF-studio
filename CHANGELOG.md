# Ändringslogg

Formatet följer [Keep a Changelog](https://keepachangelog.com/sv/1.1.0/) och
versionerna [semantisk versionering](https://semver.org/lang/sv/).

Varje post slutar med sitt uppgifts-ID från [BACKLOG.md](BACKLOG.md). Det är den
länken som gör det möjligt att svara på *varför* en rad finns.

Rubriker som används: `Tillagt`, `Ändrat`, `Rättat`, `Borttaget`, `Säkerhet`.

## [Ej släppt]

### Tillagt

- Projektmapp från Projektmallen med specifikation, backlogg för fas 0–7 och beslut B-001–B-005 [F0-01, F0-02]
- Flask-skelett med ärendenummer på varje anrop och `/health` [F0-03]
- Verify-skript (ruff, mypy, pytest) och CI i GitHub Actions [F0-09]
- Datamodell med databas per bolag, migrationer med låsta kontrollsummor och återställning [F0-04, F0-05]
- Åtkomstkontroll för dokument: egna och delade, radering kräver tillägg och loggas [F0-06]
- Seed i varje tabell, provfixtur från mallfil, schemaprov mot PostgreSQL och vaktprov [F0-07, F0-08, F0-19]
- En betrodd proxy och säkerhetshuvuden [F0-10, F0-17]
- Felsida med ärendenummer, `/health` mot alla databaser och tvättad felrapportering till GlitchTip [F0-11]
- Konton inaktiveras, tillägg delas ut uttryckligen och loggas [F0-14, F0-15]
- Radlås som läser om, och vaktprov för modulgränser [F0-17, F0-18]
- GDPR-förteckning, gallringsregel med torrkörning, beslut av GDPR-ansvarig och registerutdrag [F0-16]
- Inloggning med Microsoft och reservkonto (lösenord och engångskod), spärr, inloggningslogg och CSRF-skydd [F0-13]
- Ett inaktiverat konto tappar sin pågående session [F0-14]
- Kommandona `bolag-skapa` och `konto-skapa` [F0-13]
- Utläggning till dev och släpp till produktion: `deploy/`, jobbet `deploy-dev`, `release.yml`, bundna till den provade commiten [F0-20, F0-21]
- Kommandona `db-status`, `db-migrate` och `backup-dump` [F0-20]
- Fillagring lokalt och i Azure Blob Storage, uppladdning med kontroll av filtypen [F1-01, F1-02]
- Slå ihop, dela, rotera, ta bort och infoga sidor, och återställa en version — som nya versioner eller dokument [F1-05, F1-06, F1-07, F1-08]
- Startsidan enligt prototypen, dokumentvyn med miniatyrer och versioner, och sidorna Slå ihop och Dela [F1-03, F1-04]
- Sida i större format med zoom och bläddring, och sökning i dokumentens text [F1-04]
- Microsoft-inloggning för en organisation: med `ENTRA_TENANT_ID` godtas bara den katalogen (B-011) [F0-13]

### Rättat

- Samtidiga sidbilder kunde fälla servern: PDFium används nu bara under ett lås [U-001]
- Meddelandet "Logga in för att fortsätta" visas neutralt, inte som en bekräftelse [F0-13]

### Ändrat

- Modellerna har typade kolumner (`Mapped`); schemat är oförändrat [F0-17]
- Driften flyttas från Azure till DigitalOcean: dev bredvid PE Portal på `pe-portal-dev`, produktionen på egen droplet (B-010) [F0-20]
- Egen deploy-användare `pdfdeploy`, systemanvändare `pdfstudio` och port 8010, så att PDF-studio inte krockar med PE Portal på samma server [F0-20]
