# Leiman tietoturvamalli

Tämä dokumentti kuvaa Leiman valvonta-arkkitehtuurin, kunkin komponentin suojausominaisuudet ja tunnistetut haavoittuvuudet. Perustuu rakenteen suunnittelukeskusteluihin.

Viimeksi päivitetty: 2026-05-29

---

## Uhkamallit

Kolme hyökkääjätyyppiä, joita vastaan järjestelmä on suunniteltu:

| Tyyppi | Pääsy | Uhkataso |
|---|---|---|
| **Ulkoinen hyökkääjä** | Ei GitHub- eikä Render-pääsyä | Matala |
| **Osittainen hyökkääjä** | GitHub TAI Render, ei molempia | Keskisuuri |
| **Ylläpito-hyökkääjä** | GitHub JA Render | Korkea |

---

## Komponentit ja niiden suojaus

### 1. TREAD-cronit (tread-a.yml … tread-e.yml) + tread_check.py

Viisi identtistä GitHub Actions -workflow'ta, jotka ajavat `tread_check.py`:n vuorotellen minuutin välein. Jokainen ajo:
- Tarkistaa vastaako hosting-palvelussa pyörivä commit GitHubin main-branchia
- Tarkistaa että kaikki viisi TREAD-workflow'ta ovat aktiivisena
- Laskee SHA-256-hashit kaikista valvontatiedostoista — siis myös itsestään (`tread_check.py`)
- Kirjoittaa tuloksen `status.json`:iin GitHub Pagesiin
- Arkistoi tuloksen Arweave-lohkoketjuun pysyvästi

Viiden erillisen workflow:n redundanssi suojaa yksittäisen workflown passivoitumiselta — kaikki viisi täytyy sammuttaa samanaikaisesti, muuten valvonta jatkuu.

**Voiko tread_check.py:n muokata samalla hetkellä kuin muut valvontatiedostot?**
Kyllä — teknisesti hyökkääjä voi muokata kaikkia tiedostoja yhdessä commitissa. Mutta tämä ei auta:

- `tread_check.py` on itse valvottavien tiedostojen listalla
- Jos sen git blob SHA muuttuu, sekä Tampermonkey että dispatcher havaitsevat sen ~1–3 min sisällä
- Vaikka muokattu `tread_check.py` kirjoittaisi vääriä hasheja status.json:iin, se ei vaikuta Tampermonkeyn eikä dispatcherin tarkistukseen — molemmat hakevat git tree:n suoraan GitHubista, ei status.json:sta
- Kaikki muutokset näkyvät git-historiassa pysyvästi

Hyökkääjä ei siis pysty muokkaamaan `tread_check.py`:tä "hiljaisesti" — sen hash muuttuu välittömästi ja hälytys laukeaa.

**Haavoittuva:**
- Kompromisoitu `tread_check.py` voi kirjoittaa vääriä hasheja status.json:iin
- GitHub Actions itsessään on luotettu osapuoli — jos GitHub on kompromisoitu, koko järjestelmä pettää

**Miten TREAD-cronit voidaan yrittää sammuttaa — ja miten siitä jää kiinni:**

| Tapa | Nopeus | Kuka huomaa | Mistä |
|---|---|---|---|
| Poistaa kaikki 5 workflow'ta käytöstä GitHub-UI:ssa | Välitön | TREAD-palkki | `tread_check.py` tarkistaa workflow-tilat → `disabled_workflows` → Danger, seuraavassa TREAD-ajossa (~1 min) |
| Muokata workflow-tiedostoja sammuttaakseen ne | Seuraava ajo | Tampermonkey | Hash-muutos → hälytys minuutin sisällä |
| Poistaa koko repo tai gh-pages-branch | Välitön | TREAD-palkki | status.json lakkaa päivittymästä → `cron_fresh = false` → Danger |
| Käyttää GitHub:n abuse-suojausta tahallaan (concurrency-burstit) | Tunti | TREAD-palkki | Kaikki ajot pysähtyvät → staleness → Danger noin tunnin kuluessa |

Viisi erillistä workflow'ta tekee sammuttamisesta työläämpää — kaikki viisi täytyy poistaa käytöstä samanaikaisesti, muuten jäljelle jäävät jatkavat valvontaa.

