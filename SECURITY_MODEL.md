# Leiman tietoturvamalli

Tämä dokumentti kuvaa Leiman valvonta-arkkitehtuurin, kunkin komponentin suojausominaisuudet ja tunnistetut haavoittuvuudet.

Viimeksi päivitetty: 2026-05-29

---

## Johdanto — miten turvallisuusmalli toimii

Leiman turvallisuusmalli on rakennettu suojaamaan käyttäjän tietoja tilanteessa jossa uhka on ylläpitäjä itse — joko petollinen tai sellainen jonka tunnukset on anastettu. Tavoite on, ettei käyttäjän asiakirjoja voi urkia tai varastaa ilman että käyttäjä saa siitä hälytyksen.

Malli hyödyntää kahta perusperiaatetta:

**1. Palveluntarjoajien API-rajapinnat**
Hosting-palvelu tarjoaa API:n josta näkyy mitä koodia palvelimella tällä hetkellä pyörii ja onko deploy käynnissä. Tätä verrataan GitHubin julkiseen repositorioon. Jos ne eivät täsmää, järjestelmä hälyttää.

**2. Muutosten aikaviive**
Koodin muuttaminen tuotantopalvelimella ei tapahdu hetkessä — se vaatii GitHub-commitin, koodiarvion läpäisemisen ja hosting-deployn, joka kestää yhteensä 8–15 minuuttia. Tänä aikana järjestelmän eri osat ovat vielä muuttumattomia, joten ne voivat havaita muutoksen ja hälyttää käyttäjää ennen kuin mitään vahingollista tapahtuu.

Näiden kahden varaan on rakennettu useita toisistaan riippumattomia valvontakerroksia. Kukin tarkistaa asioita eri lähteistä ja eri viiveillä — yhden kerroksen kompromisointi ei sammuta muita.

**Luottamuksen rakentuminen**

Järjestelmä pyrkii rakentamaan luottamuksen monella toisiaan täydentävällä tavalla:

- **Muuttumaton historia** — Arweave-arkisto todistaa että palvelimella ei ole koskaan pyörinyt koodia joka ei näy GitHubissa. Tätä historiaa ei voi jälkikäteen muuttaa.
- **Automaattinen koodiarvio** — jokainen muutos tarkastetaan AI:n avulla ennen kuin se pääsee tuotantoon. Arvio vertaa muutoksia käyttöehtoihin ja politiikkadokumenttiin.
- **Deployhälytys kesken session** — jos palvelimelle ajetaan uusi versio käyttäjän session aikana, TREAD-palkki ilmoittaa siitä. Käyttäjä näkee muutoksen ennen kuin se on voimassa.
- **Hälytys ohi GitHubin** — jos koodia yritetään ajaa sisään ohittaen GitHub-repositorio ja koodiarvio, TREAD havaitsee commit-mismatchin ja hälyttää välittömästi.

---

## Uhkamallit

Kolme hyökkääjätyyppiä, joita vastaan järjestelmä on suunniteltu:

| Tyyppi | Pääsy | Uhkataso |
|---|---|---|
| **Ulkoinen hyökkääjä** | Ei GitHub- eikä hosting-pääsyä | Matala |
| **Osittainen hyökkääjä** | GitHub TAI hosting, ei molempia | Keskisuuri |
| **Ylläpito-hyökkääjä** | GitHub JA hosting | Korkea |

---

## I. GitHub Actions — julkinen valvontakerros

Tässä osiossa kuvatut komponentit pyörivät GitHubissa, eivät Leiman palvelimella. Ne ovat julkisia ja kenen tahansa tarkastettavissa. Ne toimivat riippumatta siitä mitä Leiman palvelimella tapahtuu — eikä hosting-pääsy anna mahdollisuutta muokata niitä.

---

### 1. TREAD-cronit — tread-a…e.yml, tread-run.yml, tread_check.py

GitHub Actions sallii cronille minimissään 5 minuutin välin. Yhden minuutin tarkkuuteen päästään viidellä identtisellä workflow'lla (`tread-a.yml`…`tread-e.yml`), joiden käynnistysajat on porrastettu minuutin välein (`:00`, `:01`, `:02`, `:03`, `:04`, sitten `:05`…). Jokainen niistä kutsuu `tread-run.yml`:ää, joka sisältää varsinaisen suorituslogiikan: ajaa `tread_check.py`:n, arkistoi tuloksen Arweave-lohkoketjuun (`tread_arweave.py`) ja kirjoittaa `status.json`:n GitHub Pagesiin (`push_status.py`).

