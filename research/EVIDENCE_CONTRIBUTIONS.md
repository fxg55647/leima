# Todistepaketin ehdottaminen pull requestilla

Tutkimukseen voi ehdottaa itse luotua Leima-todistepakettia, myös silloin kun
tekijällä ja tarkastajalla on eri pääsyoikeudet lähteeseen. Tunnuksia ei jaeta.
Tämä menettely kirjaa saatavuuden ja toteutuneet tarkastukset. Repositorion
ylläpitäjä päättää hyväksyttävästä aineistosta ja jakelutavasta.

## Ehdotuksen tekeminen

1. Valitse tutkimus, väite ja lähde. Kirjaa lähtöcommit täydellisenä SHA:na.
   Säilytä paketissa arvioitu väite täsmälleen alkuperäisessä muodossaan.
2. Luo Leima-paketti ja laske alkuperäisen ZIP-tiedoston SHA-256. Esimerkiksi:
   `Get-FileHash -Algorithm SHA256 -LiteralPath 'paketti.zip'`.
3. Kopioi [ehdotustietue](evidence-contribution.example.json) tutkimuksen
   `evidence-contributions/`-kansioon yksilöllisellä nimellä. Esimerkki on pohja,
   ei valmis todiste. Täytä tunnisteet, versio, paketin tiiviste ja saatavuus.
4. Paketin sijainti voi olla `repository`, `external` tai `on_request`.
   Kirjaa lähteen ja paketin saatavuus erikseen. `access` on kuvaileva tieto:
   `public`, `restricted` tai `unknown`; se ei ole lisenssi- tai oikeuspäätös.
   `location` on suhteellinen tiedostopolku tai URL, tai null kun pakettia
   pyydetään erikseen. Älä laita tietueeseen tunnuksia tai salaisia latauslinkkejä.
5. Tee PR käyttäen [todistepaketin PR-pohjaa](../.github/PULL_REQUEST_TEMPLATE/evidence_contribution.md).
   Tässä repossa kohdehaara on staging. Ehdotus voi sisältää paketin tai vain
   sen viitetiedot. Kerro myös mihin avoimeen saatavuusongelmaan se vastaa.

## Kolme erillistä tarkastusta

Jokainen tarkastus saa oman tietueensa. Alkuarvo on `not_checked`.
Merkitse tekijä, päivä, laajuus, rajoitukset ja todellinen tulos:

- `package_integrity`: `not_checked`, `passed`, `failed`, `inconclusive`.
  Vertaa ZIP:n SHA-256:ta ja tarkasta lisäksi Leima-paketin sisäinen manifesti
  asianmukaisella validaattorilla. Kirjaa käytetty työkalu ja tulos laajuuteen.
  Pelkkä ZIP:n tiivistevertailu ei riitä koko paketin `passed`-tulokseen.
- `assessment_review`: `not_checked`, `reviewed`, `inconclusive`.
  Kirjaa, mitä Leiman arviosta luettiin ja mitä huomautuksia siitä syntyi.
  `reviewed` tarkoittaa luettua arviota, ei sen oikeellisuuden hyväksyntää.
- `original_source`: `not_checked`, `checked`, `inconclusive`.
  Kirjaa todella luetut lähdekohdat ja se, mistä lähde saatiin. Jos tarkastaja
  lukee vain paketin sisältämän lähdekopion, kirjaa tämä laajuuteen;
  se ei ole riippumaton tarkastus julkaisijan kappaleesta.

Eheys ei todista lähteen aitoutta tai väitteen totuutta. Myös epäonnistunut tai
rajallinen tarkastus on hyödyllinen kirjattava tulos. Jos toisen henkilön
tarkastus lisätään, säilytä aiempi tietue ja lisää uusi `reviews`-listaan.
Paketin vaihtaminen muuttaa tiivisteen ja edellyttää uutta ehdotusversiota;
aiemman paketin tarkastuksia ei siirretä uuteen pakettiin.

## Hyväksyminen tutkimukseen

Ylläpitäjä tarkastaa ehdotuksen rajauksen ja päättää liittämisestä. Lisää
hyväksytty lähde ja alkuperäistä arvioitua väitettä vastaava leima nykyisiin
`sources`- ja `stamps`-listoihin tietomallin ohjeen mukaan. Väitetulkinnan muutos
perustellaan erikseen. PR:n yhdistäminen ei tarkoita väitteen vahvistamista.

Ehdotustietueet ovat tässä vaiheessa erillisiä JSON-tiedostoja. Nykyinen
tutkimusrakentaja ei validoi tai renderöi niitä eikä tarkasta ZIP-paketteja
automaattisesti. Tarkastustulokset ovat tekijöiden kirjauksia. Nykyisen
`research.json`-mallin `source.access` koskee julkaistavaa metadataa;
sitä ei pidä sekoittaa ehdotuksen alkuperäislähteen saatavuuteen.
