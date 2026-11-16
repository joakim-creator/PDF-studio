# Lärdomar från tidigare bygge

Fullständig genomgång: **[Tysta fel](https://claude.ai/code/artifact/fcbe3573-d8a4-4637-90fe-b2943315f24f)**
— sjutton lärdomar från hälsoappsbygget, var och en förankrad i den defekt som lärde
ut den.

Läs den innan ett nytt projekt planeras. Det som följer här är sammandraget som
[CLAUDE.md](../CLAUDE.md) bygger på.

## Genomgående mönster

Av 56 rapporterade defekter var de dyraste de som **inte gav någon signal alls**.
Ingen krasch, inget rött i loggen — bara ett värde som såg rimligt ut och var fel.
Tjugo hittades av en människa i skarp användning, och de var genomgående de
allvarligaste.

Två slutsatser styr det mesta i mallen:

1. **Grönt betyder inte rätt.** Ett prov som aldrig setts falla bevisar ingenting.
2. **Skarp användning hittar det proven inte kan.** Få något användbart i händerna
   på en riktig användare tidigt, även om det är fult.

## Vaktprov

Regler som annars glöms bort skrivs som prov mot koden och schemat i stället för som
text i ett dokument. Under förra bygget fällde de återfall fyra gånger — varje gång
innan felet nådde produktion.

Sorter som visade sig löna sig:

| Vakt | Prövar |
|---|---|
| Schemavakt | Att migrationerna ger de kolumner och villkor koden förutsätter |
| Åtkomstvakt | Att var och en ser sitt eget och inte andras — med **rader i tabellen** |
| Raderingsvakt | Att raderingslistan täcker alla tabeller som finns i schemat |
| Konventionsvakt | Att namngivning och exportregler följs i hela kodbasen |

Den fjärde sorten är den billigaste och den mest underskattade. Ett prov som läser
källkoden och faller på ett namn som avviker kostar tjugo rader och sparar en
felsökning.

## Fällor som kostade mest

- **Åtkomstprov utan data** passerar i båda riktningarna och sover tyst. Seed-data
  i varje delad tabell är en förutsättning, inte en trevlighet.
- **Kod driftsatt före sin migration** tar ner produktionen direkt, och inget prov
  fångar det eftersom provmiljön redan har migrationen.
- **Prov som raderar andras testdata** går igenom på en tom databas och faller på en
  använd. Städa bara det du själv skapade — och städa både underliggande och
  härledda tabeller.
- **`git add -A`** committade produktionsnycklar. Nycklarna fick roteras och all
  åtkomst till produktionsdata gick förlorad.
- **Tvetydig indata** ledde till tre allt smartare gissare i rad, alla fel.
  Lösningen var en inställning i källan som gjorde gissandet onödigt.
- **Ett beroendes gränser** — storleksgräns, anropstak — räknades på först efter att
  rekommendationen redan var given.

## Lärdomar från PE Portal (2026-10)

Egengranskningen före lansering ([produktionsgranskning.md](produktionsgranskning.md)) av ett system som var
välbyggt — migrationer med återställning, åtkomstprov med rader, integrationslager med låtsasläge — hittade ändå
fyra P1 och ett tiotal P2. Alla var av samma sort: **sådant som inte syns förrän det är produktion**. De står som
krav i [backend-grund.md](backend-grund.md) och som uppgifter F0-10–F0-19 så att nästa system har dem från början.

- **Bakom Nginx ser appen bara 127.0.0.1.** Inloggningsspärren räknade hela bolaget som en klient — tio
  sidvisningar per minut hade låst ute alla. Hittades med en sond, inte med ett prov; nu finns provet.
- **Ingen felrapportering, inget larm, ingen hälsosida** — ett 500-fel hade synts först när en användare ringde.
  För ett bolag som felsöker med AI är loggen det enda underlaget: ärendenummer på varje anrop, GlitchTip, `/health`.
- **Backup utan provad återställning är inte backup.** Databasen hade leverantörens backup, filerna låg på samma
  server som tar-arkivet. Återställningsprovet är nu en rutin med datum.
- **"Bestäms senare" i GDPR-förteckningen** stod kvar vid lanseringen. En regel i kod (36 månader efter senaste
  aktivitet), en roll som beslutar och ett kommando för registerutdrag är det som gjorde det beslutsbart.
- **SQLite i proven upprätthöll inte främmande nycklar.** Att ta bort en inloggning gav 500 i PostgreSQL men gick
  igenom i proven; två prov raderade rader och lämnade föräldralösa barn utan att något föll.
- **`FOR UPDATE` uppdaterar inte ett redan inläst objekt** — den andra av två samtidiga faktureringar såg gammal
  status. Hittades av den oberoende granskaren, bekräftades med två trådar mot riktig PostgreSQL.
- **En utskrift som är en handling** (kontantfaktura) byggdes från registren vid utskriftstillfället. Fryses nu.
- **Radering kräver tillägg och loggas.** "Superuser" i spec:en hade blivit "skrivnivå" i koden utan att någon såg
  det.
- **Lokala konton med sex teckens lösenord och ingen andra faktor** — en känd öppen punkt som sköts framför sig.
- **Provsviten tog 13 minuter, och det var fixturen, inte proven.** Varje prov byggde hela schemat och seeden i en
  ny SQLite-fil. En mallfil som byggs en gång per körning och kopieras per prov gav 3 minuter — och det som kändes
  som "åtgärderna gjorde allt långsamt" visade sig vid mätning vara 15 % fler prov och två sessioner som körde
  verify samtidigt. Mät innan du gissar.
  TOTP i standardbiblioteket var en kvälls arbete; proven loggar in i två steg som i drift.
- **Två granskningar är bättre än en.** Den oberoende rapporten (äldre commit) och egengranskningen hittade olika
  saker; jämförelsen efteråt gav tre fynd till. Läs den andra rapporten först *efter* att egen är skriven.
- **Hemlighetsvakten läser proven också:** provvärden som liknar riktiga nycklar fälls. **Ett prov som lämnar rader
  i en delad databas** stör senare prov — städa i `finally`. **En egen transport till sentry-sdk måste ärva
  `Transport`**, annars går anropet ut på nätet tyst.
