# `/api/stamp` — arkkitehtuuri

Tämä dokumentti kuvaa `POST /api/stamp` -rajapinnan sisäisen toteutuksen: mitä
palvelin tekee pyynnön saapuessa, mitkä moduulit osallistuvat, ja mihin
vastauksen kentät perustuvat. Tarkoitettu ylläpitäjille ja niille, jotka
liittävät rajapintaan uusia source_type-tyyppejä tai muuttavat leimausputkea.

Käyttäjädokumentaatio (pyyntö/vastausesimerkki) on README.md:ssä, kohta
"9. API". Tämä dokumentti ei toista sitä vaan selittää mitä otsikoiden takana
tapahtuu.

## 1. Mikä tämä on

`/api/stamp` on ohjelmallinen (agentti-/pipeline-) reitti samaan
leimausputkeen jota `/ask`-lomake ajaa UI:sta. Se ei ole erillinen
kevyempi toteutus — se kutsuu täsmälleen samoja funktioita
(`_run_analysis`, `_ensure_stamped`) kuin selainkäyttöliittymä, joten UI:n ja
API:n tuottamat manifestit ja ZIP-paketit ovat rakenteeltaan identtiset.

Reitti on määritelty `main.py:2938` (`api_stamp`), pyynnön muoto
`StampRequest`-Pydantic-mallissa (`main.py:2923`).

Rajapinnassa **ei ole autentikointia**. Kuka tahansa internetistä voi
kutsua sitä. Tämä on tietoinen valinta (agenttien pitää voida kutsua sitä
ilman avainten hallintaa), mutta se tarkoittaa että jokainen kutsu myös
kuluttaa Gemini- ja Arweave-kvoottia — ks. kohta 6.

## 2. Kutsuvuo (sekvenssi)

```
Agentti                    /api/stamp              analyse()           Arweave/Irys
   |                           |                  (neutral_witness)         |
   |--POST claim+source------->|                        |                  |
   |                           |--validoi source_type--->|                  |
   |                           |   (base64/url/text)     |                  |
   |                           |--_run_analysis---------->|                 |
   |                           |   1) tuki-passi          |                 |
   |                           |   2) vastapassi          |                 |
   |                           |   3) synteesi/verdikti   |                 |
   |                           |<--passes+verdict---------|                 |
   |                           |--rakenna verdict.pdf/    |                 |
   |                           |   .txt/.html/.json       |                 |
   |                           |--build_manifest---------->                 |
   |                           |   (sha256 jokaisesta     |                 |
   |                           |    tiedostosta)          |                 |
   |                           |--tallenna session_id --->|  in-memory store|
   |                           |   (TTL 1h)               |                 |
   |                           |--_ensure_stamped-------------------------->|
   |                           |   (JSON ilman "stamp") --| upload(wallet)  |
   |                           |<--tx_id------------------------------------|
   |                           |--liitä stamp{tx_id,url}  |                 |
   |                           |   manifestiin            |                 |
   |<--JSON: verdict, hashit,  |                          |                 |
   |   stamp, manifest,        |                          |                 |
   |   download_url -----------|                          |                 |
```

## 3. Syötteen käsittely (`source_type`)

`main.py:2938`–`2967`. Kolme tuettua tyyppiä, kaikki päätyvät
`contents`-listaksi Geminille + `input_bytes`+`input_label`-pariksi
manifestia/hashausta varten:

| `source_type`  | Käsittely | Rajat / validointi |
|----------------|-----------|---------------------|
| `pdf_base64`   | Base64-dekoodaus, tarkistetaan `%PDF-`-magic bytes | Max ~20 MB (base64-pituudesta laskettu, `main.py:2947`) |
| `pdf_url`      | `_fetch_pdf_from_url` (`main.py:2263`): SSRF-tarkistus (`_check_ssrf`), striimattu GET, Content-Type/pääte-tarkistus | Max 10 MB (`PDF_URL_MAX_BYTES`, `main.py:2260`), max 10 uudelleenohjausta (`_safe_get`) |
| `text`         | Muunnetaan PDF:ksi `fpdf2`:lla (`_text_to_input_pdf`, `main.py:2291`), teksti myös välitetään Geminille sellaisenaan | Ei erillistä pituusrajaa tässä kutsuketjussa |

