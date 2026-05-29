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

### 1. TREAD-cronit (tread-a.yml … tread-e.yml)

Viisi identtistä GitHub Actions -workflow'ta, jotka ajavat `tread_check.py`:n vuorotellen minuutin välein. Redundanssi suojaa yksittäisen workflown passivoitumiselta.

**Suojaa:**
- Havaitsee jos Renderissä pyörii commit jota ei löydy GitHubista
- Tarkistaa että kaikki viisi TREAD-worflow'ta ovat aktiivisia
- Laskee SHA-256-hashit kaikista valvontatiedostoista ja kirjoittaa ne status.json:iin
- Arkistoi tuloksen Arweave-lohkoketjuun pysyvästi

**Haavoittuva:**
- Jos hyökkääjällä on GitHub-kirjoitusoikeus, hän voi muokata kaikkia viittä workflow'ta samanaikaisesti
- Kompromisoitu `tread_check.py` voi kirjoittaa vääriä hasheja status.json:iin
- GitHub Actions itsessään on luotettu osapuoli — jos GitHub on kompromisoitu, koko järjestelmä pettää

**Suojausaika session aikana:**
TREAD-cronit eivät suoraan suojaa käyttäjää session aikana — ne tuottavat dataa muille kerroksille. Jos hyökkääjä muokkaa workflow'ta, muutos näkyy git tree:ssä välittömästi (~1 min), jonka Tampermonkey havaitsee seuraavalla sivulatauksella.

---

### 2. status.json (GitHub Pages + Arweave)

TREAD:n tuottama julkinen tiedosto, joka sisältää deployment-tilan, valvontatiedostojen hashit ja aikaleiman. Päivittyy minuutin välein.

**Kaksi roolia:**

| Rooli | Käyttötarkoitus | Luotettavuus |
|---|---|---|
| Reaaliaikainen tila | Deploy-statuksen seuranta | Heikko (10 min CDN-cache GitHub Pagesissa) |
| Historiallinen todiste | Arweave-arkisto osoittaa mitä hasheja on raportoitu | Erittäin vahva (muuttumaton) |

**Haavoittuva:**
- Kompromisoitu `tread_check.py` voi kirjoittaa vääriä hasheja — status.json ei itsessään todenna sisältönsä oikeellisuutta
- Ei sovi reaaliaikaiseen turvallisuusverifiointiin CDN-välimuistin takia

**Arweave-arkiston vahvuus:**
Vaikka hyökkääjä muuttaisi tiedostoja ja kirjoittaisi vääriä hasheja tuleviin ajoihin, aikaisemmat Arweave-tietueet osoittavat mitä hasheja järjestelmä raportoi ennen muutosta. Historiaa ei voi jälkikäteen väärentää.

**Suojausaika session aikana:**
Ei reaaliaikaista suojaa session aikana CDN-välimuistin takia. Arweave-arkisto on jälkikäteinen todiste, ei ennaltaehkäisevä suojaus.

---

### 3. Tampermonkey-skripti (tread.user.js)

Käyttäjän selaimessa pyörivä skripti. Ainoa komponentti jota operaattori ei kontrolloi.

**Mitä tarkastaa (v3.0):**

**a) Valvontatiedostojen hashit — riippumaton verifiointi**
- Hakee koko git tree:n GitHub API:lta (`/git/trees/main?recursive=1`)
- Poimii blob-SHA:t valvotuille tiedostoille suoraan GitHubista
- Vertaa tallennettuun baselineen (GM_setValue)
- Jos muutos → varoitusmodaali heti

Tämä on **vahvin suojauskerros**: hashit lasketaan selaimessa GitHubin raakadatasta, ei status.json:n väittämästä arvosta. Vaikka `tread_check.py` kirjoittaisi vääriä hasheja, Tampermonkey havaitsee todelliset muutokset.

**b) Deploy-status**
- Hakee status.json GitHub API:lta (60 s cache — ei 10 min Pages-CDN)
- Tarkistaa `deploying_commit_ok` ja `d.ok`
- Varoittaa jos luvaton commit deployataan tai commit ei vastaa GitHubia

**Haavoittuva:**
- Käyttäjän täytyy itse asentaa skripti ja pitää se ajan tasalla
- Ei suojaa käyttäjiä joilla ei ole Tampermonkeyta

**Suojausaika session aikana:**
Tampermonkey ajaa vain sivun latauksen yhteydessä, ei jatkuvasti. Jos hyökkäys alkaa sivulatauksen jälkeen, käyttäjä ei saa varoitusta ennen seuraavaa sivulatausta.

- **Ennen sivulatausta tapahtuva hyökkäys:** havaitaan heti
- **Sivulatauksen jälkeen tapahtuva hyökkäys:** havaitaan vasta seuraavalla sivulatauksella
- **Käytännön suojausikkuna:** niin kauan kuin käyttäjä ei lataa sivua uudelleen — tyypillisesti koko session ajan

