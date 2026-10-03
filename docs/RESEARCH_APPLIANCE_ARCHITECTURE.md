# Leima Research Appliance — arkkitehtuuri

Tila: suunnitelma hyväksytty. Vaiheet A (USB-silta, paritus, `device_status`), D (pakettien
siirto PC:lle ja arkisto) ja B (selainohjaus ja selain-capture) toteutettu.
Muut vaiheet ovat tässä dokumentissa sopimuksena, eivät vielä koodina.

Liittyvät dokumentit:

- [`RESEARCH_APPLIANCE_USB_PROTOCOL.md`](RESEARCH_APPLIANCE_USB_PROTOCOL.md) — puhelimen ja PC:n välinen protokolla
- [`RESEARCH_APPLIANCE_PACKAGES.md`](RESEARCH_APPLIANCE_PACKAGES.md) — Android-pakettien yhteinen manifesti ja PC:n kansiorakenne
- [`MCP_SERVER.md`](MCP_SERVER.md) — Leiman julkinen `/mcp` (eri asia kuin tämä paikallinen silta)
- [`../android/README.md`](../android/README.md) — Android-sovelluksen rakentaminen

## 1. Mitä tämä on

Fyysinen Android-puhelin toimii agentin ohjaamana tutkimusselaimena ja paikallisena
todistevarastona. Agentti (Claude Desktop tai muu paikallinen MCP-asiakas) ohjaa puhelinta
USB:n kautta: avaa lähteen, havainnoi sivun, pyytää tarvittaessa ihmistä kirjautumaan ja
tallentaa lähteen capture-pakettina. Paketit siirretään PC:lle tarkistettuina ja poistetaan
puhelimesta vasta onnistuneen siirron jälkeen.

Tavoiteketju:

**Agentti → MCP → USB → puhelimen selain → paikallinen capture → eheyden tarkistus → PC:n arkisto.**

Tämä on kehittäjä- ja tehokäyttäjän työkalu: se vaatii puhelimen kehittäjätilan, USB-vianmäärityksen
ja Android platform-toolsin (ADB) PC:llä. Kuluttajatuote se ei ole.

## 2. Komponentit

```text
Claude Desktop / muu paikallinen MCP-asiakas
              │ MCP (JSON-RPC, stdio)
              ▼
  PC: leima-bridge  (bridge/, Python)
    ├── MCP-palvelin (stdio)          bridge/mcp_stdio.py — käyttää mcp_server.handle_messagea
    ├── ADB-ohjaus                    bridge/adb.py — laitevalinta, oma porttiohjaus
    ├── protokolla-asiakas            bridge/client.py — kättely, paritus, autentikointi
    ├── paritustiedot                 %APPDATA%\Leima\bridge.json (ei repossa)
    └── arkisto (vaihe D)             <repo>\evidence\  (gitignoroitu)
              │ TCP 127.0.0.1:<satunnainen portti>
              ▼
  adb forward tcp:0 localabstract:fi.leima.android.bridge
              │ USB
              ▼
  Android: Leima-sovellus (android/, Kotlin)
    ├── BridgeServer        LocalServerSocket + vertaisen UID-tarkistus
    ├── BridgeProtocol      viestien käsittely (puhdas JVM, yksikkötestattu)
    ├── PairingStore        paritettujen PC:iden token-tiivisteet
    ├── BrowserController   selainistunto, havainnot, toistosuoja, capture (puhdas JVM)
    ├── WebViewBrowserHost  WebView-kutsut pääsäikeessä, PixelCopy + peitot
    ├── assets/leima_page.js  ainoa sivulle ajettava skripti (havainto, klikkaus, kirjoitus, DOM)
    ├── ohjauspaneeli       (vaihe C)
    └── EvidenceStore & MeetingEvidenceStore   paikalliset paketit
```

### Miksi `localabstract` eikä TCP-portti puhelimessa

Androidissa `127.0.0.1` ei ole sovelluskohtainen: mikä tahansa puhelimen sovellus, jolla on
`INTERNET`-oikeus, voi avata yhteyden puhelimen loopback-porttiin. Siksi sovellus ei kuuntele
TCP:tä lainkaan. Se avaa abstraktin Unix-socketin `fi.leima.android.bridge` ja tarkistaa jokaisen
yhteyden avaajan käyttäjätunnuksen (`LocalSocket.getPeerCredentials().uid`). Hyväksytään vain

