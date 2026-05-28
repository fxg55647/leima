# Deploy-pipeline: miten homma toimii

Tämä dokumentti kuvaa Leiman deploy-prosessin. Päivitetään aina kun prosessi muuttuu.

Viimeksi päivitetty: 2026-05-29

---

## Yleiskuva

```
git push origin main
    ↓
GitHub Actions: POIDE Code Review (.github/workflows/code_review.yml)
    ↓ (koodiarvio + hyväksyntä)
Render: automaattinen deploy
    ↓
leima.io live
```

Mitään ei deployta manuaalisesti. Kaikki kulkee tämän putken läpi.

---

## Vaihe 1: git push

Agentti pushaa koodin mainiin. Ennen pushia:

1. Tarkista onko jokin workflow jo käynnissä:
   ```
   gh run list --limit 1 --workflow=code_review.yml --branch=main
   ```
   - `in_progress` → **älä pushaa**. Joko odota tai peru käynnissä oleva:
     ```
     gh run cancel <run_id>
     ```
   - `completed` → voidaan pushata normaalisti

2. Push foregroundissa (ei background):
   ```
   git push origin main
   ```
   TREAD-hookki tarkistaa deployment-statuksen ennen pushia ja estää jos jokin on vialla.

---

## Vaihe 2: POIDE Code Review (GitHub Actions)

Tiedosto: `.github/workflows/code_review.yml`

Workflow käynnistyy automaattisesti jokaisen main-pushin yhteydessä.

Workflow tekee järjestyksessä:
1. **Leima code review** — ajaa koodiarvion muuttuneista tiedostoista
2. **Deploy to Render and wait** — triggeroi Render-deployn ja odottaa sen valmistumista
3. **Wake up TREAD** — käynnistää TREAD-tarkistuksen (deployment-validointi)
4. **Complete job**

Kesto normaalisti: **5–10 minuuttia**.

### Seuranta pushin jälkeen

Heti pushin jälkeen agentti ajaa:
```
gh run watch <run_id> --exit-status
```
Tämä blokkaa kunnes workflow valmistuu ja palauttaa exit-koodin:
- `0` = success → koodi läpi, Render deployasi
- `1` = failure → jokin meni pieleen, ei deployta

**Aikaraja:** jos workflow ei valmistu 10 minuutissa, keskeytetään ja raportoidaan käyttäjälle. Ei jatketa sokkona.

Run ID:n saa pushin jälkeen:
```
gh run list --limit 1 --workflow=code_review.yml --branch=main
```

---

## Vaihe 3: Render deploy

Render triggeröityy automaattisesti kun GitHub Actions hyväksyy koodin.

Render ajaa:
1. **Build command** (settings.json tai Render dashboard):
   ```
   pip install -r requirements.txt
   ```
2. **Start command:**
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

Palvelu on live osoitteessa `leima.io` kun Render ilmoittaa "Your service is live".

---

## Tiheät korjaukset — toimintamalli

Jos tehdään useita korjauksia peräkkäin ennen kuin edellinen deploy on valmis:

**Vaihtoehto A — Peru ja pushaa uusin (nopea):**
```
gh run cancel <käynnissä_oleva_run_id>
git push origin main
```

**Vaihtoehto B — Odota ja pushaa vasta sitten (turvallinen):**
```
gh run watch <käynnissä_oleva_run_id> --exit-status
# odota valmistumista
git push origin main
```

Väliversion pushaaminen jonoon ei ole sallittua — se tuuttaa versioita toistensa päälle ja sekoittaa historian.

---

## Mikä voi mennä pieleen

| Ongelma | Syy | Ratkaisu |
|---|---|---|
| Workflow epäonnistuu heti | Koodiarvio hylkäsi | Korjaa koodi, pushaa uudelleen |
| Workflow jää roikkumaan | Render-deploy jumissa | `gh run cancel`, tutki Render-logit |
| "Browserbase not configured" | Env-muuttujat puuttuu Renderistä | Tarkista Render → Environment |
| Deploy onnistui mutta koodi ei muuttunut | Cache-ongelma | Render dashboard → Clear build cache and deploy |
| TREAD-hookki estää pushin | Edellinen deploy ei läpäissyt | Katso TREAD-status sivun yläpalkista |

---

## Ympäristömuuttujat (Render)

Nämä pitää olla asetettuna Renderin dashboardissa:

- `GEMINI_API_KEY`
- `BROWSERBASE_API_KEY`
- `BROWSERBASE_PROJECT_ID`
- `IRYS_PRIVATE_KEY`
- `NOTARY_IMAP_*` (sähköpostiominaisuutta varten)
- `GITHUB_DISPATCH_TOKEN`
- `LEIMA_URL`

---

## Versiohistoria tästä dokumentista

| Päivämäärä | Muutos |
|---|---|
| 2026-05-29 | Luotu. Kuvaa Browserbase + POIDE + Render -putken. |
| 2026-05-29 | Pre-push hookki estää pushin jos workflow käynnissä. Post-push käyttää gh run watch + asyncRewake. |