Tämä tarkoittaa että jos käyttäjä on verifioinut tiedostot session alussa ja hyökkäys alkaa kesken session, TREAD-palkki on ensisijainen reaaliaikainen varoitin.

---

### 4. TREAD-palkki sivun ylälaidassa (/version-endpoint)

Palvelimella pyörivä tila-indikaattori. Hakee datansa `_poide_dispatcher`-säikeeltä.

**Dispatcher-ketju:**
```
_poide_dispatcher (30 s välein)
  → GitHub API: status-log.jsonl (60 s cache)
  → _poide_cache päivittyy
  → /version palauttaa tilan (~90 s maksimistaleness)
```

**Vahvuus — aikaikkuna-argumentti:**
Dispatcher on osa Leiman koodia (main.py). Jos hyökkääjä haluaa kompromisoida dispatcherin, hänen täytyy:
1. Muokata main.py ja committaa → **Tampermonkey havaitsee tiedostomuutoksen seuraavalla sivulatauksella**
2. Odottaa code review -workflow (2–3 min)
3. Odottaa Render-deploy (5–10 min) → **TREAD-palkki näyttää "Deploying" koko ajan**

Käyttäjä saa siis näkyvän varoituksen 8–13 minuutin ajan ennen kuin kompromisoitu koodi on edes live.

**Haavoittuva:**
- Dispatcher luottaa status.json:iin dispatcherin oman verifiointilogiikan puuttuessa
- Jos Render-ympäristö on kompromisoitu (ptrace), muistissa oleva tieto voidaan väärentää ilman uutta deployia

**Suojausaika session aikana:**
TREAD-palkki on ainoa komponentti joka varoittaa **reaaliaikaisesti kesken session** ilman sivun uudelleenlatausta (pollaa 20 s välein).

- **Hyökkäys alkaa:** palkki näyttää "Deploying" ~90 s kuluessa commitista
- **Deploy käynnissä:** varoitus näkyy koko deploy-ajan (8–13 min)
- **Deploy valmis, kompromisoitu koodi live:** palkki palaa vihreäksi (väärä positiivi) jos dispatcher on nyt väärennetty
- **Suoja loppuu:** heti kun kompromisoitu koodi on deployattu ja dispatcher alkaa palvella väärää dataa

**Johtopäätös:** TREAD-palkki suojaa käyttäjän koko deploy-prosessin ajan. Kriittinen ikkuna on deploy-prosessin jälkeen, jos dispatcher on osa hyökkäystä.

---

### 5. Code review -workflow (code_review.yml)

Jokaisen git push:n jälkeen automaattisesti ajettava workflow, joka toimii deployn portinvartijana.

**Suojaa:**
- AI-koodiarvio havaitsee ilmeiset haitalliset muutokset
- Render-deploy ei käynnisty ilman workflown hyväksyntää
- Pre-push TREAD-hookki estää pushin jos edellinen deploy ei ole vakaa

**Kriittinen turvaominaisuus — deploy ilman code review -porttia:**
Jos käyttäjä on verifioinut session alussa että valvontatiedostot ovat muuttumattomia, hän voi luottaa että TREAD ajaa legitiimiä koodia. Tällöin pätee seuraava takuu:

> Mikä tahansa deploy joka ohittaa code_review.yml:n — esimerkiksi suoraan Render-dashboardilta tai API:n kautta tehty deploy — johtaa välittömään "Danger"-tilaan TREAD-palkissa ja Tampermonkeyssa, koska deployattu commit ei täsmää GitHubin main-branchin kanssa.

Tämä tarkoittaa että code review -workflow ei ole pelkästään koodilaatuportti — se on rakenteellinen turvaeste jonka ohittaminen on automaattisesti havaittavissa.

**Haavoittuva:**
- AI-arvio ei ole aukoton — hienostuneita muutoksia voi jäädä läpi
- Jos hyökkääjällä on GitHub-oikeus, hän voi muokata myös code_review.yml:ää

**Suojausaika session aikana:**
Code review lisää 2–3 minuutin pakotetun viiveen jokaisen muutoksen ja deployn välille. Tämä aika on käyttäjälle näkyvää varoitusaikaa (TREAD-palkki "Deploying"). Workflow itse ei varoita käyttäjää suoraan.

---

### 6. Hosting-ympäristö

Hosting-alustan valinta vaikuttaa merkittävästi järjestelmän turvallisuuteen. Nykyinen ympäristö on väliaikainen.

**Suojausaika session aikana:**
Riippuu täysin alustan eristystasosta. Alustat joissa prosessieristys on heikko voivat mahdollistaa hyökkäyksiä jotka eivät näy missään valvontakerroksessa — ei TREAD-palkissa, ei Tampermonkeyssa, ei Arweavessa.

---

## Hyökkäyksen aikajana — käyttäjä on verifioinut session alussa

Oletetaan että käyttäjä on tarkistanut ennen session alkua, että valvontatiedostoja ei ole muutettu kuukausiin. Hyökkäys alkaa session aikana.

