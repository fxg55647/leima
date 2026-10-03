# Android-paketit ja PC:n arkisto

Tila: toteutettu kaikille neljälle lajille (photo, screenshot, meeting, browser).

Toteutus: `android/tools/verify_package.py` (tarkistin), `bridge/archive.py` (arkisto),
`bridge/client.py` (`sync`), Android `bridge/PackageRepository.kt`. Testit: `tests/test_bridge_packages.py`,
`PackageTransferTest.kt`.
Arkkitehtuuri: [`RESEARCH_APPLIANCE_ARCHITECTURE.md`](RESEARCH_APPLIANCE_ARCHITECTURE.md).

Palvelimen analyysileimat (`PACKAGE_FORMAT.md`, `stamp_format_version 2`) ovat eri formaatti
eivätkä kuulu tähän dokumenttiin.

## 1. Yhteinen kuori kaikille Android-paketeille

Androidilla on nyt kaksi pakettia (kuva/kuvakaappaus ja meeting) ja vaiheessa B tulee kolmas
(selain-capture). Niillä on jo sama runko, joka kiinnitetään yhteiseksi kuoreksi:

```text
<paketti>.zip
  manifest.json      {"schemaVersion", "algorithm": "SHA-256", "kind", "files": {nimi: sha256hex}}
  manifest.sha256    "<sha256(manifest.json)>  manifest.json\n"
  …sisältötiedostot, jotka kaikki on listattu files-kentässä
```

Kuoren säännöt, jotka yksi tarkistin (`android/tools/verify_package.py`) varmistaa kaikille lajeille:

1. ZIPissä ei ole päällekkäisiä nimiä, absoluuttisia polkuja eikä `..`-osia.
2. `manifest.sha256` täsmää `manifest.json`:n tavuihin.
3. ZIPin nimet = `files`-avaimet ∪ `{manifest.json, manifest.sha256}` ∪ lajin sallimat
   manifestin ulkopuoliset tiedostot (meeting: `signature.json`).
4. Jokaisen tiedoston SHA-256 täsmää.
5. Lajikohtaiset tarkistukset (alla).

Uusi kenttä `kind` lisätään manifestiin. Puhelimessa jo olevat vanhat paketit (ilman `kind`-kenttää)
tunnistetaan sisällöstä, joten niitä ei tarvitse muuntaa:

| `kind` | Tunnistus vanhasta paketista | Sisältö | Lajikohtainen tarkistus |
|---|---|---|---|
| `photo` | `photo.jpg` | `photo.jpg`, `metadata.json` | metadata on JSON |
| `screenshot` | `screenshot.png` + `metadata.json`, ei `dom.html` | `screenshot.png`, `metadata.json` | metadata on JSON |
| `meeting` | `signature.json` | ks. `android/docs/meeting_v2_schema.md` | ECDSA-allekirjoitus (`meeting_crypto.py`) |
| `browser` | — (uusi) | `metadata.json`, `observation.json`, `dom.html`, `visible-text.txt`, `screenshot.png` (valinnainen) | `captureStatus` = `complete` (kaikki tiedostot, `missing` tyhjä) tai `partial` (`missing` listaa puutteet) |

`browser`-paketin `metadata.json` (Android `BrowserController.captureNow`): `kind`, `captureStatus`,
`missing`, `requestedAt`, `completedAt`, `durationMs`, `clock` (`device_wall_clock`, ei varmennettu),
`url` ja `requestedUrl` (fragmentti pois, salaisen nimiset kyselyparametrit `REDACTED`), `title`,
`exportPolicy` (capture-hetken vientikäytäntö sivulle: `AGENT_READABLE` / `LOCAL_ONLY`),
`certificate` (lehtivarmenne, ei ketjua), `appVersion`, `webViewVersion`, `device`, `browserSession`,
`captureMethod` (tiedostoittain), `redactions`, `timing` ja `scope`. `dom.html` on DOM:n
sarjallistus (attribuutit, ei kirjoitettuja kenttäarvoja), ei palvelimen alkuperäinen vastaus.

Manifestin kanoninen muoto: puhelin kirjoittaa sen kerran ja tarkistin hashaa täsmälleen saadut
tavut. Uudelleenserialisointia ei tehdä koskaan.

## 2. Siirto puhelimesta PC:lle (`leima-bridge sync`)

1. `packages.list` palauttaa jokaisesta valmiista paketista `package_id`, `kind`, `size`,
   `sha256` (koko ZIPin tavuista) ja `created_at`. Keskeneräiset (`.partial`) eivät näy.
2. Silta lukee paketin 256 KiB:n paloina (`packages.read`), laskee ZIPin SHA-256:n ja vertaa listaukseen.
3. Silta ajaa kuoren ja lajin tarkistuksen ZIPille.
4. Silta kirjoittaa ZIPin väliaikaiseen tiedostoon arkistoon, `fsync`:aa sen, nimeää sen
   lopulliseksi ja lisää rivin `index.jsonl`:ään.
