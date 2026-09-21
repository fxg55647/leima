# Sähköpostin leimaaminen Bcc-kopiosta

Suunnitelma 22.9.2026. Ei tuotantokäyttöönottoa eikä toteutusmuutoksia.

## Käyttökokemus

Lähettäjä kirjoittaa viestin normaalisti ja lisää henkilökohtaisen Leima-osoitteensa Bcc-kenttään, esimerkiksi `leimaa+<satunnainen-tunniste>@in.example.fi`. Vastaanottaja saa alkuperäisen viestin tavalliseen tapaan ja myöhemmin Leimalta erillisen viestin, jossa on leimattu ZIP ja validointiohjeet. Bcc-kopio ei voi korvata tai viivyttää alkuperäistä toimitusta.

Ensimmäinen versio lähettää paketin vain To-kentän osoitteisiin, enintään viiteen, kullekin erillisenä viestinä. Cc ja muut Bcc-vastaanottajat eivät saa automaattista toimitusta. To ei todista, että alkuperäinen viesti toimitettiin tai luettiin. Leima voi todistaa vastaanottamansa kopion sisällön ja vastaanottohetken tarkistukset.

## Nykyisen toteutuksen hyödyntäminen

- `notary.py`: IMAP-vastaanotto, DKIM-tarkistus, EML-tiiviste, Arweave-leima ja SMTP-lähetys ovat jo olemassa. Nykyinen toteutus lähettää To- ja Cc-osoitteisiin erilliset EML- ja JSON-liitteet. UNSEEN-lippu ei riitä tuotannon työnhallintaan: osittainen toimitusvirhe voi aiheuttaa uusintaleiman ja kaksoistoimituksia.
- `email_eml.py`: alkuperäiset tavut säilyttävä MIME-käsittely, liitteiden luettelointi ja kokorajat voidaan hyödyntää.
- `historical_email_proof.py`: sisältää allekirjoitettujen kenttien ja osittaisen runkoallekirjoituksen tarkistuksia. Irrotetaan yleiskäyttöiset osat; henkilöllisyystodistuksen erityissäännöt eivät kuulu tähän palveluun.
- `evidence_package.py`, `PACKAGE_FORMAT.md` ja `validator.html`: nykyinen ZIP v2 edellyttää neljää verdict-tiedostoa. Uutta notaaripakettia ei voi vain syöttää nykyiseen lukijaan.

## Vastaanotto ja hyväksymissäännöt

1. SES vastaanottaa viestin erillisellä vastaanottoaliverkkotunnuksella. SMTP envelope -vastaanottaja tunnistaa Leima-tilin; Bcc-otsakkeen olemassaoloa ei vaadita. Tiliin sidotaan vahvistettu lähettäjäosoite, kiintiö ja peruutettava satunnainen osoitetunniste.
2. Tallennetaan palveluntarjoajan toimittama raw MIME yksityiseen objektivarastoon täsmälleen vastaanotettuina tavuina. Mahdolliset vastaanottopalvelun lisäämät otsakkeet dokumentoidaan. Ei MIME-uudelleenserialisointia ennen DKIM-tarkistusta tai tiivistystä. Jonoviesti sisältää vain objektiviitteen ja luotetun vastaanottometatiedon.
3. Tarkistetaan DKIM itse raakaviestistä. Palveluntarjoajan DKIM/SPF/DMARC-tulokset tallennetaan lisätiedoksi vain luotetusta tapahtumasta; viestin omia Authentication-Results-otsakkeita ei uskota sellaisenaan.
4. Vähintään yhden saman hyväksytyn allekirjoituksen pitää täyttää kaikki ehdot: kryptografinen tarkistus onnistuu, allekirjoittajan verkkotunnus on From-kenttään kohdistuva, From ja To ovat allekirjoitettuja ja koko runko on katettu. MVP hylkää kaikki `l=`-allekirjoitukset. Useita DKIM-allekirjoituksia sallitaan; ehtoja ei yhdistellä eri allekirjoituksista.
5. Vaaditaan yksi yksiselitteinen From- ja To-otsake, yksi From-postilaatikko sekä kelvollisesti jäsentyvä To-osoitelista. Tarkistetaan varsinaisten käytettyjen otsake-esiintymien kattavuus. Lähettäjän on vastattava tilin sallittua osoitetta. Domain-alignment tehdään standardin mukaan organisaatiodomaineilla tai tiukalla täsmäyksellä, ei merkkijonon loppuosatestillä.
6. Poistetaan toimituslistasta Leiman omat osoitteet ja duplikaatit. Tyhjä tai liian suuri lista hylätään. To luetaan alkuperäisestä otsakkeesta sähköpostiparserilla, ei näyttönimestä eikä Reply-To-kentästä.
7. Tarkistetaan haittaohjelmat ja MIME-rajat. MVP-ehdotus: raw EML enintään 10 MiB, To enintään 5, nykyiset MIME-syvyys- ja osamäärärajat. Lopullinen lähtevän MIME-viestin koko tarkistetaan erikseen: base64 kasvattaa kokoa. Ylisuuri paketti hylätään hallitusti; suojattu latauslinkki voidaan lisätä myöhemmin.

