package fi.leima.android

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Rect
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.PixelCopy
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.exifinterface.media.ExifInterface
import fi.leima.android.meeting.MeetingScreen
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.util.concurrent.Executors

class MainActivity : ComponentActivity() {
    private lateinit var recorder: SensorRecorder
    private lateinit var store: EvidenceStore
    private val io = Executors.newSingleThreadExecutor()
    private var web: WebView? = null
    private var provider: ProcessCameraProvider? = null
    private var cameraCapture: ImageCapture? = null
    private var cameraMode by mutableStateOf(false)
    private var meetingMode by mutableStateOf(false)
    private var pendingMeetingExport by mutableStateOf<File?>(null)
    private var cameraAllowed by mutableStateOf(false)
    private var cameraReady by mutableStateOf(false)
    private var busy by mutableStateOf(false)
    private var status by mutableStateOf("Kuvat tallennetaan vain tähän laitteeseen.")
    private var lastPackage by mutableStateOf<File?>(null)
    private var address by mutableStateOf("https://example.com")
    private var pageReady by mutableStateOf(false)
    private var pageGeneration = 0
    private var pendingScreenshot by mutableStateOf<PendingScreenshot?>(null)
    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        cameraAllowed = checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        recorder.start()
        status = if (cameraMode && !cameraAllowed) "Kameralupaa ei annettu. Voit sallia sen puhelimen asetuksista." else "Luvat päivitetty. Sijainti tallentuu, kun mittaus on saatavilla."
    }
    private val export = registerForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        val source = lastPackage
        if (uri != null && source != null) {
            busy = true
            io.execute {
                runCatching {
                    checkNotNull(contentResolver.openOutputStream(uri)).use { output -> source.inputStream().use { it.copyTo(output) } }
                }.fold({ report("Kuvapaketti viety.") }, { report("Vienti epäonnistui: ${it.localizedMessage}") })
            }
        }
    }
    private val meetingExport = registerForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        val source = pendingMeetingExport
        pendingMeetingExport = null
        if (uri != null && source != null) {
            io.execute {
                runCatching {
                    checkNotNull(contentResolver.openOutputStream(uri)).use { output -> source.inputStream().use { it.copyTo(output) } }
                }.fold(
                    { runOnUiThread { status = "Kuvausistunnon paketti viety." } },
                    { runOnUiThread { status = "Kuvausistunnon vienti epäonnistui: ${it.localizedMessage}" } },
                )
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        recorder = SensorRecorder(this)
        store = EvidenceStore(this)
        cameraAllowed = checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        lastPackage = File(filesDir, "evidence").listFiles()?.map { File(it, "evidence.zip") }
            ?.filter { it.isFile }?.maxByOrNull { it.lastModified() }
        setContent {
            MaterialTheme {
                Column(Modifier.fillMaxSize().systemBarsPadding().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Leima", style = MaterialTheme.typography.headlineMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(enabled = !busy, onClick = { cameraMode = false; meetingMode = false }) { Text("Selain") }
                        Button(enabled = !busy, onClick = {
                            cameraMode = true
                            meetingMode = false
                            if (!cameraAllowed) permissions.launch(arrayOf(Manifest.permission.CAMERA))
                        }) { Text("Kamera") }
                        Button(enabled = !busy, onClick = { cameraMode = false; meetingMode = true }) { Text("Kuvausistunto") }
                        TextButton(enabled = !busy, onClick = {
                            permissions.launch(arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION))
                        }) { Text("Sijaintilupa") }
                    }
                    if (!cameraMode && !meetingMode) {
                        OutlinedTextField(value = address, onValueChange = { address = it }, label = { Text("Verkko-osoite (HTTPS)") }, singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !busy)
                        Row {
                            TextButton(enabled = !busy, onClick = { if (web?.canGoBack() == true) web?.goBack() }) { Text("Takaisin") }
                            Button(enabled = !busy, onClick = {
                                val candidate = address.trim().let { if ("://" in it) it else "https://$it" }
                                if (safeUrl(candidate)) web?.loadUrl(candidate) else status = "Anna kelvollinen HTTPS-osoite."
                            }) { Text("Avaa") }
                        }
                    }
                    if (meetingMode) {
                        Box(Modifier.weight(1f).fillMaxWidth()) {
                            MeetingScreen(onExport = { file ->
                                pendingMeetingExport = file
                                meetingExport.launch("leima-meeting_${file.parentFile?.name ?: "session"}.zip")
                            })
                        }
                    } else {
                        Box(Modifier.weight(1f).fillMaxWidth()) {
                            if (cameraMode) {
                                if (cameraAllowed) CameraSurface() else Text("Kamera tarvitsee kameran käyttöluvan.")
                            } else BrowserSurface()
                        }
                        Text(status, style = MaterialTheme.typography.bodySmall)
                        Button(modifier = Modifier.fillMaxWidth(), enabled = !busy && if (cameraMode) cameraReady else pageReady, onClick = {
                            if (cameraMode) takePhoto() else takeScreenshot()
                        }) { Text(if (busy) "Tallennetaan…" else if (cameraMode) "Ota kuva ja tallenna mittaukset" else "Tallenna näkyvä sivu ja mittaukset") }
                        TextButton(enabled = !busy && lastPackage != null, onClick = { export.launch("leima-${lastPackage!!.parentFile!!.name}.zip") }) { Text("Vie viimeisin kuvapaketti") }
                    }
                }
                pendingScreenshot?.let { pending ->
                    ScreenshotEditor(pending, onCancel = {
                        pendingScreenshot = null
                        busy = false
                        status = "Kuvakaappaus peruttu. Kuvaa ei tallennettu."
                    }, onSave = { bitmap, metadata ->
                        pendingScreenshot = null
                        io.execute {
                            try {
                                runCatching {
                                    val directory = store.newDirectory()
                                    val media = File(directory, "screenshot.png")
                                    media.outputStream().use { check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
                                    store.finish(directory, media, metadata)
                                }.fold(::saved, { report("Tallennus epäonnistui: ${it.localizedMessage}") })
                            } finally { bitmap.recycle() }
                        }
                    })
                }
            }
        }
    }

    @Composable private fun BrowserSurface() {
        DisposableEffect(Unit) { onDispose { web?.destroy(); web = null; pageReady = false } }
        AndroidView(modifier = Modifier.fillMaxSize(), factory = { context ->
            WebView(context).apply {
                web = this
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = !safeUrl(request.url.toString())
                    override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) { pageReady = false; pageGeneration++ }
                    override fun onPageCommitVisible(view: WebView, url: String?) { pageReady = true; address = url.orEmpty() }
                    // Default SSL-error handling cancels; never bypass certificate errors.
                }
                loadUrl(if (safeUrl(address)) address else "https://example.com")
            }
        })
    }

    @Composable private fun CameraSurface() {
        DisposableEffect(Unit) { onDispose { provider?.unbindAll(); cameraCapture = null; cameraReady = false } }
        AndroidView(modifier = Modifier.fillMaxSize(), factory = { context ->
            PreviewView(context).apply {
                val surface = this
                val future = ProcessCameraProvider.getInstance(context)
                future.addListener({
                    if (!cameraMode || isDestroyed) return@addListener
                    runCatching {
                        provider = future.get()
                        val preview = Preview.Builder().build().also { it.setSurfaceProvider(surface.surfaceProvider) }
                        cameraCapture = ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY).build()
                        provider!!.unbindAll()
                        provider!!.bindToLifecycle(this@MainActivity, CameraSelector.DEFAULT_BACK_CAMERA, preview, requireNotNull(cameraCapture))
                        cameraReady = true
                    }.onFailure { cameraReady = false; status = "Kameran avaus epäonnistui: ${it.localizedMessage}" }
                }, mainExecutor)
            }
        })
    }

    private fun baseMetadata(kind: String) = JSONObject().put("kind", kind)
        .put("requestedAt", Instant.now().toString()).put("requestedElapsedRealtimeNs", SystemClock.elapsedRealtimeNanos())
        .put("sensorsAtRequest", recorder.snapshot())

    private fun takeScreenshot() {
        val view = web ?: return
        if (view.width <= 0 || view.height <= 0) return
        busy = true
        val generation = pageGeneration
        val metadata = baseMetadata("webview_viewport").put("url", view.url).put("title", view.title)
            .put("webViewVersion", WebView.getCurrentWebViewPackage()?.versionName)
            .put("captureMethod", "PixelCopy window rectangle; visible viewport only")
            .put("scrollX", view.scrollX).put("scrollY", view.scrollY)
            .put("width", view.width).put("height", view.height)
        val position = IntArray(2).also { view.getLocationInWindow(it) }
        val rect = Rect(position[0], position[1], position[0] + view.width, position[1] + view.height)
        val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        runCatching {
            PixelCopy.request(window, rect, bitmap, { result ->
                if (isDestroyed || isFinishing || !lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.RESUMED)) {
                    bitmap.recycle(); busy = false
                } else if (result != PixelCopy.SUCCESS || generation != pageGeneration || web !== view) {
                    bitmap.recycle(); report("Kuvakaappaus ei onnistunut tai sivu vaihtui. Yritä uudelleen.")
                } else {
                    metadata.put("completedAt", Instant.now().toString()).put("completedElapsedRealtimeNs", SystemClock.elapsedRealtimeNanos())
                    pendingScreenshot = PendingScreenshot(bitmap, store.prepareMetadata(metadata))
                }
            }, Handler(Looper.getMainLooper()))
        }.onFailure { bitmap.recycle(); report("Kuvakaappaus epäonnistui: ${it.localizedMessage}") }
    }

    private fun takePhoto() {
        val capture = cameraCapture ?: return
        busy = true
        val metadata = baseMetadata("camera_photo").put("lensFacing", "back")
            .put("sensorTiming", "Window before shutter request; not synchronized to exposure")
        val directory = store.newDirectory()
        val photo = File(directory, "photo.jpg")
        capture.targetRotation = window.decorView.display.rotation
        capture.takePicture(ImageCapture.OutputFileOptions.Builder(photo).build(), mainExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onError(exception: ImageCaptureException) { report("Kuvaus epäonnistui: ${exception.localizedMessage}") }
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    metadata.put("completedAt", Instant.now().toString()).put("completedElapsedRealtimeNs", SystemClock.elapsedRealtimeNanos())
                        .put("sensorsAtCompletion", recorder.snapshot())
                    io.execute {
                        runCatching {
                            val exif = ExifInterface(photo)
                            val fields = JSONObject()
                            listOf(ExifInterface.TAG_EXPOSURE_TIME, ExifInterface.TAG_F_NUMBER,
                                ExifInterface.TAG_PHOTOGRAPHIC_SENSITIVITY, ExifInterface.TAG_FOCAL_LENGTH,
                                ExifInterface.TAG_DATETIME_ORIGINAL, ExifInterface.TAG_ORIENTATION,
                                ExifInterface.TAG_IMAGE_WIDTH, ExifInterface.TAG_IMAGE_LENGTH).forEach {
                                fields.put(it, exif.getAttribute(it) ?: JSONObject.NULL)
                            }
                            metadata.put("cameraExif", fields)
                            store.finish(directory, photo, metadata)
                        }.fold(::saved, { report("Tallennus epäonnistui: ${it.localizedMessage}") })
                    }
                }
            })
    }
    private fun saved(file: File) { runOnUiThread { lastPackage = file; busy = false; status = "Kuvapaketti tallennettu. Voit viedä sen ZIP-tiedostona." } }
    private fun report(message: String) { runOnUiThread { busy = false; status = message } }
    private fun safeUrl(value: String): Boolean = Uri.parse(value).let { it.scheme == "https" && !it.host.isNullOrBlank() && it.userInfo == null }
    override fun onResume() { super.onResume(); if (::recorder.isInitialized) recorder.start(); web?.onResume() }
    override fun onPause() {
        if (pendingScreenshot != null) {
            pendingScreenshot = null
            busy = false
            status = "Rajaus peruttiin sovelluksen siirtyessä taustalle."
        }
        if (::recorder.isInitialized) recorder.stop(); web?.onPause(); super.onPause()
    }
    override fun onDestroy() { io.shutdown(); super.onDestroy() }
}