5. Vasta tämän jälkeen silta kutsuu `packages.delete(package_id, sha256)`. Puhelin poistaa paketin
   vain, jos tiiviste täsmää edelleen.

Jos jokin vaihe epäonnistuu, paketti jää puhelimeen ja virhe raportoidaan. Jos sama ZIP
(sama sha256) on jo indeksissä, silta laskee arkistokopion tiivisteen uudelleen ennen puhelimen
kopion poistoa. Ehjä kopio jätetään sellaisenaan (`already_archived`). Puuttuva tai vioittunut
kopio kirjoitetaan uudelleen puhelimelta tulleista, tarkistetuista tavuista (`repaired`), ja
indeksiin lisätään `repaired`-rivi.

## 3. PC:n arkisto

Sijainti: `<repo>\evidence\` (gitignoroitu). Muutettavissa: `leima-bridge sync --archive <polku>`
tai ympäristömuuttuja `LEIMA_EVIDENCE_DIR`.

```text
evidence\
  index.jsonl
  browser\2026\10\2026-10-03_143012_example.org_3f9a12c4\package.zip
  screenshot\2026\10\2026-10-03_101500_pankki.fi_77b0e1d2\package.zip
  photo\2026\10\2026-10-03_090012_a1b2c3d4\package.zip
  meeting\2026\10\2026-10-03_084500_9f3e5a10\package.zip
```

- Kansion nimi: `<capture-aika UTC>_<verkkotunnus, jos on>_<ZIPin sha256:n 8 ensimmäistä merkkiä>`.
  Aika ja verkkotunnus luetaan paketin metatiedoista; ne ovat vain apu selaamiseen eivätkä kuulu
  todisteeseen.
- `package.zip` on täsmälleen puhelimesta tulleet tavut. Arkistossa ZIPejä ei koskaan muokata
  eikä pureta paikoilleen.
- `index.jsonl` on vain lisättävä loki; jokaisesta arkistoidusta paketista yksi rivi:

```json
{"event":"archived","sha256":"3f9a12c4…","kind":"screenshot","path":"screenshot/2026/10/2026-10-03_143012_example.org_3f9a12c4/package.zip","size":482113,"captured_at":"2026-10-03T14:30:12Z","domain":"example.org","device":"Pixel 7","pulled_at":"2026-10-03T15:02:44Z","verified":true}
```

- Tapaus- tai projektiryhmittely tehdään tageilla, ei kansioilla, koska sama paketti voi kuulua
  useaan tapaukseen. `python -m bridge tag <sha256> <tagi>` lisää indeksiin erillisen rivin:

```json
{"event":"tag","sha256":"3f9a12c4…","tag":"case-42","at":"2026-10-03T15:10:00Z"}
```

Arkistointirivillä on `"event":"archived"`. Korjausrivi:

```json
{"event":"repaired","sha256":"3f9a12c4…","path":"screenshot/…/package.zip","reason":"hash_mismatch","at":"2026-10-04T09:00:00Z"}
```

`reason` on `hash_mismatch` tai `missing`. Leimausrivi (`python -m bridge stamp`, vaihe F) osoittaa
paketin viereen tallennettuun Leiman vastaukseen `stamp-<tx>.json`:

```json
{"event":"stamped","sha256":"3f9a12c4…","stamp_file":"browser/…/stamp-<tx>.json","arweave_tx":"…","arweave_url":"…",
 "network":"arweave-mainnet-via-irys","permanent":true,"provenance":"device_captured","verdict_category":"Supported","at":"…"}
```

Rivejä ei koskaan muokata eikä poisteta.

## 4. Käyttö

```text
python -m bridge sync [--serial S] [--archive DIR] [--keep]   siirto + tarkistus + poisto puhelimesta
python -m bridge verify <sha256>                              arkistoidun paketin uusintatarkistus
python -m bridge tag <sha256> <tagi>
python android\tools\verify_package.py polku\package.zip    itsenäinen tarkistus ilman siltaa
```

`--keep` jättää paketit puhelimeen. Sama siirto onnistuu MCP:n kautta (`packages_sync`), ja se
poistaa puhelimen kopion samoin ehdoin. Työkalu on merkitty poistavaksi (`destructiveHint: true`),
ja `keep_on_phone: true` jättää paketit puhelimeen. Sync on turvallista ajaa uudelleen: jo arkistoitu ZIP
tunnistetaan sha256:sta.

Tunnettu rajoitus: puhelimen Kuvausistunto-näkymän istuntolista päivittyy vasta, kun näkymä
avataan uudelleen siirron jälkeen.
