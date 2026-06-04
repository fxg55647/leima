# Optimaalinen turvattomuus? — nelikenttä tekoälyagenttien etiikalle

## 1. Silta joka ei saa sortua — ja mitä se maksaa

Insinöörikoulutuksessa elää periaate joka on aivan oikein: edes yksi silta sadasta ei saa sortua. Siltojen kohdalla tämä on järkevää. Vikaantuminen on fysikaalista ja näkyvää, pahin tapaus on tiedossa etukäteen, ja rakentaminen on kertaluonteinen investointi jonka turvallisuusmarginaali voidaan laskea.

Periaate on niin ilmeinen sillalle että se siirtyy helposti muuallekin. Ja siinä piilee ongelma — sillä se piilottaa moraalisen valinnan jonka se oikeasti tekee.

Rakennusbudjetti on aina rajallinen. Jokainen euro jonka käytät sillan yliturvallisuuteen on pois sairaaloista, kouluista tai muista silloista. Nolla-toleranssi yhdessä kohdassa ei ole neutraali valinta — se on implisiittinen päätös hyväksyä suurempi riski toisaalla. Täydellinen turvallisuus yhdessä paikassa maksaa turvallisuutta muualla.

Ja mitä vastaamme kun todennäköisyys pienenee? Yksi silta sadasta on helppo tuomita. Entä yksi kymmenestätuhannesta? Entä yksi kymmenestä miljoonasta — jos ne rahat poistamalla voisit rakentaa kymmenen uutta siltaa sinne missä niitä ei vielä ole? Kysymys ei muutu epämukavammaksi sitä mukaa kun luvut pienenevät. Se muuttuu vaikeammaksi.

Tämä jännite ei poistu tekoälyaikana. Se moninkertaistuu.

Silta-maailmassa riskit ovat tunnettuja ja fysikaalisia. Pahin tapaus on tiedossa etukäteen. Kustannus skaalautuu lineaarisesti turvallisuuden kanssa. Silta ei opi, ei mukaudu eikä toimi autonomisesti.

Tekoälyagenttien maailmassa nämä oletukset hajoavat. Vikaantuminen on usein näkymätön pitkään. Pahin tapaus on tuntematon ja muuttuva. Hyökkääjä mukautuu puolustukseen reaaliajassa. Agentti toimii autonomisesti tilanteissa joita suunnittelija ei osannut ennustaa. Nolla-toleranssi tuntemattomalle ja muuttuvalle riskijoukolle ei ole varovainen tavoite — se on mahdottomuus.

Mutta ongelma ei ole vain tekninen. Se on myös moraalinen.

Tekoälyteknologia jota ei oteta käyttöön turvallisuuspelon takia ei ole turvallinen valinta. Se on näkymätön moraalinen kustannus — kaikille niille joita teknologia olisi voinut auttaa. Kehittäjä joka lykkää hyödyllistä sovellusta siksi että se ei ole sataprosenttisen turvallinen tekee moraalisen valinnan siinä missä kehittäjä joka julkaisee puutteellisen version. Kumpikaan ei pääse moraalisesta vastuusta pakoon pelkästään toimimalla tai olemalla toimimatta.

Tämä ei ole hypoteettinen kysymys. Kun kenialainen mobiilimaksujärjestelmä M-Pesa otettiin käyttöön vuonna 2007, se oli puutteellinen — järjestelmässä oli tietoturva-aukkoja, sääntely oli epäselvää ja väärinkäytösriski todellinen. Silti se julkaistiin. Jo varhaiset tutkimukset osoittivat sen nostaneen satoja tuhansia kotitalouksia pois äärimmäisestä köyhyydestä ja mahdollistaneen naisille siirtymisen maanviljelyksestä liiketoimintaan — ja tämä ennen kuin käyttäjämäärät todella räjähtivät. Jos kehittäjät olisivat odottaneet täydellistä turvallisuutta, nuo ihmiset olisivat odottaneet heidän mukanaan. Teknologian julkaisematta jättäminen ei ole neutraali tila. Se on päätös säilyttää nykyinen kärsimys ennallaan.

Tästä syntyy kysymys jota tämä essee yrittää jäsentää: jos täydellinen turvallisuus ei ole tavoite vaan kustannus, mitä pitäisi optimoida sen sijaan?