Jokainen ajo:
- Tarkistaa vastaako hosting-palvelussa pyörivä commit GitHubin main-branchia (Render API:n kautta)
- Tarkistaa onko parhaillaan deployatumassa commit jota ei löydy GitHubista
- Tarkistaa että kaikki viisi TREAD-workflow'ta ovat aktiivisena
- Laskee SHA-256-hashit kaikista valvontatiedostoista — siis myös itsestään (`tread_check.py`)
- Kirjoittaa tuloksen `status.json`:iin GitHub Pagesiin
- Arkistoi tuloksen Arweave-lohkoketjuun pysyvästi

Viiden erillisen workflow'n redundanssi suojaa yksittäisen workflown passivoitumiselta — kaikki viisi täytyy sammuttaa samanaikaisesti, muuten valvonta jatkuu.

**Render API -tarkistukset**

`tread_check.py` tekee joka ajolla kolme erillistä tarkistusta Render API:n kautta:

- **Nykyinen tila** — hakee live-commitin ja vertaa GitHubin main-branchin viimeisimpään committiin. Jos ei täsmää → `deployment_ok: false` → Danger-hälytys.
- **Deploy käynnissä** — tarkistaa onko juuri nyt deployatumassa commit jota ei löydy GitHubista. Jos kyllä → välitön Danger-hälytys ennen kuin luvaton koodi on edes live.
- **Deploy-historia** — skannaa 100 viimeistä deployta ja tarkistaa jokaisen commitin GitHubista. Jos commit palauttaa 404, se kirjataan `last_mismatch_at`-kenttään. Tämä on ainoa komponentti joka pystyy paljastamaan **menneisyyden hyökkäyksen** — esimerkiksi katkoksen tai deaktivoitujen cronien aikana tehty luvaton deploy jää deploy-historiaan. Historia kattaa 100 viimeistä deployta.
- **Deploy-burstit** — jos tunnin sisällä tapahtuu yli 10 deployta, TREAD raportoi `rapid_deploy_warning: true`.

**Miten TREAD-cronit voidaan yrittää sammuttaa — ja miten siitä jää kiinni:**

| Tapa | Kuka huomaa | Miten |
|---|---|---|
| Poistaa kaikki 5 workflow'ta käytöstä GitHub-UI:ssa | TREAD-palkki | Workflow-tilat → `disabled_workflows` → Danger (~1 min) |
| Muokata workflow-tiedostoja | Tampermonkey | Hash-muutos → hälytys minuutin sisällä |
| Poistaa repo tai gh-pages-branch | TREAD-palkki | status.json lakkaa päivittymästä → staleness → Danger |
| Käyttää GitHub:n abuse-suojausta tahallaan | TREAD-palkki | Cronit pysähtyvät → staleness → Danger noin tunnin kuluessa |

**Haavoittuva:**
- Kompromisoitu `tread_check.py` voi kirjoittaa vääriä hasheja `status.json`:iin — mutta Tampermonkey ja dispatcher laskevat hashit suoraan GitHubin git tree API:lta eivätkä luota `status.json`:iin
- GitHub Actions itsessään on luotettu osapuoli — jos GitHub on kompromisoitu, koko järjestelmä pettää

---

### 2. TREAD:n tuottama data — status.json ja Arweave-arkisto

`tread_check.py` laskee deployment-tilan ja valvontatiedostojen hashit, `push_status.py` kirjoittaa tuloksen `status.json`:iin GitHub Pagesiin, ja `tread_arweave.py` arkistoi sen Arweave-lohkoketjuun. Tiedostot päivittyvät minuutin välein.

**status.json — kaksi roolia:**

| Rooli | Käyttötarkoitus | Luotettavuus |
|---|---|---|
| Reaaliaikainen tila | Deploy-statuksen seuranta | Heikko (10 min CDN-cache GitHub Pagesissa) |
| Historiallinen todiste | Arweave-arkisto osoittaa mitä hasheja on raportoitu | Erittäin vahva (muuttumaton) |

