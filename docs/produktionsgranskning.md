# Styrdokument: Produktionsgranskning före lansering

> Detta dokument styr hur Claude Code ska granska hela kodbasen innan vi går live.
> Läs det i sin helhet innan du gör något. Följ faserna i ordning. Generell version (från PE Portal 2026-10-17);
> projektets egna regler i avsnitt 0 anpassas per projekt.

---

## 0. Projektets egna regler gäller först

Det här dokumentet är en generell granskningsmall. I varje projekt gäller följande före allt annat:

1. **`CLAUDE.md`** i repots rot — reglerna som inte förhandlas, arbetssätt, grenmodell, commit-format och
   arbetssätt mot servrarna går före detta dokument vid konflikt.
2. **Provning:** kör projektets verify-kedja (lint + typkontroll + prov). Prov som kräver en riktig databas körs
   mot den (aldrig hoppas över tyst) — prov som hoppas över räknas som ej körda och ska redovisas.
3. **Nivåer och bevisstatus:** P0 = Kritisk, P1 = Hög, P2 = Medel, P3 = Låg. Ange bevisstatus per fynd:
   *verifierat*, *indikation* eller *ej bedömt*.
4. **Rapporten sparas i `docs/granskning/`** som `EGENGRANSKNING-<datum>.md`, med `Granskning\RAPPORTMALL.md` som
   utgångspunkt. Där dokumentet nedan säger `GRANSKNINGSRAPPORT.md` menas den filen.
5. **Inga ändringar i Fas 1–3** (se grundreglerna) och **ingen commit eller push utan att systemägaren godkänt** —
   i åtgärdsfasen gäller projektets commit-format och uppgiftsgrenar från utvecklingsgrenen, **en åtgärd per
   commit**, varje ny vakt sedd falla före rättningen, verify grön före ihopslagning.
6. **Serverkommandon kör systemägaren själv.** Granska och testa bara lokalt eller mot dev-miljön med påhittade data.
   Belastningstest och skarpa anrop mot externa tjänster görs aldrig utan uttryckligt mandat.
7. **Läs [backend-grund.md](backend-grund.md) först** — det är listan över vad som ska finnas från början; granskningen
   kontrollerar att det finns och fungerar, inte bara att det är beskrivet.
8. **Jämför med en oberoende granskning** när en sådan finns, först *efter* att egen rapport skrivits (så att de två
   kan jämföras), och för in skillnaderna som ett avsnitt i rapporten: vilka fynd som kvarstår, vilka som är
   åtgärdade, vilka som tas in.

---

## 1. Syfte och roll

Systemet är ett modulärt affärssystem (CRM först, därefter uthyrning, verkstad, planering m.fl.) som har byggts under ca en månad. Det har vuxit snabbt och ska nu lanseras i produktionsmiljö.

**Din roll:** oberoende granskare och arkitekt. Du ska inte bara hitta fel, du ska bedöma om grunden håller för att bygga vidare på, och vad som måste byggas om eller ordnas *före* lansering.

**Målet är ett beslutsunderlag:** Go / Go med villkor / No-Go, baserat på bevis i koden.

---

## 2. Grundregler (gäller hela granskningen)

1. **Fas 1–3 är skrivskyddade.** Ändra ingen kod, inga migrationer och ingen konfiguration förrän granskningsrapporten är levererad och jag har godkänt åtgärdsplanen.
2. **Bevisa, anta inte.** Varje fynd ska ha fil, rad/funktion och en kort förklaring. Skriv "ej verifierat" i stället för att gissa.
3. **Kör faktiskt saker.** Kör tester, bygge, lint, typkontroll, beroendeskanning och migrationer mot en tom testdatabas. Rapportera exakta kommandon och utfall.
4. **Rör aldrig produktionsdata eller produktionshemligheter.** Använd bara lokal/test-miljö. Om du hittar hemligheter i koden: rapportera plats, men skriv aldrig ut värdet.
5. **Var rak.** Överdriv inte och släta inte över. Säg tydligt vad som är bra och vad som är farligt.
6. **Skriv på svenska** i rapporten. Kod, filnamn och tekniska termer får vara på engelska.
7. **Fråga när något är oklart** i affärslogik (t.ex. prisregler, behörighet, regelverk) i stället för att tolka fritt.

