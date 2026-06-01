# Deploy-pipeline: miten homma toimii

Tämä dokumentti kuvaa Leiman deploy-prosessin. Päivitetään aina kun prosessi muuttuu.

Viimeksi päivitetty: 2026-06-01

---

## Yleiskuva

```
git push origin main
    ↓
GitHub Actions: POIDE Code Review (.github/workflows/code_review.yml)
    ↓ (koodiarvio + hyväksyntä)
Vercel: deploy API-kutsuilla (target: production)
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
2. **Deploy to Vercel and wait** — triggeroi Vercel-deployn API-kutsuilla (target: production) ja odottaa sen valmistumista
3. **Wake up TREAD** — käynnistää TREAD-tarkistuksen (deployment-validointi)
4. **Complete job**

Kesto normaalisti: **5–10 minuuttia**.

**Turvaominaisuus:** Code review -workflow on ainoa laillinen deploy-reitti. Jos deploy tapahtuu tämän putken ulkopuolelta, deployattu commit ei täsmää GitHubin main-branchin kanssa — TREAD havaitsee tämän välittömästi ja näyttää "Danger"-tilan. Tämä takuu on voimassa kun käyttäjä on verifioinut session alussa että valvontatiedostot ovat muuttumattomia.

### Seuranta pushin jälkeen

Heti pushin jälkeen agentti käynnistää `/loop` 2 minuutin välein:
```
gh run list --workflow code_review.yml --limit 1 --json databaseId,status,conclusion
```
- `completed` + `success` → raportoi käyttäjälle, lopeta loop
- `completed` + muu → raportoi failure, lopeta loop
- ei valmis + alle 8 min → jatka loopia
- 8 min kulunut → raportoi timeout, lopeta loop

---

## Vaihe 3: Vercel deploy

Workflow triggeroi Vercel-deployn API-kutsuilla code reviewin hyväksymisen jälkeen. Auto-deploy git-pushista on estetty "Ignored Build Step: exit 0" -asetuksella.

Vercel ajaa:
1. **Build command:** `pip install -r requirements.txt`
2. **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

Palvelu on live osoitteessa `leima.io` kun Vercel ilmoittaa status `READY`.

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
| Workflow jää roikkumaan | Vercel-deploy jumissa | `gh run cancel`, tutki Vercel-logit |
| "Browserless not configured" | Env-muuttujat puuttuu Vercelistä | Tarkista Vercel → Environment Variables |
| Deploy onnistui mutta koodi ei muuttunut | Cache-ongelma | Vercel dashboard → Redeploy with cleared cache |
| TREAD-hookki estää pushin | Edellinen deploy ei läpäissyt | Katso TREAD-status sivun yläpalkista |

---

## Ympäristömuuttujat (Vercel)

Nämä pitää olla asetettuna Vercel-projektin Environment Variables -osiossa:

- `GEMINI_API_KEY`
- `BROWSERLESS_API_KEY`
- `IRYS_PRIVATE_KEY`
- `NOTARY_IMAP_*` (sähköpostiominaisuutta varten)
- `GITHUB_DISPATCH_TOKEN`
- `LEIMA_URL`

---

## Versiohistoria tästä dokumentista

## Tietoturvahuomiot

**Operaattorin luottamusvaatimus:** Leima vaatii luottamuksen operaattoriin samoin kuin notaari — ei enempää eikä vähempää. Tämä pitää kommunikoida käyttäjille rehellisesti.

---

## Versiohistoria

| Päivämäärä | Muutos |
|---|---|
| 2026-05-29 | Luotu. Kuvaa Browserbase + POIDE + Render -putken. |
| 2026-05-29 | Pre-push hookki estää pushin jos workflow käynnissä. Post-push käyttää gh run watch. asyncRewake poistettu — ei luotettava aktiivisessa chatissa. push.ps1 synkroninen vaihtoehto. |
| 2026-05-29 | Tietoturvatesti: /proc/mem readable, seccomp=0. Docker tarvitaan muistieristykseen. |
| 2026-05-29 | Browserbase → Browserless (sessioraja ylittyi). Seuranta: gh run watch → /loop 2min välein. |
| 2026-06-01 | Render → Vercel. Deploy API-kutsuilla (target: production). Auto-deploy estetty exit 0. |
