# Leima — ohjeet Claude Codelle

## TREAD-workflowt (KRIITTINEN)

**ÄLÄ KOSKAAN** lisää `concurrency`-ryhmää `tread-run.yml`:ään.
Concurrency-ryhmä jonottaa ajot → jonoburstit → GitHub:n abuse-suojaus aktivoituu → kaikki scheduled cron-ajot pysähtyvät tunniksi.

**ÄLÄ KOSKAAN** muuta `tread-run.yml`:ää useita kertoja samassa sessiossa ilman että odotat että cron pyörii kunnolla välissä.

**ÄLÄ KOSKAAN** palauta `sys.exit(1)` `tread_check.py`:hyn tai "Fail if check failed" -steppiä `tread-run.yml`:ään.
Workflow täytyy aina exitata 0:lla — muuten GitHub passivoi scheduled-ajot.

## Git push — code review -seuranta (PAKOLLINEN)

Pushausohje (järjestys tärkeä):
1. **Kerro ensin yhteenveto** mitä tehtiin: mitkä tiedostot muuttuivat ja miksi. Muutama rivi riittää.
2. **Pushaa** (`git push origin staging` — kaikki muutokset menevät stagingiin, ei suoraan mainiin)
3. **Aseta ajastin 2 minuuttiin**: `gh run list --workflow code_review.yml --limit 1 --json databaseId,status,conclusion,headBranch`
4. Jos 2 min kuluttua ei valmista → tarkista **kerran lisää** 2 min päästä
5. Jos silloinkaan ei valmista → totea käyttäjälle että jokin meni pieleen ja ala tutkimaan (`gh run view <id> --log-failed`)

Jos completed:
- `success` → kerro että läpäisi ja mergautui mainiin
- `failure` → näytä virhe ja korjaa

## Muuta
- Puhu aina suomea käyttäjälle