---

## 3. Arbetsgång

### Fas 0 – Orientering
- Läs README, befintliga CLAUDE.md, ADR:er och dokumentation.
- Kartlägg repostruktur, moduler, tjänster, databaser och externa beroenden.
- Lista tech stack och versioner.
- Skapa en **modulkarta**: vilka moduler finns, vad äger varje modul, vilka beroenden går mellan dem.
- Notera vad som är live redan (t.ex. CRM) respektive vad som är under uppbyggnad.

### Fas 0b – Beslut som måste vara fattade
Vissa beslut avgör hur alla kommande moduler (uthyrning m.fl.) hänger ihop. **Du fattar inte
dessa beslut.** Du kontrollerar att de finns i `docs/Freja/beslutslogg.md` och att koden följer
dem. Saknas ett beslut: lägg det under "Öppna frågor" med 2–3 alternativ och deras konsekvenser
i stället för att välja. Ett fattat beslut ändras inte i efterhand, det ersätts av ett nytt.

Kontrollera i den här ordningen (det som påverkar kommande moduler mest först):

1. **Ägarskap för kundregister, tillgångar och reservationer.** För varje entitet: vilken modul
   äger den, vilka får skriva, och hur refererar andra moduler till den (via ID och
   gränssnitt, aldrig via direktåtkomst till tabellen). Kundregistret är beslutat i B-027
   (gemensamt register, Fortnox master): verifiera att koden följer det, d.v.s. att ingen modul
   har ett eget kundregister vid sidan av. Kontrollera särskilt om maskiner/fordon och
   reservationer har en dokumenterad ägare.
2. **Bolags- och behörighetsmodell.** Bolag (databas per bolag), depå som dimension (B-022),
   roller och modulåtkomst (H-04 är inte byggd: bedöm risken i det som lanseras), vad som följer
   av `is_admin` och vad som aldrig gör det (HR).
3. **Gränsen mellan konfiguration och kod.** Vilka egna fält, dokument- och checklistmallar,
   prispåslag och arbetsflöden som får konfigureras per bolag, och hur konfigurationen
   valideras, versionshanteras och spåras (vem ändrade, kan den rullas tillbaka, påverkar den
   redan skapade ordrar?). Jämför med det som finns i dag (t.ex. standardmallar, prispåslag
   per kategori).

Väg bristen mot det som faktiskt lanseras (se modultabellen i CLAUDE.md). Ett ofattat beslut om
uthyrning blockerar inte lansering av Freja, men ska vara fattat innan nästa modul byggs.

### Fas 1 – Arkitektur och modulgränser
Granska mot principen *modulär monolit med strikta gränser*:

- [ ] Äger varje modul sina egna tabeller/schema? Finns det moduler som läser eller skriver direkt i andra modulers tabeller?
- [ ] Finns cirkulära beroenden mellan moduler?
- [ ] Är delade entiteter (kunder, kontakter, användare, maskiner/assets) ägda av en tydlig kärna, och refereras de via ID?
- [ ] Kommunicerar moduler via definierade gränssnitt eller händelser, eller via "genvägar"?
- [ ] Är affärsregler (prissättning, bokningsregler, statusövergångar) samlade i domänlagret, eller utspridda i controllers/UI?
- [ ] Är statusflöden uttryckta som tydliga tillståndsmaskiner med tillåtna övergångar?
- [ ] Är priser, avtalsvillkor och regler **data**, inte hårdkodade konstanter?
- [ ] Är det möjligt att lägga till nästa modul (t.ex. uthyrning, verkstad) utan att röra CRM-koden? Testa tankeexperimentet konkret.
- [ ] Dubblerad logik eller dubblerade datamodeller mellan moduler?
- [ ] **Modulgränserna kontrolleras automatiskt**, inte bara genom mappstruktur. Finns ett vaktprov
  eller verktyg (t.ex. ett prov i `tests/` eller import-linter) som fäller en otillåten import
  mellan moduler, och som fäller om `app.py` importerar en enskild modul? Lista alla faktiska
  beroenden mellan `modules/*` och vilka som går via `core/`. Pröva vakten genom att
  tillfälligt bryta regeln i en scratch-kopia och se att den faller (grönt betyder inte rätt).
