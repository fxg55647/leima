# Meeting proof — pakettimuoto v2 ja QR-protokolla

Tila: Vaihe 0 -sopimus (ks. `MEETING_PROOF_IMPLEMENTATION_PLAN.md` luku 12). Tämä
dokumentti kiinnittää tarkat kentät ja tavumuodon ennen Vaihe 1 -toteutusta.
Skeema voi vielä muuttua ennen Vaihe 3:n (`meeting_session.py`/`meeting_pair.py`)
julkaisua; muutos vaatii uudet testivektorit.

## 1. Allekirjoitusskeema

Kaikki allekirjoitetut viestit (QR-viestit ja paketin manifesti) käyttävät samaa
skeemaa. Toteutus: `meeting_crypto.py` (Python) ja
`android/app/src/main/java/fi/leima/android/meeting/MeetingCrypto.kt` (Kotlin).

- Käyrä: P-256 (secp256r1).
- Algoritmi: ECDSA / SHA-256 (`SHA256withECDSA`).
- Allekirjoitusmuoto: ASN.1 DER (SEQUENCE kahdesta INTEGERistä r, s) — sekä
  Kotlinin `Signature`-luokan että Python `cryptography`-paketin oletusmuoto.
- Julkinen avain: DER SubjectPublicKeyInfo.
- Allekirjoitetut tavut: `utf8("leima-meeting-v2:" + messageType) + 0x00 + payloadBytes`.
  NUL-tavu erottaa domain-erottimen payloadista, jotta yksikään erotin ei voi
  olla toisen erottimen ja lyhyemmän payloadin etuliite.
- `payloadBytes` on kiinnitetty tavusarja sellaisena kuin lähettäjä sen kirjoitti
  (esim. `json.dumps(..., separators=(",", ":"), sort_keys=True)` tuottamana).
  Tarkistin **ei** serialisoi JSON:ia uudelleen — se allekirjoittaa/tarkistaa
  täsmälleen saadut tavut.

Ristikielisyys on lukittu testivektoreilla `android/testdata/meeting_crypto_vectors.json`,
joita `test_meeting_crypto.py` (Python) ja `MeetingCryptoTest.kt` (Kotlin,
`:app:testDebugUnitTest`) molemmat tarkistavat.

## 2. QR-viestien envelope

Jokainen QR-koodiin kirjoitettu JSON-envelope:

```json
{
  "type": "finish_challenge",
  "protocolVersion": 2,
  "sessionId": "b2b0b8fa-1a4b-4a3e-9d3a-6f2f0a2f0a11",
  "senderKeyId": "8f3e1c2a9b7d4e56",
  "receiverKeyId": "1a2b3c4d5e6f7081",
  "messageId": "m-000001",
  "payloadBase64": "<base64: täsmälleen allekirjoitetut payload-tavut>",
  "signatureBase64Der": "<base64: ASN.1 DER ECDSA-allekirjoitus>"
}
```

`senderKeyId`/`receiverKeyId` ovat lähettäjän/vastaanottajan istuntokohtaisen
julkisen avaimen SHA-256-tiivisteen ensimmäiset 8 tavua hex-muodossa. Kutsu- ja
liittymisviesteissä (`join_invite`, `join_response`) välitetään täysi julkinen
avain (DER SPKI, base64); myöhemmissä viesteissä vain tunniste, koska avain on
jo tiedossa.

Rajat (ks. suunnitelman luku 6): tuntemattomat protokollaversiot, päällekkäiset
JSON-avaimet, yli 2 KiB QR-viestit ja yli 64 KiB JSONL-rivit hylätään.

## 3. Loppuvaiheen viestit — esimerkit

Taulukko suunnitelman luvusta 6, konkreettiset `payload`-sisällöt (ennen
base64/tiivistämistä). Todelliset esimerkkitavut ja niiden allekirjoitukset:
`android/testdata/meeting_crypto_vectors.json`.

### `finish_challenge` (A → B)

```json
{
  "type": "finish_challenge",
  "protocolVersion": 2,
  "sessionId": "b2b0b8fa-1a4b-4a3e-9d3a-6f2f0a2f0a11",
  "senderKeyId": "8f3e1c2a9b7d4e56",
  "receiverKeyId": "1a2b3c4d5e6f7081",
  "nonce": "<base64: ≥128-bittinen kryptografisesti satunnainen>",
  "messageId": "m-000001"
}
```

Vastaanottajan tarkistus: tunnettu istunto ja A:n allekirjoitus (ks. luku 1).

### `finish_response` (B → A)

```json
{
  "type": "finish_response",
  "protocolVersion": 2,
  "sessionId": "b2b0b8fa-1a4b-4a3e-9d3a-6f2f0a2f0a11",
  "senderKeyId": "1a2b3c4d5e6f7081",
  "receiverKeyId": "8f3e1c2a9b7d4e56",
  "inResponseToHash": "<hex SHA-256 finish_challenge-viestin signedBytes-tavuista>",
  "nonceA": "<sama nonce kuin finish_challengessa>",
  "nonceB": "<base64: B:n uusi tuore nonce>",
  "messageId": "m-000002"
}
```

Vastaanottajan tarkistus: B:n allekirjoitus ja `nonceA` täsmää juuri avoimeen
A:n haasteeseen (ei vanhaan, uusintaan tai eri istuntoon).

