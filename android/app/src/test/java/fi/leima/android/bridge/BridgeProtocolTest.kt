package fi.leima.android.bridge

import java.io.ByteArrayInputStream
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class BridgeProtocolTest {
    @get:Rule val tmp = TemporaryFolder()

    private val bridgeId = "b_" + "0123456789abcdef".repeat(2)
    private val device = DeviceInfoProvider {
        JSONObject().put("device", JSONObject().put("model", "Test")).put("webview_version", "129.0")
    }

    private fun store() = PairingStore(File(tmp.newFolder(), "bridge/pairings.json"))

    private fun connection(store: PairingStore, decision: PairingDecision = PairingDecision.APPROVED, prompts: MutableList<String> = mutableListOf()) =
        BridgeConnection(store, { name, code, _ -> prompts += "$name/$code"; decision }, device, "0.1.0")

    private fun BridgeConnection.call(id: Int, method: String, params: JSONObject = JSONObject()): JSONObject =
        JSONObject(handle(JSONObject().put("id", id).put("method", method).put("params", params).toString()))

    private fun JSONObject.errorCode(): String? = optJSONObject("error")?.optString("code")

    private fun BridgeConnection.hello(): JSONObject =
        call(1, "hello", JSONObject().put("protocol_versions", listOf(1)).put("bridge_id", bridgeId).put("bridge_name", "PC"))

    @Test
    fun pairsThenAuthenticatesOnALaterConnection() {
        val store = store()
        val prompts = mutableListOf<String>()
        val first = connection(store, prompts = prompts)
        assertFalse(first.hello().getJSONObject("result").getBoolean("paired"))
        val token = first.call(2, "pair_begin", JSONObject().put("code", "123456")).getJSONObject("result").getString("token")
        assertEquals(listOf("PC/123456"), prompts)
        assertEquals(43, token.length)

        val second = connection(store)
        assertTrue(second.hello().getJSONObject("result").getBoolean("paired"))
        assertEquals("NOT_AUTHENTICATED", second.call(3, "device_status").errorCode())
        val session = second.call(4, "auth", JSONObject().put("token", token)).getJSONObject("result").getString("session_id")
        val status = second.call(5, "device_status").getJSONObject("result")
        assertEquals(session, status.getString("session_id"))
        assertEquals(1, status.getInt("protocol_version"))
        assertEquals("Test", status.getJSONObject("device").getString("model"))
        assertEquals("device_status", status.getJSONArray("capabilities").getString(0))
        assertEquals("NOT_AVAILABLE", status.getJSONObject("browser").getString("state"))
    }

    @Test
    fun storesOnlyTheTokenHash() {
        val store = store()
        val first = connection(store)
        first.hello()
        val token = first.call(2, "pair_begin", JSONObject().put("code", "123456")).getJSONObject("result").getString("token")
        val file = File(tmp.root.listFiles()!!.single(), "bridge/pairings.json")
        assertFalse(file.readText().contains(token))
    }

    @Test
    fun rejectsWrongTokenAndTokenOfAnotherBridge() {
        val store = store()
        store.pair("b_" + "f".repeat(32), "Other PC", "other-token", "2026-10-03T00:00:00Z")
        val connection = connection(store)
        connection.hello()
        assertEquals("AUTH_FAILED", connection.call(2, "auth", JSONObject().put("token", "other-token")).errorCode())
        assertEquals("AUTH_FAILED", connection.call(3, "auth", JSONObject().put("token", "guess")).errorCode())
        assertEquals("NOT_AUTHENTICATED", connection.call(4, "device_status").errorCode())
    }

    @Test
    fun requiresHelloAndACommonProtocolVersion() {
        val connection = connection(store())
        assertEquals("HELLO_REQUIRED", connection.call(1, "auth", JSONObject().put("token", "x")).errorCode())
        val unsupported = connection.call(2, "hello", JSONObject().put("protocol_versions", listOf(2)).put("bridge_id", bridgeId).put("bridge_name", "PC"))
        assertEquals("UNSUPPORTED_PROTOCOL", unsupported.errorCode())
        val badId = connection.call(3, "hello", JSONObject().put("protocol_versions", listOf(1)).put("bridge_id", "nope").put("bridge_name", "PC"))
        assertEquals("BAD_REQUEST", badId.errorCode())
    }

    @Test
    fun reportsPairingRefusals() {
        for ((decision, code) in listOf(
            PairingDecision.REJECTED to "PAIRING_REJECTED",
            PairingDecision.TIMEOUT to "PAIRING_TIMEOUT",
            PairingDecision.BUSY to "PAIRING_BUSY",
        )) {
            val store = store()
            val connection = connection(store, decision)
            connection.hello()
            assertEquals(code, connection.call(2, "pair_begin", JSONObject().put("code", "123456")).errorCode())
            assertFalse(store.isPaired(bridgeId))
        }
        val connection = connection(store())
        connection.hello()
        assertEquals("BAD_REQUEST", connection.call(2, "pair_begin", JSONObject().put("code", "12345")).errorCode())
    }

    @Test
    fun unpairRemovesThisBridgeOnly() {
        val store = store()
        store.pair("b_" + "f".repeat(32), "Other PC", "other-token", "2026-10-03T00:00:00Z")
        val connection = connection(store)
        connection.hello()
        val token = connection.call(2, "pair_begin", JSONObject().put("code", "123456")).getJSONObject("result").getString("token")
        connection.call(3, "auth", JSONObject().put("token", token))
        assertTrue(connection.call(4, "unpair").has("result"))
        assertFalse(store.isPaired(bridgeId))
        assertEquals(1, store.count())
        assertEquals("NOT_AUTHENTICATED", connection.call(5, "device_status").errorCode())
    }

    @Test
    fun malformedRequestsGetErrorsNotCrashes() {
        val connection = connection(store())
        assertEquals("BAD_REQUEST", JSONObject(connection.handle("not json")).errorCode())
        assertEquals("BAD_REQUEST", JSONObject(connection.handle("{\"method\":\"hello\"}")).errorCode())
        assertEquals("UNKNOWN_METHOD", connection.call(1, "shell").errorCode())
        assertTrue(connection.call(2, "bye").has("result"))
        assertTrue(connection.closeRequested)
    }

    @Test
    fun readLineIsBounded() {
        assertEquals("abc", BridgeProtocol.readLine(ByteArrayInputStream("abc\nrest".toByteArray())))
        assertNull(BridgeProtocol.readLine(ByteArrayInputStream(ByteArray(0))))
        val threw = runCatching { BridgeProtocol.readLine(ByteArrayInputStream(ByteArray(20) { 'a'.code.toByte() }), maxBytes = 10) }
            .exceptionOrNull() is LineTooLongException
        assertTrue(threw)
    }
}
