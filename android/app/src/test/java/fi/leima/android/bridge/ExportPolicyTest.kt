package fi.leima.android.bridge

import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ExportPolicyTest {
    @get:Rule val tmp = TemporaryFolder()

    private val jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"

    private class Host(var url: String) : BrowserHost {
        override fun state() = PageState(url, "Tilin saldo", false, 1, false)
        override fun navigate(url: String, timeoutMs: Long): PageState { this.url = url; return state() }
        override fun back(timeoutMs: Long): PageState? = null
        override fun settle(timeoutMs: Long) = state()
        override fun pageCommand(command: String, args: JSONObject, timeoutMs: Long): JSONObject = when (command) {
            "observe" -> JSONObject().put("url", "$url?session=abc").put("title", "Tilin saldo").put("ready_state", "complete")
                .put("visible_text", "Saldo 1 234 € token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
                .put("elements", JSONArray().put(JSONObject().put("element_id", "el_1").put("role", "link")
                    .put("name", "Tiliote").put("href", "https://bank.example/statement?auth=xyz&month=9")))
                .put("limitations", JSONArray()).put("human_action_hints", JSONArray())
            "masks" -> JSONObject().put("rects", JSONArray()).put("viewport", JSONObject().put("width", 400)).put("unmaskable_frames", 0)
            else -> error(command)
        }
        override fun screenshot(masks: List<MaskRect>, cssWidth: Double) = Screenshot(byteArrayOf(9), 1, 1)
        override fun certificate(): JSONObject? = null
        override fun environment() = JSONObject()
    }

    private fun code(block: () -> Unit): String = try { block(); "none" } catch (e: ProtocolError) { e.code }

    @Test
    fun scrubberRemovesKnownTokenFormats() {
        val text = "jwt $jwt bearer Bearer abcdefghijklmnopqrstuvwxyz012345 key sk-ant-api03-abcdefghijklmnopqrstuvwx " +
            "gh ghp_abcdefghijklmnopqrstuvwxyz0123456789 aws AKIAIOSFODNN7EXAMPLE\n" +
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----\nordinary text 1234"
        val (clean, count) = SecretScrubber.scrub(text)
        assertEquals(6, count)
        for (secret in listOf(jwt, "abcdefghijklmnopqrstuvwxyz012345", "sk-ant-api03", "ghp_", "AKIAIOSFODNN7EXAMPLE", "MIIEow")) {
            assertFalse(secret, clean.contains(secret))
        }
        assertTrue(clean.contains("ordinary text 1234"))
    }

    @Test
    fun agentReadableRedactsSecretsButKeepsContent() {
        val c = BrowserController(Host("https://bank.example/home"), tmp.newFolder(), initialExportPolicy = ExportPolicy.AGENT_READABLE)
        val out = c.exportView(c.observe())
        assertEquals("AGENT_READABLE", out.getString("export_policy"))
        assertEquals("https://bank.example/home?session=REDACTED", out.getString("url"))
        assertTrue(out.getString("visible_text").contains("Saldo 1 234 €"))
        assertFalse(out.getString("visible_text").contains(jwt))
        val element = out.getJSONArray("elements").getJSONObject(0)
        assertEquals("https://bank.example/statement?auth=REDACTED&month=9", element.getString("href"))
        assertEquals("Tiliote", element.getString("name"))
        assertEquals(3, out.getInt("secrets_redacted"))
    }

    @Test
    fun localOnlyWithholdsAllPageContent() {
        val c = BrowserController(Host("https://bank.example/home"), tmp.newFolder(), initialExportPolicy = ExportPolicy.LOCAL_ONLY)
        val out = c.exportView(c.observe())
        assertEquals("LOCAL_ONLY", out.getString("export_policy"))
        assertEquals("https://bank.example", out.getString("url"))
        assertTrue(out.getBoolean("content_withheld"))
        assertFalse(out.has("visible_text") || out.has("title"))
        val element = out.getJSONArray("elements").getJSONObject(0)
        assertEquals(setOf("element_id", "role"), element.keys().asSequence().toSet())
        val serialized = out.toString()
        for (content in listOf("Saldo", "Tiliote", "Tilin saldo", "statement", "eyJ")) assertFalse(content, serialized.contains(content))
        assertEquals("CONTENT_WITHHELD", code { c.screenshot() })
    }

    @Test
    fun autoBecomesLocalOnlyAfterLoginAndStaysAcrossSessions() {
        val originsFile = File(tmp.newFolder(), "private-origins.json")
        val origins = PrivateOriginStore(originsFile)
        val host = Host("https://bank.example/login")
        val c = BrowserController(host, tmp.newFolder(), privateOrigins = origins)
        assertEquals("AGENT_READABLE", c.exportView(c.observe()).getString("export_policy"))
        val id = c.requestHuman(JSONObject().put("reason", "LOGIN").put("request_id", "h1")).getJSONObject("handoff").getString("handoff_id")
        host.url = "https://bank.example/home"
        c.personContinue(host.url)
        val resumed = c.exportView(c.resume(JSONObject().put("handoff_id", id)))
        assertEquals("LOCAL_ONLY", resumed.getString("export_policy"))
        assertFalse(resumed.getJSONObject("observation").has("visible_text"))
        assertEquals("CONTENT_WITHHELD", code { c.screenshot() })

        // the agent cannot get the content back by starting a new session
        c.endSession()
        assertEquals("LOCAL_ONLY", c.exportView(c.observe()).getString("export_policy"))
        // other sites stay readable, and the marker survives an app restart
        host.url = "https://news.example/"
        assertEquals("AGENT_READABLE", c.exportView(c.observe()).getString("export_policy"))
        assertTrue(PrivateOriginStore(originsFile).contains("https://bank.example"))
    }

    @Test
    fun captchaHandoffDoesNotMarkTheSitePrivate() {
        val origins = PrivateOriginStore(File(tmp.newFolder(), "o.json"))
        val c = BrowserController(Host("https://shop.example/"), tmp.newFolder(), privateOrigins = origins)
        c.requestHuman(JSONObject().put("reason", "CAPTCHA").put("request_id", "h1"))
        c.personContinue("https://shop.example/")
        assertTrue(origins.all().isEmpty())
    }

    @Test
    fun protocolAppliesThePolicyToEveryBrowserResult() {
        val store = PairingStore(File(tmp.newFolder(), "p.json"))
        val browser = BrowserController(Host("https://bank.example/home"), tmp.newFolder(), initialExportPolicy = ExportPolicy.LOCAL_ONLY)
        val connection = BridgeConnection(store, { _, _, _ -> PairingDecision.APPROVED }, { JSONObject() }, "0.1.0", browser = browser)
        fun call(id: Int, method: String, params: JSONObject = JSONObject()) =
            JSONObject(connection.handle(JSONObject().put("id", id).put("method", method).put("params", params).toString()))
        call(1, "hello", JSONObject().put("protocol_versions", listOf(1)).put("bridge_id", "b_" + "a".repeat(32)).put("bridge_name", "PC"))
        val token = call(2, "pair_begin", JSONObject().put("code", "123456")).getJSONObject("result").getString("token")
        call(3, "auth", JSONObject().put("token", token))
        val observed = call(4, "browser.observe").getJSONObject("result")
        assertFalse(observed.has("visible_text"))
        assertEquals("LOCAL_ONLY", observed.getString("export_policy"))
        assertEquals("CONTENT_WITHHELD", call(5, "browser.screenshot").getJSONObject("error").getString("code"))
        assertEquals("https://bank.example", call(6, "device_status").getJSONObject("result").getJSONObject("browser").getString("url"))
    }
}