Virheellinen tai puuttuva DKIM ei tuota hyväksyttyä todistusta eikä vastaanottajatoimitusta. Tilapäinen DNS-virhe uudelleenyritykseen; pysyvä virhe hylkäykseen. Virhetieto näytetään tilillä tai toimitetaan ennalta vahvistettuun tiliosoitteeseen, ei mielivaltaiseen From-osoitteeseen.

DKIM ei yksin estä roskapostia, todista henkilöllisyyttä tai anna oikeutta käyttää Leimaa lähetysreleenä. Tilikohtainen lupa, lähettäjäsidonta, kiintiöt, toistojen tunnistus ja vastaanottajakohtaiset estot tarvitaan. Bcc-tunniste on pidettävä yksityisenä eikä sitä julkaista todistuksessa.

## ZIP ja leima

Lisätään erillinen versionoitu `email-notary`-pakettiprofiili sekä Python- että selainvalidaattoriin. Nykyinen analyysipaketti v2 säilyttää oman tulkintansa. Paketin tunniste ja säännöt dokumentoidaan ennen toteutusta; tuntemattomat profiilit hylätään.

Ehdotettu sisältö:

```text
manifest.json
original.eml
attachments.json
verification.json
README.txt
```

`original.eml` sisältää koko viestin liitteineen. Liitteitä ei tarvitse kopioida erillisiksi ZIP-jäseniksi: koko EML:n tiiviste kattaa myös niiden MIME-esityksen. `attachments.json` luettelee MIME-polun, turvallisen näyttönimen, koon, tyypin ja dekoodatun sisällön SHA-256:n, myös inline-liitteille. Liitetunnistus ei perustu pelkkään tiedostonimeen. Viestiä tai liitteitä ei suoriteta eikä HTML:ää renderöidä validoinnissa.

`verification.json` sisältää tarkistusajan, hyväksytyn DKIM-allekirjoituksen tunnisteen, d/s/a/c/h-tiedot, alignment-tuloksen, koko rungon kattavuuden, käytetyn julkisen DNS-avaimen ja tarkistusohjelmiston version. Tallennettu DNS-vastaus on Leiman havainto eikä itsenäinen todistus historiallisesta DNS-tilasta.

Manifesti sitoo kaikkien muiden tiedostojen täsmälliset tavut SHA-256-tiivisteillä. Leima allekirjoittaa kanonisen manifestin omalla julkaistulla avaimellaan; avaimen tunniste ja rotaatio kuvataan. Tämä erottaa Leiman lausuman kenen tahansa Arweaveen lataamasta JSON-tiedostosta.

Yksityistä viestiä, osoitteita, otsikkoa, Bcc-tunnistetta tai liitenimiä ei julkaista Arweaveen. Julkaistaan vain versionoitu sitoumus: SHA-256(domain separation || satunnainen 32 tavun nonce || kanoninen allekirjoitettu manifesti). Nonce ja allekirjoitus säilyvät ZIP:ssä. `stamp`-ankkuriviite lisätään vasta jälkeenpäin eikä sisälly omaan sitoumukseensa. Tämän profiilin ankkurintarkistus on toteutettava erikseen nykyisestä julkisen manifestin vertailusta.