### `finish_ack` (A → B)

```json
{
  "type": "finish_ack",
  "protocolVersion": 2,
  "sessionId": "b2b0b8fa-1a4b-4a3e-9d3a-6f2f0a2f0a11",
  "senderKeyId": "8f3e1c2a9b7d4e56",
  "receiverKeyId": "1a2b3c4d5e6f7081",
  "inResponseToHash": "<hex SHA-256 finish_response-viestin signedBytes-tavuista>",
  "nonceB": "<sama nonce kuin finish_responsessa>",
  "messageId": "m-000003"
}
```

Vastaanottajan tarkistus: A:n allekirjoitus ja `nonceB` täsmää juuri avoimeen
B:n haasteeseen. Tämän jälkeen B:llä on A:n allekirjoitettu lukukuittaus.

Vastausaikaraja: 120 sekuntia per odotettu vastaus (paikallinen, prototyyppi).
Uusinta luo uuden `messageId`:n ja tuoreet noncet; vanha yritys jää lokiin
keskeytyneenä (`events.jsonl`).

## 4. Pakettirakenne v2

```text
session.json
pairing.json                   # vain jos pariutunut; ei solo-istunnoissa
events.jsonl
sensors/imu.jsonl
sensors/location.jsonl
sensors/gnss.jsonl             # vain jos kerättiin
captures/000001.jpg            # vain kuvaajalla
captures/000001.json
manifest.json
manifest.sha256
signature.json
```

`manifest.json` luettelee kaikki muut sisältötiedostot (ei itseään, ei
`manifest.sha256`:tä eikä `signature.json`:ia — kehämäisen riippuvuuden
välttämiseksi):

```json
{
  "schemaVersion": 2,
  "algorithm": "SHA-256",
  "files": {
    "session.json": "<hex sha256>",
    "captures/000001.jpg": "<hex sha256>"
  }
}
```

`signature.json` allekirjoittaa `manifest.json`:n täsmälleen tavut
(`messageType = "manifest"`, `payloadBytes = manifest.json:n sisältö sellaisenaan`):

```json
{
  "algorithm": "SHA256withECDSA",
  "curve": "P-256",
  "publicKeySpkiDerBase64": "<base64>",
  "signatureBase64Der": "<base64>"
}
```

## 5. Testivektorit

`android/testdata/meeting_crypto_vectors.json` sisältää **vain testikäyttöön**
tarkoitetun P-256-avainparin (yksityinen avain mukana, selkeästi merkitty) sekä
neljä esimerkkiviestiä (`finish_challenge`, `finish_response`, `finish_ack`,
`manifest`) allekirjoituksineen. Tiedostoa ei käytetä missään
tuotantopolussa — vain `test_meeting_crypto.py`:ssä ja `MeetingCryptoTest.kt`:ssä.

Jos allekirjoitusskeema (domain-erotin, tavujärjestys tai algoritmi) muuttuu,
vektorit on generoitava uudelleen molempien kielten testien kanssa
yhdenmukaisiksi — muutoin Vaihe 0:n "valmis, kun" -kriteeri ei enää päde.

## 6. Vaihe 2 -toteutus: join-pariutuminen ja pairing.json

`QrPairingProtocol.kt` toteuttaa myös `join_invite`/`join_response`-viestit
(A luo istunnon → B liittyy). Näissä `senderPublicKeySpkiDerBase64` on aina
mukana, ja viesti on itseallekirjoitettu: `senderKeyId` ja allekirjoitus
tarkistetaan samasta mukana tulevasta avaimesta (luottamus ensimmäisellä
käytöllä — ei ulkoista varmennusta, ks. suunnitelman luku 11).

```json
{
  "type": "join_invite",
  "protocolVersion": 2,
  "sessionId": "b2b0b8fa-1a4b-4a3e-9d3a-6f2f0a2f0a11",
  "senderKeyId": "8f3e1c2a9b7d4e56",
  "receiverKeyId": null,
  "messageId": "m-...",
  "senderPublicKeySpkiDerBase64": "<base64 DER SPKI>",
  "payloadBase64": "<base64: {type, protocolVersion, sessionId, role, messageId}>",
  "signatureBase64Der": "<base64>"
}
```

`join_response` on muuten sama, mutta `receiverKeyId` on kutsujan `senderKeyId`
ja `sessionId` on kutsusta opittu (liittyjä omaksuu sen omakseen).

`MeetingCoordinator` pitää istuntokohtaisen `MeetingKeyStore`-avaimen
(Android Keystore, alias sidottu paikalliseen hakemistonimeen, ei jaettuun
`sessionId`:hen — se voi vielä muuttua pariutumisen aikana). `manifest.json`
allekirjoitetaan aina `finalizeSession()`-kutsussa riippumatta siitä onko
istunto solo vai pariutunut; `signature.json` ei siis enää ole "kehitysaineiston"
merkki niin kuin Vaihe 1:ssä.

Kaikki QR-protokollan rakennus/validointi (`QrPairingProtocol.kt`) on puhdasta
`java.security`/`org.json`-koodia ja JVM-yksikkötestattu ilman laitetta.
`QrAnalyzer`/`QrCodec` (ZXing/CameraX) ja `MeetingKeyStore` (Android Keystore)
vaativat oikean laitteen — niitä ei ole voitu ajaa tässä ympäristössä.
