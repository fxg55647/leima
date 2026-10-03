package fi.leima.android.bridge

import java.io.File
import java.util.zip.ZipFile
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class BrowserControllerTest {
    @get:Rule val tmp = TemporaryFolder()

    /** Scripted WebView: records page commands and lets tests change the page under the agent. */
    private class FakeHost : BrowserHost {
        var available = true
        var page = PageState("https://example.org/a?token=abc&q=kissa#frag", "Example", false, 1, true)
        var crossOriginFrames = 0
        val commands = mutableListOf<String>()
        val navigations = mutableListOf<String>()
        var clickError: String? = null
        var shotBytes = byteArrayOf(1, 2, 3)

        private fun check() { if (!available) throw ProtocolError("BROWSER_UNAVAILABLE", "hidden") }
        override fun state(): PageState { check(); return page }
        override fun navigate(url: String, timeoutMs: Long): PageState {
            check(); navigations += url
            page = page.copy(url = url, generation = page.generation + 1); return page
        }
        override fun back(timeoutMs: Long): PageState? { check(); return if (page.canGoBack) page.copy(generation = page.generation + 1).also { page = it } else null }
        override fun settle(timeoutMs: Long) = state()
        override fun pageCommand(command: String, args: JSONObject, timeoutMs: Long): JSONObject {
            check(); commands += command
            return when (command) {
                "observe" -> JSONObject().put("url", page.url).put("title", page.title).put("ready_state", "complete")
                    .put("visible_text", "Hello").put("elements", JSONArray().put(JSONObject().put("element_id", "el_1").put("role", "button")))
                    .put("limitations", JSONArray())
                "click" -> clickError?.let { JSONObject().put("error", it) } ?: JSONObject().put("ok", true).put("method", "dom_click")
                "type" -> JSONObject().put("ok", true).put("method", "dom_value_setter")
                "masks" -> JSONObject().put("rects", JSONArray().put(JSONObject().put("x", 1).put("y", 2).put("width", 3).put("height", 4)))
                    .put("viewport", JSONObject().put("width", 400)).put("unmaskable_frames", crossOriginFrames)
                "dom" -> JSONObject().put("html", "<html><body>Hello</body></html>")
                    .put("redactions", JSONObject().put("sensitive_inputs", 1).put("hidden_inputs", 0).put("csrf_meta", 0))
                else -> error(command)
            }
        }
        override fun screenshot(masks: List<MaskRect>, cssWidth: Double): Screenshot {
            check(); assertEquals(1, masks.size); return Screenshot(shotBytes, 800, 600)
        }
        override fun certificate() = JSONObject().put("issuedTo", JSONObject().put("cn", "example.org"))
        override fun environment() = JSONObject().put("appVersion", "0.1.0").put("webViewVersion", "129").put("device", JSONObject().put("model", "Test"))
    }

    private val host = FakeHost()
    private fun controller() = BrowserController(host, tmp.newFolder("evidence"))
    private fun JSONObject.req(id: String) = put("request_id", id)

    private fun code(block: () -> Unit): String = try { block(); "none" } catch (e: ProtocolError) { e.code }

    @Test
    fun clickNeedsTheCurrentObservationAndInvalidatesIt() {
        val c = controller()
        val obs = c.observe()
        val params = JSONObject().put("session_id", obs.getString("session_id")).put("observation_id", obs.getString("observation_id")).put("element_id", "el_1")
        assertEquals("dom_click", c.click(JSONObject(params.toString()).req("r1")).getString("method"))
        // the same observation cannot be used twice: the click may have changed the page
        assertEquals("STALE_OBSERVATION", code { c.click(JSONObject(params.toString()).req("r2")) })
        assertEquals(1, host.commands.count { it == "click" })
    }

    @Test
    fun navigationByThePersonMakesTheObservationStale() {
        val c = controller()
        val obs = c.observe()
        host.page = host.page.copy(generation = host.page.generation + 1)
        val params = JSONObject().put("session_id", c.sessionId).put("observation_id", obs.getString("observation_id")).put("element_id", "el_1").req("r1")
        assertEquals("STALE_OBSERVATION", code { c.click(params) })
        assertFalse("click" in host.commands)
        assertEquals("STALE_SESSION", code {
            c.click(JSONObject().put("session_id", "bs_other").put("observation_id", "x").put("element_id", "el_1").req("r2"))
        })
    }

    @Test
    fun repeatedRequestIdReturnsStoredOutcomeWithoutActingAgain() {
        val c = controller()
        val first = c.navigate(JSONObject().put("url", "https://example.org/b").req("nav-1"))
        val again = c.navigate(JSONObject().put("url", "https://example.org/b").req("nav-1"))
        assertEquals(listOf("https://example.org/b"), host.navigations)
        assertFalse(first.has("replayed"))
        assertTrue(again.getBoolean("replayed"))
        assertEquals("done", c.commandStatus(JSONObject().req("nav-1")).getString("state"))
        assertEquals("https://example.org/b", c.commandStatus(JSONObject().req("nav-1")).getJSONObject("result").getString("url"))
        assertEquals("unknown", c.commandStatus(JSONObject().req("never")).getString("state"))
    }

    @Test
    fun failedOutcomesAreStoredToo() {
        val c = controller()
        val obs = c.observe()
        host.clickError = "ELEMENT_DISABLED"
        val params = JSONObject().put("session_id", c.sessionId).put("observation_id", obs.getString("observation_id")).put("element_id", "el_1").req("c1")
        assertEquals("ELEMENT_DISABLED", code { c.click(params) })
        assertEquals("ELEMENT_DISABLED", code { c.click(params) })
        assertEquals(1, host.commands.count { it == "click" })
        assertEquals("ELEMENT_DISABLED", c.commandStatus(JSONObject().req("c1")).getJSONObject("error").getString("code"))
    }

    @Test
    fun rejectsUnsafeUrlsAndHiddenBrowser() {
        val c = controller()
        for ((i, url) in listOf("http://example.org", "javascript:alert(1)", "file:///sdcard/x", "https://user:pw@example.org/", "https:///nohost").withIndex()) {
            assertEquals(url, "URL_NOT_ALLOWED", code { c.navigate(JSONObject().put("url", url).req("u$i")) })
        }
        assertTrue(host.navigations.isEmpty())
        host.available = false
        assertEquals("BROWSER_UNAVAILABLE", code { c.observe() })
        assertEquals("NOT_AVAILABLE", c.status().getString("state"))
        assertEquals("BAD_REQUEST", code { c.navigate(JSONObject().put("url", "https://example.org")) })
    }

    @Test
    fun screenshotIsMaskedAndBlockedWhenACrossOriginFrameIsVisible() {
        val c = controller()
        assertEquals(1, c.screenshot().getInt("masked_regions"))
        host.crossOriginFrames = 1
        assertEquals("SCREENSHOT_BLOCKED", code { c.screenshot() })
    }

    @Test
    fun largeScreenshotIsReadInChunksOnlyWhileAllowed() {
        host.shotBytes = ByteArray(700_000).also { java.util.Random(3).nextBytes(it) }
        val c = controller()
        val meta = c.screenshot()
        assertFalse(meta.has("png_base64"))
        assertEquals(700_000, meta.getInt("size"))
        val id = meta.getString("screenshot_id")
        val out = java.io.ByteArrayOutputStream()
        var chunks = 0
        while (true) {
            val chunk = c.screenshotRead(JSONObject().put("screenshot_id", id).put("offset", out.size()).put("length", PackageRepository.MAX_READ_BYTES))
            // every chunk fits a protocol line with room to spare
            assertTrue(chunk.toString().length < BridgeProtocol.MAX_LINE_BYTES / 2)
            out.write(java.util.Base64.getDecoder().decode(chunk.getString("data_base64")))
            chunks++
            if (chunk.getBoolean("eof")) break
        }
        assertTrue(chunks >= 3)
        assertTrue(host.shotBytes.contentEquals(out.toByteArray()))
        assertEquals(BrowserCaptureStore.sha256Hex(host.shotBytes), meta.getString("sha256"))

        val newer = c.screenshot().getString("screenshot_id")
        assertEquals("SCREENSHOT_EXPIRED", code { c.screenshotRead(JSONObject().put("screenshot_id", id).put("offset", 0).put("length", 10)) })
        c.exportPolicy = ExportPolicy.LOCAL_ONLY
        assertEquals("CONTENT_WITHHELD", code { c.screenshotRead(JSONObject().put("screenshot_id", newer).put("offset", 0).put("length", 10)) })
    }

    @Test
    fun captureWritesAVerifiableBrowserPackage() {
        val c = controller()
        c.navigate(JSONObject().put("url", "https://example.org/a?token=abc&q=kissa#frag").req("n1"))
        val result = c.capture(JSONObject().req("cap-1"))
        assertEquals("complete", result.getString("capture_status"))
        val repo = PackageRepository(tmp.root)
        val pkg = repo.find(result.getString("package_id"))!!
        assertEquals("browser", pkg.kind)
        assertEquals(result.getString("sha256"), repo.sha256(pkg))
        ZipFile(pkg.file).use { zip ->
            val names = zip.entries().asSequence().map { it.name }.toSet()
            assertEquals(setOf("metadata.json", "observation.json", "dom.html", "visible-text.txt", "screenshot.png", "manifest.json", "manifest.sha256"), names)
            val metadata = JSONObject(zip.getInputStream(zip.getEntry("metadata.json")).readBytes().toString(Charsets.UTF_8))
            assertEquals("browser", metadata.getString("kind"))
            assertEquals("https://example.org/a?token=REDACTED&q=kissa", metadata.getString("url"))
            assertEquals(2, metadata.getJSONObject("redactions").getInt("urlParameters"))
            assertFalse(metadata.getJSONObject("clock").getBoolean("verified"))
            assertEquals("example.org", metadata.getJSONObject("certificate").getJSONObject("issuedTo").getString("cn"))
        }
        assertFalse(File(pkg.file.parentFile, "evidence.zip.partial").exists())
    }

    @Test
    fun captureIsPartialWhenScreenshotIsBlocked() {
        val c = controller()
        host.crossOriginFrames = 2
        val result = c.capture(JSONObject().req("cap-2"))
        assertEquals("partial", result.getString("capture_status"))
        assertEquals("SCREENSHOT_BLOCKED", result.getJSONArray("missing").getJSONObject(0).getString("reason"))
    }

    @Test
    fun redactUrlHandlesPlainUrls() {
        assertEquals("https://example.org/path" to 0, BrowserController.redactUrl("https://example.org/path"))
        assertEquals("https://e.org/?session_id=REDACTED&page=2" to 1, BrowserController.redactUrl("https://e.org/?session_id=x&page=2"))
    }
}
