# Historialliseen sähköpostiin perustuva todistus — toteutussuunnitelma

Päiväys: 22.9.2026. Tila: suunnitelma, ei toteutettu ominaisuus.

## 1. Tavoite ja työnjako

Stampd tarkistaa alkuperäisen viranomaisviestin aitouden sekä sen, että allekirjoitettu päiväys on ennen hyväksymissäännön rajapäivää. Todistus sidotaan viestin allekirjoitettuun vastaanottajaosoitteeseen piilotetulla hash-sidonnalla. Stampd ei vahvista sähköpostin nykyistä hallintaa eikä edellytä käyttäjän avainparia.

Vastaanottava palvelu, esimerkiksi Reddit, vahvistaa sähköpostin nykyisen hallinnan omalla menettelyllään ja tarkistaa todistuksen vastaavuuden tähän osoitteeseen. Reddit on tässä integraatioesimerkki: suunnitelma ei oleta, että Reddit tukisi tällaista todistusta nykyisin.

Todistuksen tarkka väite: hyväksytyn säännön mukainen, aitouden tarkistuksen läpäissyt viesti on osoitettu sidonnan sähköpostiosoitteelle, ja sen allekirjoitettu päiväys edeltää rajapäivää. Väite ei koske lataajan henkilöllisyyttä tai sähköpostin nykyistä hallintaa.

Todistus on historiallinen ihmisyyssignaali. Se ei yksin takaa yhtä tiliä per ihminen, viestin tosiasiallista vastaanottohetkeä eikä sitä, ettei ihminen olisi antanut AI:lle tilinsä käyttöoikeutta.

## 2. Suositeltu käyttökokemus: julkinen todistus ja yksityinen kuitti

Käyttäjän ei tarvitse käsitellä hashia tai kopioida satunnaisarvoa erikseen.

1. Käyttäjä lataa alkuperäisen `.eml`-tiedoston Stampd:hen.
2. Stampd tarkistaa viestin ja näyttää tuloksen, sovelletun säännön ja piilotettavan vastaanottajaosoitteen käyttäjälle.
3. Käyttäjä käynnistää todistuksen julkaisun. Näkymä kertoo, mitkä tiedot tallennetaan pysyvästi.
4. Stampd allekirjoittaa ja tallentaa julkisen todistuksen Arweaveen.
5. Käyttäjä saa ladattavan `stampd-proof.json`-tiedoston. Käyttöliittymä tarjoaa myös painikkeen ”Lähetä todistus sähköpostiini”.
6. Sähköpostissa on sama yksityinen JSON-tiedosto liitteenä, lyhyt käyttöohje ja julkinen Arweave-linkki.
7. Todistuksia tukeva palvelu tarjoaa ”Lisää Stampd-todistus” -toiminnon. Käyttäjä tuo JSON-tiedoston; palvelu tekee tarkistuksen omaan vahvistettuun sähköpostiin.

Todistus liitetään yleensä kerran kuhunkin palveluun. Palvelu tallentaa tarkistetun yhteyden omaan käyttäjätiliin; käyttäjä ei toimita tiedostoa jokaisella kirjautumisella. Sähköpostin vaihtuessa sidonta tarkistetaan uudelleen, ja vanha todistus ei automaattisesti siirry uudelle osoitteelle.

Sähköpostitoimitus on säilytys- ja palautuskeino, ei lisätodiste sähköpostin hallinnasta. Käyttäjä pyytää toimituksen nimenomaisesti. Lähetys kohdistetaan tarkistetun viestin vastaanottajaosoitteeseen, ei vapaasti syötettyyn kolmannen osapuolen osoitteeseen. Lähetysrajoitukset estävät toiminnon käyttämisen roskapostiin. Epäonnistunut lähetys ei mitätöi ladattavaa todistusta.

Ensiversioon tiedostotuonti on selkein. Myöhemmin voidaan tehdä ”Kopioi todistuslinkki” ja palvelukohtainen suora siirto. Pelkkä julkinen Arweave-linkki ei sisällä sidonnan avaamiseen tarvittavaa salaisuutta.