- [ ] Är konfiguration (egna fält, mallar, prispåslag, arbetsflöden) skild från kod enligt
  besluten i Fas 0b, och är den validerad och versionshanterad?

### Fas 2 – Data och databas
- [ ] Finns versionshanterade migrationer? Går hela migrationskedjan att köra från tom databas till nuvarande schema utan fel?
- [ ] Är migrationerna reversibla eller har de en dokumenterad återställningsplan?
- [ ] Främmande nycklar, unika villkor, NOT NULL och CHECK-villkor där det behövs?
- [ ] Index på de kolumner som filtreras, sorteras och joinas på. Hitta troliga N+1-frågor.
- [ ] Hantering av tid: tidszoner, `timestamptz`, konsekvent lagring (UTC).
- [ ] Pengar och mängder lagras exakt (inte flyttal). Valuta och moms hanteras tydligt.
- [ ] Dubbelbokningsrisk: förhindras konflikter på databasnivå (t.ex. exclusion constraints) eller bara i applikationskoden?
- [ ] Soft delete och historik på affärsdata. Finns audit-logg över vem som ändrade vad och när?
- [ ] **Multi-tenancy:** om systemet ska användas av flera bolag/regioner, finns `tenant_id`/regionsavgränsning och Row Level Security, eller risk för dataläckage mellan kunder?
- [ ] Seed-data och testdata är åtskilda från produktionsdata.
- [ ] Plan för backup, återställning och kvarhållning. Är återställning faktiskt testad?

### Fas 3 – Säkerhet och behörighet
- [ ] Autentisering: standardlösning (OIDC/OAuth2) eller hemmabyggt? Lösenordshantering, sessioner, token-livslängd, utloggning.
- [ ] **Behörighet kontrolleras i backend på varje endpoint**, inte bara i gränssnittet. Gå igenom *samtliga* endpoints och lista de som saknar kontroll.
- [ ] Roller (RBAC) och eventuell regionsbaserad åtkomst (Sthlm/Väst/Syd/Nord). Testa att en användare inte kan nå en annan regions eller annans kunds data genom att byta ID (IDOR).
- [ ] Indatavalidering på alla inkommande data. Skydd mot SQL-injektion, XSS, CSRF, SSRF, path traversal och osäker filuppladdning.
- [ ] Hemligheter: inga nycklar, lösenord eller tokens i koden, i git-historiken, i loggar eller i klientkod. Kontrollera `.env`-hantering.
- [ ] CORS, säkerhetshuvuden, HTTPS-krav, cookie-flaggor, rate limiting och skydd mot brute force.
- [ ] Separata tjänstekonton/API-nycklar för integrationer och AI-agenter, med minsta möjliga rättigheter.
- [ ] Beroenden: kör beroendeskanning (t.ex. `npm audit`, `pip-audit` eller motsvarande). Lista kända sårbarheter och föråldrade paket.
- [ ] Felmeddelanden läcker inte stacktrace, SQL eller interna detaljer till användaren.
- [ ] Känsliga fält (personuppgifter, priser, avtal) är skyddade och loggas inte i klartext.

### Fas 4 – API och integrationer
- [ ] Konsekvent API-design: namngivning, felformat, statuskoder, paginering, filtrering, sortering.
- [ ] API-versionering. Finns OpenAPI-spec och stämmer den med verkligheten?
- [ ] Idempotens på skapa-anrop som kan dubbleras (bokningar, fakturor, betalningar).
- [ ] Integrationer (ekonomisystem, e-post, externa API:er) ligger bakom ett eget lager så att externa datamodeller inte läcker in i vår.
- [ ] Återförsök, timeout, felhantering och köhantering för långsamma eller opålitliga anrop. Webhooks är signerade.
- [ ] Händelser mellan moduler: finns outbox eller liknande så att händelser inte tappas vid fel?
- [ ] Import/export (CSV/Excel) fungerar och validerar data.

