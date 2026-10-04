# Tutkimuksen arviointi pull requestilla

Anna arvioivalle ihmiselle tai agentille tutkimuksen polku ja Git-commit.
Arvio kohdistuu tähän tilaan, ei epämääräisesti uusimpaan tutkimukseen.
PR:n kohdehaara tässä repossa on `staging`. Arvioija tarvitsee GitHub-oikeuden
haaraan tai voi avata PR:n omasta forkistaan. Ohje ei itsessään anna tunnuksia
eikä käynnistä agentteja tai automaattista yhdistämistä.

## Kopioitava tehtävä agentille

> Arvioi tutkimus tiedostossa [POLKU] commitissa [SHA]. Lue ensin repositorion
> ohjeet ja research/README.md. Tarkista väitteiden lähdeperusta, menetelmä,
> vaihtoehtoiset selitykset ja epävarmuudet. Erota lähteistetty vastanäyttö,
> päättelykritiikki ja avoin tarkistuskysymys. Kirjaa vain perusteltuja huomautuksia;
> jos niitä ei löydy, raportoi tarkastettu laajuus luomatta keinotekoista kritiikkiä.
> Lisää huomautukset criticisms-listaan uusilla pysyvillä ID:illä. Säilytä aiemmat
> huomautukset ja vastaukset. Jätä uuden kritiikin ratkaisu avoimeksi. Älä muuta
> tutkimusväitteitä tai päätä oman kritiikkisi hyväksymisestä. Merkitse lukematta
> jääneet lähteet ja käytetyn mallin tiedon rajat. Validoi, rakenna esitykset ja
> avaa luonnos-PR staging-haaraan; PR:n kuvauksessa ilmoita tarkastettu commit,
> kohteet, havainnot, tarkastuksen rajat ja ajetut tarkistukset.

## Kirjaus

Rajattuun työhön käytä GitHubin `Tutkimustehtävä`-issue-pohjaa. Se sitoo tehtävän
commitiin, kohteeseen, rajaukseen ja valmistumiskriteereihin. Linkitä issue PR:ään.

Luo oma haara, esimerkiksi `codex/review-japan-americas-c1`. Jos sinulla on
jo muutoksia, käytä erillistä checkoutia tai worktreetä. Älä sisällytä muiden työtä.

Uuden kritiikin kentät:

```json
{
  "id": "K4",
  "target": {"kind": "claim", "id": "C1"},
  "type": "missing_evidence",
  "priority": 1,
  "text": "Täsmällinen huomautus",
  "basis": "Perustelu ja mitä havaintoa tarvitaan",
  "author": {"kind": "agent", "name": "Arvioivan agentin nimi", "model": "Tosiasiallinen malli tai tuntematon"},
  "reviewed_version": "Tarkastetun tutkimuksen version arvo",
  "reviewed_target_sha256": "Laske alla olevalla komennolla",
  "sources": [],
  "verification": {"level": "report", "scope": "Luetut raportin kohdat", "limitations": "Lähteiden kokotekstejä ei tarkistettu"},
  "response": "",
  "resolution": {"status": "open", "rationale": "", "changes": ""}
}
```

Tämä on täytettävä pohja, ei validoitu tutkimustietue. Tarkista ID:n vapaus
kaikista listoista. Älä keksi malliversiota. `sources` sisältää tutkimuksen
lähdetunnisteita, ei URL-osoitteita. Lisää tarvittavat uudet julkaisukelpoiset
lähdemetadatat sources-listaan; linkitä tarkka kohta ja erota oma tulkinta lainauksesta.
Muut kohteet ovat `source` ja `method` (jälkimmäisen ID on `method`).
Tyypit: `source_error`, `reasoning`, `missing_evidence`, `alternative`, `sensitivity`.

`verification` kuvaa toteutunutta tarkastusta, ei aiottua työtä tai väitteen
totuusastetta. Tasot: `report` (raportin luku), `source_check` (lähdekohtien
tarkistus), `rerun` (laskennan tai kokeen toisto). `scope` yksilöi tarkastetut
kohdat, lähteet tai ajot; `limitations` ilmoittaa jäljelle jääneet rajat. Valitse
taso huomautuksen perustan mukaan: yhden laskennan toisto ei tarkoita koko
tutkimuksen toistamista. Vanhoista tietueista puuttuva kenttä näkyy muodossa
"ei kirjattu". Älä täydennä sitä oletuksilla. Jos työssä ei löydy huomautuksia,
kirjaa taso, laajuus ja rajat PR:n tai issuen raporttiin.

Laske tiiviste **tarkastetusta syötteestä** ennen kohteen muuttamista:

```powershell
.venv\Scripts\python.exe -c "import json; from pathlib import Path; from research.build import review_fingerprint; d=json.loads(Path('research/japan-americas/research.json').read_text(encoding='utf-8')); print(review_fingerprint(d, {'kind':'claim','id':'C1'}))"
```

Kirjaa reviewed_version samasta syötteestä. Älä päivitä vanhoja tiivisteitä vain
saadaksesi `needs_reassessment`-tilan pois. Jos PR:n kohdehaara muuttuu, säilytä
arvion alkuperäinen sidonta ja tarkasta vaikutus uudelleen.

## Tarkistukset ja PR

```powershell
.venv\Scripts\python.exe -m research.build research/japan-americas/research.json --out outputs/japan-americas
.venv\Scripts\python.exe -m pytest tests/test_research_package.py -q
```

Mukauta input ja output arvioitavaan tutkimukseen. Liitä PR:ään syöte ja sen
uudelleen rakennetut esitykset. CI validoi nykyiset esimerkkipaketit ja tuottaa
koontiartefaktin. Se tarkistaa rakennetta; lähteiden oikeellisuus ja kritiikin
ansio eivät ratkea testien läpäisyllä. Uusi tutkimuskansio tarvitsee myös
rakennuskomennon CI:hin.

Valitse PR-pohja `research_review.md` GitHubin template-parametrilla tai kopioi
sen sisältö PR-kuvaukseen. CLI:llä voit käyttää `gh pr create --draft --base staging
--title "Research review: ..." --body-file <kuvaustiedosto>` oman haaran pushin jälkeen.

## Kritiikin käsittely

Tutkimuksen ylläpitäjä voi yhdistää perustellun huomautuksen avoimena. Tämä
tallentaa kritiikin eikä tarkoita sen hyväksymistä oikeaksi. Vastauksen tekijä
kirjaa erillisessä muutoksessa response- ja resolution-kentät perusteluineen.
Hyväksytyn korjauksen jälkeen changed-target-tarkistus voi näyttää
`needs_reassessment`: arvioijan pitää tarkistaa uusi perusta ennen uuden
tiivisteen kirjaamista. Aiempi arvio ja päätös säilyvät Git-historiassa.

PR-keskusteluun jääneet olennaiset vastaväitteet ja vastaukset tulee siirtää
tutkimustietueeseen, jotta ne näkyvät myös GitHubin ulkopuolisissa esityksissä.