- `2000` (`shell`) — `adbd` välittää `adb forward` -yhteydet tällä tunnuksella,
- `0` (`root`) — `adb root` -tilassa; root pystyy joka tapauksessa kaikkeen.

Muiden sovellusten yhteydet suljetaan heti. Sama malli on Chromen etävianmäärityksessä
(`chrome_devtools_remote`).

### Miksi silti paritus ja token

UID-tarkistus todistaa vain, että yhteys tuli ADB:n kautta. PC:llä mikä tahansa prosessi voi
käyttää ADB:tä tai ottaa yhteyden sillan avaamaan paikalliseen porttiin. Siksi silta paritetaan
kerran puhelimella hyväksyttävällä menettelyllä (koodi näkyy sekä PC:llä että puhelimessa), ja
jokainen istunto autentikoidaan parituksessa saadulla tokenilla. Puhelin tallentaa vain tokenin
SHA-256-tiivisteen.

Uhkamalli, jota tämä **ei** kata: PC:n käyttäjätilin haltuunotto (hyökkääjä lukee `bridge.json`:n)
tai puhelimen haltuunotto. Rooted-puhelimen muut sovellukset voivat ohittaa UID-tarkistuksen.

### Rajapinta ei tarjoa ADB-shelliä

Silta käyttää ADB:tä vain laitteiden listaamiseen ja oman porttiohjauksensa luomiseen ja
poistamiseen. MCP-työkalut eivät koskaan välitä mielivaltaisia komentoja ADB:lle.

## 3. Vaiheet

| Vaihe | Sisältö | Tila |
|---|---|---|
| A | ADB-laitevalinta, porttiohjaus, kättely, paritus, autentikointi, `device_status` | toteutettu |
| D | Yhteinen pakettimanifesti, `package_verify`, pakettien siirto PC:lle ja poisto puhelimesta | toteutettu |
| B | Selainohjaus: `browser_navigate`, `browser_observe`, `browser_click`, `browser_type`, `browser_back`, `browser_screenshot`, `browser_capture` | toteutettu |
| C | Ihmiselle luovutus: tilakone ja puhelimen ohjauspaneeli | seuraava |
| E | Vientikäytännöt (agent-readable / local-only), lokien rajaus, salaisuuksien peitto | |
| F | Leima-liitos: uusi provenance `device_captured`, leimaus vain hasheista | |

Järjestys poikkeaa alkuperäisestä A–F:stä: siirto PC:lle (D) tehdään heti A:n jälkeen, koska se
käyttää samaa kanavaa ja hyödyttää heti myös nykyisiä kuva- ja meeting-paketteja.

## 4. Istunnon elinkaari

```text
bridge                                   puhelin
  │ adb devices -l → valitse laite
  │ adb forward tcp:0 localabstract:…
  │ ── TCP connect ─────────────────────▶ accept, UID-tarkistus
  │ ── hello ──────────────────────────▶  protokollaversio, paired?
  │ ── pair_begin (vain kerran) ──────▶   näytä dialogi + koodi → käyttäjä hyväksyy
  │ ◀───────────────────── token ──────
  │ ── auth(bridge_id, token) ────────▶   vertaa tiivisteeseen
  │ ◀──────────────── session_id ──────
  │ ── device_status / muut ──────────▶
  │ ── bye ───────────────────────────▶
  │ adb forward --remove tcp:<oma portti>
```

Puhelin hyväksyy yhden yhteyden kerrallaan. Toinen samanaikainen yhteys saa virheen `BUSY`.

USB-ohjaus on puhelimessa erikseen päälle kytkettävä asetus ("USB-ohjaus"). Kun se on pois,
socketia ei avata lainkaan.

### Katkokset

USB-katkos näkyy sillalle suljettuna yhteytenä. Silta ei toista komentoja automaattisesti.
Tilaa muuttavat selainkomennot (navigate, click, type, back, capture) kantavat sillan arpoman
`request_id`:n. Jos yhteys katkeaa kesken komennon, silta yhdistää kerran uudelleen ja kysyy
`command_status`-metodilla, mitä tapahtui. Jos lopputulos ei selviä, agentti saa virheen
`COMMAND_OUTCOME_UNKNOWN` ja ohjeen havainnoida sivu ennen uutta yritystä. Puhelin palauttaa
saman `request_id`:n toistolle tallennetun lopputuloksen eikä tee toimintoa kahdesti.