## 3. Julkinen ja yksityinen sisältö

Arweaveen tallennetaan allekirjoitettu JWS-objekti. Alla on sen hyötykuorman luonnos, ei lopullinen skeema:

```json
{
  "type": "HistoricalEmailAttestation",
  "version": 1,
  "issuer": "<Stampd issuer identifier>",
  "credentialId": "<random identifier>",
  "policyId": "stampd-historical-email-v1",
  "policyDigest": "<hash of immutable policy>",
  "cutoff": "<agreed UTC timestamp>",
  "emailCommitment": "<base64url SHA-256>",
  "commitmentScheme": "stampd-email-v1",
  "normalization": "stampd-email-normalization-v1",
  "evidenceClass": "approved-government-notification",
  "checks": {
    "approvedDkimSigner": true,
    "signedRecipient": true,
    "signedDateBeforeCutoff": true
  },
  "issuedAt": "<UTC timestamp>",
  "statusReference": "<signed status mechanism>"
}
```

JWS:n suojattu otsake sisältää algoritmin, tyypin ja myöntäjän avaintunnisteen. Käytetään ylläpidettyä kirjastoa ja kiinnitettyä sallittujen algoritmien listaa. Todistuksessa mainittu avain tai URL ei itsessään tee myöntäjästä luotettua: palvelu konfiguroi hyväksytyt myöntäjät ja avaimet erikseen.

Yksityinen `stampd-proof.json` sisältää:

```json
{
  "format": "stampd-proof-package-v1",
  "arweaveTxId": "<transaction id>",
  "signedCredential": "<same JWS as on Arweave>",
  "disclosure": {
    "randomSecret": "<base64url of 32 random bytes>"
  }
}
```

Sähköpostia ei tarvitse sisällyttää pakettiin: vastaanottava palvelu käyttää omaa vahvistettua osoitettaan. Allekirjoitetun todistuksen paikallinen kopio helpottaa säilyttämistä ja tarkistamista gatewayn häiriötilanteessa. Arweave-julkaisun tila tarkistetaan erikseen.

Julkiseen tietueeseen, Arweave-tageihin tai lokeihin ei laiteta sähköpostia, salaista satunnaisarvoa, alkuperäistä viestiä, verotietoja, viestin otsikkoa tai Message-ID:tä. Tarkkaa viestipäivää ja lähettäjäverkkotunnusta ei julkaista oletuksena: hyväksytty todistusluokka ja sääntö riittävät. Sääntö voi silti paljastaa esimerkiksi viranomaisen tai maan.

## 4. Sähköpostin sidonta ja salasanavaihtoehto

Sidonta lasketaan SHA-256:lla yksiselitteisesti koodatusta kokonaisuudesta, jossa ovat protokollatunniste, normalisoitu sähköposti ja 32 tavun kryptografisesti satunnainen salaisuus. Lopullinen tavukoodaus määritellään ja lukitaan yhteisillä testivektoreilla. Saman osoitteen erillisiin todistuksiin luodaan eri satunnaisarvot.

Normalisointi on versioitu: verkkotunnuksen kirjainkoko ja kansainväliset verkkotunnukset käsitellään sovitusti. Paikallisosaa ei yleisesti muuteta pieniksi kirjaimiksi eikä pisteitä tai plus-osia poisteta. Monitulkintaiset tai tukemattomat osoitteet hylätään ensiversiossa. Palvelun normalisointiero ei saa johtaa eri osoitteiden hyväksymiseen samaksi.

Salasana on vapaaehtoinen yksityisen paketin suoja. Käytetään Argon2id:llä johdettua avainta ja autentikoitua salausta; parametrit, satunnainen KDF-suola ja salauksen nonce tallennetaan salattuun pakettiin. Salasana ei ole sähköpostisidonnan satunnaisarvo eikä sitä anneta vastaanottavalle palvelulle. Avaaminen tehdään käyttäjän laitteella ennen tuontia.

