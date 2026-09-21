# Leiman testit

## Asennus ja ajo

Python 3.12. Projektin juuressa, aktiivisessa virtuaaliympäristössä:

```sh
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -m "not browser"
python -m pytest tests/browser
```

Windowsin olemassa olevalla ympäristöllä Python-komennon voi korvata komennolla
`.venv\Scripts\python.exe`. `uv pip install -r requirements-dev.txt` toimii myös.
Linuxin CI-asennuksessa selaimen asennuskomentoon lisätään `--with-deps`.

Näkyvä selain PowerShellissä:

```powershell
$env:HEADED = '1'
.venv\Scripts\python.exe -m pytest tests/browser -x
Remove-Item Env:HEADED
```

Jokainen selaintesti tallentaa kuvan ja Playwright-jäljen hakemistoon
`test-results/<testin nimi>/`. Jälki avataan näin:

```sh
python -m playwright show-trace "test-results/<testin nimi>/trace.zip"
```

`TEST_BROWSER=firefox` tai `TEST_BROWSER=webkit` vaihtaa selaimen, kun vastaava
selain on asennettu Playwrightilla. Ensimmäinen toteutus on varmennettu Chromiumilla.

## Testien rajat

- `tests/test_integrity.py`: oikea `/ask` → `/files` → `package.zip`-lataus → `/validate`,
  sekä `/check-correspondence` ja bundle-haara (`/ask` `active_tab=bundle`). PDF:t, manifesti
  (stamp_format_version=2) ja ZIP tuotetaan oikealla sovelluskoodilla. Vain Gemini ja
  Irys/Arweave korvataan testivastauksilla. Muutettu sisältötiedosto, manifesti ja
  ketjutietue hylätään; yhteysvirhe ei tuota onnistumista. Kattaa myös leimauksen
  idempotenssin (uudelleenyritys epäonnistumisen jälkeen, ei tuplajulkaisua onnistumisen
  jälkeen) ja sen, että pakatun ZIP-kuoren muuttaminen samoilla sisältötavuilla ei riko
  validointia.
- `tests/test_evidence_package.py`: `evidence_package`-moduulin ZIP-lukijan/-kirjoittajan
  yksikkötestit — puuttuva/ylimääräinen jäsen, duplikaattinimi, polkuhyökkäykset, väärä
  versio, virheelliset JSON-tyypit, JSON:n duplikaattiavaimet, salattu/tukematon jäsen,
  liian suuri paketti, viallinen ZIP.
- `tests/test_analysis.py`: AI-analyysien riippumattomuus, synteesin syötteet ja
  hylätyn aineiston käsittelyn keskeytyminen. Ei mittaa oikean mallin laatua.
- `tests/test_tread_monitor.py`: palvelimen tarkistus, muutoksen havaitseminen ja
  palautuminen, julkaistavan SHA:n katselmointikysely, tuntematon julkaisulähde,
  API-häiriö ja julkaisusignaalin ohittama välimuisti.
- `tests/test_tread_script.py`: oikea `tread_check.py` suoritetaan väliaikaiseen
  hakemistoon, HTTP-vastaukset simuloidaan. Normaali tila, SHA-poikkeama, julkaisu,
  GitHub-häiriö, vanhentunut ajastus ja poistettu workflow.
- `tests/browser`: oikea FastAPI-palvelin satunnaisessa localhost-portissa ja
  oikea selain. TREADin palveluvastauksia ohjataan selaimen verkkorajalla;
  validointilomake käyttää oikeaa backendia. Testataan myös erikseen julkaistava
  `validator.html` sen omalla selaimen sisäisellä ZIP-lukijalla (tarjoillaan
  testipalvelimelta väliaikaisesta reitistä, Arweave-gateway mockataan). Testataan
  myös 360 px ja 1440 px leveydet.
- Olemassa olevat selainkaappauksen Python-testit ja Android-paketin tarkistimen
  Python-testit kuuluvat pytestin oletusajoon. Androidin laitetestit eivät kuulu siihen.

`.env`-tiedostoa ei lueta testien aikana. Uusien testien requests-kutsut ja
ulkoiset socket-yhteydet estetään oletuksena; sallitut palveluvastaukset määritellään
testikohtaisesti. Selain saa vain paikallisen sovelluksen, testivastaukset ja
paikallisen HTMX-kopion. Testit eivät leimaa oikeaan Arweaveen tai lähetä sähköpostia.
`test_gemini.py` ja `test_webhook.py` ovat erillisiä käsin ajettavia diagnostiikkatyökaluja,
eivätkä kuulu oletusajoon.

## CI ja jatkokattavuus

`tests.yml` ajaa backend- ja Chromium-testit pull requesteille sekä staging/main-pusheille.
Raportit ja selainjäljet säilyvät Actions-artifakteina seitsemän päivää.
Tuotannon deploy-workflow ajaa testit ennen julkaisusignaaleja ja koodikatselmointia.
Workflowt tulevat käyttöön vasta muutosten pushauksen jälkeen.

Tämä on ensimmäinen toimiva testikerros, ei koko sovelluksen kattavuuslupaus.
Seuraavaksi tarvitaan kaikkien syötetapojen selainpolut, sähköpostin MIME/DKIM,
saavutettavuuden axe-tarkistukset, hyväksyttävät kuvavertailut, näppäimistökäyttö,
verkon vastausjärjestyksen kilpailutilanteet, varoitusten 24 tunnin vaimennus sekä
aidot palveluintegraatiot erillisessä ympäristössä. Web-page-korrespondenssitarkistuksen
onnistumispolku (oikea nykyisen sivun uudelleenhaku) on tässä testattu vain
kielteisiltä poluilta (puuttuva source-index, virheellinen ankkuri) — onnistumispolku
vaatisi turvallisen tavan simuloida `_safe_get`-hakua verkkoon koskematta, mikä on
jätetty myöhemmäksi.
TREADin koko GitHub → hosting → Arweave -ketjua ei tässä ajeta oikeita palveluja vasten.
Automaattitesti ei myöskään todista hosting-palvelussa ajettavan koodin aitoutta.

## Testien selainriippuvuus

`tests/browser/vendor/htmx-2.0.3.min.js` vastaa sovelluksen käyttämää HTMX 2.0.3:a:
https://unpkg.com/htmx.org@2.0.3/dist/htmx.min.js
Lisenssi on viereisessä `HTMX-LICENSE`-tiedostossa. Päivitä testiassetti samalla kun
sovelluksen HTMX-versio vaihtuu. Fontit ja analytiikka eivät ole osa offline-testejä.
