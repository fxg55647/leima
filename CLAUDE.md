# Leima — ohjeet Claude Codelle

## POIDE-workflowt (KRIITTINEN)

**ÄLÄ KOSKAAN** lisää `concurrency`-ryhmää `poide-run.yml`:ään.
Concurrency-ryhmä jonottaa ajot → jonoburstit → GitHub:n abuse-suojaus aktivoituu → kaikki scheduled cron-ajot pysähtyvät tunniksi.

**ÄLÄ KOSKAAN** muuta `poide-run.yml`:ää useita kertoja samassa sessiossa ilman että odotat että cron pyörii kunnolla välissä.

**ÄLÄ KOSKAAN** palauta `sys.exit(1)` `poide_check.py`:hyn tai "Fail if check failed" -steppiä `poide-run.yml`:ään.
Workflow täytyy aina exitata 0:lla — muuten GitHub passivoi scheduled-ajot.

## Muuta
- Puhu aina suomea käyttäjälle
