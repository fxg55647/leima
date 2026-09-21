# Historiallinen sähköpostitodistus — arkkitehtuuri

Tämä dokumentti kuvaa `/api/historical-email-proof/*`-rajapinnan ja sen
taustamoduulien nykyisen toteutuksen: mitä kukin osa tarkistaa, mihin
päätökset perustuvat, ja miten osat kytkeytyvät toisiinsa. Tarkoitettu
ylläpitäjille ja niille, jotka jatkavat ominaisuuden rakentamista.

Alkuperäinen suunnitelma on
[`docs/todo/HISTORICAL_EMAIL_PROOF_PLAN.md`](todo/HISTORICAL_EMAIL_PROOF_PLAN.md).
Se on **vanhentunut** useassa kohdassa (ks. kohta 12) — tämä dokumentti kuvaa
mitä oikeasti rakennettiin, ei alkuperäistä ehdotusta sellaisenaan.

## 1. Mikä tämä on

Historiallinen todistus siitä, että joku hyväksytyn viranomaisen/palvelun
allekirjoittama sähköposti on osoitettu tietylle osoitteelle ennen tiettyä
rajapäivää. Käytetään "historiallisena ihmisyyssignaalina" — ei uutta
rekisteröitymistä vaativana identiteettitarkistuksena.

Todistus **todistaa**:
- DKIM-allekirjoitetun viestin olemassaolon, tarkalta hyväksytyltä
  allekirjoittajalta, tarkasta hyväksytystä viestiluokasta.
- Että viesti on osoitettu tiettyyn (piilotettuun, hash-sidottuun)
  sähköpostiosoitteeseen, ennen policyn rajapäivää.

Todistus **ei todista**:
- Sähköpostin nykyistä hallintaa (sen tekee vastaanottava palvelu erikseen).
- Lataajan henkilöllisyyttä.
- Että viestin sisältö sinänsä on totta — vain että allekirjoittaja lähetti
  juuri nämä tavut.

Ks. myös kaksikerrosmalli kohdassa 9: kryptografiset tarkistukset (kova tae)
vs. AI:n arvio allekirjoittajan luotettavuudesta (pehmeä, käytännön ohjenuora).

## 2. Kutsuvuo (sekvenssi)

```
Käyttäjä              /api/historical-email-proof/*      Arweave/Irys        SMTP
   |                          |                                |              |
   |--POST .eml-------------->|                                |              |
   |                (check)   |--check_message_fields---------->|             |
   |                          |   DKIM + allekirjoittaja +      |             |
   |                          |   viestiluokka + vastaanottaja +|             |
   |                          |   rajapäivä                     |             |
   |<--session_id, checks-----|                                |              |
   |                          |                                |              |
   |--POST /{id}/issue------->|                                |              |
   |                (issue)   |--issue_credential--------------->|            |
   |                          |   (uusintaa check_message_fields)|            |
   |                          |   -> Ed25519 JWS + salaisuus     |            |
   |                          |--publish_anchor----------------------------->|
   |                          |   SHA-256(JWS) vain, ei muuta    |  Irys      |
   |<--credential_jws, tx_id--|<--------------------------------|            |
   |                          |                                |              |
   |--GET /{id}/download----->|                                |              |
   |<--stampd-proof.json------|                                |              |
   |                          |                                |              |
   |--POST /{id}/email------->|                                |              |
   |                          |--send_proof_email (vain omaan---------------->|
   |                          |   tarkistettuun osoitteeseen)   |    SMTP      |
   |<--{"sent": true}---------|                                |              |
```

## 3. Policy ja lukitut kentät (`historical_email_policy.py:31`)

`HistoricalEmailPolicy` on jäädytetty (`frozen=True`) dataclass. Kaikki
kentät — myös `human_verification_basis` ja `allowed_subjects` — ovat osa
`canonical_bytes()`/`digest()`-laskentaa (`historical_email_policy.py:52,64`),
eli policyn perustelu on sidottu samaan lukittuun versioon kuin sallitut
allekirjoittajat.

`__post_init__` (`historical_email_policy.py:43`) pakottaa:
- `cutoff` aikavyöhyketietoinen.
- `human_verification_basis` ei tyhjä — perustelu miksi tämä allekirjoittaja
  hyväksyttiin, ei vapaaehtoinen kommentti.
- `allowed_subjects` ei tyhjä — tarkka, ennalta tarkastettu viestiluokka
  (ks. kohta 4).