Vastauksen hahmottamiseksi tarvitsemme kaksi erillistä akselia. Ensimmäinen on taloudellinen: mikä on odotettu tuotto suhteessa pahimpaan realistiseen vahinkoon? Toinen on moraalinen: onko toiminta itsessään oikeutettua riippumatta taloudellisesta tuloksesta? Nämä akselit muodostavat nelikentän joka ei ratkaise eettisiä kysymyksiä — mutta pakottaa esittämään ne oikein.

## 2. Ensimmäinen kenttä — tuotto vastaan pahin realistinen vahinko

Vastaus alkaa yksinkertaisella havainolla: riski ei ole yksi luku vaan kahden muuttujan tulo. Todennäköisyys kertaa vakavuus. Tämä on tuttu insinööriajattelusta — mutta tekoälyagenttien kohdalla se pakottaa tekemään erottelun jota harvoin tehdään ääneen.

Turvallisuuden optimointi ei tarkoita huolimattomuutta. Se tarkoittaa että turvallisuusinvestointi pitää suhteuttaa siihen mitä oikeasti voi tapahtua — ei pahimpaan kuviteltavissa olevaan skenaarioon vaan pahimpaan realistiseen skenaarioon.

Ero on merkittävä. Kalenterimarämuistutuksia lähettävä agentti voi kyllä toimia väärin. Pahin realistinen vahinko on väärä aika tai peruutettu tapaaminen — kiusallista mutta palautuvaa. Tilintarkastusta tekevä agentti taas voi virheen sattuessa jättää merkittävän taloudellisen poikkeaman huomaamatta. Pahin realistinen vahinko on eri kertaluokkaa.

Tämä johtaa ensimmäiseen käytännön periaatteeseen: turvallisuustaso pitäisi olla toimintokohtainen, ei järjestelmäkohtainen. Sama agentti voi vaatia tiukkaa valvontaa yhdessä toiminnossa ja löysää toisessa.

Todennäköisyys muuttaa laskelman dramaattisesti. Vahinkotodennäköisyys 1/100 on helppo tuomita — se tarkoittaa että joka sadas käyttö päättyy vahinkoon. Mutta entä 1/10 000 000? Jos teknologia auttaa miljoonaa ihmistä päivittäin ja vahinko on kerran kymmenessä vuodessa, laskelma muuttuu. Ei katoa — mutta muuttuu.

Tässä piilee kuitenkin vaara joka pitää tunnistaa. Todennäköisyyslaskenta houkuttelee häivyttämään vahingon laadun sen määrän taakse. Pieni todennäköisyys ei tee vahingosta hyväksyttävää jos se on peruuttamaton, kohdistuu haavoittuvaan ihmiseen tai loukkaa jotain sellaista jonka arvo ei palaudu rahaksi. Siksi pelkkä ensimmäinen kenttä ei riitä.

Palautuvuus on yksi tärkeimmistä muuttujista jota taloudellinen laskenta ei automaattisesti tavoita. Väärä kalenterimerkintä on palautuva — se korjataan. Vuotanut potilasdata on käytännössä ikuinen — sitä ei voi ottaa takaisin. Tämä tarkoittaa että agenttien kohdalla kysymys ei ole vain "voiko virhe tapahtua" vaan "voiko siitä toipua". Peruuttamattomat toiminnot ovat eri kategoriassa kuin palautuvat riippumatta siitä kuinka pieni niiden todennäköisyys on.


## 3. Toinen kenttä — toiminnan moraali

Taloudellinen riski on mitattavissa. Moraalinen akseli on vaikeampaa — mutta ei vähemmän todellista.

Moraalinen akseli kysyy: onko toiminta oikeutettua riippumatta siitä mitä se tuottaa? Tämä on eri kysymys kuin taloudellinen. Taloudellinen kenttä katsoo seurauksia — mitä tapahtuu ja kuinka todennäköisesti. Moraalinen akseli katsoo toiminnan luonnetta — kuka hyötyy, kuka kärsii, ja mikä on toimijan todellinen motiivi.

