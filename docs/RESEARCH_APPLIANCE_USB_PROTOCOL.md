# Leima USB-protokolla v1

Puhelimen (Leima Android) ja PC:n sillan (`bridge/`) välinen protokolla.
Arkkitehtuuri: [`RESEARCH_APPLIANCE_ARCHITECTURE.md`](RESEARCH_APPLIANCE_ARCHITECTURE.md).

Toteutukset:

- Android: `android/app/src/main/java/fi/leima/android/bridge/` (`BridgeProtocol.kt`, `PairingStore.kt`, `BridgeServer.kt`)
- PC: `bridge/client.py`, `bridge/adb.py`
- Testit: `android/app/src/test/java/fi/leima/android/bridge/`, `tests/test_bridge.py`

## 1. Kuljetus

- Puhelin: abstrakti Unix-socket `fi.leima.android.bridge`. Vertaisen UID:n on oltava `2000`
  (shell) tai `0` (root); muuten yhteys suljetaan ilman vastausta.
- PC: `adb -s <serial> forward tcp:0 localabstract:fi.leima.android.bridge` — ADB valitsee
  vapaan portin ja tulostaa sen. Silta poistaa sulkeutuessaan vain tämän oman ohjauksensa
  (`adb -s <serial> forward --remove tcp:<portti>`).
- Kehys: yksi UTF-8 JSON-objekti per rivi, rivinvaihto `\n`. Rivin enimmäispituus 1 MiB;
  pidempi rivi katkaisee yhteyden.
- Yksi pyyntö kerrallaan: asiakas odottaa vastauksen ennen seuraavaa pyyntöä.
- Puhelin palvelee yhtä yhteyttä kerrallaan. Ylimääräinen yhteys saa yhden virherivin
  (`BUSY`, `id: null`) ja suljetaan.

## 2. Viestit

Pyyntö:

```json
{"id": 1, "method": "hello", "params": {}}
```

Vastaus, onnistunut / virhe:

```json
{"id": 1, "result": {}}
{"id": 1, "error": {"code": "NOT_AUTHENTICATED", "message": "..."}}
```

`id` on asiakkaan valitsema kokonaisluku, joka palautetaan sellaisenaan. Jäsentämätön pyyntö
saa `id: null`.

## 3. Metodit

| Metodi | Vaatii auth | Tarkoitus |
|---|---|---|
| `hello` | ei | Protokollaversio, sovelluksen versio, onko silta jo paritettu |
| `pair_begin` | ei | Pyydä paritusta; vastaus tulee vasta kun käyttäjä hyväksyy puhelimella |
| `auth` | ei | Avaa istunto parituksessa saadulla tokenilla |
| `device_status` | kyllä | Laitteen tiedot ja toteutetut ominaisuudet |
| `unpair` | kyllä | Poistaa tämän sillan parituksen puhelimesta |
| `bye` | ei | Lopettaa yhteyden siististi |

Ennen `hello`-viestiä kaikki muut metodit palauttavat `HELLO_REQUIRED`.

### `hello`

```json
→ {"id":1,"method":"hello","params":{"protocol_versions":[1],"bridge_id":"b_3f…","bridge_name":"DESKTOP-H79NRLA"}}
← {"id":1,"result":{"protocol_version":1,"app":"fi.leima.android","app_version":"0.1.0","paired":true}}
```

- `protocol_versions`: asiakkaan tukemat versiot. Jos yhteistä ei ole: `UNSUPPORTED_PROTOCOL`.
- `bridge_id`: sillan pysyvä satunnainen tunniste (`b_` + 32 hex-merkkiä), luodaan kerran.
- `bridge_name`: näytetään puhelimen paritusdialogissa (enintään 64 merkkiä).
- `paired`: onko puhelimella tallennettu token tälle `bridge_id`:lle.

### `pair_begin`

```json
→ {"id":2,"method":"pair_begin","params":{"code":"482913"}}
← {"id":2,"result":{"token":"<43 merkkiä base64url>"}}
```

- `code`: sillan arpoma 6-numeroinen koodi, jonka silta näyttää käyttäjälle. Puhelin näyttää
  saman koodin dialogissa yhdessä `bridge_name`:n kanssa; käyttäjä hyväksyy vain, jos koodit
  täsmäävät.