**Voidaanko status.json väärentää?**
Kyllä — jos hyökkääjällä on GitHub-kirjoitusoikeus, hän voi muokata kaikkia kolmea tuotantoketjun tiedostoa (`tread_check.py`, `tread_arweave.py`, `push_status.py`) yhdessä commitissa. Tämä ei kuitenkaan vaikuta reaaliaikaiseen suojaan: Tampermonkey ja dispatcher eivät luota `status.json`:iin vaan laskevat hashit suoraan GitHubin git tree API:lta. Lisäksi kaikkien kolmen tiedoston muokkaaminen on itsessään havaittavaa — jokainen muutos näkyy Tampermonkeyn git tree -tarkistuksessa.

**Arweave-arkisto — repo ei ole ainoa totuuden lähde**

Arweave-arkisto on pysyvä ja muuttumaton — kerran kirjoitettua dataa ei voi poistaa eikä muuttaa. Jokainen status.json-snapshot sisältää: deployatun commitin, GitHubin expected-commitin, kaikkien valvontatiedostojen SHA-256-hashit, workflow-tilat ja aikaleiman.

Vaikka GitHub-repositorio syystä tai toisesta häviäisi tai sen historia väärentyisi, Arweave-arkistoon jää minuutin tarkkuudella dokumentoitu historia järjestelmän tilasta. Vertaamalla Arweave-tietueita ja repositorion nykyistä tilaa voidaan rekonstruoida mitä koodia kulloinkin ajettiin.

Jos Arweave-tietue on epäilyttävä, sen voi ristiin tarkistaa GitHubin commit-historiasta — repositoriosta nähdään mitä koodia kyseisenä päivänä todella pyöri.

**Rajoitus:** jos `tread_arweave.py` on kompromisoitu, arkistoon voi tallentua vääristeltyä dataa hyökkäyksen jälkeen. Ennen hyökkäystä tallennetut tietueet säilyvät kuitenkin muuttumattomina.

---

### 3. Code review -workflow (code_review.yml)

Jokaisen git push:n jälkeen automaattisesti ajettava workflow, joka toimii deployn portinvartijana.

- AI-koodiarvio tarkastaa muutokset ja vertaa käyttöehtoihin ennen deployta
- Hosting-deploy ei käynnisty ilman workflown hyväksyntää
- Pre-push TREAD-hookki estää pushin jos edellinen deploy ei ole vakaa

**Code review -portti turvarakenteena**

Jos käyttäjä on verifioinut session alussa että valvontatiedostot ovat muuttumattomia, hän voi odottaa saavansa hälytyksen jos Leiman palvelimelle yritetään ujuttaa tarkastamatonta koodia. Tarkastamaton koodi tarkoittaa commitia joka ei ole kulkenut `code_review.yml`:n läpi — tällainen deploy jättää commit-mismatchin jonka TREAD havaitsee. Tämä ei ole absoluuttinen takuu, mutta hyökkäys jättää havaittavan jäljen.

**Miten code review -portti voidaan yrittää ohittaa — ja miten siitä jää kiinni:**

| Tapa | Miten kiinni |
|---|---|
| Muokata `code_review.yml`:ää | Vaatii commitin → Tampermonkey havaitsee hash-muutoksen → hälytys |
| Deployata suoraan API:n kautta | Deployattu commit ≠ GitHubin main → TREAD commit-mismatch → Danger-hälytys |
| Poistaa workflow käytöstä | `tread_check.py` tarkistaa workflow-tilat → `disabled_workflows` → TREAD-palkki hälyttää |

**Haavoittuva:** AI-arvio ei ole aukoton — hienostuneita muutoksia voi jäädä läpi.

---

## II. Leiman palvelin

Tässä osiossa kuvatut komponentit pyörivät hosting-ympäristössä. Niiden muuttaminen vaatii aina deployn, jonka aikana TREAD-palkki näyttää "Deploying" 8–13 minuutin ajan — käyttäjä näkee muutoksen ennen kuin se on voimassa. Palvelinpuolen komponenteilla on pääsy Render API -avaimiin, mikä mahdollistaa deploy-statuksen suoran tarkistuksen.