Salasanan vaihtaminen salaa saman paketin uudelleen eikä muuta Arweave-todistusta. Unohtunutta salasanaa ei voida palauttaa ilman muuta avaamatonta varmuuskopiota. Ensiversiossa priorisoidaan tavallinen ladattava ja sähköpostitse toimitettava paketti; salattu vienti lisätään erillisenä vaiheena.

Paketti on yksityinen: sen haltija voi testata arvattuja osoitteita sidontaa vasten. Se ei silti kelpaa palvelun sähköpostivahvistuksen korvikkeeksi. Sähköpostiliite on käyttäjän ja sähköpostipalvelun saatavilla; se ei ole päästä päähän salattu oletuksena.

## 5. Viestin hyväksyminen

- Käytetään alkuperäisiä viestitavuja. Kuvakaappaus tai tavallinen edelleenlähetyksen tekstiosa ei riitä.
- Säännössä sallitaan tarkat DKIM-allekirjoittajat ja viestiluokat. Pelkkä näkyvä From-osoite tai viranomaisen nimi ei riitä.
- Sama hyväksytty DKIM-allekirjoitus suojaa väitteen kannalta tarvittavaa vastaanottajaosoitetta, päiväystä ja sisältöä. Tarkistetaan myös lähettäjän suhde sallittuun allekirjoittajaan.
- Hylätään monitulkintaiset kaksoisotsakkeet, usean vastaanottajan tapaukset ensiversiossa, puuttuvat suojatut kentät ja DKIM:n osittaiseen runkoallekirjoitukseen perustuvat tapaukset. Parserin ja tarkistajan on tulkittava samat kentät.
- Rajapäivä on kiinteä sääntöversiolle. Sitä ei anneta asiakkaan vapaasti valita. Päiväys muunnetaan UTC:ksi; rajalla hyväksytään vain aidosti aikaisemmat ajankohdat.
- DKIM:n suojaama päiväys on lähettäjän väite ajasta, ei riippumaton aikaleima. DKIM:n allekirjoitusaika ei myöskään muuta tätä luottamusmallia.
- Puuttuva vanha DNS-avain tuottaa tuloksen ”ei todennettavissa”. Käyttäjän toimittamaa avainta ei hyväksytä ilman erikseen määriteltyä luotettavaa historiallista lähdettä. Vanhan allekirjoitusavaimen myöhempi vuoto voi mahdollistaa takautuvasti päivättyjä väärennöksiä; pelkkä rajapäivä ei estä niitä.
- Viestiluokka rajataan pilotissa tarkasti. Yrityksen, perheenjäsenen tai päämiehen puolesta saadut ilmoitukset eivät automaattisesti kelpaa henkilökohtaiseen ihmisyyssignaaliin.
- AI voi auttaa viestiluokan arvioinnissa, mutta ei ohittaa kryptografisia hylkäyksiä. Epäselvä luokittelu ei myönnä todistusta. Viestin sisältö on epäluotettua dataa, ei ohjeita tarkistajalle.

Ensimmäinen toteutusvaihe tarkistaa käyttäjän luvalla muutaman aidon esimerkin: täyttävätkö hyväksyttävät viestit todella DKIM-, vastaanottaja- ja päiväysvaatimukset? Tuotantokelpoisuutta ei oleteta ennen tätä. Näytteitä tai niiden henkilötietoja ei viedä repositorioon.

## 6. Vastaanottavan palvelun tarkistus