- `required_signed_headers` sisältää aina vähintään `{to, date, subject}` —
  tätä ei voi löysätä policytasolla (korjattu katselmoinnin löydöksestä:
  policy saattoi aiemmin vaatia signeeratuksi vain `subject`-otsikon, jolloin
  allekirjoittamaton vastaanottaja/päiväys olisi silti raportoitu
  tarkistetuksi).

## 4. Viestin tarkistus (`historical_email_proof.check_message_fields`, `historical_email_proof.py:83`)

Kaikki tai ei mitään — mikään tarkistus ei voi hiljaa löystyä:

1. Täsmälleen yksi `DKIM-Signature`-otsikko.
2. `dkim.DKIM(raw).verify()` onnistuu (mahdollisuus injektoida `dnsfunc`
   testejä varten, ks. `tests/test_historical_email_proof.py`).
3. Allekirjoittajan `d=`-domain on `policy.allowed_dkim_signers`-listalla.
4. Ei `l=`-tagia (osittainen runkoallekirjoitus hylätään).
5. `h=`-tagi kattaa kaikki `policy.required_signed_headers`.
6. **Viestiluokka**: dekoodattu `Subject`-otsikko täsmää täsmälleen
   johonkin `policy.allowed_subjects`-arvoon. Tämä on erikseen lisätty
   tarkistus alkuperäisen suunnitelman jälkeen: sama hyväksytty
   allekirjoittaja voi lähettää muitakin viestiluokkia (esim. yleinen
   "kiitos yhteydenotosta" -vastaus julkisesta lomakkeesta), joilla ei ole
   samaa merkitystä henkilöllisyyden todentamisen kannalta kuin
   vahvistetulla ilmoitustyypillä.
7. Täsmälleen yksi `To`-otsikko, normalisoitu (`normalize_email`,
   `historical_email_policy.py:91`).
8. Täsmälleen yksi `Date`-otsikko, aikavyöhyketietoinen, ennen
   `policy.cutoff`.

Palauttaa `MessageCheckResult` (`historical_email_proof.py:50`): vastaanottaja,
päivämäärä, allekirjoittajadomain, ja `checks`-sanakirja
(`approvedDkimSigner`, `approvedMessageClass`, `signedRecipient`,
`signedDateBeforeCutoff`).

## 5. Sidonta ja allekirjoitus (`issue_credential`, `historical_email_proof.py:219`)

1. Ajaa `check_message_fields` uudelleen (ei luota mahdolliseen aiemmin
   tallennettuun tulokseen — ks. kohta 10 istuntojen osalta).
2. `compute_email_commitment` (`historical_email_policy.py:115`): SHA-256
   protokollatunnisteesta + normalisoidusta osoitteesta + 32 tavun
   satunnaisesta salaisuudesta, nollatavuin erotettuna (yksiselitteinen
   koodaus).
3. Rakentaa JWS-hyötykuorman (tyyppi, versio, myöntäjä, `credentialId`,
   `policyId`+`policyDigest`, `cutoff`, `emailCommitment`, `checks`, ...) ja
   allekirjoittaa sen `sign_jws`:llä (`historical_email_proof.py:161`) —
   **EdDSA/Ed25519, kiinnitetty algoritmilista** (`ALLOWED_JWS_ALGORITHMS`).
4. Palauttaa `IssuedCredential` (`historical_email_proof.py:213`):
   `credential_jws`, `disclosure_secret_b64`, `recipient_email`.

`verify_jws` (`historical_email_proof.py:183`) ja sen apufunktio
`_decode_json_object` (`historical_email_proof.py:169`) hylkäävät kaikki
base64/JSON/tyyppivirheet yhtenäisenä `RejectedMessage`:na — otsikon tai
hyötykuorman ei tarvitse edes olla validi JSON-objekti kaataakseen prosessin
ennen tätä korjausta (katselmoinnin löydös).

## 6. Vastaanottajan tarkistus (`proof_verifier.verify_attestation`, `proof_verifier.py:25`)

Tarkoituksella kevyt moduuli: ei riipu `dkim`- tai `email_eml`-kirjastoista,
vain `historical_email_policy`- ja `historical_email_proof`-moduulien
allekirjoitus-/sidontaprimitiiveistä. Tarkistaa allekirjoituksen, että
`policyId`+`policyDigest` täsmää odotettuun lukittuun policyyn, että kaikki
`checks`-kentät ovat `true`, ja laskee sidonnan uudelleen **omasta**
vahvistetusta vastaanottajaosoitteestaan + paketin salaisuudesta
(`hmac.compare_digest`, ei ajoitushyökkäyksille altis vertailu).

## 7. Arweave-ankkurointi (`historical_email_anchor.py`)