## 4b. Selainohjaus (vaihe B)

- **Selainistunto** (`session_id`) on puhelimessa sovelluksen käynnissäoloajan pituinen ja
  riippumaton USB-yhteyksistä. Jokainen MCP-työkalukutsu avaa oman yhteyden; havainto- ja
  elementtitunnisteet säilyvät silti.
- **Havainto** on voimassa vain seuraavaan tilaa muuttavaan komentoon tai sivunvaihtoon asti
  (myös ihmisen tekemään). Vanhentuneella havainnolla toiminto palauttaa `STALE_OBSERVATION`;
  se ei koskaan osu toiseen elementtiin. Myös epäonnistunut tilaa muuttava komento päättää havainnon.
- **Klikkaus ja kirjoitus** tehdään DOM-tasolla (`element.click()`, arvon asetus + `input`/`change`-
  tapahtumat). Tapahtumat eivät ole sivun silmissä käyttäjän tekemiä (`isTrusted = false`); osa
  sivuista voi ohittaa ne. Koordinaattitaputus lisätään vasta tarvittaessa.
- **Salaisuudet**: salasana- ja kertakoodikenttien (myös `autocomplete`-vihjeet) arvoja ei
  palauteta, niihin ei kirjoiteta (`SENSITIVE_FIELD`), ne maalataan mustiksi kuvakaappauksessa ja
  niiden `value`-attribuutit poistetaan `dom.html`:stä. Myös piilokenttien arvot ja CSRF-metat
  tyhjennetään. Kuvakaappausta ei viedä lainkaan, jos näkyvissä on cross-origin-kehys, koska sen
  kenttiä ei voi tunnistaa (`SCREENSHOT_BLOCKED`); capture merkitään silloin osittaiseksi.
- **Saatavuus**: agentti voi käyttää selainta vain, kun Selain-välilehti on näkyvissä, sovellus
  on etualalla eikä ihminen ole kesken omaa tallennustaan (`BROWSER_UNAVAILABLE`). Puhelimen
  tilarivi näyttää, mitä agentti viimeksi teki.
- **Vientikäytäntö**: vaiheessa B kaikki on *agent-readable*: `browser_observe` palauttaa sivun
  tekstin MCP-asiakkaalle. *local-only*-tila tulee vaiheessa E.
- **Kirjautuminen**: ihminen kirjautuu puhelimella itse. Hallittu luovutus (agentin komennot
  estetty, Jatka/Keskeytä-painikkeet) tulee vaiheessa C.

## 5. Todisteen merkitys ja rajat

Nämä pätevät kaikkiin vaiheisiin ja näkyvät myös käyttäjälle:

- `dom.html` (vaihe B/D) on selaimen DOM:n sarjallistus capture-hetkellä, ei palvelimen
  alkuperäinen HTTP-vastaus eikä täydellinen sivuarkisto.
- Varmennetiedot luetaan `WebView.getCertificate()`-kutsulla (nykyisen sivun varmenne).
  `onReceivedSslError` laukeaa vain virhetilanteissa, eikä sovellus koskaan ohita TLS-virheitä.
- Redirect-ketjua tai HTTP/TLS-metadataa ei luvata kattavasti; tallennetaan vain havaittu.
- DOM, teksti ja kuva voivat tallentua hieman eri hetkinä. Pakettia ei kutsuta atomiseksi.
- Sivulle ajettava havainto-JavaScript on sivun havaittavissa. Sovellus ei väitä havainnoinnin
  olevan näkymätöntä.
- SHA-256 todistaa vain eheyden suhteessa vertailutiivisteeseen — ei alkuperää, aikaa eikä
  väitteen totuutta. Laitteen kello ja anturit eivät ole riippumattomasti varmennettuja.

### Kaksi kerrosta pidetään erillään

1. Puhelimen tekemä lähdetallennus (capture-paketti, hashit).
2. Verifierin arvio lähteen ja väitteen suhteesta (AI-verdict).
3. Tiivisteiden ja arvion ulkoinen leimaus (Arweave, vain hashit).

Puhelimen capture ei koskaan saa provenance-arvoa `fetched_by_leima`, koska Leiman palvelin ei
hakenut lähdettä. Vaiheessa F lisätään arvo `device_captured` nykyisten `fetched_by_leima` ja
`agent_supplied` rinnalle.

