# Leima — ohjeet Claude Codelle

## PoDe-workflowt (KRIITTINEN)

**ÄLÄ KOSKAAN** lisää `concurrency`-ryhmää `pode-run.yml`:ään.
Concurrency-ryhmä jonottaa ajot → jonoburstit → GitHub:n abuse-suojaus aktivoituu → kaikki scheduled cron-ajot pysähtyvät tunniksi.

**ÄLÄ KOSKAAN** muuta `pode-run.yml`:ää useita kertoja samassa sessiossa ilman että odotat että cron pyörii kunnolla välissä.

**ÄLÄ KOSKAAN** palauta `sys.exit(1)` `pode_check.py`:hyn tai "Fail if check failed" -steppiä `pode-run.yml`:ään.
Workflow täytyy aina exitata 0:lla — muuten GitHub passivoi scheduled-ajot.

## Muuta
- Puhu aina suomea käyttäjälle