Otetaan esimerkki. Kaksi kehittäjää tekee saman teknisen päätöksen: he julkaisevat sovelluksen jonka tietoturva ei ole täydellinen. Ensimmäinen kehittäjä tietää että sovellus voi nostaa miljoonia ihmisiä köyhyydestä — hän on nähnyt M-Pesan vaikutukset ja uskoo tekevänsä saman. Toinen kehittäjä tavoittelee vain nopeaa kasvua ja sijoittajarahaa, ja tietoturva on hänelle vain kustannuserä joka hidastaa aikataulua.

Tekninen päätös on identtinen. Moraalinen paino ei ole.

Tämä on tärkeä havainto siksi että se estää kaksi yleistä virhettä. Ensimmäinen virhe on tuomita kaikki epätäydellinen teknologia yhtä ankarasti riippumatta siitä mitä sillä tavoitellaan. Toinen virhe on antaa hyvien tarkoitusten pestä puhtaaksi kaikki tekniset laiminlyönnit — ikään kuin jalot tavoitteet poistaisivat vastuun seurauksista.

Motiivi ei poista vahinkoa. Mutta se vaikuttaa siihen miten vahinkoa pitäisi arvioida ja kenen vastuulla korjaus on.

Moraalinen kenttä ei kuitenkaan ole yksinkertainen asteikko itsekkäästä jalomieliseen. Se on kaksiulotteinen samalla tavalla kuin taloudellinen kenttä. Voidaan kysyä: kuinka laajalle vahinko jakautuu ja kuinka paljon toimija on valmis kantamaan vastuun kun vahinko tapahtuu? Kehittäjä joka julkaisee puutteellisen sovelluksen mutta seuraa aktiivisesti mitä tapahtuu, korjaa virheet nopeasti ja pitää käyttäjät tietoisina on moraalisesti eri asemassa kuin kehittäjä joka julkaisee ja katoaa.

Tässä palataan silta-analogiaan — mutta toisesta suunnasta. Siltarakentaja ei voi katoaa sillan valmistumisen jälkeen. Hän on vastuussa siitä mitä rakentaa. Sama vastuu pätee ohjelmistokehittäjään — ja tekoälyagenttien aikana se vastuu on suurempi kuin koskaan, koska agentti toimii itsenäisesti tilanteissa joita kukaan ei täysin ennustanut.

## 4. Päivä ja yö — missä moraali on selvää

Moraalinen akseli houkuttelee relativismiin. Jos kaikki riippuu kontekstista, motivaatiosta ja todennäköisyyksistä, voiko mikään olla selvästi väärin? Voidaanko sanoa että jokin toiminta ylittää hyväksyttävän rajan — vai onko raja aina neuvoteltavissa?

Filosofiassa tätä kutsutaan sorites-paradoksiksi. Missä kohdassa kasa hiekkajyviä lakkaa olemasta kasa? Missä kohdassa päivä muuttuu yöksi? Tarkkaa rajaa ei ole — mutta se ei tarkoita että kategoriat olisivat merkityksettömiä. Puolenpäivän auringossa ei ole epäselvyyttä. Keskiyön pimeydessä ei ole epäselvyyttä. Hämärä on todellinen mutta se on kapea kaistale kahden selvän alueen välissä.

Sama rakenne pätee moraaliin.

Voimme kiistellä siitä onko tietty tietoturva-aukko hyväksyttävä kun otetaan huomioon teknologian hyöty. Voimme väitellä missä kohdassa vahinkotodennäköisyys on riittävän pieni. Nämä ovat aitoja ja vaikeita kysymyksiä. Mutta on myös asioita joista ei tarvitse kiistellä — jos pysähtyy hetkeksi ajattelemaan.

Aloitetaan helposta tapauksesta. Kehittäjä myy käyttäjiensä potilastiedot kiristäjälle rikastuakseen. Käytännössä jokainen pitää tätä tuomittavana — motiivi on läpinäkyvästi itsekäs ja uhrit maksavat hinnan.

Mutta entä jos motiivi muuttuu? Kehittäjä myy samat tiedot samalle kiristäjälle — mutta lahjoittaa tuoton kokonaan sairaaloiden rakentamiseen. Todennäköisesti lähes yhtä moni tuomitsee tämänkin. Yksittäisille potilaille aiheutuva vahinko on suhteeton ja konkreettinen. Luottamus terveydenhuollon tietosuojaan rapautuu laajemminkin. Hyvä tarkoitus ei poista sitä mitä teolle tehtiin — eikä niille ihmisille joiden tiedot myytiin.