**Suojausaika session aikana:**
TREAD-cronit eivät suoraan suojaa käyttäjää session aikana — ne tuottavat dataa muille kerroksille. Jos hyökkääjä muokkaa workflow'ta, muutos näkyy git tree:ssä välittömästi ja Tampermonkey havaitsee sen minuutin sisällä. Render API -vertailu kuvataan erikseen kohdassa [Render API -valvonta](#6-render-api--valvonta).

---

### 2. status.json (GitHub Pages + Arweave)

`tread_check.py` laskee deployment-tilan ja valvontatiedostojen hashit, `push_status.py` kirjoittaa tuloksen `status.json`:iin GitHub Pagesiin ja `tread_arweave.py` arkistoi sen Arweave-lohkoketjuun. Tiedosto päivittyy minuutin välein.

**Kaksi roolia:**

| Rooli | Käyttötarkoitus | Luotettavuus |
|---|---|---|
| Reaaliaikainen tila | Deploy-statuksen seuranta | Heikko (10 min CDN-cache GitHub Pagesissa) |
| Historiallinen todiste | Arweave-arkisto osoittaa mitä hasheja on raportoitu | Erittäin vahva (muuttumaton) |

**Voidaanko status.json väärentää?**
Kyllä — jos hyökkääjällä on GitHub-kirjoitusoikeus, hän voi muokata kaikkia kolmea tuotantoketjun tiedostoa (`tread_check.py`, `tread_arweave.py`, `push_status.py`) yhdessä commitissa. Tämä ei kuitenkaan vaikuta reaaliaikaiseen suojaan, koska Tampermonkey ja dispatcher eivät luota status.json:iin — ne laskevat hashit suoraan GitHubin git tree API:lta.

Arweave-arkistoon sen sijaan voi tallentua vääristeltyjä tietoja: jos `tread_arweave.py` on kompromisoitu, se voi arkistoida väärät hashit. Aiemmat legitiimit tietueet säilyvät muuttumattomina, mutta hyökkäyksen jälkeiset arkistomerkinnät eivät ole luotettavia.

Lisäksi: kaikkien kolmen tiedoston muokkaaminen on itsessään havaittavaa — jokainen muutos näkyy Tampermonkeyn git tree -tarkistuksessa.

**Suojausaika session aikana:**
Ei reaaliaikaista suojaa — CDN-välimuistin (10 min) takia data voi olla vanhentunutta. Arweave-arkisto on jälkikäteinen todiste, ei ennaltaehkäisevä suojaus.

---

### 3. Tampermonkey-skripti (tread.user.js)

Käyttäjän selaimessa pyörivä skripti. Ainoa komponentti jota operaattori ei kontrolloi.

**Mitä tarkastaa (v3.0):**

**a) Valvontatiedostojen hashit — riippumaton verifiointi**
- Hakee koko git tree:n GitHub API:lta (`/git/trees/main?recursive=1`)
- Poimii blob-SHA:t valvotuille tiedostoille suoraan GitHubista
- Vertaa tallennettuun baselineen (GM_setValue)
- Jos muutos → hälytysmodaali heti

Tämä on **vahvin suojauskerros**: hashit lasketaan selaimessa GitHubin raakadatasta, ei status.json:n väittämästä arvosta. Vaikka `tread_check.py` kirjoittaisi vääriä hasheja, Tampermonkey havaitsee todelliset muutokset.

**b) Deploy-status**
- Hakee status.json GitHub API:lta (60 s cache — ei 10 min Pages-CDN)
- Tarkistaa `deploying_commit_ok` ja `d.ok`
- Hälyttää jos luvaton commit deployataan tai commit ei vastaa GitHubia

**Haavoittuva:**
- Käyttäjän täytyy itse asentaa skripti ja pitää se ajan tasalla
- Ei suojaa käyttäjiä joilla ei ole Tampermonkeyta

**Suojausaika session aikana:**
Tampermonkey ajaa `main()`-funktion sivulatauksen yhteydessä ja sen jälkeen minuutin välein koko session ajan. Hyökkäys havaitaan enintään ~1 minuutin kuluessa tiedostomuutoksesta.

- **Ennen sivulatausta tapahtuva hyökkäys:** havaitaan heti
- **Sivulatauksen jälkeen tapahtuva hyökkäys:** havaitaan seuraavassa 1 min pollausvuorossa
- **Käytännön suojausikkuna:** koko session ajan, jatkuva valvonta

