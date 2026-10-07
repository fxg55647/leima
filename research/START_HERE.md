# Aloita tästä: tutkimukseen osallistuminen

Tutkimuksen ensisijainen aineisto on research.json. Generoitu artikkeli on yksi
esitys siitä. Lue repositorion ohjeet ja [tietomallin ohje](README.md) ennen muutoksia.

**Haluatko tarjota itse luodun Leima-todistepaketin?** Noudata
[todistepaketin PR-ohjetta](EVIDENCE_CONTRIBUTIONS.md). Voit ehdottaa myös
pakettia, jonka alkuperäislähteeseen muilla ei ole pääsyä. Paketin eheys,
arvion lukeminen ja lähteen tarkastus kirjataan erikseen.

## Valitse tutkimus ja rajattu tehtävä

- [Japanilaiset ajelehtijat Amerikassa ennen vuotta 1492](japan-americas/research.json):
  avoin tutkimussuunnitelma. Väitteitä ei ole vielä osoitettu; alustavat lähteet
  eivät tarkoita tehtyä kokotekstien tarkastusta.
- [Finlex-esimerkki](example/research.json): pieni esimerkkipaketti, jolla voi
  kokeilla tiedostomuotoa ja rakentamista.

Katso GitHubin avoimet issuet ja niiden aiemmat kommentit. Valitse
[tutkimustehtävä](../.github/ISSUE_TEMPLATE/research_task.md), jossa on tutkimuspolku,
täysi commit-SHA, kohdetunniste, rajaus ja valmistumiskriteerit. Jos sopivaa
tehtävää ei ole, ehdota sellaista issueen. Tehtävän olemassaolo ei ole käyttäjän
valtuutus käynnistää agenttia, maksullisia ajoja tai viestittää muihin palveluihin.

## Tarkasta sovittu versio

Kirjaa lähtöcommit ennen muokkauksia (git rev-parse HEAD). Käytä tehtävässä
nimettyä versiota ja laske kohteen tiiviste siitä. Ilmoita issueen työn aloittamisesta;
kommentti ei lukitse tehtävää. Pidä muiden paikalliset muutokset erillään.

Lue lähteet mahdollisuuksien mukaan. Erota bibliografinen tieto, todella luettu
lähdekohta ja oma päätelmä. Kirjaa myös saatavuusrajoitukset. Älä korvaa
puuttuvaa tarkastusta oletuksella.

## Palauta arvio, vaikka huomautuksia ei löytyisi

Noudata [arviointiohjetta](REVIEWING.md). Lisää reviews-listaan arviointitietue:
tarkastuksen kohde, tekijä, päivä, commit, tiiviste, todellinen laajuus ja rajat.
Mahdolliset huomautukset kirjataan criticisms-listaan ja linkitetään arvioon.
Tulos no_findings tarkoittaa vain, ettei ilmoitetussa laajuudessa löytynyt
huomautuksia. inconclusive sopii tarkastukseen, jota aineisto ei mahdollistanut.

Rakenna kyseisen tutkimuksen esitykset ja aja tutkimuspaketin testit ohjeen mukaan.
Palauta syöte ja esitykset luonnos-PR:nä staging-haaraan ja linkitä tehtävä.
Ylläpitäjä käsittelee huomautukset erikseen. Älä ratkaise omaa kritiikkiäsi tai
muuta tutkimusväitteitä arvioinnin sivutuotteena.

Jos et voi tehdä PR:ää, palautettu raportti voidaan kirjata myöhemmin; se ei
kuitenkaan ole vielä osa tutkimuspakettia. Älä ilmoita tekemättömiä tarkastuksia.