Nämä eivät ole kulttuurisidonnaisia reunatapauksia. Ne ovat moraalisen ajattelun kiintopisteitä — asioita joista lähes kaikki ihmiset ovat yhtä mieltä kun he pysähtyvät ajattelemaan niitä hetken. Kiintopisteet eivät ratkaise harmaata aluetta. Mutta ne asettavat pohjan jonka alle ei voi mennä millään laskelmalla.

Tämä on nelikentän käytännöllisin seuraus. Korkean moraalisen riskin ruutu ei ole hinnoittelukysymys — se on kategorinen raja. Protokolla, sovellus tai agentti joka toimii siellä ei tarvitse tarkempaa riskianalyysiä. Se tarvitsee kieltäytymisen.


## 5. Kenttien vuorovaikutus — missä logiikka pitää ja missä hajoaa

Kaksi kenttää yhdessä tekevät neljä ruutua. Kolme niistä on melko selkeitä. Yksi on petollinen.

Korkea taloudellinen riski ja korkea moraalinen riski on ilmeinen tapaus — älä tee. Matala taloudellinen riski ja matala moraalinen riski on myös selvä — voit ajaa löysemmällä turvallisuudella, vahinko on pieni ja palautuva. Korkea taloudellinen riski ja matala moraalinen riski on vakuutettavissa — tämä on insinöörin ongelma, ei filosofin.

Petollinen ruutu on matala taloudellinen riski ja korkea moraalinen riski.

Se on petollinen siksi että markkinamekanismi ei korjaa sitä. Jos vahinko on taloudellisesti pieni, yrityksellä ei ole taloudellista kannustinta välttää sitä. Mutta moraalinen vahinko voi silti olla suuri — kolmas osapuoli loukattu, yksityisyys rikottu, luottamus menetetty. Tämä on juuri se ruutu jossa vapaat markkinat epäonnistuvat systemaattisesti ja jossa jokin muu mekanismi — läpinäkyvyys, maine, sääntely tai protokollatason kielto — on ainoa korjaus.

Kenttien välillä on myös dynaaminen jännite jota staattinen nelikenttä ei täysin tavoita. Sama toiminto voi siirtyä ruudusta toiseen kontekstin muuttuessa. Kalenterimuistutuksia lähettävä agentti on matalan riskin ruudussa — kunnes se alkaa käsitellä lääkäriaikojen tietoja. Kirjanpitoa tekevä agentti on kohtuullisen turvallinen — kunnes se saa pääsyn asiakkaiden henkilötietoihin. Ruutu ei ole toiminnon ominaisuus. Se on toiminnon ja kontekstin yhdistelmä.

Tässä piilee yksi käytännön vaara jota on vaikea torjua: vähittäinen valuminen. Kukaan kehittäjä ei yleensä päätä astua yön pimeyteen kerralla. Sen sijaan agentti saa tänään pääsyn kalenteriin, ensi viikolla lääkäriaikoihin, ensi kuussa automaattisen reseptien uusimisen. Jokainen askel tuntuu pieneltä. Kokonaisuus on siirtynyt ruudusta toiseen ilman että kukaan teki tietoista päätöstä. Arkkitehtuurin tehtävä on pakottaa uudelleenarviointi aina kun toiminto ottaa askeleen eteenpäin hämärässä.

Tämä johtaa käytännön periaatteeseen joka on helpompi sanoa kuin toteuttaa: turvallisuuspäätökset pitäisi tehdä toimintokohtaisesti ja kontekstisensitiivisesti, ei järjestelmätasolla kertaalleen. Sama agentti voi olla eri ruudussa riippuen siitä mitä dataa se käsittelee, kenen puolesta se toimii ja mitä seurauksia sen virheellä voi olla.

Nelikenttä ei ratkaise näitä kysymyksiä. Se on keskustelun jäsentäjä — työkalu joka estää taloudellisen logiikan salakuljettamisen moraalisen päätöksen varjolla, tai päinvastoin. Oikeat päätökset syntyvät kentän sisällä käytävästä harkinnasta. Mutta ilman kenttää harkinta alkaa helposti väärästä kysymyksestä.


## 6. Pelin muutos jota kukaan silmäätekevä ei kyseenalaistanut