Paketti rakennetaan kerran samoista tavuista. Uudelleenlähetys käyttää samaa pakettia ja ankkuria. Lähetys tapahtuu vasta kun ankkuri voidaan tarkistaa; julkaisu palveluntarjoajalle ja vahvistettu ankkuri erotetaan tiloissa. Paikallinen tarkistusaika, viestin Date ja ankkurin aikaleima esitetään eri asioina.

## Vastaanottajan viesti ja validointi

Lähettäjä on Leiman oma DKIM-allekirjoitettu osoite. Alkuperäistä From-osoitetta ei käytetä lähetysidentiteettinä. Viestissä on paketin tunniste, ZIP-liite ja esimerkiksi seuraavat ohjeet:

> Liitteenä on Leiman leimaama kopio sähköpostista liitteineen. Tallenna ZIP, avaa Leiman /validate-sivu ja valitse ZIP. Pakettia ei tarvitse purkaa. Tarkistin tarkistaa sisällön eheyden, Leiman allekirjoituksen ja julkisen ankkurin. Säilytä ZIP myöhempää tarkistamista varten.

Validaattori käsittelee yksityiset tavut selaimessa ja hakee verkosta vain ankkurin ja luotetut avaintiedot. Näytetään erikseen sisällön eheys, Leiman allekirjoitus, ankkurin tila sekä Leiman vastaanottohetkellä tekemä DKIM-havainto. Tuore DKIM-tarkistus voi myöhemmin epäonnistua DNS-avaimen vaihduttua; sitä ei sekoiteta alkuperäiseen havaintoon. Verkkovirhe merkitsee tarkistamatta jäänyttä ankkuria, ei hyväksyntää. Todistus ei väitä sisällön totuutta, ihmisen henkilöllisyyttä tai alkuperäisen viestin toimitusta.

## Tuotantopolku ja toimitusvarmuus

SES → yksityinen S3 → SQS → Leiman worker → DKIM/politiikka → paketti ja ankkuri → toimitus-outbox → SES → toimitustapahtumat.

Nykyinen web-sovellus voi pysyä nykyisessä hostingissa. Worker voi lukea jonoa rajatuilla AWS-oikeuksilla. Objektin valmistuminen ja tarkistustulosten saatavuus varmistetaan ennen käsittelyä; S3-tallennus ja jonotapahtuma eivät ole oletuksena atomisia.

Pysyvät tietokantataulut: vastaanotot, tarkistukset, leimaustyöt, paketit ja vastaanottajakohtaiset toimitukset. Tilat: received → verifying → rejected/verified → anchoring → packaged → sending → delivered/bounced/failed. Tapahtumat ja työt varataan atomisesti.

Duplikaatit estetään palveluntarjoajan tapahtumatunnisteella sekä tilin ja viestin sisältöön sidotulla tunnisteella. Pelkkä Message-ID tai vastaanottopalvelun lisäämien otsakkeiden sisältävä raw-hash ei riitä uudelleenlähetysten tunnistamiseen. Tallennetaan lisäksi hyväksytyn allekirjoituksen ja allekirjoitetun sisällön identiteetti. Samaa tunnistetta eri sisällöllä käsitellään ristiriitana.

Verkko- ja ankkurivirheet uudelleenyritykseen viiveellä, pysyvät virheet dead-letter-jonoon. Lähetyksen epäselvä aikakatkaisu sovitetaan palveluntarjoajan tapahtumiin ennen automaattista uusintaa; ulkoisella sähköpostipalvelulla ei luvata täydellistä exactly-once-toimitusta. SES:n hyväksyntä ei vielä tarkoita perillemenoa. Bounce- ja complaint-tapahtumat päivittävät vastaanottajakohtaisen tilan ja estolistan. Automaattivastaukset, DSN-viestit ja Leiman omat viestit eivät käynnistä uutta leimausta.

Ehdotettu säilytys: EML ja ZIP yksityisesti salattuna 7 vuorokautta toimituksen jälkeen, epäonnistuneet työt enintään 30 vuorokautta. Lokit eivät sisällä runkoa tai osoitteita tarpeettomasti. Säilytysajat vahvistetaan tuotteen asetuksiksi; pysyvä julkinen sitoumus jää Arweaveen.

## Palveluvalinta

