# Databasändringar

Register över samtliga migrationer. **Varje migration ska ha en dokumenterad
återställning innan den körs skarpt.** Det är den här filen som gör det möjligt att
svara på "vad hände med databasen den 14:e" utan att gissa.

Migrationsfilerna namnges `<tidsstämpel>_<beskrivning>.sql` och **ändras aldrig efter
att de körts skarpt** — fel rättas med en ny migration.

## Ordningen som gäller

1. Skriv migrationen.
2. Skriv återställningen och fyll i raden i registret nedan.
3. Kör mot **dev**.
4. Kör mot **prod**.
5. Först därefter slås koden som förutsätter ändringen ihop till `main`.

Steg 5 är inte en formalitet. Kod som läser en kolumn som ännu inte finns tar ner
produktionen direkt, och felet syns inte i något prov — provmiljön har redan
migrationen.

Kontrollera alltid vilken miljö som är länkad innan något körs.

## Register

Migrationerna körs med `core/migrations.py`, som vägrar köra en migration utan
`.down.sql`, stoppar om en körd migration har ändrats och låser varje fil i
`migrations/checksums.txt` (vaktprov i `tests/test_vakt.py`).

| Migration | Uppgift | Innehåll | Körd i dev | Körd i prod | Återställning |
|---|---|---|---|---|---|
| master/202611162200_baslinje | F0-04 | Bolagsregistret `tenants` | – | – | R-001 |
| tenant/202611162200_baslinje | F0-04, F0-05 | Användare, tillägg, dokument, versioner, delningar, kommentarer, jobb, AI-kostnader, händelselogg | – | – | R-002 |
| tenant/202611170200_inloggning | F0-13 | Inloggningsloggen `login_events`; `users.totp_enabled_at`, `users.last_login_at` | – | – | R-003 |

## Återställningar

**R-001** — master/202611162200_baslinje

```sql
DROP TABLE tenants;
```

Inga bolag går att slå upp; appen kan inte välja databas för någon inloggning.
Återställs bara på en databas utan bolag (dev innan första bolaget lagts in).

**R-002** — tenant/202611162200_baslinje

```sql
DROP TABLE ai_usage;
DROP TABLE jobs;
DROP TABLE annotations;
DROP TABLE document_versions;
DROP TABLE document_shares;
DROP TABLE user_permissions;
DROP TABLE documents;
DROP TABLE audit_events;
DROP TABLE users;
```

Tar bort allt i bolagets databas. Får bara köras på en bolagsdatabas utan
riktiga dokument. Ta backup först, och kontrollera att det är dev.

**R-003** — tenant/202611170200_inloggning

```sql
DROP TABLE login_events;
ALTER TABLE users DROP COLUMN last_login_at;
ALTER TABLE users DROP COLUMN totp_enabled_at;
```

Inloggningsloggen försvinner, och alla lokala konton måste registrera engångskoden på
nytt. Koden från F0-13 måste tas tillbaka först, annars fallerar inloggningen.