---

### 4. _poide_dispatcher

Palvelimen taustasäie (main.py), joka hakee deployment-tilan GitHubista ja pitää `/version`-endpointin ajan tasalla.

**Toimintaperiaate:**
```
_poide_dispatcher (30 s välein)
  → GitHub API: status-log.jsonl (60 s cache)
  → _poide_cache päivittyy
  → /version palauttaa tilan (~90 s maksimistaleness)
```

Dispatcher tarkistaa itsenäisesti onko valvontatiedostot muuttuneet — riippumatta `tread_check.py`:stä tai status.json:sta. Se hakee git tree:n GitHub API:lta jokaisen pollaussyklin yhteydessä (~30 s välein), vertaa blob-SHA:ita tallennettuun baselineen ja merkitsee muutokset `/version`-vastaukseen (`dispatcher_monitor_changed`). TREAD-palkki näyttää Danger-hälytyksen välittömästi.

Tämä tarkistus on **riippumaton** `tread_check.py`:stä — se hakee hashit suoraan GitHubista eikä luota status.json:iin.

**Vahvuus — muuttaminen vaatii deployn:**
Dispatcher on osa Leiman koodia (main.py). Jos hyökkääjä haluaa kompromisoida dispatcherin, hänen täytyy:
1. Muokata main.py ja committaa → **Tampermonkey havaitsee tiedostomuutoksen ~1 min sisällä**
2. Odottaa code review -workflow (2–3 min)
3. Odottaa hosting-deploy (5–10 min) → **TREAD-palkki näyttää "Deploying" koko ajan**

Sinä aikaikkunana (commit → deploy = ~10–15 min) **legitiimi dispatcher tarkistaa hashit** ja hälyttää jos valvontatiedostot muuttuvat. Hyökkääjä ei pysty hiljentämään dispatcheria ennen kuin kompromisoitu koodi on deployattu.

**Haavoittuva:**
- Deploy-ikkunan jälkeen kompromisoitu dispatcher voi lopettaa tarkistuksen — Tampermonkey ottaa vastuun

**Suojausaika session aikana:**
Dispatcher hälyttää ~2–3 min kuluessa valvontatiedostojen muutoksesta (git tree API 60 s cache + 30 s pollausväli). Yhdessä Tampermonkeyn kanssa kaksi erillistä riippumatonta tarkistajaa.

---

### 5. TREAD-palkki sivun ylälaidassa (/version-endpoint)

Palvelimella pyörivä tila-indikaattori joka näyttää deployment-tilan sivun yläreunassa. Pollaa `/version`-endpointia 20 sekunnin välein.

**Mitä palkki näyttää eri tilanteissa:**

| Tilanne | Palkin tila | Merkitys |
|---|---|---|
| Kaikki kunnossa | OK (vihreä) | Deployattu commit vastaa GitHubin main-branchia |
| Deploy käynnissä (normaali tai epäilyttävä) | Notice — Deploying | Jokin on deployautumassa — paranoidi käyttäjä voi reagoida |
| Koodi puskettu suoraan ohi code reviewin | Danger (punainen) | Deployattu commit ei löydy tai ei vastaa GitHubista — välitön hälytys |
| Workflow poistettu käytöstä | Danger | TREAD havaitsee workflow-tilan muutoksen |

**Keskeinen ominaisuus — paranoidin käyttäjän suoja:**
Palkki näyttää "Deploying" aina kun jokin deployautuu — riippumatta siitä onko se normaali päivitys vai hyökkäys. Tämä antaa käyttäjälle mahdollisuuden reagoida: vaikka haitallinen koodi läpäisisi AI-koodiarvion, palkki ilmoittaa siitä 8–13 minuutin ajan. Käyttäjä joka ei odota päivitystä voi pitää tätä epäilyttävänä.

**Haavoittuva:**
- Palautuu normaalitilaan kun kompromisoitu dispatcher alkaa palvella väärää dataa — Tampermonkey ottaa vastuun tästä eteenpäin

**Suojausaika session aikana:**
Sekä TREAD-palkki että Tampermonkey valvovat jatkuvasti kesken session ilman käyttäjän toimenpiteitä. Kumpikin on pohjimmiltaan pollaus eikä reaaliaikainen — viiveet eroavat:

| Komponentti | Pollausväli | Viive hyökkäyksen havaitsemiseen |
|---|---|---|
| Tampermonkey | 1 min | ~1 min (git tree API) |
| TREAD-palkki | 20 s | ~90 s (dispatcher-latenssi) + 20 s poll = ~2 min |

- **Suora deploy ohi code reviewin:** TREAD-palkki Danger ~2 min kuluessa
- **Deploy virallista kautta (myös haitallinen):** kumpikin näyttää "Deploying"-tilan 8–13 min ajan
- **Deploy valmis, dispatcher väärennetty:** Tampermonkey hälyttää ~1 min sisällä

---

### 6. Render API -valvonta

`tread_check.py` tekee joka ajolla kolme erillistä tarkistusta Render API:n kautta:

**a) Nykyinen tila**
Hakee nykyisen live-commitin ja vertaa GitHubin main-branchia vasten. Jos ne eivät täsmää → `deployment_ok: false` → TREAD-palkki näyttää Danger. Tämä on perustarkistus joka laukeaa myös suoran API-deployn yhteydessä (ks. [Code review -portti](#7-code-review--workflow-code_reviewyml)).

**b) Deploy käynnissä**
Tarkistaa onko juuri nyt deployatumassa commit jota ei löydy GitHubista (`deploying_commit_ok: false`). Jos kyllä → välitön Danger-hälytys käyttäjälle TREAD-palkissa ja Tampermonkeyssa ennen kuin luvaton koodi on edes live.

**c) Deploy-historia — forensinen työkalu**
Skannaa 100 viimeistä deployta ja tarkistaa jokaisen commitin GitHubin kautta. Jos commit palauttaa 404 (ei löydy GitHubista), se kirjataan `last_mismatch_at`- ja `last_mismatch_commit`-kenttiin.

Tämä on ainoa komponentti joka pystyy paljastamaan **menneisyyden hyökkäyksen** — esimerkiksi katkoksen tai väliaikaisesti deaktivoitujen cronien aikana tehty luvaton deploy jää deploy-historiaan. Jos palvelussa on ollut aukko, deploy-historian tutkiminen on relevantti tapa selvittää tapahtuiko sen aikana jotain epäilyttävää.

Historia kattaa 100 viimeistä deployta — pidemmälle ei ulotu ilman Render-dashboardin manuaalista tutkimista.

**Lisäksi: deploy-burstien tunnistus**
Jos tunnin sisällä tapahtuu yli 10 deployta, TREAD raportoi `rapid_deploy_warning: true`. Tämä voi viitata automatisaatioon tai tahalliseen häirintään.

---

### 7. Code review -workflow (code_review.yml)

Jokaisen git push:n jälkeen automaattisesti ajettava workflow, joka toimii deployn portinvartijana.

**Suojaa:**
- AI-koodiarvio havaitsee ilmeiset haitalliset muutokset
- Hosting-deploy ei käynnisty ilman workflown hyväksyntää
- Pre-push TREAD-hookki estää pushin jos edellinen deploy ei ole vakaa

**Code review -portti turvarakenteena:**
Jos käyttäjä on verifioinut session alussa että valvontatiedostot ovat muuttumattomia, hän voi odottaa saavansa hälytyksen jos Leiman palvelimelle yritetään ujuttaa tarkastamatonta koodia. Tarkastamaton koodi tarkoittaa commitia joka ei ole kulkenut code_review.yml:n läpi — tällainen deploy jättää commit-mismatchin jonka TREAD havaitsee.

Tämä ei ole absoluuttinen takuu, mutta se tarkoittaa että hyökkäys jättää havaittavan jäljen.

**Haavoittuva:**
- AI-arvio ei ole aukoton — hienostuneita muutoksia voi jäädä läpi

**Miten code review -portti voidaan yrittää ohittaa — ja miten siitä jää kiinni:**

| Tapa | Miten kiinni |
|---|---|
| Muokata `code_review.yml`:ää (esim. auto-pass) | Vaatii commitin → Tampermonkey havaitsee hash-muutoksen → hälytys |
| Ohittaa workflow ja deployata suoraan API:n kautta | Deployattu commit ≠ GitHubin main → TREAD commit-mismatch → Danger-hälytys |
| Poistaa workflow käytöstä GitHub-käyttöliittymästä | `tread_check.py` tarkistaa workflow-tilat → `disabled_workflows` → TREAD-palkki hälyttää |