---

### 4. _poide_dispatcher

Palvelimen taustasäie (`main.py`), joka tekee kolme itsenäistä tarkistusta jokaisen pollaussyklin yhteydessä (~30 s välein), riippumatta TREAD-croneista:

1. **Deploy käynnissä?** — Render API suoraan. Jos deploy alkaa, TREAD-palkki päivittyy 30 s sisällä.
2. **Koodi oikein?** — Vertaa Render-live-commitin GitHubin main-branchin viimeisimpään committiin suoraan. Jos ei täsmää → `deployment_ok: false` → Danger-hälytys.
3. **Valvontatiedostot muuttuneet?** — Hakee git tree:n GitHub API:lta, vertaa blob-SHA:ita tallennettuun baselineen. Jos muutos → `dispatcher_monitor_changed` → Danger-hälytys.

**Lisäksi:** dispatcher lähettää `workflow_dispatch`-kutsun GitHub Actionsille 30 s välein, jolloin TREAD-cronit käynnistyvät luotettavammin kuin pelkän GitHub-ajastuksen varassa.

**Miksi main.py ei ole valvottavien tiedostojen listalla**

Dispatcher on osa `main.py`:tä, joka on sovelluksen pääkoodi. Se muuttuu normaalin kehitystyön yhteydessä usein — jos se lisättäisiin Tampermonkeyn seurantalistalle, hälytys laukaisisi joka deployssa ja koko periaate "muutos on aina merkittävä" romahtaisi.

`main.py`:n suojaus toimii eri mekanismilla: sen muuttaminen vaatii deployn, jonka aikana TREAD-palkki näyttää "Deploying". Lisäksi code review tarkastaa jokaisen muutoksen.

**Vahvuus — muuttaminen vaatii deployn:**
Sinä aikaikkunana (commit → deploy = ~10–15 min) **legitiimi dispatcher tarkistaa hashit** ja hälyttää jos valvontatiedostot muuttuvat. Hyökkääjä ei pysty hiljentämään dispatcheria ennen kuin kompromisoitu koodi on deployattu.

**Haavoittuva:** deploy-ikkunan jälkeen kompromisoitu dispatcher voi lopettaa tarkistuksen — Tampermonkey ottaa vastuun.

---

### 5. TREAD-palkki sivun ylälaidassa (/version)

Palvelimella pyörivä tila-indikaattori joka näyttää deployment-tilan sivun yläreunassa. Pollaa `/version`-endpointia 20 sekunnin välein.

**Mitä palkki näyttää:**

| Tilanne | Palkin tila |
|---|---|
| Kaikki kunnossa | OK (vihreä) |
| Deploy käynnissä — normaali tai epäilyttävä | Notice — Deploying |
| Deployattu commit ei vastaa GitHubista | Danger (punainen) |
| Workflow poistettu käytöstä | Danger |

**Paranoidin käyttäjän suoja:** palkki näyttää "Deploying" aina kun jokin deployautuu — riippumatta siitä onko se normaali päivitys vai hyökkäys. Vaikka haitallinen koodi läpäisisi AI-koodiarvion, palkki ilmoittaa siitä 8–13 minuutin ajan. Käyttäjä joka ei odota päivitystä voi pitää tätä epäilyttävänä.

**Pollausviiveet:**

| Komponentti | Pollausväli | Viive hyökkäyksen havaitsemiseen |
|---|---|---|
| Tampermonkey | 1 min | ~1 min (git tree API) |
| TREAD-palkki | 20 s | ~90 s (dispatcher-latenssi) + 20 s poll = ~2 min |

**Haavoittuva:** palautuu normaalitilaan kun kompromisoitu dispatcher alkaa palvella väärää dataa — Tampermonkey ottaa vastuun tästä eteenpäin.

---

### 6. Hosting-ympäristö

Hosting-alustan valinta vaikuttaa merkittävästi järjestelmän turvallisuuteen. Alustat joissa prosessieristys on heikko voivat mahdollistaa hyökkäyksiä jotka eivät näy missään valvontakerroksessa. Nykyinen ympäristö on väliaikainen — migraatio suunnitteilla.

---

## III. Käyttäjän selain — riippumaton valvonta