Kaikki ne jotka ovat yrittäneet ottaa tekoälyturvallisuuden vakavasti — OpenAI, NIST, kansainvälinen tiedeyhteisö — ovat lähestyneet sitä samalla perusoletuksella: on olemassa joukko riskejä, ne voidaan tunnistaa, mitata ja hallita prosessilla. Parempi data, paremmat menetelmät, enemmän sidosryhmiä pöytään. Tämä on rationaalinen lähestymistapa — ja se toimii deterministisessä maailmassa.

OpenAI näki jo vuonna 2019 että ihmispuoli on epädeterministinen — julkaisemassaan paperissa he argumentoivat että tekoälyturvallisuus tarvitsee yhteiskuntatieteilijöitä, koska ihmisten arvot ovat epäjohdonmukaisia ja kontekstiriippuvaisia. Kysymys joka jäi kysymättä oli toinen: kenen pitäisi ylipäätään päättää mikä turvallisuusratkaisu on moraalisesti hyväksyttävä — ja onko insinööri oikea ihminen tekemään sen päätöksen yksin? Historian tutkija, lääketieteen etiikko tai yhteisön edustaja jonka data on pelissä näkee petollisen ruudun eri tavalla kuin se joka rakentaa järjestelmää. NIST vei ajatusta pidemmälle vuoden 2023 AI Risk Management Frameworkissaan — tunnustaen eksplisiittisesti että tekoälyriskit ovat sosiotekniisiä, eivät pelkästään teknisiä. Yoshua Bengio kokosi sen helmikuussa 2026 yli sadan asiantuntijan ja kolmenkymmenen maan kansainväliseksi raportiksi. Jokainen askel oli oikea suunta.

Mutta kukaan heistä ei kyseenalaistanut sitä perusoletusta — että malli itse on deterministinen järjestelmä jonka riskit ovat prosessilla hallittavissa.

LLM ei ole deterministinen järjestelmä jossa on tunnistettavia vikoja. Se on tilastollinen järjestelmä jossa sama syöte voi tuottaa eri tuloksen eri kerroilla, jossa "virhe" ei ole poikkeama normaalista toiminnasta vaan normaali toiminta tietyissä tilanteissa, ja jossa kukaan — ei edes rakentaja — ei täysin ymmärrä miksi se tekee mitä tekee. Et voi kartoittaa riskejä järjestelmässä jonka käyttäytyminen on luonteeltaan tilastollinen ja kontekstiriippuvainen. Et voi mitata luotettavuutta samalla tavalla kuin mittaat sillan lujuuden. Et voi korjata ongelmaa päivityksellä kun ongelma ei ole virhe koodissa vaan ominaisuus siitä miten malli toimii.

Ennen LLM:ää tietoturva toimi tai ei toiminut. Regex tunnisti hyökkäyksen tai ei tunnistanut. Palomuuri päästi läpi tai esti. Nämä ovat binäärisiä tiloja — ja binäärisessä maailmassa täydellisyys on ainakin teoriassa saavutettavissa. Seuraava päivitys voi korjata kaiken. Tämä intuitio on jäänyt elämään vaikka maailma muuttui.

LLM:n myötä tietoturva muuttui tilastolliseksi. Ei ole olemassa tilaa jossa järjestelmä "toimii oikein" kaikissa tapauksissa — on vain todennäköisyyksiä, konteksteja ja reunaehtoja. Tämä ei ole väliaikainen ongelma joka ratkeaa seuraavassa versiossa. Se on fundamentaalinen ominaisuus siitä mitä nämä järjestelmät ovat. Odotettava päivitys joka ratkaisee kaiken ei ole myöhässä. Sitä ei ole tulossa.

Tässä piilee myös se miksi tietoturvayhteisö on ollut niin hiljainen. Ratkaisu jonka lähestymistapa ei voi edes periaatteessa koskaan päästä sataan prosenttiin on erilainen suunnittelufilosofia kuin mihin olemme tottuneet — vaikka se korjaisi 95%. Se voi tuntua petokselta, jopa luovuttamiselta. Kuin julkinen tunnustus että tähän se jää. Mutta kenelläkään ei ole hajuakaan miltä täydellinen ratkaisu edes näyttäisi. Ehkä se on olemassa. Mutta jos kukaan ei osaa osoittaa tietä sinne, odottaminen ei ole varovaisuutta — se on piileskelyä hypoteettisen varjossa. Paras saatavilla oleva on parempi kuin täydellisyys jota kukaan ei osaa rakentaa.


