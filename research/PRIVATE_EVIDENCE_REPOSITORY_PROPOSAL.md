# Ehdotus: tutkimuskohtainen yksityinen aineistorepo

7.10.2026 · suunnittelumuistio · ei vielä toteutettu

## Tarkoitus

Tutkimuksen julkisia väitteitä ja lähdeviitteitä voidaan kehittää avoimilla
pull requesteilla, vaikka kaikkea lähdeaineistoa ei julkaistaisi. Osallistuja,
jolla on pääsy lähteeseen, voisi toimittaa Leima-todistepaketin rajattuun
aineistorepoon. Toinen ihminen tai agentti voisi tarkastaa sen omilla
käyttöoikeuksillaan ja palauttaa julkaisukelpoisen tarkastustuloksen.

Yksityinen aineistorepo olisi valinnainen. Pienelle tutkimukselle julkinen
repo ja ulkoinen aineistovarasto voivat riittää. Tutkimuskohtainen repo on
hyödyllinen, kun aineistoilla on yhteinen tarkastajaryhmä; eri käyttöoikeuksia
vaativat paketit voivat tarvita erilliset varastot. Yhden repon lukuoikeutta
ei pidä olettaa tiedostokohtaiseksi pääsynhallinnaksi.

## Työnjako

| Julkinen tutkimusrepo | Yksityinen aineistorepo |
| --- | --- |
| Väitteet, lähdeviitteet ja tarkat kohtaviitteet | Lähdetiedostot ja Leima-todistepaketit |
| Pakettien SHA-256-tiivisteet ja pysyvät tunnisteet | Pakettien sisäiset manifestit ja tarkastukset |
| Julkaisukelpoiset arviot ja tarkastuksen rajoitukset | Rajatun aineiston yksityiskohtaiset tarkastusmuistiot |
| Ehdotusten ja tulkintamuutosten PR:t | Aineiston vastaanoton ja tarkastuksen PR:t |

Julkiseen metadataan ei tarvita yksityisen repon nimeä tai osoitetta, jos
nekin halutaan pitää rajattuina. Tällöin paketti yksilöidään tunnisteella ja
tiivisteellä, ja pääsyn pyyntömenettely kuvataan erikseen.

## Ehdotettu työnkulku

1. Keruuagentti kirjaa puuttuvan lähteen ihmiskäsittelyjonoon.
2. Osallistuja hankkii lähteen omalla pääsyllään ja luo Leima-paketin
   täsmällisestä väitteestä. Palvelutunnuksia ei jaeta.
3. Osallistuja lisää paketin ja ehdotustietueen yksityiseen aineistorepoon
   PR:llä. Tietue yksilöi alkuperäisen ZIP:n SHA-256:lla sekä tutkimuksen
   lähtöcommitin, väitteen, lähteen, saatavuuden ja luetut kohdat.
4. Tarkastaja tai toinen agentti saa aineistorepoon rajatun, tehtävään
   riittävän pääsyn. Agentin pääsy ja aineiston AI-käsittely sovitaan ennen
   ajoa. Repon pääsy ei itsessään käynnistä agenttia tai maksullista työtä.
5. Tarkastaja kirjaa erikseen paketin eheyden, Leiman arvion lukemisen ja
   alkuperäislähteen tarkastuksen. Paketin lähdekopion lukeminen erotetaan
   julkaisijan kappaleen riippumattomasta tarkastamisesta.
6. Julkiseen tutkimusrepoon ehdotetaan PR:llä vain valittu tarkastustulos,
   rajat, lähdeviitteet ja tarkastetun paketin tiiviste. Rajattua aineistoa
   ei kopioida automaattisesti julkisen PR:n sisältöön tai ajolokeihin.
7. Ylläpitäjä päättää tuloksen liittämisestä. Paketin vastaanotto tai PR:n
   yhdistäminen ei itsessään vahvista tutkimusväitettä.

Tarkastajan nimi, käytetty agentti tai malli, päivä, tarkastettu paketti ja
todellinen laajuus kirjataan. Muuttunut paketti saa uuden tiivisteen ja
tarkastuksen; vanhoja tarkastuksia ei siirretä uuteen sisältöön.

## Saatavuus ja oikeudet

Private-repo rajaa aineiston julkista saatavuutta. Se ei yksin ratkaise
aineiston kopioimiseen, jakamiseen tarkastajalle tai AI-käsittelyyn liittyviä
oikeuksia. Repositorion ylläpitäjä ja aineiston toimittaja päättävät
hyväksyttävästä aineistosta soveltuvien oikeuksien ja ehtojen perusteella.
Leima kirjaa saatavuuden ja tarkastuksen kattavuuden; se ei tee pelkästä
private-merkinnästä oikeudellista hyväksyntää.

Pääsyn poistaminen ei poista jo tehtyjä paikallisia kopioita. Git-historia,
CI-lokit ja muut kopiot on huomioitava säilytys- ja poistokäytännössä.
Suuret paketit voivat soveltua paremmin erilliseen aineistovarastoon kuin
Git-historiaan; repo voisi silloin sisältää vain manifestit ja viitteet.

Taustalähteet:

- [GitHub: About repositories](https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories)
- [Tekijänoikeuslaki, erityisesti 13 b §](https://finlex.fi/fi/lainsaadanto/1961/404)

## Suhde nykyiseen toteutukseen

[Todistepakettien PR-ohje](EVIDENCE_CONTRIBUTIONS.md) ja
[ehdotustietue](evidence-contribution.example.json) tukevat jo ulkoista
pakettia, saatavuusmerkintää ja kolmea erillistä tarkastusta. Yksityistä
repoa voisi käyttää tällä käsin tehtävällä menettelyllä.

Automaattinen repon perustaminen, käyttöoikeuksien myöntäminen, agentin
käynnistäminen, paketin validointi ja tulosten siirto julkiseen repoon eivät
kuulu nykyiseen toteutukseen. Muistio ei perusta repoja eikä muuta oikeuksia.

## Ehdotettu ensimmäinen kokeilu

Valitaan yksi tutkimus, yksi jaettavaksi soveltuva paketti ja yksi tarkastaja.
Kokeillaan ensin käsin tehtävää PR-ketjua. Onnistumiskriteerit:

- Tarkastaja saa oikean paketin ja varmistaa sen tiivisteen sekä sisäisen eheyden.
- Tarkastuksen kolme osa-aluetta ja niiden rajoitukset kirjataan erikseen.
- Julkinen tulos yksilöi tarkastetun paketin paljastamatta rajattua aineistoa.
- Käyttöoikeudet sekä säilytys- ja poistokäytäntö ovat tiedossa.

Avoimet päätökset: repon omistaja, tarkastajaryhmä, aineiston säilytyspaikka,
pakettien kokorajat, pääsyn pyyntömenettely ja julkisen tuloksen tarkastus
ennen siirtoa. Automaatiota suunnitellaan kokeilun havaintojen perusteella.