Tampermonkey-skripti on ainoa komponentti jota operaattori ei kontrolloi. Se pyörii käyttäjän omassa selaimessa eikä ole riippuvainen Leiman palvelimesta, dispatcherista eikä GitHub Actionsista. Tämä tekee siitä turvallisuusmallin vahvimman yksittäisen kerroksen.

---

### 7. Tampermonkey-skripti (tread.user.js)

Skripti ajaa `main()`-funktion sivulatauksen yhteydessä ja sen jälkeen minuutin välein koko session ajan.

**a) Valvontatiedostojen hashit — riippumaton verifiointi**
- Hakee koko git tree:n GitHub API:lta (`/git/trees/main?recursive=1`)
- Poimii blob-SHA:t valvotuille tiedostoille suoraan GitHubista
- Vertaa tallennettuun baselineen (GM_setValue)
- Jos muutos → hälytysmodaali heti

Hashit lasketaan selaimessa GitHubin raakadatasta, ei `status.json`:n väittämästä arvosta. Vaikka `tread_check.py` kirjoittaisi vääriä hasheja, Tampermonkey havaitsee todelliset muutokset.

**b) Deploy-status**
- Hakee `status.json`:n GitHub API:lta (60 s cache — ei 10 min Pages-CDN)
- Hälyttää jos luvaton commit deployataan tai commit ei vastaa GitHubia

**Haavoittuva:**
- Käyttäjän täytyy itse asentaa skripti ja pitää se ajan tasalla
- Ei suojaa käyttäjiä joilla ei ole Tampermonkeyta

---

## Valvottavat tiedostot

Tampermonkey ja dispatcher vertaavat hasheja samoille tiedostoille. Tampermonkey käyttää GitHubin git blob SHA:ta, `tread_check.py` SHA-256:ta.

**Miksi juuri nämä tiedostot?**

Valvottavat tiedostot ovat nimenomaan **valvontainfrastruktuuri** — tiedostot jotka hallitsevat valvontaa itse. Sovelluksen pääkoodi (`main.py`) ei ole listalla, koska se muuttuu usein normaalin kehitystyön yhteydessä ja sen suojaus toimii deploy-viiveen ja code reviewn kautta.

Tiedostot muuttuvat käytännössä vain jos valvontajärjestelmää muutetaan tarkoituksellisesti — tämä on tietoinen suunnittelupäätös. Harva muutos tarkoittaa että muutos on aina merkittävä.

| Tiedosto | Miksi valvotaan |
|---|---|
| `.github/workflows/tread-a.yml` … `tread-e.yml` | TREAD-cronien ajastus — muokkaamalla voi sammuttaa valvonnan |
| `.github/workflows/tread-run.yml` | TREAD:n suorituslogiikka — muokkaamalla voi tehdä valvonnasta tyhjää |
| `.github/workflows/code_review.yml` | Deploy-portti — muokkaamalla voi ohittaa koodiarvion |
| `.github/workflows/monthly-audit.yml` | Kuukausittainen laajempi tarkistus |
| `tread_check.py` | Tarkistuslogiikka — muokkaamalla voi kirjoittaa vääriä hasheja; hashaa myös itsensä |
| `tread_arweave.py` | Arweave-arkistointi — muokkaamalla voi estää historian tallentumisen |
| `code_review.py` | AI-koodiarvion toteutus — muokkaamalla voi tehdä arviosta tyhjää |
| `monthly_audit.py` | Kuukausittaisen auditoinnin toteutus |
| `POLICY.example.md` | Julkinen politiikkadokumentti — muutos olisi merkki väärinkäytöstä |

Yhdenkin muuttaminen ilman lupaa laukaisee hälytyksen.

**Tarkistus ennen sessiota**

Käyttäjä voi tallentaa seuraavan skriptin omalle koneelleen ja ajaa sen ennen sessiota. Se hakee nykyiset hashit GitHubista ja vertaa tallennettuihin arvoihin:

```python
import json, urllib.request

REPO   = "fxg55647/leima"
BRANCH = "main"
PATHS  = {
    ".github/workflows/tread-a.yml",
    ".github/workflows/tread-b.yml",
    ".github/workflows/tread-c.yml",
    ".github/workflows/tread-d.yml",
    ".github/workflows/tread-e.yml",
    ".github/workflows/tread-run.yml",
    ".github/workflows/monthly-audit.yml",
    ".github/workflows/code_review.yml",
    "tread_check.py", "tread_arweave.py",
    "monthly_audit.py", "code_review.py", "POLICY.example.md",
}
SAVED = "leima_hashes.json"

url = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
tree = json.loads(urllib.request.urlopen(url).read())["tree"]
current = {i["path"]: i["sha"] for i in tree if i["path"] in PATHS}

try:
    prev = json.load(open(SAVED))
    changed = [p for p in current if current[p] != prev.get(p)]
    if changed:
        print("MUUTTUNUT:", changed)
    else:
        print("OK — kaikki valvontatiedostot ennallaan")
except FileNotFoundError:
    json.dump(current, open(SAVED, "w"), indent=2)
    print("Hashit tallennettu. Aja uudelleen seuraavalla kerralla.")
```

Saman tarkistuksen voi pyytää myös AI-agentilta: anna sille lista tiedostoista ja edellinen hash-tiedosto, ja pyydä hakemaan nykyiset hashit GitHubista ja vertaamaan.

---

## Hyökkäyksen aikajana — käyttäjä on verifioinut session alussa

Oletetaan että käyttäjä on tarkistanut ennen session alkua, että valvontatiedostoja ei ole muutettu kuukausiin. Hyökkäys alkaa session aikana.

```
t=0        Hyökkääjä committaa muutokset GitHubiin
           → Git tree muuttuu välittömästi

t=0–60s    Tampermonkey havaitsee muutoksen seuraavassa pollausvuorossa → HÄLYTYS
           TREAD-palkki jatkaa normaalia näyttöä (dispatcher ei ole vielä päivittynyt)

t=90s      Dispatcher hakee päivitetyn status-log.jsonl:n ja git tree:n
           → Valvontatiedostomuutos havaitaan → TREAD-palkki Danger

t=2–3min   Code review -workflow käynnistyy ja valmistuu
           → TREAD-palkki näyttää "Deploying" ← HÄLYTYS

t=3–13min  Hosting-deploy käynnissä
           → TREAD-palkki näyttää "Deploying" koko ajan

t=13min    Kompromisoitu koodi on live
           → Jos dispatcher on kompromisoitu: TREAD-palkki palaa vihreäksi
           → Tampermonkey hälyttää minuutin sisällä (pollaa jatkuvasti)
```

**Yhteenveto suojausajasta:**

| Vaihe | Kesto | Käyttäjän suoja |
|---|---|---|
| Commit → Tampermonkey pollaa | 0–60 s | ✅ Hälytys minuutin sisällä |
| Commit → dispatcher päivittyy | 0–90 s | ✅ TREAD-palkki Danger |
| Deploy käynnissä | 8–13 min | ✅ TREAD-palkki "Deploying" |
| Kompromisoitu koodi live | Jatkuva | ✅ Tampermonkey hälyttää minuutin sisällä |

**Käytännön suositus käyttäjälle:** Älä lähetä arkaluonteisia dokumentteja jos TREAD-palkki näyttää "Deploying", "Notice" tai "Danger".

---

## Yhteenveto: suojaus eri uhkia vastaan

### Ulkoinen hyökkääjä (ei GitHub/hosting-pääsyä)

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

### Ylläpito-hyökkääjä (GitHub + hosting)

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
GitHub Actions (TREAD + code review) — luotettu jos GitHub ei kompromisoitu
  ↓
_poide_dispatcher + TREAD-palkki    — luotettu jos koodi ei kompromisoitu, ~90 s latenssi
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
| RENDER_API_KEY ja RENDER_SERVICE_ID hosting-ympäristöön | Lisättävä Render-dashboardille — dispatcher tarvitsee ne suoraan Render API -kutsuihin |

---

## Operaattorin luottamusvaatimus

Leima vaatii luottamuksen operaattoriin samoin kuin perinteinen notaari — ei enempää eikä vähempää. Järjestelmän valvontamekanismit tekevät mahdollisesta pettämisestä havaittavaa ja historiallisesti todistettavaa, mutta eivät täysin mahdotonta ilman TEE:tä. Tämä kommunikoidaan käyttäjille rehellisesti.