## 7. Käytäntö — nelikenttä tekoälyagenttien rakentamisessa

Teoria on hyödyllistä vain jos se muuttaa sitä miten asioita tehdään. Miten nelikenttä näkyy käytännössä kun rakennetaan tekoälyagentteja?

Nykyiset autonomiset agentit — kuten avoimen lähdekoodin OpenClaw, joka saavutti yli 100 000 GitHub-tähteä ensimmäisellä viikollaan vuonna 2026 — voivat lähettää sähköpostia, hallita kalenteria, suorittaa komentoja ja selata verkkoa käyttäjän puolesta. Ne ovat käytännössä ensimmäinen sukupolvi teknologiaa jossa nämä kysymykset tulevat vastaan jokapäiväisessä ohjelmistokehityksessä.

OpenClawın käyttöönottovauhti osoitti myös jotain mitä tietoturvayhteisö ei halunnut myöntää: kun palkinto kuulostaa riittävän houkuttelevalta, ihmiset ovat valmiita heittämään tietoturvan kokonaan roskiin. Kehittäjät asensivat OpenClawn täysillä järjestelmäoikeuksilla, auditoimattomalla koodilla ja ilman hiekkalaatikkoa — eivät siksi että he olisivat huolimattomia, vaan siksi että täydellisen version odottaminen tuntui saman kuin jonkin sellaisen odottaminen jota ei koskaan tulisi. Tämä on ennakoitava seuraus kulttuurista joka kohtelee tietoturvaa binäärisenä tilana eikä jatkumona. Kun rimaksi asetetaan täydellinen, ja täydellinen on saavuttamattomissa, todellinen valinta on usein nolla. Suhteellinen turvallisuus — aito mutta rajattu — on ainoa standardi jolla on käytännön merkitystä ihmisten käyttäytymiseen.

Nelikenttä ohjaa kolmeen käytännön periaatteeseen.

Ensimmäinen: turvallisuustaso on toimintokohtainen. Kalenterimuistutuksia lähettävä agentti ja potilastietoja käsittelevä agentti eivät kuulu samaan turvallisuusluokkaan vaikka ne ajaisivatkin samalla alustalla. Yhden tason turvallisuus kaikille toiminnoille on sekä yliturvallisuutta yhdessä paikassa että aliturvallisuutta toisessa.

Sama logiikka pätee toimialatasolla. Autopaja joka ottaa agentin hoitamaan ajanvaraukset, varaosatilaukset ja huoltomuistutukset toimii matalassa moraalisessa riskissä: jos agentti tilaa väärät varaosat tai tuplavaraa ajan, vahinko kohdistuu enimmäkseen pajaan itseensä. Kynnys ottaa tällainen agentti käyttöön on matala, ja hyödyt — vapautunut henkilöstöaika, vähemmän unohdettuja yhteydenottoja, nopeampi hankinta — ovat saavutettavissa jopa pienelle toimijalle ilman merkittävää tietoturvainvestointia.

Pankki tai sairaala, joka ajaa agentteja samalla alustalla, kohtaa perustavanlaatuisesti erilaisen moraalisen laskelman — teknisestä samankaltaisuudesta huolimatta. Kun agentti käsittelee asiakkaan taloudellisia tietoja tai osallistuu kliinisiin päätöksiin, kolmansien osapuolten altistuminen on väistämätöntä. Virheet eivät ole vain kalliita — ne voivat olla peruuttamattomia, ja ne kohdistuvat ihmisiin jotka eivät itse valinneet kantaa tätä riskiä. Sekä pankki että sairaala voivat hyötyä agenteista valtavasti. Mutta molempien täytyy punnita moraalinen puoli tavalla jota autopajan ei juuri tarvitse tehdä.

Toinen: henkilödatan minimointi on markkinamekanismi etiikan toteuttamiseksi. Jos agentti pääsee vain siihen dataan jota se välttämättä tarvitsee tehtävänsä suorittamiseen, moraalisen riskin ruutu pienenee automaattisesti. Tämä ei vaadi sääntelyä — se vaatii arkkitehtuuripäätöksen.

