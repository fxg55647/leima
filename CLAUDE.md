# Leima — ohjeet Claude Codelle

## POIDE-workflowt (KRIITTINEN)

**ÄLÄ KOSKAAN** lisää `concurrency`-ryhmää `poide-run.yml`:ään.
Concurrency-ryhmä jonottaa ajot → jonoburstit → GitHub:n abuse-suojaus aktivoituu → kaikki scheduled cron-ajot pysähtyvät tunniksi.

**ÄLÄ KOSKAAN** muuta `poide-run.yml`:ää useita kertoja samassa sessiossa ilman että odotat että cron pyörii kunnolla välissä.

**ÄLÄ KOSKAAN** palauta `sys.exit(1)` `tread_check.py`:hyn tai "Fail if check failed" -steppiä `poide-run.yml`:ään.
Workflow täytyy aina exitata 0:lla — muuten GitHub passivoi scheduled-ajot.

## Git push — code review -seuranta (PAKOLLINEN)

Jokaisen `git push`:n jälkeen käynnistä `/loop` 2 minuutin välein:
- Hae uusin code review run: `gh run list --workflow code_review.yml --limit 1 --json databaseId,status,conclusion`
- Jos completed → kerro tulos käyttäjälle suomeksi → lopeta loop (älä aseta uutta ajastinta)
- Jos ei valmis ja alle 8 min kulunut pushista → jatka loopia
- Jos 8 min kulunut → kerro timeout → lopeta loop

## Muuta
- Puhu aina suomea käyttäjälle
