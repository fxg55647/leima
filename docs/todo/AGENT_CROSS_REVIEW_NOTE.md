# Agenttien allekirjoitetut ristiintarkastuslausunnot

Päiväys: 7.10.2026. Tila: muistiinpano ja toteutusehdotus, ei toteutettu ominaisuus.

## Ajatus

Toinen agentti saa lukea Leiman todistepaketin ja alkuperäisen verdictin, tehdä oman tarkastuksensa ja julkaista päärepossa allekirjoitetun lausunnon. Lausunto voidaan toteuttaa W3C Verifiable Credential -muodossa yhteisen VC-suunnitelman mukaisesti. Se täydentää alkuperäistä arviota; myös eriävä tulos säilytetään.

Muut agentit voivat käyttää pientä, koneellisesti tarkistettavaa lausuntoa oman hyväksymispolitiikkansa mukaan. Alkuperäinen evidenssi jää saataville syvempää tarkastusta varten. Pelkkä merkintä ”tarkastus tehty” ei riitä: tarkastuksen laajuus ja havainnot on kerrottava.

## Lausunnon sisältö

- Todistepaketin täsmällisten tavujen SHA-256-tiiviste ja alkuperäisen verdictin tiiviste, sekä pysyvät tunnisteet tai sijaintiviitteet.
- Tarkastuksen laajuus: tiedostojen eheys, lähteen tuki nimetylle väitteelle, arvioinnin uusiminen tai muu täsmällisesti rajattu tarkastus.
- Tulos: samaa mieltä, eri mieltä tai epävarma; perustelut ja viitteet tarkastettuihin kohtiin. Eheystarkastuksen tulos erotetaan sisällöllisestä arviosta.
- Tarkastajan/myöntäjän tunniste, agentti ja malli, menetelmän ja sääntöjen versiot sekä tarkastus- ja myöntämisajat.
- Lausunnon allekirjoitus ja avaintunniste yhteisen VC-profiilin mukaan.

Allekirjoittaja on agenttia ajava palvelu tai organisaatio omalla avaimellaan. Saman Leima-toimijan toinen agentti tuottaa toisen tarkastuksen; ulkopuolisen toimijan tarkastus tuo lisäksi organisatorista riippumattomuutta. Mallin nimeä ei pidetä allekirjoittajan henkilöllisyytenä.

## Tallennus ja tarkistus

Ehdotettu sijainti päärepossa on `reviews/<paketin-tunniste>/<tarkastaja>/<lausunnon-tunniste>.vc.json`. Lopullinen tiedostopääte määräytyy valitun VC-allekirjoitusmuodon mukaan; JOSE-profiilissa käytetään esimerkiksi `.vc.jwt`-tiedostoa. JSON-kenttien luonnos ei vielä ole valmis VC-skeema.

Lausunto allekirjoitetaan ennen committia. Git-historia tarjoaa jakelun ja muutoshistorian; lausunnon oma allekirjoitus mahdollistaa tarkistuksen myös repositorion ulkopuolella. Yksityiset allekirjoitusavaimet eivät kuulu repositorioon.

Vastaanottaja tarkistaa allekirjoituksen, hyväksytyn myöntäjän ja avaimen, kohteiden tiivisteet, lausunnon laajuuden sekä soveltuvan voimassaolo- ja peruutuspolitiikan. Paketin tai verdictin muuttuessa vanha lausunto koskee edelleen vain vanhoja tavuja ja uusi versio tarvitsee uuden tarkastuksen.

Julkiseen repoon julkaistaan vain siihen soveltuvat lausunnot ja viitteet. Evidenssin käyttöoikeus ja mahdollinen luottamuksellisuus säilytetään myös tarkastuspolussa.

## Liittyvät suunnitelmat

- [W3C VC -siirtymäsuunnitelma](W3C_VC_MIGRATION_PLAN.md): yhteinen allekirjoitus-, evidenssi- ja tarkistuskerros.
- Verdictin mahdollinen kuljettaminen PDF:n tai DOCX:n mukana on erillinen integraatio; ristiintarkastuslausunto voi viitata samaan allekirjoitettuun verdictiin.

## Ensimmäinen pilotti

Valitaan yksi todistepaketti ja väite. Toinen agentti tarkastaa eheyden ja lähteen tuen erillisinä tehtävinä, tuottaa rajatun lausunnon ja allekirjoittaa sen tarkastajapalvelun avaimella. Riippumaton tarkistin varmistaa allekirjoituksen ja tiivisteet. Pilotti kattaa myös eriävän arvion sekä tapauksen, jossa pakettia muutetaan allekirjoituksen jälkeen.
