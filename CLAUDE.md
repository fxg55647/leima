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

## Git push — staging (PAKOLLINEN)

Pushausohje (järjestys tärkeä):
1. **Kerro ensin yhteenveto** mitä tehtiin: mitkä tiedostot muuttuivat ja miksi. Muutama rivi riittää.
2. **Pushaa** (`git push origin staging` — kaikki muutokset menevät stagingiin, ei suoraan mainiin)
3. **Odota käyttäjän pyyntöä** — staging-push ei itsessään käynnistä blokkavaa code reviewia. **Varsinainen code review tapahtuu vasta deploy.yml:n sisällä mergen yhteydessä.**

Huom: `code_review.yml` saattaa ajautua staging-pushista erillisenä ajona, mutta se ei ole merge-gate — älä odota sen webhookia ennen kuin käyttäjä pyytää deployta.

## Deploy tuotantoon (PAKOLLINEN)

**ÄLÄ KOSKAAN** deployaa mainiin ilman käyttäjän eksplisiittistä pyyntöä.

Kun käyttäjä pyytää deployta:
1. Aja `gh workflow run deploy.yml --repo fxg55647/leima`
2. Seuraa: `gh run watch $(gh run list --workflow deploy.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status`
3. Kerro käyttäjälle tulos

## Webhook-vastaanotto — SHA-tarkistus (PAKOLLINEN)

Webhook-arkkitehtuuri: `GHA → Hookdeck :8787 → webhook_proxy.py (HMAC-verify) → Claude :8788`
Viestit: `code_review_done` (success) ja `code_review_failed` (failure) — molemmat stagingista.

Kun saat webhook-viestin jossa on `sha`-kenttä:

1. **Aja** `python hooks/webhook_sha_check.py <sha>` — palauttaa JSON: `{"is_mine": bool, ...}`
2. **Reagoi tuloksen mukaan**:
   - `is_mine: true` + `code_review_failed` → näytä virhe, ala korjaamaan
   - `is_mine: true` + `code_review_done` → kerro käyttäjälle että läpäisi, kysy haluaako deployata
   - `is_mine: true` + `deploy_done` → kerro käyttäjälle että deploy valmis, uusi versio tuotannossa
   - `is_mine: true` + `deploy_failed` → näytä virhe
   - `is_mine: false` → jonkun muun push → kirjaa lokiin, älä häiritse käyttäjää
   - `push_log.json puuttuu` → tuntematon alkuperä → ilmoita lyhyesti

## Muuta
- Puhu aina suomea käyttäjälle
