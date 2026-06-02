# Leima — ohjeet Claude Codelle

## TREAD-workflowt (KRIITTINEN)

**ÄLÄ KOSKAAN** lisää `concurrency`-ryhmää `tread-run.yml`:ään.
Concurrency-ryhmä jonottaa ajot → jonoburstit → GitHub:n abuse-suojaus aktivoituu → kaikki scheduled cron-ajot pysähtyvät tunniksi.

**ÄLÄ KOSKAAN** muuta `tread-run.yml`:ää useita kertoja samassa sessiossa ilman että odotat että cron pyörii kunnolla välissä.

**ÄLÄ KOSKAAN** palauta `sys.exit(1)` `tread_check.py`:hyn tai "Fail if check failed" -steppiä `tread-run.yml`:ään.
Workflow täytyy aina exitata 0:lla — muuten GitHub passivoi scheduled-ajot.

## SHA-eheys (KRIITTINEN)

**ÄLÄ KOSKAAN** pushaa suoraan `origin main`:iin.
**ÄLÄ KOSKAAN** käytä `git rebase` ennen merge-pushia.

Molemmat muuttavat SHA:n — TREAD ei löydä code review -ajoa uudelle SHA:lle → `unauthorized_deploy: true`.
Ainoa sallittu flow: `git push origin staging` → code review → workflow pushaa SHA:n sellaisenaan mainiin.

Jos staging on joskus jäljessä mainista (bootstrap-tilanne), se on merkki siitä että joku pushasi suoraan mainiin. Synkronoi käsin ja hyväksy kertaluonteinen danger — älä rebasea.

## Git push — code review -seuranta (PAKOLLINEN)

Pushausohje (järjestys tärkeä):
1. **Kerro ensin yhteenveto** mitä tehtiin: mitkä tiedostot muuttuivat ja miksi. Muutama rivi riittää.
2. **Pushaa** (`git push origin staging` — kaikki muutokset menevät stagingiin, ei suoraan mainiin)
3. **Aseta ajastin heti pushin jälkeen** — älä odota käyttäjän pyyntöä: `gh run list --workflow code_review.yml --limit 1 --json databaseId,status,conclusion,headBranch`
4. Jos 2 min kuluttua ei valmista → tarkista **kerran lisää** 2 min päästä
5. Jos silloinkaan ei valmista → totea käyttäjälle että jokin meni pieleen ja ala tutkimaan (`gh run view <id> --log-failed`)

Jos completed:
- `success` → kerro että läpäisi ja mergautui mainiin
- `failure` → näytä virhe ja korjaa

## Webhook-vastaanotto — SHA-tarkistus (PAKOLLINEN)

Webhook-arkkitehtuuri: `GHA → Hookdeck :8787 → webhook_proxy.py (HMAC-verify) → Claude :8788`
Viestit: `code_review_done` (success) ja `code_review_failed` (failure) — molemmat stagingista.

Kun saat webhook-viestin jossa on `sha`-kenttä:

1. **Aja** `python hooks/webhook_sha_check.py <sha>` — palauttaa JSON: `{"is_mine": bool, ...}`
2. **Reagoi tuloksen mukaan**:
   - `is_mine: true` + `code_review_failed` → näytä virhe, ala korjaamaan
   - `is_mine: true` + `code_review_done` → kerro käyttäjälle että läpäisi ja mergautui mainiin
   - `is_mine: false` → jonkun muun push → kirjaa lokiin, älä häiritse käyttäjää
   - `push_log.json puuttuu` → tuntematon alkuperä → ilmoita lyhyesti

## Muuta
- Puhu aina suomea käyttäjälle