```
t=0        Hyökkääjä committaa muutokset GitHubiin
           → Git tree muuttuu välittömästi

t=0–90s    TREAD-palkki jatkaa normaalia näyttöä (dispatcher ei ole vielä päivittynyt)
           → Tampermonkey havaitsee muutoksen VAIN jos sivu ladataan uudelleen

t=90s      _poide_dispatcher hakee päivitetyn status-log.jsonl:n
           → Jos muutos on valvontatiedostoissa: status.json raportoi uudet hashit
           → TREAD-palkki: ei vielä vaikutusta (dispatcher seuraa deploy-statusta)

t=2–3min   Code review -workflow käynnistyy ja valmistuu
           → TREAD-palkki näyttää "Deploying" ← KÄYTTÄJÄ NÄKEE VAROITUKSEN

t=3–13min  Render-deploy käynnissä
           → TREAD-palkki näyttää "Deploying" koko ajan
           → Käyttäjällä on 8–13 min näkyvää varoitusaikaa

t=13min    Kompromisoitu koodi on live
           → Jos dispatcher on kompromisoitu: TREAD-palkki palaa vihreäksi (väärä positiivi)
           → Tampermonkey havaitsee tiedostomuutoksen seuraavalla sivulatauksella

t=13min+   Käyttäjä on suojattu vain jos:
           a) lataa sivun uudelleen (Tampermonkey varoittaa), TAI
           b) Tampermonkey ei ole kompromisoitu ja status.json näyttää mismatchin
```

**Yhteenveto suojausajasta:**

| Vaihe | Kesto | Käyttäjän suoja |
|---|---|---|
| Commit → dispatcher päivittyy | 0–90 s | ❌ Ei varoitusta |
| Deploy käynnissä | 8–13 min | ✅ TREAD-palkki "Deploying" |
| Kompromisoitu koodi live, sivu ei ladattu | Kunnes reload | ⚠️ Ei varoitusta — riski |
| Käyttäjä lataa sivun uudelleen | Heti | ✅ Tampermonkey varoittaa |

**Käytännön suositus käyttäjälle:** Älä koskaan lähetä arkaluonteisia dokumentteja jos TREAD-palkki näyttää "Deploying" tai "Notice". Lataa sivu uudelleen ennen tärkeää toimenpidettä.

---

## Yhteenveto: suojaus eri uhkia vastaan

### Ulkoinen hyökkääjä (ei GitHub/Render-pääsyä)

| Uhka | Suojaus |
|---|---|
| Luvaton koodi Renderiin | Code review -workflow estää |
| Commit-väärennös | TREAD havaitsee commit-mismatchin |
| Valvontatiedostojen muokkaus | Vaatii GitHub-pääsyn |

✅ **Hyvin suojattu**

---

### Osittainen hyökkääjä (vain hosting-pääsy)

| Uhka | Suojaus |
|---|---|
| Luvaton deploy API:n kautta | TREAD havaitsee commit-mismatchin |
| Alustatason hyökkäys | Riippuu hosting-ympäristön eristystasosta |

⚠️ **Hosting-ympäristön valinta kriittinen — migraatio suunnitteilla**

---

### Osittainen hyökkääjä (vain GitHub-pääsy)

| Uhka | Suojaus |
|---|---|
| Valvontatiedostojen muokkaus | Tampermonkey havaitsee git tree API:lla seuraavalla sivulatauksella |
| Väärät hashit status.json:iin | Tampermonkey laskee hashit itse, ei luota status.json:iin |
| Deploy ilman koodiarvioita | Code review -workflow estää |

✅ **Hyvin suojattu**

---

### Ylläpito-hyökkääjä (GitHub + Render)

| Uhka | Suojaus |
|---|---|
| Kaikkien komponenttien muokkaus | Vaatii commitin → TREAD-palkki näyttää "Deploying" 8–13 min |
| Väärät hashit status.json:iin | Tampermonkey käyttää git tree API:a, ei luota status.json:iin |
| Deploy-aikaikkuna | Käyttäjällä 8–13 min näkyvää varoitusaikaa |
| Historian peittäminen | Arweave-arkisto on muuttumaton — aiempi oikea tila säilyy |
| Alustatason hyökkäys | Riippuu hosting-ympäristön eristystasosta |

⚠️ **Osittainen suojaus — havaittavissa deploy-aikana, mutta ei estettävissä. Täydellinen suojaus vaatii TEE:n.**

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
| Browserbase → Browserless | Tehty 2026-05-29 |

---

## Operaattorin luottamusvaatimus

Leima vaatii luottamuksen operaattoriin samoin kuin perinteinen notaari — ei enempää eikä vähempää. Järjestelmän valvontamekanismit tekevät mahdollisesta pettämisestä havaittavaa ja historiallisesti todistettavaa, mutta eivät täysin mahdotonta ilman TEE:tä. Tämä kommunikoidaan käyttäjille rehellisesti.