Suositus: Amazon SES vastaanottoon ja lähetykseen sekä S3/SQS varastoksi ja jonoksi. SES tarjoaa raakamuotoisen MIME-viestin, vastaanoton autentikointitulokset ja SMTP/API-lähetyksen. Esimerkiksi eu-west-1 tukee vastaanottoa. Kokonaisuus vaatii enemmän infrastruktuuria kuin pelkkä sähköposti-API, mutta tarjoaa hyvän perustan alkuperäistavujen säilytykselle ja uudelleenyrityksille.

Käyttöönotto: erillisen aliverkkotunnuksen MX, lähtevän domainin DKIM/SPF/DMARC, SES-tuotantokäyttöoikeus sandboxin ulkopuolelle, rajatut IAM-oikeudet, salaisuuksien hallinta ja bounce/complaint-käsittely. Pelkkä SMTP ei ratkaise Bcc-vastaanottoa. Vastaanoton kokoraja ei myöskään takaa ZIP:n perillemenoa muiden palvelujen vastaanottorajoissa.

Vaihtoehto: Mailgun Routes vastaanottaa ja välittää viestejä HTTP-käsittelyyn. Ennen valintaa kokeillaan raw MIME -tavujen säilyminen ja DKIM päästä päähän; uudelleenrakennettu parsed JSON ei kelpaa todistuksen lähteeksi. Seuranta ja sisältömuokkaukset poistetaan käytöstä. Palvelupaketin vastaanottotuki, alue ja hinta tarkistetaan tilauksen yhteydessä.

Kustannusarvio tehdään vastaanotettujen viestien, To-vastaanottajien määrän, liitetavujen, säilytyksen, workerin ja ankkuroinnin perusteella. Bcc-viesti voi tuottaa viisi lähtevää viestiä; pelkkä saapuvien viestien määrä ei kuvaa kustannusta.

## Toteutusjärjestys ja hyväksymistestit

1. SES-koe omilla testiosoitteilla: Gmail/Outlook ja oma domain, oikea Bcc, raw MIME ja DKIM, liitteellinen paluuviesti. Selvitetään puuttuvan To-allekirjoituksen yleisyys ennen tuotteen avaamista.
2. Yleinen DKIM/politiikkakerros ja tilin lähettäjäsidonta. Testataan moniallekirjoitus, väärennetty To, tuplaotsakkeet, l=, From-alignment ja tilapäinen DNS-virhe.
3. Versionoitu notaaripaketti, Leiman allekirjoitus ja yksityinen ankkurisidonta. Testataan EML:n ja liitteiden muutos, manifestin väärentäminen, väärä avain, tuntematon profiili, ZIP-pommi ja ankkurin puuttuminen.
4. Selainvalidaattori ja yhden ZIP:n ohjeet. Validointi onnistuu ilman sähköpostitiliä tai ZIP:n purkamista. Nykyiset analyysipaketit toimivat edelleen.
5. Pysyvä jono/outbox, rajat ja toimitustapahtumat. Testataan duplikaattitapahtuma, workerin kaatuminen ankkuroinnin jälkeen, yhden vastaanottajan virhe, lähetyksen aikakatkaisu ja automaattivastaussilmukka.
6. Rajattu pilotti: ennalta vahvistetut lähettäjät, kokorajat, kiintiöt ja hälytykset. Hyväksyntä: sama sisältö ja liitteet voidaan validoida, To-muutos estää toimituksen, uusinta ei aiheuta uutta leimaa ja epäonnistuminen näkyy tilillä.

## Lähteet

- [SES-vastaanotto ja autentikointi](https://docs.aws.amazon.com/ses/latest/dg/receiving-email-concepts.html)
- [SES:n tapahtumien sisältö](https://docs.aws.amazon.com/ses/latest/dg/receiving-email-notifications-contents.html)
- [Raakaviestit S3:een](https://docs.aws.amazon.com/ses/latest/dg/receiving-email-action-s3.html)
- [SES-alueet ja rajat](https://docs.aws.amazon.com/general/latest/gr/ses.html)
- [SES-tuotantokäyttö](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html)
- [SES-hinnasto](https://aws.amazon.com/ses/pricing/)
- [Mailgun Routes](https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/routes)
- [Mailgun-reittien toiminnot ja sisältömuokkaukset](https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/route-actions)
- [DKIM RFC 6376](https://www.rfc-editor.org/rfc/rfc6376.html)