### Fas 5 – Kodkvalitet och underhållbarhet
- [ ] Kör bygge, lint och typkontroll. Rapportera antal fel och varningar.
- [ ] Död kod, oanvända filer, kommenterad kod, kvarglömda TODO/FIXME och debug-utskrifter.
- [ ] Duplicerad kod som bör bli delade komponenter. Filer eller funktioner som är orimligt stora.
- [ ] Konsekvent namngivning, mappstruktur och kodstil över modulerna. (Snabb utveckling ger ofta olika "dialekter" mellan veckor.)
- [ ] Felhantering: inga tomma catch-block, inga tysta fel, tydliga felklasser.
- [ ] Konfiguration separerad per miljö (dev/test/prod). Inga hårdkodade URL:er, portar eller ID:n.
- [ ] Dokumentation: README, hur man kör lokalt, miljövariabler, arkitekturöversikt och beslutslogg.

### Fas 6 – Tester och kvalitetssäkring
- [ ] Kör hela testsviten. Rapportera: antal tester, passerar/fallerar, flaky tester.
- [ ] Mät täckning, men värdera framför allt *vad* som är testat. Är affärskritisk logik täckt (priser, bokningsregler, behörighet, statusövergångar)?
- [ ] Finns integrationstester mot riktig databas? End-to-end-test för de viktigaste flödena?
- [ ] Testa kantfall: tomma värden, mycket stora data, specialtecken (åäö), tidszonsbyten, samtidiga anrop.
- [ ] Testa att migrationer fungerar både på tom databas och på databas med data.

### Fas 7 – Drift och produktionsberedskap
- [ ] CI/CD: automatisk test, bygge, migrering och deploy. Går det att rulla tillbaka en release?
- [ ] Separata miljöer (dev/test/prod) med egna databaser och hemligheter.
- [ ] Observability: strukturerade loggar, trace-ID, felrapportering, mätvärden, larm och hälsokontroller (health/readiness).
- [ ] Prestanda: identifiera långsamma frågor och tunga endpoints. Grundläggande belastningstest på de mest kritiska flödena.
- [ ] Hantering av bakgrundsjobb och köer: återförsök, dead-letter, övervakning.
- [ ] Filhantering via objektlagring, inte i databasen. Backup av filer.
- [ ] Skalning och resurser: vad händer vid 10x användare eller data?
- [ ] Plan för driftsättning: datamigrering, nedtid, rollback, kommunikation till användare.

### Fas 8 – Regelefterlevnad (GDPR och ISO)
Vi arbetar mot ISO 9001, 14001 och 45001, så spårbarhet är viktigt.

- [ ] GDPR: kartläggning av var personuppgifter lagras, dataminimering, raderingsrutin, exportmöjlighet, loggning av åtkomst till personuppgifter.
- [ ] Audit-logg och spårbarhet: går det att visa vem som gjorde vad, när och varför på affärskritisk data?
- [ ] Versionshistorik på dokument, avtal och priser.
- [ ] Kan systemet stödja avvikelsehantering, förbättringsförslag och dokumentstyrning som ISO-processerna kräver?
- [ ] Behörighetsloggning och möjlighet att visa behörighetsstruktur vid revision.

### Fas 9 – Användbarhet och funktionell fullständighet
- [ ] Gå igenom de verkliga kärnflödena från användarens sida (t.ex. lead → offert → avtal; maskin → uthyrning → retur → service → tillgänglig).
- [ ] Brutna flöden, döda länkar, halvfärdiga sidor, funktioner som ser klara ut men inte är det.
- [ ] Felmeddelanden och tomtillstånd som är begripliga på svenska.
- [ ] Tillgänglighet och fungerande layout på mobil/surfplatta (verkstad och fält).
- [ ] Prestanda i gränssnittet vid stora listor.

---

## 4. Allvarlighetsnivåer

| Nivå | Betydelse | Krav |
|---|---|---|
| **P0 – Blockerare** | Säkerhetshål, dataförlust, dataläckage mellan kunder, trasig kärnfunktion, ej återställningsbar migration | Måste åtgärdas före lansering |
| **P1 – Hög** | Allvarlig risk eller stor teknisk skuld som snart ger problem (saknad behörighetskontroll på enstaka endpoint, avsaknad av backup-test, avsaknad av tester på kritisk logik) | Bör åtgärdas före lansering, annars dokumenterad risk och datum |
| **P2 – Medel** | Försämrar underhåll eller kvalitet, men blockerar inte | Planeras in efter lansering |
| **P3 – Låg** | Kosmetiskt, förbättringsförslag | Backlog |