Kolmas: peruuttamattomat toiminnot vaativat oman vahvistuslogiikkansa. Agentti joka lähettää sähköpostin, poistaa tiedoston tai tekee taloudellisen sitoumuksen toimii eri tavalla kuin agentti joka lukee kalenterin. Peruuttamattomuus nostaa automaattisesti sekä taloudellisen että moraalisen riskin kertaluokkaa.

Nämä periaatteet eivät ratkaise kaikkia kysymyksiä. Ne eivät kerro missä täsmälleen kulkee hyväksyttävän riskin raja. Mutta ne estävät pahimman — sen että taloudellinen kiire tai tekninen mukavuus tekee moraalisen päätöksen kehittäjän puolesta huomaamatta.

Turvallisuuden optimoinnin käytännön sovelluksista — mukaan lukien hajautetut vakuutusprotokollat agenttiriskien hallintaan — lisää artikkelissa [Insuring the Agent](INSURANCE-FOR-AGENTS.md).


## 8. Johtopäätös — mitä turvallisuuden optimointi oikeasti tarkoittaa

Optimaalinen turvattomuus on huono nimi. Se kuulostaa vastuuttomuuden puolustamiselta — ja juuri siksi se on otsikossa kysymysmerkin kanssa. Parempi nimi voisi olla proportionaalinen turvallisuus, tai ehkä yksinkertaisesti vastuullinen riski. Mutta nimitystä tärkeämpää on ajatus sen takana.

Se on rehellisyyttä siitä mitä turvallisuus maksaa — ja kenelle. Täydellinen turvallisuus ei ole ilmaista. Se maksaa kehitysaikaa, käyttöönottonopeutta ja viime kädessä hyötyä jota teknologia ei koskaan tuota niille jotka sitä eniten tarvitsisivat. M-Pesa oli epätäydellinen. Se muutti silti miljoonien ihmisten elämän antamalla heille pääsyn moderneihin maksupalveluihin ensimmäistä kertaa.

Nelikenttä ei ole moraalinen algoritmi. Se ei anna vastausta — se pakottaa esittämään oikeat kysymykset erikseen. Mikä on todellinen taloudellinen riski, ei kuviteltu pahin tapaus? Onko toiminta moraalisesti oikeutettua riippumatta siitä mitä se tuottaa? Nämä kysymykset johtavat eri paikkoihin kuin yksi epämääräinen turvallisuuskysymys johon vastataan intuitiolla tai pelolla.

Kiintopisteet ovat silti olemassa. Harmaalla alueella voidaan neuvotella. Mutta on myös selkeää yötä — toimintaa jota ei voi oikeuttaa millään laskelmalla. Kehittäjä joka tietää missä yö alkaa ja silti astuu sinne ei voi puolustella toimintaansa millään nelikentällä. Hän on vain valinnut väärin.

Insinöörikoulutus opetti että sillat eivät saa sortua. Sillan kohdalla se oli oikein. Tekoälyagenttien aikana tarvitaan tarkempaa ajattelua — ei löysempää moraalia, vaan täsmällisempää. Turvallisuuden optimointi on täsmällisyyttä, ei välinpitämättömyyttä.

On yksi viimeinen ironia joka ansaitsee nimetä. Täydellisen turvallisuuden tavoittelu ei ole tehnyt meistä turvallisempia — se on tehnyt meistä epärehellisiä. Epärehellisiä siitä mitä turvallisuus maksaa, epärehellisiä siitä kuka maksaa kun lykkäämme, ja epärehellisiä siitä mitä ihmiset oikeasti tekevät kun rima asetetaan mahdottoman korkealle. He eivät odota. He kiertävät.

Rehellisyys turvallisuuden rajoista ei ole myönnytys riskille. Se on ainoa perusta jolle todellisia turvallisuusstandardeja voidaan rakentaa ja ylläpitää. Kun lopetamme teeskentelemisen että täydellinen on saavutettavissa, voimme alkaa rakentaa jotain joka on oikeasti hyvää — ja vaatia sitä toisiltamme. Se on se mikä vapauttaa meidät: ei nollariskin illuusio, vaan selkeys nähdä minkä riskin oikeasti otamme, miksi ja kenen puolesta.
