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
1. Muokata main.py ja committaa → **Tampermonkey havaitsee tiedostomuutoksen**
2. Odottaa code review -workflow (2–3 min)
3. Odottaa Render-deploy (5–10 min) → **TREAD-palkki näyttää "Deploying"**

Käyttäjä saa siis kaksi varoitusta ennen kuin kompromisoitu koodi on edes live.

**Haavoittuva:**
- Dispatcher luottaa status.json:iin dispatcherin oman verifiointilogiikan puuttuessa
- Jos Render-ympäristö on kompromisoitu (ptrace), muistissa oleva tieto voidaan väärentää ilman uutta deployia

---

### 5. Code review -workflow (code_review.yml)

Jokaisen git push:n jälkeen automaattisesti ajettava workflow, joka toimii deployn portinvartijana.

**Suojaa:**
- AI-koodiarvio havaitsee ilmeiset haitalliset muutokset
- Render-deploy ei käynnisty ilman workflown hyväksyntää
- Pre-push TREAD-hookki estää pushin jos edellinen deploy ei ole vakaa

**Haavoittuva:**
- AI-arvio ei ole aukoton — hienostuneita muutoksia voi jäädä läpi
- Jos hyökkääjällä on GitHub-oikeus, hän voi muokata myös code_review.yml:ää

---

### 6. Render-ympäristö

**Tunnistettu kriittinen haavoittuvuus:**
Renderin natiivi Python-ympäristö (ei Dockeria) sallii:
- `/proc/<pid>/mem` luettavissa — käynnissä olevan prosessin muisti ei ole suojattu
- `seccomp: 0` — ei järjestelmäkutsusuodatusta, ptrace todennäköisesti sallittu

**Vaikutus:** Render-dashboardiin pääsevä hyökkääjä voi muokata muistia suoraan ilman uutta deployia. TREAD ei havaitsisi tätä, koska commit-hash ei muutu.

**Ratkaisu:** Siirtyminen Lambda/TEE-ympäristöön (suunniteltu).

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

### Osittainen hyökkääjä (vain Render-pääsy)

| Uhka | Suojaus |
|---|---|
| Muistin manipulointi (ptrace) | ❌ Ei suojaa — kriittinen haavoittuvuus |
| Uusi luvaton deploy | TREAD havaitsee commit-mismatchin |

⚠️ **Ptrace-haavoittuvuus tunnistettu — migraatio suunnitteilla**

---

### Osittainen hyökkääjä (vain GitHub-pääsy)

| Uhka | Suojaus |
|---|---|
| Valvontatiedostojen muokkaus | Tampermonkey havaitsee git tree API:lla heti |
| Väärät hashit status.json:iin | Tampermonkey laskee hashit itse, ei luota status.json:iin |
| Deploy ilman koodiarvioita | Code review -workflow estää |

✅ **Hyvin suojattu**

---

### Ylläpito-hyökkääjä (GitHub + Render)

| Uhka | Suojaus |
|---|---|
| Kaikkien komponenttien muokkaus | Vaatii commitin → Tampermonkey havaitsee |
| Väärät hashit status.json:iin | Tampermonkey käyttää git tree API:a, ei luota status.json:iin |
| Deploy-aikaikkuna | Käyttäjä näkee "Deploying"-varoituksen + Tampermonkey-hälytyksen ennen kuin kompromisoitu koodi on live |
| Historian peittäminen | Arweave-arkisto on muuttumaton — aiempi oikea tila säilyy |
| Muistin manipulointi | ❌ Ei suojaa (ptrace) |

⚠️ **Osittainen suojaus — havaittavissa mutta ei estettävissä. Täydellinen suojaus vaatii TEE:n.**

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
Render-ympäristö                    — matalin, ptrace-haavoittuvuus
```

---

## Avoimet asiat

| Asia | Tila |
|---|---|
| Render → Lambda/TEE -migraatio | Suunniteltu — ptrace-haavoittuvuuden poistaminen |
| Tampermonkey-baseline session alussa | Suunniteltu — status-log.jsonl:n stabiliteetin tarkistus |
| Browserbase → Browserless | Tehty 2026-05-29 |

---

## Operaattorin luottamusvaatimus

Leima vaatii luottamuksen operaattoriin samoin kuin perinteinen notaari — ei enempää eikä vähempää. Järjestelmän valvontamekanismit tekevät mahdollisesta pettämisestä havaittavaa ja historiallisesti todistettavaa, mutta eivät täysin mahdotonta ilman TEE:tä. Tämä kommunikoidaan käyttäjille rehellisesti.
