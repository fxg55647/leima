package fi.leima.android.bridge

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.PixelCopy
import android.webkit.WebView
import org.json.JSONObject
import org.json.JSONTokener
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ExecutionException
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

/**
 * [BrowserHost] over the app's WebView. Called on the bridge thread; every WebView access is posted
 * to the main thread and awaited. The activity supplies the WebView and page state through lambdas
 * that are only invoked on the main thread.
 */
class WebViewBrowserHost(
    private val activity: Activity,
    private val pageScript: String,
    private val webView: () -> WebView?,
    private val isAvailable: () -> Boolean,
    private val generation: () -> Int,
    private val finished: () -> Boolean,
    private val environment: () -> JSONObject,
) : BrowserHost {
    private val main = Handler(Looper.getMainLooper())
    /** Names the page-side element store; random per app run so pages cannot predict it. */
    private val key = "__leima_" + ByteArray(12).also(SecureRandom()::nextBytes).joinToString("") { "%02x".format(it) }

    override fun state(): PageState = onMain { f ->
        val web = requireWeb()
        f.complete(PageState(web.url.orEmpty(), web.title.orEmpty(), !finished(), generation(), web.canGoBack()))
    }

    override fun navigate(url: String, timeoutMs: Long): PageState {
        val before = onMain<Int> { f -> val web = requireWeb(); val g = generation(); web.loadUrl(url); f.complete(g) }
        return waitForLoad(before, timeoutMs)
    }

    override fun back(timeoutMs: Long): PageState? {
        val before = onMain<Int?> { f ->
            val web = requireWeb()
            if (!web.canGoBack()) f.complete(null) else { val g = generation(); web.goBack(); f.complete(g) }
        } ?: return null
        return waitForLoad(before, timeoutMs)
    }

    override fun settle(timeoutMs: Long): PageState {
        SystemClock.sleep(300) // a click usually starts any navigation within this window
        val deadline = SystemClock.elapsedRealtime() + timeoutMs
        var state = state()
        while (state.loading && SystemClock.elapsedRealtime() < deadline) { SystemClock.sleep(100); state = state() }
        return state
    }

    override fun pageCommand(command: String, args: JSONObject, timeoutMs: Long): JSONObject {
        val script = "($pageScript)(${JSONObject.quote(command)}, ${JSONObject(args.toString()).put("key", key)})"
        val raw = onMain<String>(timeoutMs) { f -> requireWeb().evaluateJavascript(script) { f.complete(it) } }
        val text = runCatching { JSONTokener(raw).nextValue() as? String }.getOrNull()
            ?: throw ProtocolError("SCRIPT_ERROR", "The page script did not return a result")
        return JSONObject(text)
    }

    override fun screenshot(masks: List<MaskRect>, cssWidth: Double): Screenshot = onMain(10_000) { f ->
        val web = requireWeb()
        if (web.width <= 0 || web.height <= 0) throw ProtocolError("BROWSER_UNAVAILABLE", "Browser view has no size")
        val position = IntArray(2).also { web.getLocationInWindow(it) }
        val rect = Rect(position[0], position[1], position[0] + web.width, position[1] + web.height)
        val bitmap = Bitmap.createBitmap(web.width, web.height, Bitmap.Config.ARGB_8888)
        PixelCopy.request(activity.window, rect, bitmap, { result ->
            try {
                if (result != PixelCopy.SUCCESS) throw ProtocolError("SCREENSHOT_FAILED", "PixelCopy failed ($result)")
                val scale = web.width / cssWidth
                val paint = Paint().apply { color = android.graphics.Color.BLACK; style = Paint.Style.FILL }
                val canvas = Canvas(bitmap)
                masks.forEach { m ->
                    canvas.drawRect(RectF((m.x * scale - MASK_MARGIN).toFloat(), (m.y * scale - MASK_MARGIN).toFloat(),
                        ((m.x + m.width) * scale + MASK_MARGIN).toFloat(), ((m.y + m.height) * scale + MASK_MARGIN).toFloat()), paint)
                }
                val png = ByteArrayOutputStream().use { out -> check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)); out.toByteArray() }
                f.complete(Screenshot(png, bitmap.width, bitmap.height))
            } catch (e: Throwable) {
                f.completeExceptionally(e)
            } finally {
                bitmap.recycle()
            }
        }, main)
    }

    override fun certificate(): JSONObject? = onMain { f ->
        val cert = requireWeb().certificate
        if (cert == null) { f.complete(null); return@onMain }
        val json = JSONObject()
            .put("issuedTo", JSONObject().put("cn", cert.issuedTo.cName).put("o", cert.issuedTo.oName))
            .put("issuedBy", JSONObject().put("cn", cert.issuedBy.cName).put("o", cert.issuedBy.oName))
            .put("validNotBefore", cert.validNotBeforeDate?.toInstant()?.toString())
            .put("validNotAfter", cert.validNotAfterDate?.toInstant()?.toString())
            .put("source", "WebView.getCertificate(); leaf certificate only, chain and trust anchor not exported")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            cert.x509Certificate?.let { x509 ->
                json.put("sha256Fingerprint", MessageDigest.getInstance("SHA-256").digest(x509.encoded).joinToString(":") { "%02X".format(it) })
            }
        }
        f.complete(json)
    }

    override fun environment(): JSONObject = onMain { f -> f.complete(environment.invoke()) }

    private fun waitForLoad(before: Int, timeoutMs: Long): PageState {
        val start = SystemClock.elapsedRealtime()
        while (true) {
            val state = state()
            val elapsed = SystemClock.elapsedRealtime() - start
            // A same-document navigation (fragment change) never starts a new page load.
            if (!state.loading && (state.generation != before || elapsed > 1_500)) return state
            if (elapsed >= timeoutMs) return state
            SystemClock.sleep(100)
        }
    }

    private fun requireWeb(): WebView {
        val web = webView()
        if (web == null || !isAvailable()) {
            throw ProtocolError("BROWSER_UNAVAILABLE", "Show the Selain tab on the phone with the app in the foreground; the browser is hidden or busy")
        }
        return web
    }

    private fun <T> onMain(timeoutMs: Long = 5_000, block: (CompletableFuture<T>) -> Unit): T {
        val future = CompletableFuture<T>()
        main.post { try { block(future) } catch (e: Throwable) { future.completeExceptionally(e) } }
        try {
            return future.get(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (e: TimeoutException) {
            throw ProtocolError("BROWSER_TIMEOUT", "The phone browser did not respond in ${timeoutMs / 1000} s")
        } catch (e: ExecutionException) {
            throw e.cause as? ProtocolError ?: ProtocolError("INTERNAL", e.cause?.message ?: "Browser call failed")
        }
    }

    private companion object { const val MASK_MARGIN = 4.0 }
}
