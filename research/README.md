# Leima Research — yksi tutkimus, monta esitystä

Ensimmäinen paikallinen prototyyppi. Tutkimuksen ensisijainen muoto on `research.json`,
ei generoitu artikkeli. Pysyvät lähde- ja väitetunnisteet yhdistävät esitykset.

## Käyttö

```powershell
.venv\Scripts\python.exe -m research.build research/japan-americas/research.json --out outputs/japan-americas
.venv\Scripts\python.exe -m research.build research/example/research.json --out outputs/research-demo
```

Tulokset: `article.md`, `audit.md`, `index.html`, `research.json`,
`ro-crate-metadata.json` (RO-Crate 1.3) ja `release-manifest.json`.
Verkkonäkymä toimii paikallisena tiedostona ilman ulkoisia skriptejä tai palvelinta.
Esimerkin pelattavat valinnat visualisoivat tulkintaa; ne eivät ole historiallinen simulaatio.
Japanin tutkimuspaketti on avoin suunnitelma, ei valmis tutkimus.

## Tietomalli 0.1

- `sources`: lähde, osoite, täsmällinen kohta, lainaus, lähdekritiikki ja mahdollinen capture-tiiviste.
- `claims`: väite, tila, epävarmuus, riippuvuudet ja perustellut FOR/AGAINST/CONTEXT-suhteet.
- `stamps`: alkuperäinen leimattu väite ja lähde, AI-arvio, verkko ja vahvistustila.
  Leimaa ei siirretä automaattisesti muutetulle väitteelle.
- `work_log`: toteutuneet työtapahtumat. Tyhjä loki ei merkitse nollaa työtä tai kustannusta.
- `game`: kohtaukset ja valinnat, jotka viittaavat väitteisiin ja ilmoittavat lisäoletuksensa.

Tämä on Leiman oma versionoitu malli. RO-Crate kuvaa tiedostot ja viittaa väitteisiin;
tarkat evidenssisuhteet säilyvät JSON-tiedostossa. Täysi RDF-ontologia ja ulkoinen
RO-Crate-vaatimustenmukaisuusvalidointi ovat jatkotyötä. Paikallinen validointi tarkistaa
ID:t, linkit, riippuvuussyklit, tuetut tilat ja keskeiset vientirajat.

## GitHub-työnkulku

### Kritiikki ja vastaukset

Valinnainen `criticisms`-lista sisältää pysyvän ID:n, kohteen (`claim`, `source`
tai `method`), tyypin, prioriteetin (1 tärkein), huomautuksen ja perustelun,
tekijän/mallin, lähdetunnisteet, vastauksen sekä ratkaisun perusteluineen ja vaikutuksineen.
Tilat ovat `open`, `accepted`, `partly_accepted` ja `rejected`.
Suljettu ratkaisu vaatii vastauksen ja perustelun. Kritiikki ei ole automaattisesti vastanäyttöä.

`reviewed_version` ja `reviewed_target_sha256` sitovat huomautuksen arvioituun versioon
ja sen sisältöön. Väitekohteen tiiviste kattaa myös riippuvuudet, niiden lähteet ja menetelmän.
Jos perusta muuttuu, esityksessä näkyy `needs_reassessment`; kirjattu ratkaisu ja vastaus
säilyvät. Pelkkä muualla tehty muutos ei avaa ratkaisua uudelleen.
Uudelleenarvioinnissa säilytä aiempi huomautus ja ratkaisu Git-historiassa ennen uuden
tiivisteen hyväksymistä. Älä päivitä tiivistettä automaattisesti rakentamisen yhteydessä.

Japanin paketissa K1–K3 ovat avoimia tarkistuskysymyksiä, eivät tehtyjä lähdekatselmointeja.
Kritiikit näkyvät artikkelissa, tarkastusnäkymässä, verkkonäkymässä ja RO-Cratessa.

1. Muuta tutkimuksen JSON-tiedostoa ja kirjaa tulkinnan muutoksen peruste.
2. Säilytä ID, jos sama väite täsmentyy; luo uusi ID, jos väite vaihtuu olennaisesti.
3. Tee PR, joka kertoo muuttuneet väitteet, uudet lähdekohdat ja vaikutukset esityksiin.
4. CI validoi ja renderöi tutkimuspaketit. Tarkastaja arvioi lähdeperustan erikseen.
5. Hyväksytty tutkimusversio voidaan julkaista tagilla ja liittää siihen CI:n paketti.

Tässä repossa noudatetaan olemassa olevaa staging/deploy-menettelyä. Tämä lisäys ei
muuta tuotannon deployta, ei luo tagia eikä julkaise mitään automaattisesti.
CI:n zip on koontiartefakti; GitHub Release ja ulkoinen säilytys ovat erillisiä vaiheita.

## Todiste ja tietosuoja

Release-manifesti sitoo kaikkien julkaisutiedostojen täsmälliset tavut SHA-256:lla,
paitsi oman tiedostonsa. Ulkoinen leimatulos tallennetaan erilliseen kuoreen, jotta
omaa leimaa ei lisätä jo tiivistettyyn tiedostoon. Tiiviste ei todista väitteen totuutta.
Rakentaminen on determinististä: sama syöte tuottaa samat julkaisutiedostot.

Raakalähteitä, cookies-tietoja, yksityisiä captureja tai käyttörajoitettua aineistoa
ei lisätä tähän julkiseen malliin. Renderer hylkää muut kuin public-lähteet; tämä ei
korvaa ihmisen metadatan tietosuojatarkistusta. `access: public` tarkoittaa tässä
metadatan julkaisukelpoisuutta, ei kokotekstin lisenssiä tai vapaata saatavuutta.

## Seuraavat kokonaisuudet

- Kirjallisuuskatsaus, lähdepaketit ja tarkat kohtaviitteet Japanin tutkimukseen.
- Työ- ja kustannuslokin formaatti sekä yhteenvedot (puuttuva tieto erikseen).
- Väitemuutosten vaikutusraportti ja julkaisuversioiden vertailu.
- RO-Crate-profiili ja riippumaton validointi.
- Lähteistetty simulaatio/peli, jonka oletukset ovat erillisiä tutkimustuloksista.
- Leima-integraatio release-manifestille; rakentaja ei kutsu leimauspalvelua.