Ombyggnad ska bara föreslås som "måste före lansering" när det är en P0/P1-risk. Allt annat ska prioriteras bort från lanseringsvägen så att vi inte bygger om i onödan.

---

## 5. Rapportformat (leverabel för Fas 1–9)

Skapa filen `GRANSKNINGSRAPPORT.md` med följande struktur:

1. **Sammanfattning (max en halv sida)**
   - Helhetsbedömning: Go / Go med villkor / No-Go
   - De 5 viktigaste fynden
   - Vad som är bra och bör bevaras
2. **Modulkarta och arkitekturöversikt** (text, gärna Mermaid-diagram)
3. **Fynd per fas.** För varje fynd:
   - ID (t.ex. `SEC-03`), allvarlighet (P0–P3)
   - Beskrivning och *bevis* (fil, rad/funktion, kommando)
   - Konsekvens om det inte åtgärdas
   - Rekommenderad åtgärd och uppskattad insats (S/M/L)
4. **Resultat från körningar:** bygge, lint, typer, tester, beroendeskanning, migrationstest
5. **Ombyggnadsbehov:** vad behöver strukturellt byggas om, varför, och vad händer om det inte görs
6. **Åtgärdsplan:** prioriterad lista i tre block: *Före lansering (P0/P1)*, *Direkt efter lansering (P2)*, *Backlog (P3)*
7. **Öppna frågor till mig:** sådant du inte kunde avgöra utan affärskunskap
8. **Go-live-checklista:** konkreta punkter som ska vara gröna innan lansering

---

## 6. Efter godkännande: åtgärdsfasen

När jag har godkänt åtgärdsplanen:

1. Arbeta i **små, separata ändringar**, en åtgärd (ett fynd-ID) per commit/PR, med tydligt meddelande.
2. Skriv eller uppdatera tester *innan eller tillsammans med* ändringen, särskilt för P0/P1.
3. Kör hela testsviten, lint och bygge efter varje ändring. Gå inte vidare om något är rött.
4. Ändra aldrig befintliga migrationer som redan körts i någon miljö. Skapa nya.
5. Bryt aldrig bakåtkompatibilitet i API:er som används av live-system (t.ex. CRM) utan att flagga det först.
6. Uppdatera dokumentationen när något ändras.
7. Rapportera status per fynd-ID: *åtgärdad / delvis / skjuten med motivering*.
8. Gör en avslutande **omkörning av Fas 3 och Fas 6** som verifiering och uppdatera rapporten.

---

## 7. Go-live-kriterier (minimikrav)

Systemet får inte lanseras förrän följande är uppfyllt:

- [ ] Inga öppna P0-fynd. P1-fynd är åtgärdade eller har dokumenterad, godkänd risk.
- [ ] Alla endpoints har verifierad behörighetskontroll i backend.
- [ ] Inga hemligheter i kod eller git-historik.
- [ ] Migrationer körs rent från tom databas och är testade på kopia av data.
- [ ] Backup finns och återställning är testad.
- [ ] Testsviten är grön och täcker de kritiska flödena.
- [ ] Bygge och driftsättning är automatiserade, och rollback är beprövad.
- [ ] Loggning, felrapportering och larm är på plats.
- [ ] Dataisolering mellan kunder/regioner är testad.
- [ ] GDPR-grunderna (kartläggning, radering, åtkomstloggning) är uppfyllda.
- [ ] Dokumentation för drift och felsökning finns.

---

## 8. Så startar du

1. Läs hela detta dokument.
2. Börja med Fas 0 och presentera modulkartan för mig kort innan du går vidare.
3. Gå igenom Fas 1–9. Håll koll på tiden: om en fas visar sig mycket omfattande, rapportera det och föreslå uppdelning i stället för att hoppa över delar.
4. Leverera `GRANSKNINGSRAPPORT.md` och vänta på mitt godkännande innan du ändrar något.