**Tunnettu puute:** `pdf_base64`-polulla ei ole tarkkaa tavurajaa yhtä
tiukkaa kuin `pdf_url`-polulla (`SUGGESTIONS_CODE.md`, rivi 9). Jos tätä
korjataan, raja pitäisi asettaa `main.py:2946`-tarkistukseen, ei erilliseen
paikkaan.

`_check_ssrf` (`main.py:782`) estää yksityiset/loopback/link-local/reserved
osoitteet sekä itse URL:sta että jokaisesta uudelleenohjauksen kohteesta
erikseen — pelkkä alkuperäisen hostnamen tarkistus ei riitä, koska
uudelleenohjaus voisi osoittaa sisäverkkoon.

## 4. Analyysi — kolme passia (`neutral_witness.analyse`)

`neutral_witness.py:426`. Sama funktio jota `/ask` käyttää.

1. **Tukeva näyttö** — malli etsii sisällöstä väitettä tukevaa evidenssiä.
   Jos malli palauttaa `REJECTED...` tässä passissa, koko pyyntö keskeytyy
   `ValueError`:lla → `/api/stamp` palauttaa `422`. Tämä on ainoa
   sisältöön perustuva hylkäysreitti (esim. tyhjä/lukukelvoton dokumentti).
2. **Vastainen näyttö** — sama, mutta vastaevidenssi.
3. **Synteesi/verdikti** — malli saa molemmat edelliset passit kontekstiksi
   ja tuottaa `CATEGORY:`/`VERDICT:`-etuliitteellisen lopputuloksen, joka
   parsitaan `summary_verdict`- ja `verdict_category`-kentiksi.

Malli on kiinteä: `gemini-3.1-flash-lite` (`neutral_witness.py:15`,
`MODEL`-vakio, näkyy myös vastauksen `model`-kentässä).

`prompt_log` (kaikki kolme systeemipromptia) tallennetaan sessioon ja
upotetaan `verdict.pdf`:ään läpinäkyvyyden vuoksi, mutta sitä **ei**
palauteta `/api/stamp`-vastauksen JSON:ssa suoraan — se on vain PDF:n
sisällä.

## 5. Manifesti ja hashaus (`evidence_package.py`)

`build_manifest` (`evidence_package.py:59`) laskee SHA-256:n jokaisesta
tuotetusta tiedostosta erikseen (`source.<ext>`, `verdict.pdf`,
`verdict.txt`, `verdict.html`, `verdict.json`, valinnainen
`source-index.json`) ja kokoaa ne `files`-sanakirjaksi. Tämä
`stamp_format_version=2`-manifesti on se objekti joka lopulta menee
Arweaveen — **ei** alkuperäinen lähdetiedosto sellaisenaan, vaan sen hash.

`input_hash` ja `verdict_hash` vastauksessa lasketaan erikseen
`_run_analysis`:ssa (`main.py:2307`, `2316`) samalla `sha256`-apufunktiolla,
ja ne ovat samat arvot jotka löytyvät `manifest["files"]`-sanakirjasta
(muodossa `sha256:<hex>`).

Tämä on projektin kaksikerroksinen luottamusmalli
([[project_two_layer_model]]):
- **Hash-sitoumus** (kova tae): manifest.json — siis nämä tarkat
  tavusummat — on olemassa Arweavella tästä ajanhetkestä alkaen, muuttumattomana.
- **AI-verdikti** (käytännön ohjenuora): passien sisältö on mallin arvio,
  ei kryptografisesti todistettu totuus.

`/api/stamp`-vastaus sisältää molemmat kerrokset samassa JSON:ssa, ja
kutsujan (agentin) vastuulla on olla sekoittamatta niitä keskenään.

## 6. Arweave-leimaus (`_ensure_stamped` / Irys)

`main.py:1797`. Tapahtuu vasta analyysin jälkeen, kertaalleen per
`session_id`:

1. `evidence_package.strip_stamp` poistaa `stamp`-kentän (sitä ei voi olla
   olemassa vielä, koska tx_id syntyy vasta uploadista — muna–kana-ongelma
   vältetään näin).
2. Manifest serialisoidaan JSON:ksi ja ladataan Irys-uploaderilla
   (`_irys_upload`, `main.py:2019`) Ethereum-lompakkoa vasten
   (`IRYS_PRIVATE_KEY`). Verkko on `IRYS_NETWORK` (oletus `mainnet`,
   `devnet` mahdollinen ympäristömuuttujalla).