Kaikki kolme jättävät jälkiä: joko git-historiaan, GitHub API:n workflow-tilatietoon tai Arweave-arkistoon.

**Suojausaika session aikana:**
Code review lisää 2–3 minuutin pakotetun viiveen jokaisen muutoksen ja deployn välille. Tämä aika on käyttäjälle näkyvää hälytysaikaa (TREAD-palkki "Deploying").

---

### 7. Hosting-ympäristö

Hosting-alustan valinta vaikuttaa merkittävästi järjestelmän turvallisuuteen. Nykyinen ympäristö on väliaikainen.

**Suojausaika session aikana:**
Riippuu täysin alustan eristystasosta. Alustat joissa prosessieristys on heikko voivat mahdollistaa hyökkäyksiä jotka eivät näy missään valvontakerroksessa.

---

## Valvottavat tiedostot

Sekä `tread_check.py` (palvelinpuoli) että Tampermonkey (asiakaspuoli) laskevat hashit samoille tiedostoille. `tread_check.py` käyttää SHA-256, Tampermonkey git blob SHA:ta (GitHubin sisäinen tunniste joka muuttuu sisällön muuttuessa).

| Tiedosto | Miksi valvotaan |
|---|---|
| `.github/workflows/tread-a.yml` … `tread-e.yml` | TREAD-cronien ajastus ja konfiguraatio — muokkaamalla voi sammuttaa valvonnan |
| `.github/workflows/tread-run.yml` | TREAD:n varsinainen suorituslogiikka — muokkaamalla voi tehdä valvonnasta tyhjää |
| `.github/workflows/code_review.yml` | Deploy-portin logiikka — muokkaamalla voi ohittaa koodiarvion tai estää deployt |
| `.github/workflows/monthly-audit.yml` | Kuukausittainen laajempi tarkistus |
| `tread_check.py` | Varsinainen tarkistuslogiikka — muokkaamalla voi kirjoittaa vääriä hasheja status.json:iin |
| `tread_arweave.py` | Arweave-arkistointi — muokkaamalla voi estää historian tallentumisen |
| `code_review.py` | AI-koodiarvion toteutus — muokkaamalla voi tehdä arviosta tyhjää |
| `monthly_audit.py` | Kuukausittaisen auditoinnin toteutus |
| `POLICY.example.md` | Julkinen politiikkadokumentti jonka muutos olisi merkki väärinkäytöstä |

Kaikki yhdeksän tiedostoa muodostavat yhdessä valvontajärjestelmän ytimen. Yhdenkin muuttaminen ilman lupaa laukaisee hälytyksen.

---

## Hyökkäyksen aikajana — käyttäjä on verifioinut session alussa

Oletetaan että käyttäjä on tarkistanut ennen session alkua, että valvontatiedostoja ei ole muutettu kuukausiin. Hyökkäys alkaa session aikana.

```
t=0        Hyökkääjä committaa muutokset GitHubiin
           → Git tree muuttuu välittömästi

t=0–60s    Tampermonkey havaitsee muutoksen seuraavassa pollausvuorossa → HÄLYTYS
           TREAD-palkki jatkaa normaalia näyttöä (dispatcher ei ole vielä päivittynyt)

t=90s      _poide_dispatcher hakee päivitetyn status-log.jsonl:n
           → TREAD-palkki: ei vielä vaikutusta (dispatcher seuraa deploy-statusta)

t=2–3min   Code review -workflow käynnistyy ja valmistuu
           → TREAD-palkki näyttää "Deploying" ← HÄLYTYS

t=3–13min  Hosting-deploy käynnissä
           → TREAD-palkki näyttää "Deploying" koko ajan
           → Käyttäjällä on 8–13 min näkyvää hälytysaikaa

t=13min    Kompromisoitu koodi on live
           → Jos dispatcher on kompromisoitu: TREAD-palkki palaa vihreäksi
           → Tampermonkey hälyttää minuutin sisällä (pollaa jatkuvasti)
```

**Yhteenveto suojausajasta:**

