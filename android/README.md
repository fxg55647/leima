# Leima Android — ensimmäinen prototyyppi

Itsenäinen Kotlin / Jetpack Compose -sovellus samassa repossa Python-palvelun kanssa.
Avaa **tämä android-kansio** Android Studiossa projektina.

## Käynnistys

1. Asenna Android Studio, JDK 17 ja Android SDK 36 (SDK Manager).
2. Avaa `android` ja anna Gradlen ladata riippuvuudet.
3. Liitä Android 9 tai uudempi puhelin, salli USB-vianmääritys ja valitse Run.
4. Avaa HTTPS-sivu tai valitse Kamera ja myönnä kameran käyttöoikeus.
5. Sijaintilupa on erillinen, vapaaehtoinen painike. Odota sijaintimittausta ennen kuvaamista.
6. Kuvakaappauksessa siirrä ja venytä rajauskehystä. Valitse Peitä ja vedä musta alue
   salattavan tiedon päälle. Peittoja voi perua, ja Nollaa palauttaa koko kuvan.
7. Valitse tarvittaessa osoitepolku, sivun otsikko ja sensorit/sijainti mukaan.
   Oletuksena nämä jätetään kuvakaappauksen paketista pois. Verkkotunnus, ajat ja laitetiedot säilyvät.
8. Esikatsele lopullinen kuva ja metatiedot. Hyväksy ja tallenna, ja vie ZIP-paketti
   puhelimen tiedostovalitsimella. Kamerakuvan tallennus toimii edelleen ilman rajausvaihetta.

Komentoriviltä Windowsissa: `gradlew.bat :app:assembleDebug :app:lintDebug`.
Muilla alustoilla: `sh gradlew :app:assembleDebug :app:lintDebug`.
SDK:n polun voi asettaa paikalliseen `local.properties`-tiedostoon (`sdk.dir=...`).
Sitä ei tallenneta versionhallintaan. APK syntyy `app/build/outputs/apk/debug/`-kansioon.

## Toteutettu pohja

- Android WebView, HTTPS-osoitekenttä, takaisin-navigointi ja näkyvän selainalueen PixelCopy-kuvakaappaus.
- Kuvakaappauksen paikallinen rajaus kaikista reunoista ja kulmista, siirtäminen sekä
  pysyvät mustat peitot. Esikatselu näyttää täsmälleen tallennettavan kuvan.
- CameraX-esikatselu ja takakameran JPEG-kuva. Tallennettua JPEG-tiedostoa ei muokata jälkikäteen.
- Saatavilla olevien anturien luettelo ja tavallisten sensorikuuntelijoiden rekisteröinnin onnistuminen.
- Enintään viisi sekuntia / 2000 sensorinäytettä, alkuperäiset anturin aikaleimat ja tarkkuustila.
- Sijainti luvan perusteella: koordinaatit, tarkkuus, mittauksen ikä, aikaleimat,
  mock-merkintä ja saatavilla olevat korkeus-, nopeus- ja suuntatiedot.
- Kameran saatavilla olevat EXIF-kuvausasetukset; puuttuvat arvot merkitään nulliksi.
- Paikallinen tallennus sovelluksen yksityiseen tilaan ja viimeisimmän valmiin paketin vienti.

Paketti sisältää `photo.jpg` tai `screenshot.png`, `metadata.json`, `manifest.json`
ja `manifest.sha256`. Manifesti sitoo kuvan ja metatietojen täsmälliset tavut
SHA-256-tarkistussummilla. `manifest.sha256` tarkistaa manifestin; se ei ole allekirjoitus.
Paketti voidaan tarkistaa Pythonilla: `python tools/verify_package.py polku/pakettiin.zip`.

### Kuvakaappauksen yksityisyys

PixelCopy-kuva pidetään vain muistissa rajauksen ajan. Levyllä tai ZIP-paketissa ei
säilytetä alkuperäistä kuvakaappausta eikä sen pienoiskuvaa. Rajattu kuva luodaan uuteen
bittikarttaan ja peitot maalataan täysin mustiksi lopullisiin pikseleihin ennen PNG:n
tallennusta ja tarkistussummien laskentaa. Peruuttaminen ei luo kuvapakettia.
Muokkausikkuna estää Androidin tavallisen kuvakaappauksen ikkunasta; taustalle siirtyminen
tai näytön kääntäminen peruu keskeneräisen muokkauksen. Selaimen sisältö ja välimuistit
eivät kuulu tähän alkuperäisen kuvakaappauksen tallentamista koskevaan lupaukseen.

`metadata.json.edits` sisältää lähdenäkymän mitat, rajausalueen ja näkyvien peittojen
koordinaatit lähdekuvan pikseleinä. Oikea ja alareuna ovat poissulkevia. Päätason
`width` ja `height` tarkoittavat lopullisen kuvan mittoja. `privacy` kertoo käyttäjän
metatietovalinnat. URL:n kyselyparametrit ja fragmentti poistetaan aina tästä paketista,
myös osoitepolun ollessa valittuna. Muokkaus ei muuta kuvaushetken aikaleimoja.
Tämä koskee uusia kuvakaappauksia; aiemmin tallennetut paketit eivät muutu.