- Puhelin vastaa vasta, kun käyttäjä hyväksyy (`token`) tai hylkää (`PAIRING_REJECTED`), tai
  120 sekunnin jälkeen (`PAIRING_TIMEOUT`). Asiakkaan lukuaikakatkaisun pitää olla pidempi.
- Token: 32 satunnaistavua base64url-muodossa ilman täytettä. Puhelin tallentaa vain sen
  SHA-256-tiivisteen; uusi paritus korvaa saman `bridge_id`:n vanhan tokenin.
- Jos paritusdialogi on jo auki: `PAIRING_BUSY`.

### `auth`

```json
→ {"id":3,"method":"auth","params":{"token":"…"}}
← {"id":3,"result":{"session_id":"s_9c…"}}
```

Token tarkistetaan `hello`:ssa ilmoitettua `bridge_id`:tä vastaan vakioaikaisella vertailulla.
Väärä tai tuntematon token: `AUTH_FAILED`. Istunto on voimassa yhteyden ajan.

### `device_status`

```json
← {"id":4,"result":{
    "protocol_version":1,
    "session_id":"s_9c…",
    "app_version":"0.1.0",
    "device":{"manufacturer":"Google","model":"Pixel 7","android_api":35,"android_release":"15"},
    "webview_version":"129.0.6668.100",
    "capabilities":["device_status"],
    "browser":{"state":"NOT_AVAILABLE"}
  }}
```

`capabilities` listaa toteutetut metodit; silta ja agentti käyttävät sitä ominaisuuksien
tunnistamiseen versionumeron sijaan. Vaihe A: `["device_status"]`.

### `unpair`

Poistaa puhelimesta tämän `bridge_id`:n tokenin. Silta poistaa omasta `bridge.json`:staan
saman laitteen tokenin.

## 4. Virhekoodit

| Koodi | Merkitys |
|---|---|
| `BAD_REQUEST` | Jäsentämätön JSON, puuttuva kenttä tai väärä tyyppi |
| `HELLO_REQUIRED` | Metodi ennen `hello`-viestiä |
| `UNSUPPORTED_PROTOCOL` | Ei yhteistä protokollaversiota |
| `UNKNOWN_METHOD` | Tuntematon metodi |
| `NOT_AUTHENTICATED` | Metodi vaatii `auth`-istunnon |
| `AUTH_FAILED` | Token ei kelpaa tälle sillalle |
| `PAIRING_REJECTED` | Käyttäjä hylkäsi parituksen |
| `PAIRING_TIMEOUT` | Käyttäjä ei vastannut 120 sekunnissa |
| `PAIRING_BUSY` | Toinen paritus on jo kesken |
| `BUSY` | Puhelin palvelee jo toista yhteyttä |
| `INTERNAL` | Odottamaton virhe puhelimessa |

Sillan omat (ei protokollan) virheet MCP-asiakkaalle: `ADB_NOT_FOUND`, `NO_DEVICE`,
`MULTIPLE_DEVICES`, `DEVICE_UNAUTHORIZED` (USB-vianmääritystä ei hyväksytty puhelimella),
`DEVICE_OFFLINE`, `APP_NOT_LISTENING` (sovellus ei käynnissä tai USB-ohjaus pois päältä),
`NOT_PAIRED`, `CONNECTION_LOST`.

## 5. Versiointi ja laajennukset

Uudet metodit lisätään versioon 1 ja ilmoitetaan `capabilities`-listassa. Versio nostetaan vain,
jos olemassa olevan metodin merkitys muuttuu. Vaiheiden B–F metodit (suunniteltu, ei toteutettu):

- B: `browser.navigate`, `browser.observe`, `browser.click`, `browser.type`, `browser.back`, `browser.screenshot`
  — muuttavat komennot kantavat `request_id`:n; `command_status(request_id)` katkoksen jälkeen.
- C: `browser.request_human`, `browser.resume`, `browser.end_session`
- D: `packages.list`, `packages.read(package_id, offset, length)`, `packages.delete(package_id, sha256)`

Puhelimen sisäiset metodinimet ovat pisteellisiä; MCP-työkalut käyttävät alaviivoja
(`browser_navigate` jne.).