**Arkkitehtuuripäätös**: Arweaveen viedään vain
`SHA-256(credential_jws)` (`compute_credential_digest`,
`historical_email_anchor.py:49`) — ei koko JWS:ää, ei `issuer`/`credentialId`/
muuta metadataa. Koko allekirjoitettu todistus toimitetaan käyttäjälle
yksityisesti (kohta 8). Tämä noudattaa projektin "vain hash Arweaveen"
-periaatetta ja on tietoisesti ristiriidassa alkuperäisen suunnitelman
(`HISTORICAL_EMAIL_PROOF_PLAN.md` kohta 3) kanssa, joka ehdotti koko JWS:n
julkaisua — ks. myös `docs/todo/W3C_VC_MIGRATION_PLAN.md` kohta 5-6, joka
päätyy samaan hash-only-ankkuri-malliin yleisemmällä tasolla.

`publish_anchor` (`historical_email_anchor.py:61`) ottaa injektoidun
`upload_fn`:n (tuotannossa `main._irys_upload`), yrittää uudelleen
(`max_attempts`, oletus 3, kasvava viive). `verify_anchor`
(`historical_email_anchor.py:93`) hakee tallennetun tietueen ja vertaa
sisältöä eksplisiittisesti — pelkkä HTTP 200 gatewaylta ei ole tae.

## 8. Todistuspaketti ja toimitus (`proof_delivery.py`)

`build_proof_package` (`proof_delivery.py:29`) kokoaa
`stampd-proof-package-v1`-muotoisen JSON:n (`signedCredential`,
`disclosure.randomSecret`, `arweaveTxId`). `send_proof_email`
(`proof_delivery.py:42`) vaatii, että toimituksen kohde
(`requested_recipient_email`) täsmää tarkistetun viestin omaan
vastaanottajaan (`verified_recipient_email`) — käyttäjä ei voi pyytää
toimitusta mielivaltaiseen osoitteeseen.

Lähetyskohtainen nopeusrajoitus (per-sessio, ei per-kirjasto — ks. kohta 10)
on toteutettu `main.py`:n endpointissa, ei tässä moduulissa, koska se
tarvitsee sovelluksen sessiotilaa.

## 9. AI-avusteinen allekirjoittajan arviointi (`signer_vetting.py`)

Erillinen, ei osa myöntämis-/tarkistuspolkua. `assess_signer_human_verification_basis`
(`signer_vetting.py:65`) käyttää Gemini+Google Search -groundingia
(sama kuvio kuin `main.py`:n `_fetch_web_context`) tutkimaan **pelkkää
DKIM-domainia** — ei koskaan yksittäisen viestin sisältöä, koska
allekirjoittajan itse toistama vapaateksti (esim. otsikkorivi) on validisti
DKIM-allekirjoitettuna silti hyökkääjän vaikutettavissa (prompt injection
-riski säilyy vaikka allekirjoitus on aito).

`draft_human_verification_basis` (`signer_vetting.py:101`) muotoilee mallin
parhaan arvion suoraan `policy.human_verification_basis`-tekstiksi **ilman
ihmisen hyväksyntäporttia** — myös `uncertain`-verdikti näkyy tekstissä
rehellisesti. Tämä on kaksikerrosmallin pehmeä kerros: se ei koskaan ohita
tai muuta kohdan 4 kryptografisia tarkistuksia, riippumatta siitä mitä se
päättelee.

## 10. `main.py`-endpointit ja sessiot

| Reitti | Rivi | Tekee |
|---|---|---|
| `POST /api/historical-email-proof/check` | `main.py:3102` | Lataa `.eml`, ajaa `check_message_fields`, luo session |
| `POST /api/historical-email-proof/{id}/issue` | `main.py:3132` | Myöntää todistuksen, julkaisee ankkurin |
| `GET /api/historical-email-proof/{id}/download` | `main.py:3181` | Palauttaa `stampd-proof.json`-tiedoston |
| `POST /api/historical-email-proof/{id}/email` | `main.py:3198` | Toimittaa paketin vain tarkistettuun osoitteeseen |

Sessiot: `historical_email_proof_sessions: dict[str, dict]` (`main.py:383`),
prosessin muistissa, TTL `SESSION_TTL` (3600 s, sama pooli kuin muillakin
sessioilla, siivotaan `_evict_old_sessions`:lla).

**`/issue` on idempotentti onnistuneen myöntämisen jälkeen** (`main.py:3137`):
jos `entry["issued"]` on jo olemassa mutta Arweave-ankkurointi epäonnistui
edellisellä kerralla, uusi kutsu käyttää samaa todistusta uudelleen eikä
myönnä uutta (uusi todistus tarkoittaisi uutta satunnaista sidonnan
salaisuutta samalle sähköpostille — turhaa ja sekavaa). Vasta kun paketti on
tallennettu (`entry["package"]`), lisäkutsu hylätään `409`:llä.

