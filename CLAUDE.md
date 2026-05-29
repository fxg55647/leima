# Leima — ohjeet Claude Codelle

## POIDE-workflowt (KRIITTINEN)

**ÄLÄ KOSKAAN** lisää `concurrency`-ryhmää `poide-run.yml`:ään.
Concurrency-ryhmä jonottaa ajot → jonoburstit → GitHub:n abuse-suojaus aktivoituu → kaikki scheduled cron-ajot pysähtyvät tunniksi.

**ÄLÄ KOSKAAN** muuta `poide-run.yml`:ää useita kertoja samassa sessiossa ilman että odotat että cron pyörii kunnolla välissä.

**ÄLÄ KOSKAAN** palauta `sys.exit(1)` `tread_check.py`:hyn tai "Fail if check failed" -steppiä `poide-run.yml`:ään.
Workflow täytyy aina exitata 0:lla — muuten GitHub passivoi scheduled-ajot.

## Git push — code review -seuranta (PAKOLLINEN)

Jokaisen `git push`:n jälkeen:
1. Hae uuden code review -ajon run ID: `gh run list --workflow code_review.yml --limit 1 --json databaseId`
2. Aseta yksi ScheduleWakeup 120s päähän promptilla:
   `Tarkista code review run [RUN_ID]: aja gh run view [RUN_ID] --json status,conclusion — jos status on completed kerro tulos käyttäjälle suomeksi. Jos ei vielä valmis, aseta uusi ScheduleWakeup 120s päähän samalla promptilla (max 4 kertaa yhteensä).`
3. Ketju jatkuu kunnes review valmis tai 8 min kulunut.

## Muuta
- Puhu aina suomea käyttäjälle