Muokkaus on toistaiseksi yhden kuvakaappauksen työnkulku. Selausistunnon tallennus,
vastaanottajan valinta ja palvelinlähetys ovat erillisiä tulevia vaiheita.

## Rajat ja seuraavat vaiheet

Tämä on testausta varten tehty pohja, ei vielä todennettu todistusjärjestelmä.
Palvelinlähetys, Leima-leima, palvelimen vastaanottoaika, Android Keystore -allekirjoitus
ja palvelimen varmentama laiteattestaatio ovat toteuttamatta. Kuvia ei lähetetä automaattisesti.
Tarkistussummat havaitsevat muutoksen suhteessa säilytettyyn manifestiin, mutta koko
allekirjoittamaton paketti voidaan korvata. Laitteen aika, sijainti ja sovellusversio
ovat laitteen ilmoittamia tietoja.

Sensorinäytteet ovat kuvauspyynnön ympäriltä, eivät tarkasti kameran valotukseen
synkronoituja. Kaikkia laitteiden sensoreita ei saada tavallisella SensorManager-kuuntelijalla:
esimerkiksi kertalaukeavat, terveysluvan vaativat ja valmistajan suljetut sensorit
vaativat erillisen toteutuksen. Mittausikkuna on rajattu ja näytteenottotaajuus tavallinen
SENSOR_DELAY_NORMAL; tämä ei tallenna kaikkea raakadataa. Keruu päättyy taustalle siirryttäessä.

WebView ei ole Chrome-sovellus. Kuvakaappaus sisältää vain näkyvän sivualueen;
animaatiot, videopinnat, näppäimistö ja sivun muutokset on testattava oikealla laitteella.
Navigointi kaappauksen aikana hylkää kaappauksen, mutta dynaaminen sivu ei ole atominen
dokumentti. HTTPS-virheitä ei ohiteta. Täyttä TLS-varmenneketjua, selainhistoriaa,
tiedostolatauksia ja erillisiä kirjautumisikkunoita ei tässä pohjassa kerätä tai toteuteta.
Selaimen välilehden vaihto kameraan luo WebView'n uudelleen.

Paketit säilyvät yksityisessä sovellustilassa, kunnes sovelluksen tiedot poistetaan.
Vanhojen pakettien selaus ja poisto sekä tilankäytön hallinta tarvitaan ennen tuotantokäyttöä.
Sijainti ja anturitiedot sisältyvät vietyyn ZIP-tiedostoon. Androidin automaattinen varmuuskopiointi on poistettu käytöstä.

## Tarkistus ennen käyttöä

- Rakenna APK ja aja Android Lint yllä olevalla komennolla.
- Testaa kameran ja sijainnin lupien hyväksyminen, hylkääminen ja poistaminen asetuksista.
- Testaa kuvaus ilman sijaintia, sijainnin ollessa pois päältä ja ilman verkkoyhteyttä.
- Vertaa kuvakaappausta näkyvään sivuun, myös vieritetyllä sivulla ja videolla.
- Testaa näytön kääntäminen, taustalle siirtyminen, paluu ja kameran puuttuminen.
- Vie molemmat pakettityypit; tarkista ne erillisellä tarkistimella ja kokeile muokattua kuvaa.
- Testaa rajauksen kaikki reunat/kulmat, siirtäminen, eri suuntiin vedetyt peitot,
  osittain rajauksen ulkopuolella olevat peitot, peruminen ja paluu esikatselusta.
- Varmista ZIP:stä, ettei alkuperäistä kuvaa, peitettyjä pikseleitä tai valitsematta
  jätettyjä metatietoja ole mukana. Testaa rajaus myös pienellä näytöllä ja suurella tekstikoolla.

Androidin pikseli-, tietosuoja- ja pakettitestit: `gradlew.bat :app:connectedDebugAndroidTest`
(puhelin tai emulaattori vaaditaan). Testit kattavat peittojen lopulliset pikselit,
rajauksen ulkopuolisen sisällön poistumisen, PNG:n tarkistussumman sekä metatietosuodatuksen.
Testiriippuvuudet: [AndroidX Test](https://developer.android.com/jetpack/androidx/releases/test).

Tässä kehitysympäristössä ei ollut JDK:ta eikä Android SDK:ta, joten APK:n käännöstä,
Lint-tarkistusta tai laitetestejä ei ole vielä ajettu. Gradle-wrapperin tarkistussumma
on tarkistettu Gradlen julkaisemaa arvoa vastaan.

Versiovalintojen lähteet: [Android Gradle Plugin 8.13](https://developer.android.com/build/releases/agp-8-13-0-release-notes),
[CameraX](https://developer.android.com/jetpack/androidx/releases/camera),
[Compose December 2025](https://android-developers.googleblog.com/2025/12/whats-new-in-jetpack-compose-december.html).
