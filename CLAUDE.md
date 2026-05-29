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
2. Aseta **kolme ScheduleWakeup-ajastinta**: 120s, 240s ja 360s, kaikki samalla promptilla:
   `Tarkista code review run [RUN_ID]: gh run view [RUN_ID] --json status,conclusion — jos completed, kerro tulos käyttäjälle. Jos ei vielä valmis, pysy hiljaa.`
3. Kun ajastin laukeaa ja review on valmis, kerro käyttäjälle tulos. Muut ajastimet laukeavat myös mutta pysyvät hiljaa jos review jo valmis.

## Muuta
- Puhu aina suomea käyttäjälle