| Vaihe | Kesto | Käyttäjän suoja |
|---|---|---|
| Commit → Tampermonkey pollaa | 0–60 s | ✅ Hälytys minuutin sisällä |
| Commit → dispatcher päivittyy | 0–90 s | TREAD-palkki ei vielä hälytä |
| Deploy käynnissä | 8–13 min | ✅ TREAD-palkki "Deploying" |
| Kompromisoitu koodi live | Jatkuva | ✅ Tampermonkey hälyttää minuutin sisällä |

**Käytännön suositus käyttäjälle:** Älä lähetä arkaluonteisia dokumentteja jos TREAD-palkki näyttää "Deploying", "Notice" tai "Danger".

---

## Yhteenveto: suojaus eri uhkia vastaan

### Ulkoinen hyökkääjä (ei GitHub/Render-pääsyä)

Ulkoisella hyökkääjällä ei ole pääsyä kumpaankaan järjestelmään, joten deployment-integriteetin uhkia ei käytännössä ole — koodi ei pääse tuotantoon ilman GitHub- tai hosting-tunnuksia.

✅ **Deployment-integriteetti täysin suojattu tältä hyökkääjätyypiltä**

---

### Osittainen hyökkääjä (vain hosting-pääsy)

| Uhka | Suojaus |
|---|---|
| Luvaton deploy API:n kautta | TREAD havaitsee commit-mismatchin → Danger-hälytys |
| Alustatason hyökkäys | Riippuu hosting-ympäristön eristystasosta |

⚠️ **Hosting-ympäristön valinta kriittinen — migraatio suunnitteilla**

---

### Osittainen hyökkääjä (vain GitHub-pääsy)

| Uhka | Suojaus |
|---|---|
| Valvontatiedostojen muokkaus | Tampermonkey hälyttää minuutin sisällä |
| Väärät hashit status.json:iin | Tampermonkey laskee hashit itse, ei luota status.json:iin |
| Deploy ilman koodiarvioita | Code review -workflow estää → ohitus hälyttää |

✅ **Hyvin suojattu**

---

### Ylläpito-hyökkääjä (GitHub + Render)

| Uhka | Suojaus |
|---|---|
| Valvontatiedostojen muokkaus | Tampermonkey hälyttää minuutin sisällä ✅ |
| Deploy ilman code review -porttia | TREAD commit-mismatch → Danger-hälytys ✅ |
| Deploy ohi code reviewin | TREAD commit-mismatch → Danger-hälytys ✅ |
| Väärät hashit status.json:iin | Tampermonkey laskee hashit itse git tree API:lta ✅ |
| Historian peittäminen | Arweave muuttumaton ✅ |
| Haitallinen koodi joka **läpäisee AI-koodiarvion** eikä muokkaa valvottuja tiedostoja | ❌ Ei hälytystä |
| Alustatason hyökkäys | Riippuu hosting-ympäristön eristystasosta |

⚠️ **Ainoa havaitsematon aukko: hienostunut haitallinen koodi joka läpäisee AI-koodiarvion muuttamatta valvottuja tiedostoja. Kaikki muut hyökkäysvektorit tuottavat hälytyksen.**

---

## Luottamushierarkia

```
Tampermonkey (käyttäjän selain)     — korkein, operaattori ei kontrolloi
  ↓
Arweave-arkisto                     — muuttumaton historiallinen todiste
  ↓
GitHub Actions (TREAD)              — luotettu jos GitHub ei kompromisoitu
  ↓
/version + TREAD-palkki             — luotettu jos koodi ei kompromisoitu, ~90 s latenssi
  ↓
status.json (GitHub Pages)          — auditointiartefakti, ei reaaliaikainen turvatae
  ↓
Hosting-ympäristö                   — matalin, riippuu alustan eristystasosta
```

---

## Avoimet asiat

| Asia | Tila |
|---|---|
| Hosting-ympäristön migraatio | Suunniteltu |
| Tampermonkey-baseline session alussa | Suunniteltu — status-log.jsonl:n stabiliteetin tarkistus |

---

## Operaattorin luottamusvaatimus

Leima vaatii luottamuksen operaattoriin samoin kuin perinteinen notaari — ei enempää eikä vähempää. Järjestelmän valvontamekanismit tekevät mahdollisesta pettämisestä havaittavaa ja historiallisesti todistettavaa, mutta eivät täysin mahdotonta ilman TEE:tä. Tämä kommunikoidaan käyttäjille rehellisesti.