1. Palvelin tunnistaa kirjautuneen tilin ja hakee oman luotetun tietonsa vahvistetusta sähköpostista. Asiakkaan ilmoittama `emailVerified=true` ei riitä.
2. Parseri tarkistaa paketin skeeman ja kokorajat. Arweave-tunniste käsitellään tunnisteena, ei mielivaltaisena palvelimen haettavana URL:na.
3. Palvelu tarkistaa myöntäjän allekirjoituksen, luotetun avaimen, hyväksytyn sääntöversion ja rajapäivän sekä peruutustilan ja tilatiedon tuoreuden.
4. Palvelu laskee sidonnan omasta vahvistetusta sähköpostista ja paketin satunnaisarvosta.
5. Palvelu varmistaa Arweave-tallennuksen ja allekirjoitetun kopion vastaavuuden hyväksymispolitiikkansa mukaan. Julkaisun ollessa kesken käyttöliittymä näyttää odottavan tilan.
6. Palvelu liittää tuloksen käyttäjätiliin ja säilyttää tarvittavan todistustunnisteen, sääntöversion ja tarkistusajankohdan. Satunnaisarvoa ei tallenneta tarpeettomasti.

Sama julkinen tunniste mahdollistaa käytön yhdistämisen palvelujen välillä. Tämä hyväksytään MVP:n ominaisuutena; anonyymi eri palveluihin todistaminen vaatii erillisen ratkaisun. Sähköpostin kierrätys uudelle omistajalle on mallin rajoite: historiallinen todistus seuraa osoitetta, ei varmasti samaa ihmistä.

## 7. Myöntäminen, elinkaari ja palautus

Stampd:n allekirjoitus on myöntäjän lausuma tekemistään tarkistuksista. Alkuperäistä viestiä näkemätön palvelu luottaa tähän lausumaan. Arweave todistaa tallennetun tietueen eheyden ja pysyvyyden, ei itsenäisesti DKIM-tarkistuksen tai ihmisyysarvion oikeellisuutta.

Sääntötiedosto julkaistaan muuttumattomana versiona. Tuotantoon määritellään allekirjoitusavainten säilytys, kierto, vanhojen avainten luotettu historia, kompromissien käsittely sekä allekirjoitettu, tuoreusrajattu peruutuslista. Todistusta ei voi poistaa Arweavesta; virheellinen todistus peruutetaan. Peruutustiedon puuttuessa palvelu näyttää ”ei voitu tarkistaa”, ei onnistumista.

Alkuperäinen viesti käsitellään tilapäisesti eikä sitä julkaista tai säilytetä pysyvästi. Myös jonojen, virhelokien ja mahdollisen AI-palvelun tietojen säilytys määritellään ennen tuotantoa. Sähköpostin lähetysjonossa yksityinen paketti säilytetään suojattuna rajatun ajan ja poistetaan toimituksen tai määräajan jälkeen.

Sähköpostiin toimitettu liite ja paikallinen lataus ovat MVP:n palautuskeinot. Kadonnutta satunnaisarvoa ei voi palauttaa Arweavesta. Jos molemmat kopiot katoavat, käyttäjä voi hakea uuden todistuksen alkuperäisellä viestillä, jos se voidaan edelleen tarkistaa. Stampd ei lupaa ikuista palautusta.

Myöhempi jakolinkki voi sisältää yksityisen paketin URL-fragmentissa. Sitä ei toteuteta tavallisena query-parametrina. Fragmenttikaan ei suojaa sivun JavaScriptiltä, selainhistorialta tai linkin vastaanottajalta: avaussivulla ei saa olla analytiikkaa tai kolmannen osapuolen skriptejä. Tiedostopohjainen MVP välttää tämän lisäpinnan.

## 8. Toteutus nykyiseen projektiin

Alustavan katselmuksen perusteella `email_eml.py` säilyttää alkuperäisiä viestitavuja ja sisältää `verify_dkim_raw`-toiminnon. `main.py` sisältää EML-latauksen ja `_irys_upload`-toiminnon. Nykyinen yleinen DKIM-tulos ei yksin riitä tämän ominaisuuden allekirjoitettujen kenttien ja hyväksymissäännön tarkistamiseen.

Ehdotetut uudet moduulit:

- `historical_email_policy.py`: sääntöskeema, sallitut allekirjoittajat, viestiluokat, rajapäivä ja normalisointi.
- `historical_email_proof.py`: kenttien suojaustarkistus, hyväksymispäätös, sidonta ja allekirjoitus.
- `proof_delivery.py`: yksityinen vientipaketti ja käyttäjän pyytämä sähköpostitoimitus.
- `proof_verifier.py`: vastaanottajan käyttämä tarkistuskirjasto ja testivektorit.
- Erillinen näkymä nykyisen sähköpostitoiminnon yhteyteen sekä demo vastaanottavasta palvelusta.

Tarkat endpointit suunnitellaan nykyisen istunto- ja latausmallin perusteella. Luonnos: tarkista viesti, julkaise hyväksytty todistus, lataa paketti ja pyydä toimitus. Palvelin sitoo julkaisemisen omaan tarkistettuun tulokseensa; selain ei saa syöttää hyväksyntäarvoja tai vaihtaa vastaanottajaa. Julkaisu ja lähetys ovat idempotentteja, rajattuja operaatioita.

## 9. Työvaiheet ja hyväksymiskriteerit

1. **Toteuttamiskelpoisuus:** tarkistetaan aidot näytteet ja valitaan yksi hyväksyttävä viestiluokka. Sovitaan todellinen rajapäivä. Mikäli vaatimukset eivät täyty, raportoidaan este eikä heikennetä tarkistusta hiljaisesti.
2. **Protokolla:** lukitaan skeemat, tavukoodaus, normalisointi, säännön versiointi, myöntäjän luottamus ja peruutusmalli. Kirjoitetaan yhteiset testivektorit.
3. **Paikallinen kokonaisuus:** EML-tarkistus → allekirjoitettu todistus → yksityinen vienti → demopalvelun tarkistus omalla vahvistetulla sähköpostilla.
4. **Arweave:** integroidaan julkaisu, odottava/vahvistettu tila, uudelleenyritykset ja tallennetun tietueen tarkistus.
5. **Käyttökokemus:** lataus, käyttäjän pyytämä sähköpostikuitti, liitteen tuonti ja selkeät virhetilat. Sähköpostilähetys edellyttää valittua lähetyspalvelua ja lähettäjäverkkotunnuksen asetuksia.
6. **Pilotti:** yksi hyväksytty viestiluokka ja oma vastaanottajademo. Oikea Reddit-integraatio on erillinen yhteistyö- tai integraatiotyö.
7. **Jatkokehitys:** salasanalla suojattu vienti, suora siirto integroituihin palveluihin ja tarvittaessa anonyymit todistukset.

Keskeiset testit: väärä lähettäjä, rikottu allekirjoitus, allekirjoittamaton To/Date, otsakkeiden monistaminen, osittainen runkoallekirjoitus, väärä tai rajalla oleva päiväys, puuttuva DNS-avain, väärä sähköposti tai salaisuus, muutettu paketti, tuntematon myöntäjä, peruutettu todistus, vanhentunut tilatieto ja julkaisun tai sähköpostitoimituksen epäonnistuminen. Lisäksi varmistetaan, ettei julkinen tietue tai lokitus vuoda yksityisiä tietoja ja ettei toistettu pyyntö aiheuta tarpeettomia julkaisuja tai viestejä.

Valmis MVP: käyttäjä saa hyväksytystä viestistä todistuksen Arweaveen, lataa yksityisen paketin tai pyytää sen sähköpostiinsa ja tuo sen demopalveluun. Demo hyväksyy sen vain omaan vahvistettuun sähköpostiin täsmäävänä, luotetun myöntäjän allekirjoittamana ja hyväksytyn säännön sekä voimassa olevan tilatiedon mukaisena.

## 10. Tekninen tausta

- DKIM: https://www.rfc-editor.org/rfc/rfc6376/
- JWS: https://www.rfc-editor.org/rfc/rfc7515
- Argon2: https://www.rfc-editor.org/rfc/rfc9106
- Arweaven pysyvä tallennus: https://docs.arweave.org/developers/development/motivation

Linkit ovat toteutuksen taustalähteitä. Toteutuksen alussa tarkistetaan käytettävien kirjastojen ja algoritmien ajantasaiset vaatimukset.