## 6. Tietosuoja (vaihe E, periaatteet sovittu jo nyt)

- **local-only** on oletus kirjautumista vaativille sivuille: MCP-vastauksiin ei palauteta
  sivun tekstiä, DOM:ia eikä kuvia, vain sallittu metadata ja hashit.
- **agent-readable**: teksti ja kuvat palautetaan MCP-asiakkaalle. Jos asiakas käyttää
  pilvimallia (esim. Claude Desktop), sisältö siirtyy pilvipalveluun.
- Evästeet, bearer-tokenit ja salasanakenttien arvot eivät koskaan päädy havaintoihin,
  lokeihin eikä manifesteihin.
- Paketit tallennetaan sovelluksen yksityiseen tallennustilaan; Androidin automaattinen
  varmuuskopiointi on pois päältä (`allowBackup="false"`).
- PC:n arkisto on repon alla `evidence/`-kansiossa, joka on gitignoroitu. Jos repo-kansio
  synkronoituu pilveen (OneDrive tms.), paketit synkronoituvat mukana.

## 7. Käyttöönotto Windowsilla (vaihe A)

1. Asenna Android platform-tools (tulee Android Studion mukana). Silta etsii `adb.exe`:n
   järjestyksessä `LEIMA_ADB`, `PATH`, `%LOCALAPPDATA%\Android\Sdk\platform-tools`, `ANDROID_HOME`.
2. Puhelimessa: kehittäjätila ja USB-vianmääritys päälle, kytke kaapeli, hyväksy PC:n
   RSA-avain. `python -m bridge devices` näyttää laitteen tilassa `device`.
3. Avaa Leima-sovellus ja kytke **USB-ohjaus (ADB)** päälle.
4. Parita kerran: `python -m bridge pair`. Hyväksy puhelimen dialogi vain, jos koodi on sama
   kuin PC:llä. Token tallentuu `%APPDATA%\Leima\bridge.json`:iin.
5. Testaa: `python -m bridge status`.
6. Siirrä paketit: `python -m bridge sync` (ks. [`RESEARCH_APPLIANCE_PACKAGES.md`](RESEARCH_APPLIANCE_PACKAGES.md)).
7. Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "leima-phone": {
      "command": "C:\\projects\\stampd\\.venv\\Scripts\\python.exe",
      "args": ["C:\\projects\\stampd\\bridge\\__main__.py", "mcp"]
    }
  }
}
```

MCP-työkalut: `device_status`, `packages_list`, `packages_sync`, `package_verify` (vain
metatietoja ja tiivisteitä) sekä selaintyökalut `browser_navigate`, `browser_observe`,
`browser_click`, `browser_type`, `browser_back`, `browser_screenshot` (palauttaa kuvan) ja
`browser_capture`. `browser_observe` ja `browser_screenshot` palauttavat sivun sisältöä
MCP-asiakkaalle.

Paritus tehdään aina CLI:llä, ei MCP-työkalulla: agentti ei voi parittaa itseään.
Puhelimen **Poista PC-paritukset** -painike mitätöi kaikki tokenit; `python -m bridge unpair`
poistaa vain tämän PC:n.

Testit: `.venv\Scripts\python.exe -m pytest tests/test_bridge.py tests/test_bridge_packages.py` ja
`android\gradlew.bat :app:testDebugUnitTest` (`BridgeProtocolTest`, `PackageTransferTest`,
`BrowserControllerTest`). Sivuskripti ajetaan Chromiumissa: `pytest -m browser tests/browser/test_leima_page_js.py`.
Python: myös `tests/test_bridge_browser.py`. Laitteella ajettavaa
päästä päähän -testiä ei ole automatisoitu.

## 8. Myöhemmät kokonaisuudet (eivät kuulu MVP:hen)

Credential vault, useat selainprofiilit, jatkuva videostream, paikallinen AI-verifier
(`LOCAL_VERIFIER_UNAVAILABLE`, jos ei käytettävissä — ei hiljaista pilvimallia), laitteen
attestointi ja pilviagentin pääsy paikalliseen siltaan. `submit_evidence` ja `evaluate_claim`
tulevat MVP:n jälkeen; `relation` (`FOR`/`AGAINST`/`CONTEXT`) on ehdotettu rooli, ei verdict.