3. Palautuva `tx_id` + `IRYS_GATEWAY`-pohjainen URL liitetään manifestiin
   `stamp`-avaimeksi.

`threading.Lock` per sessio estää kaksoisuploadin, jos samaan
`session_id`:hen osuisi kaksi samanaikaista pyyntöä (esim. `/api/stamp`
palauttaa vastauksen ja joku hakee samaa `download_url`:ia rinnakkain).
Epäonnistunut Arweave-upload jättää session leimaamattomaksi eikä kirjaa
osittaista tilaa — kutsuja saa `502` ja voi olettaa ettei mitään
julkaistu.

**Tärkeä huomio agenteille:** joka ikinen `/api/stamp`-kutsu joka pääsee
analyysivaiheen ohi tuottaa oikean, pysyvän, maksullisen Arweave-transaktion.
Ei ole "dry run" -tilaa. Auth-vapaus (kohta 1) yhdistettynä tähän tarkoittaa
että rajapinta on avoin väylä lompakon varojen kulutukseen jos sitä spämmätään.

## 7. Sessio, ZIP-paketti ja pysyvyys

`store: dict[str, dict]` (`main.py:376`) on prosessin muistissa oleva
sanakirja, TTL `SESSION_TTL = 3600` s (`main.py:386`), siivotaan
`_evict_old_sessions`:lla. Se sisältää mm. `verdict_pdf`, `manifest`,
`source`-tavut, kaikki verdict-eksportit.

`download_url` (`/download/{session_id}/package.zip`) kokoaa ZIP:n
pyynnön hetkellä `evidence_package.pack`:lla — pakettia **ei** ole
esirakennettuna levyllä. Kun sessio vanhenee tai palvelin käynnistyy
uudelleen (esim. Vercel-deploy), linkki lakkaa toimimasta pysyvästi.
Ainoa pysyvä asia on Arweavella oleva manifest.json — `stamp.url`.

Tästä syystä `/api/stamp`-vastauksen `manifest`-kenttä (koko sisältö, ei
vain linkki) on tarkoituksella palautettu suoraan JSON:ssa: agentin
kannattaa tallentaa se itse, ei luottaa `download_url`:iin pitkällä
aikavälillä.

## 8. Suhde muihin reitteihin

- **`/ask`** — sama ydinputki (`_run_analysis` + `_ensure_stamped`), mutta
  HTML-partial-vastauksin selaimelle, ja tukee enemmän lähdetyyppejä
  (email/IMAP, .eml, web-fetch, kuva, selainkaappaus) joita `/api/stamp`
  ei tällä hetkellä altista JSON-rajapinnan kautta.
- **`/api/historical-email-proof/*`** — eri putki, eri manifestimuoto
  (W3C VC -tyylinen todistus + policy-tarkistus), rakennettu tiettyä
  demo-käyttötapausta varten. Ei jaa koodia `_run_analysis`:n kanssa.
- **`/api/code-review`** — käyttää samaa `analyse`-perhettä
  (`analyse_code_review`, `neutral_witness.py:371`) mutta eri promptit ja
  eri syöte (GitHub-repo, ei tiedosto).

Jos `/api/stamp`:iin lisätään uusi `source_type`, oikea paikka on
`main.py:2946`-alkuinen `if/elif`-ketju — sen jälkeen loppu putki
(`_run_analysis` → `_ensure_stamped`) toimii muuttumattomana, koska se ei
tiedä mistä `input_bytes`/`contents` tulivat.

## 9. Tunnetut rajoitteet / jatkokehitysaiheet

- Ei autentikointia eikä rate limitiä → avoin kulutusväylä (kohta 6).
- `pdf_base64`:n kokoraja ei ole yhtä eksplisiittinen kuin `pdf_url`:n
  (kohta 3).
- `download_url` ei ole pysyvä (kohta 7) — ei dokumentoitu virhevastausta
  sille kun sessio on jo evictoitu paitsi tavallinen `404`.
- W3C VC -migraatiosuunnitelma (`docs/todo/W3C_VC_MIGRATION_PLAN.md`)
  kattaa myös `/api/stamp`:n manifestimuodon — jos se etenee, tämä
  dokumentti pitää päivittää samalla.
