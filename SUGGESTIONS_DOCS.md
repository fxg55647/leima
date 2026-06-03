## POLICY.example.md

- "Where your document goes" — States "Neither is stored permanently by Leima" early on, but later documents that the email notary flow permanently stores sender address, recipient, and subject to Arweave. Should clearly mark the email notary as an exception to this rule.

## README.md

- Setup section — Uses `stamp@yourdomain.com` as a template (correct), but USECASES.md hardcodes `stamp@leima.fi` in examples. Readers may think they must use the leima.fi address.

## USECASES.md

- Email notary section — Hardcodes `stamp@leima.fi` as the example address. Should use a generic template like `stamp@yourdomain.com` to match README.md setup instructions.

## .env.example

- Line 7 — Uses "PoDe" as a comment but all other files use "POIDE". Should be standardised to "POIDE".

---

## DEPLOY.md

*Päivitettävä — nykytilanne muuttunut 2026-06-02*

- **Yleiskuva ja vaihe 1** — Kuvaa edelleen pushin suoraan `main`-haaraan. Todellinen flow on `staging` → code review → automaattinen merge mainiin. Korjattava vastaamaan todellisuutta.

- **Staging-arkkitehtuuri puuttuu kokonaan** — Lisättävä kuvaus siitä että staging-haara on kehittäjän työskentelyalue ja main on "hyväksytty, tuotantovalmis". Push stagingiin ei deployta automaattisesti — vaatii erillisen hyväksynnän.

- **Render poistettu** — Versiohistoriaan merkintä 2026-06-02: dispatcher-säie poistettu, Vercel cron `* * * * *` (joka minuutti) korvaa sen. GitHub secrets poistettava: `RENDER_API_KEY`, `RENDER_SERVICE_ID`, `RENDER_DEPLOY_HOOK`.

- **Suunnitteilla: staging-palvelin** — Erillinen staging-ympäristö (Vercel preview tai oma) jonne voi pushata vapaasti ilman TREAD-valvontaa. Tuotantodeploy on eksplisiittinen erillinen toimenpide.

- **Suunnitteilla: pre-deploy signal** — Ennen tuotantodeployta `code_review.yml` lähettää signaalin Leiman `/api/pre-deploy`-endpointiin. Leima tallentaa tämän KV:hen (TTL 10 min). Jos `p.ok === false` mutta signaali löytyy → ei varoitusta käyttäjälle. Ratkaisee TREAD-false alarm -ongelman deploy-ikkunassa.

## TREAD-turvaketju (client-side verification)

- **Selain itsenäisenä todistajana** — Harkitaan arkkitehtuurimuutosta jossa selain tallentaa localStorageen: (1) SHA kun `deploy_incoming` havaitaan, (2) "review valmis tälle SHA:lle" kun code_review.yml päättyy, (3) tarkistaa deployn alkaessa että deploying_commit == odotettu SHA && review kirjattu. Vaatii uuden `review_completed_sha`-kentän `/tread-monitor`-vastaukseen. Lisäksi `main.py` pitäisi lisätä `MONITOR_FILES`-listaan jotta serverin vastauksia ei voi väärentää huomaamatta.

## templates/index.html (TREAD-varoituslogiikka)

- **Auto-clear toteutettu 2026-06-02** — Kun `p.ok` palaa `true`:ksi, `leima_tread_mismatch` -LocalStorage-lippu poistetaan automaattisesti. Käyttäjä ei enää näe vanhentunutta varoitusta. Dokumentoi tämä käyttäytyminen TREAD.md:hen tai vastaavaan.
