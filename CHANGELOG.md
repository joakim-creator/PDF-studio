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

### Ändrat

- Modellerna har typade kolumner (`Mapped`); schemat är oförändrat [F0-17]