**`/email`-nopeusrajoitus** (`main.py:3194`): enintään
`HISTORICAL_EMAIL_MAX_SENDS_PER_SESSION` (3) lähetystä per sessio,
`HISTORICAL_EMAIL_MIN_SEND_INTERVAL_SECONDS` (30 s) minimiväli. Tila on
istuntokohtainen muuttuja (`email_send_count`, `email_last_sent_at`) —
ei siis kestä prosessin uudelleenkäynnistystä eikä toimi usean instanssin
yli (ks. kohta 12).

**Myöntäjäavain** (`_historical_email_issuer_key`, `main.py:3087`):
`HISTORICAL_EMAIL_ISSUER_PRIVATE_KEY_B64`-ympäristömuuttujasta (base64url,
32-tavuinen Ed25519-siemen), tai — jos muuttuja puuttuu — prosessin sisäinen
väliaikainen avain, joka lakkaa toimimasta uudelleenkäynnistyksessä (varoitus
lokiin). Ei koskaan hiljainen: puuttuva ympäristömuuttuja näkyy joko
lokivaroituksena (dev) tai `503`-vastauksena jos avainta ei saada millään
tavalla ladattua.

**Demo-policy** (`_HISTORICAL_EMAIL_DEMO_POLICY`, `main.py:3070`):
`allowed_dkim_signers=("stampd-demo.example",)` — keksitty domain, jolla ei
ole julkaistua DKIM-avainta. Endpointit eivät siis toistaiseksi hyväksy
yhtään oikeaa sähköpostia; ks. kohta 12.

## 11. Suhde muihin dokumentteihin ja reitteihin

- **`docs/todo/HISTORICAL_EMAIL_PROOF_PLAN.md`** — alkuperäinen suunnitelma.
  Vanhentunut kohdissa: Arweave-julkaisun laajuus (kohta 7 tässä
  dokumentissa), viestiluokan otsikkotarkistus (ei mainita ollenkaan
  alkuperäisessä), moduulilista (ei sisällä `historical_email_anchor.py`
  eikä `signer_vetting.py`).
- **`docs/todo/W3C_VC_MIGRATION_PLAN.md`** — laajempi, myöhempi suunnitelma
  siirtää kaikki Leiman todistukset (myös tämä) yhteiseen W3C VC -muotoon.
  Päätimme tietoisesti *olla* odottamatta tätä migraatiota ja jatkaa oman
  JWS-hyötykuorman kanssa (ks. kohta 7) — VC-suunnitelman oma P3-vaihe
  huomioi tämän päivityksen myöhemmin.
- **`docs/STAMP_API_ARCHITECTURE.md`** — viittaa tähän ominaisuuteen kohdassa
  8 ("eri putki... ei jaa koodia `_run_analysis`:n kanssa").

## 12. Tunnetut rajoitteet / jatkokehitysaiheet

- **Demo-policy, ei oikeaa allekirjoittajaa**: `stampd-demo.example` ei ole
  oikea domain. Ennen tuotantokäyttöä pitää valita ja varmistaa oikea
  DKIM-allekirjoittaja oikeasta `.eml`-näytteestä (suunnitelman kohta 9.1).
- **Ei UI:ta**: vain JSON-API, ei lomaketta/näkymää.
- **Nopeusrajoitus ei kestä uudelleenkäynnistystä eikä skaalaudu usealle
  instanssille** — istuntokohtainen muuttuja prosessin muistissa, ei jaettu
  tila (esim. KV/Redis).
- **Ei salattua vientiä**: suunnitelman kohta 4 mainitsee valinnaisen
  Argon2id-suojatun paketin — ei toteutettu, tietoisesti myöhemmäksi
  siirretty ensiversiossa.
- **Ei peruutusmekanismia**: `statusReference` on kiinteä
  `"local-test:no-revocation-mechanism-yet"` — väärin myönnettyä todistusta
  ei voi vielä peruuttaa.
- **Yksi viestiluokka kerrallaan per policy**: `allowed_subjects` on tarkka
  merkkijonolista. Jos oikean allekirjoittajan otsikko sisältää
  henkilökohtaista tekstiä (esim. vastaanottajan nimi), tarkka täsmäys ei
  toimi sellaisenaan — vaatii joko normalisointia tai eri
  tunnistuskeinon, päätettävä oikeasta näytteestä.
