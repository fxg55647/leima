package fi.leima.android.bridge

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.security.SecureRandom
import java.time.Instant
import java.util.Base64

/**
 * USB protocol v1 between the phone and the PC bridge (docs/RESEARCH_APPLIANCE_USB_PROTOCOL.md).
 * Transport-free: [BridgeConnection] turns one request line into one response line, so the whole
 * handshake/pairing/auth state machine is testable on the plain JVM.
 */
object BridgeProtocol {
    const val VERSION = 1
    const val SOCKET_NAME = "fi.leima.android.bridge"
    const val MAX_LINE_BYTES = 1024 * 1024
    const val PAIRING_TIMEOUT_MS = 120_000L
    /** `shell` (adbd forwards as this uid) and `root` (`adb root`); every other peer is refused. */
    val ALLOWED_PEER_UIDS = setOf(2000, 0)
    val CAPABILITIES = listOf("device_status")
    val PACKAGE_CAPABILITIES = listOf("packages.list", "packages.read", "packages.delete")

    private val BRIDGE_ID = Regex("^b_[0-9a-f]{32}$")
    private val PAIRING_CODE = Regex("^[0-9]{6}$")

    fun isValidBridgeId(value: String) = BRIDGE_ID.matches(value)
    fun isValidPairingCode(value: String) = PAIRING_CODE.matches(value)

    fun error(id: Any?, code: String, message: String): String =
        JSONObject().put("id", id ?: JSONObject.NULL).put("error", JSONObject().put("code", code).put("message", message)).toString()

    fun result(id: Any?, result: JSONObject): String =
        JSONObject().put("id", id ?: JSONObject.NULL).put("result", result).toString()

    /** Reads one `\n`-terminated UTF-8 line. Returns null at end of stream; throws [LineTooLongException]. */
    fun readLine(input: InputStream, maxBytes: Int = MAX_LINE_BYTES): String? {
        val buffer = ByteArrayOutputStream()
        while (true) {
            val byte = input.read()
            if (byte < 0) return if (buffer.size() == 0) null else buffer.toString(Charsets.UTF_8.name())
            if (byte == '\n'.code) return buffer.toString(Charsets.UTF_8.name())
            if (buffer.size() >= maxBytes) throw LineTooLongException()
            buffer.write(byte)
        }
    }
}

class LineTooLongException : Exception("Request line exceeds ${BridgeProtocol.MAX_LINE_BYTES} bytes")

enum class PairingDecision { APPROVED, REJECTED, TIMEOUT, BUSY }

/** Asks the person holding the phone to approve a pairing. Blocks until they answer or [timeoutMs] passes. */
fun interface PairingApprover {
    fun requestApproval(bridgeName: String, code: String, timeoutMs: Long): PairingDecision
}

/** Device fields for `device_status`: `app_version`, `device`, `webview_version`. */
fun interface DeviceInfoProvider {
    fun deviceInfo(): JSONObject
}

/** A protocol error with a stable code (docs/RESEARCH_APPLIANCE_USB_PROTOCOL.md section 4). */
class ProtocolError(val code: String, message: String) : Exception(message)

/** One client connection's protocol state. Not thread-safe; one connection is served by one thread. */
class BridgeConnection(
    private val pairings: PairingStore,
    private val approver: PairingApprover,
    private val deviceInfo: DeviceInfoProvider,
    private val appVersion: String,
    private val random: SecureRandom = SecureRandom(),
    private val clock: () -> Instant = Instant::now,
    private val packages: PackageRepository? = null,
    private val onPackagesChanged: () -> Unit = {},
    private val browser: BrowserController? = null,
) {
    private var bridgeId: String? = null
    private var bridgeName: String = ""
    var sessionId: String? = null
        private set
    private var sessionToken: String? = null
    var closeRequested = false
        private set

    fun handle(line: String): String {
        val request = try { JSONObject(line) } catch (e: JSONException) {
            return BridgeProtocol.error(null, "BAD_REQUEST", "Request is not a JSON object")
        }
        val id: Any? = request.opt("id").takeIf { it is Int || it is Long }
        if (id == null) return BridgeProtocol.error(null, "BAD_REQUEST", "Request id must be an integer")
        val method = request.opt("method") as? String ?: return BridgeProtocol.error(id, "BAD_REQUEST", "method must be a string")
        val params = when (val raw = request.opt("params")) {
            null, JSONObject.NULL -> JSONObject()
            is JSONObject -> raw
            else -> return BridgeProtocol.error(id, "BAD_REQUEST", "params must be an object")
        }
        return try {
            BridgeProtocol.result(id, dispatch(method, params))
        } catch (e: ProtocolError) {
            BridgeProtocol.error(id, e.code, e.message.orEmpty())
        } catch (e: JSONException) {
            BridgeProtocol.error(id, "BAD_REQUEST", e.message.orEmpty())
        }
    }

    private fun dispatch(method: String, params: JSONObject): JSONObject {
        if (method == "bye") { closeRequested = true; return JSONObject() }
        if (method == "hello") return hello(params)
        if (method !in KNOWN_METHODS || (method in BridgeProtocol.PACKAGE_CAPABILITIES && packages == null) ||
            (method in BrowserController.METHODS && browser == null)) {
            throw ProtocolError("UNKNOWN_METHOD", "Unknown method: $method")
        }
        val bridge = bridgeId ?: throw ProtocolError("HELLO_REQUIRED", "Send hello first")
        return when (method) {
            "pair_begin" -> pairBegin(bridge, params)
            "auth" -> auth(bridge, params)
            "device_status" -> { requireSession(bridge); deviceStatus() }
            "unpair" -> { requireSession(bridge); pairings.unpair(bridge); endSession(); JSONObject() }
            "packages.list" -> { requireSession(bridge); listPackages(requireNotNull(packages)) }
            "packages.read" -> { requireSession(bridge); readPackage(requireNotNull(packages), params) }
            "packages.delete" -> { requireSession(bridge); deletePackage(requireNotNull(packages), params) }
            else -> { requireSession(bridge); browserCommand(requireNotNull(browser), method, params) }
        }
    }

    /** Every browser result passes the phone's export policy before it leaves the device. */
    private fun browserCommand(browser: BrowserController, method: String, params: JSONObject): JSONObject {
        return browser.exportView(browserResult(browser, method, params))
    }

    private fun browserResult(browser: BrowserController, method: String, params: JSONObject): JSONObject {
        return when (method) {
            "browser.navigate" -> browser.navigate(params)
            "browser.observe" -> browser.observe()
            "browser.click" -> browser.click(params)
            "browser.type" -> browser.type(params)
            "browser.back" -> browser.back(params)
            "browser.screenshot" -> browser.screenshot()
            "browser.capture" -> browser.capture(params)
            "command_status" -> browser.commandStatus(params)
            "browser.request_human" -> browser.requestHuman(params)
            "browser.resume" -> browser.resume(params)
            "browser.end_session" -> browser.endSession()
            else -> throw ProtocolError("UNKNOWN_METHOD", "Unknown method: $method")
        }
    }

    private fun hello(params: JSONObject): JSONObject {
        val versions = params.optJSONArray("protocol_versions") ?: throw ProtocolError("BAD_REQUEST", "protocol_versions is required")
        if ((0 until versions.length()).none { versions.opt(it) == BridgeProtocol.VERSION }) {
            throw ProtocolError("UNSUPPORTED_PROTOCOL", "Phone supports protocol version ${BridgeProtocol.VERSION}")
        }
        val id = params.opt("bridge_id") as? String
        if (id == null || !BridgeProtocol.isValidBridgeId(id)) throw ProtocolError("BAD_REQUEST", "bridge_id must match b_<32 hex>")
        val name = (params.opt("bridge_name") as? String)?.trim().orEmpty()
        if (name.isEmpty() || name.length > 64) throw ProtocolError("BAD_REQUEST", "bridge_name must be 1-64 characters")
        if (bridgeId != null && bridgeId != id) throw ProtocolError("BAD_REQUEST", "bridge_id cannot change within a connection")
        bridgeId = id
        bridgeName = name
        return JSONObject().put("protocol_version", BridgeProtocol.VERSION).put("app", "fi.leima.android")
            .put("app_version", appVersion).put("paired", pairings.isPaired(id))
    }

    private fun pairBegin(bridge: String, params: JSONObject): JSONObject {
        val code = params.opt("code") as? String
        if (code == null || !BridgeProtocol.isValidPairingCode(code)) throw ProtocolError("BAD_REQUEST", "code must be 6 digits")
        when (approver.requestApproval(bridgeName, code, BridgeProtocol.PAIRING_TIMEOUT_MS)) {
            PairingDecision.APPROVED -> Unit
            PairingDecision.REJECTED -> throw ProtocolError("PAIRING_REJECTED", "Pairing was rejected on the phone")
            PairingDecision.TIMEOUT -> throw ProtocolError("PAIRING_TIMEOUT", "Nobody answered the pairing request on the phone")
            PairingDecision.BUSY -> throw ProtocolError("PAIRING_BUSY", "Another pairing request is already open on the phone")
        }
        val token = randomToken(32)
        pairings.pair(bridge, bridgeName, token, clock().toString())
        return JSONObject().put("token", token)
    }

    private fun auth(bridge: String, params: JSONObject): JSONObject {
        val token = params.opt("token") as? String ?: throw ProtocolError("BAD_REQUEST", "token is required")
        if (!pairings.verify(bridge, token)) throw ProtocolError("AUTH_FAILED", "Token is not valid for this bridge")
        val session = "s_" + randomToken(12)
        sessionId = session
        sessionToken = token
        return JSONObject().put("session_id", session)
    }

    private fun deviceStatus(): JSONObject {
        val info = deviceInfo.deviceInfo()
        return JSONObject().put("protocol_version", BridgeProtocol.VERSION).put("session_id", sessionId)
            .put("app_version", appVersion)
            .put("device", info.optJSONObject("device") ?: JSONObject())
            .put("webview_version", info.opt("webview_version") ?: JSONObject.NULL)
            .put("capabilities", JSONArray(BridgeProtocol.CAPABILITIES +
                (if (packages != null) BridgeProtocol.PACKAGE_CAPABILITIES else emptyList()) +
                (if (browser != null) BrowserController.METHODS else emptyList())))
            .put("browser", browser?.status() ?: JSONObject().put("state", "NOT_AVAILABLE"))
    }

    /**
     * Re-checks the session's token against the pairing store on every command, so removing or
     * replacing a pairing on the phone revokes sessions that authenticated before the change.
     */
    private fun requireSession(bridge: String) {
        val token = sessionToken
        if (sessionId == null || token == null) throw ProtocolError("NOT_AUTHENTICATED", "Authenticate with auth first")
        if (!pairings.verify(bridge, token)) {
            endSession()
            throw ProtocolError("SESSION_REVOKED", "The pairing was removed or replaced on the phone; pair again")
        }
    }

    private fun endSession() { sessionId = null; sessionToken = null }

    private fun listPackages(repository: PackageRepository): JSONObject {
        val list = JSONArray()
        repository.list().forEach { pkg ->
            list.put(JSONObject().put("package_id", pkg.packageId).put("kind", pkg.kind).put("size", pkg.size)
                .put("sha256", repository.sha256(pkg)).put("created_at", Instant.ofEpochMilli(pkg.createdAt).toString()))
        }
        return JSONObject().put("packages", list)
    }

    private fun findPackage(repository: PackageRepository, params: JSONObject): StoredPackage {
        val id = params.opt("package_id") as? String ?: throw ProtocolError("BAD_REQUEST", "package_id is required")
        return repository.find(id) ?: throw ProtocolError("PACKAGE_NOT_FOUND", "No finished package $id")
    }

    private fun readPackage(repository: PackageRepository, params: JSONObject): JSONObject {
        val pkg = findPackage(repository, params)
        val offset = (params.opt("offset") as? Number)?.toLong() ?: throw ProtocolError("BAD_REQUEST", "offset is required")
        val length = (params.opt("length") as? Number)?.toInt() ?: throw ProtocolError("BAD_REQUEST", "length is required")
        if (offset < 0 || length !in 1..PackageRepository.MAX_READ_BYTES) {
            throw ProtocolError("BAD_REQUEST", "offset must be >= 0 and length 1..${PackageRepository.MAX_READ_BYTES}")
        }
        val bytes = repository.read(pkg, offset, length)
        return JSONObject().put("offset", offset).put("data_base64", Base64.getEncoder().encodeToString(bytes))
            .put("eof", offset + bytes.size >= pkg.size)
    }

    private fun deletePackage(repository: PackageRepository, params: JSONObject): JSONObject {
        val pkg = findPackage(repository, params)
        val sha256 = params.opt("sha256") as? String ?: throw ProtocolError("BAD_REQUEST", "sha256 is required")
        try {
            repository.delete(pkg, sha256)
        } catch (e: PackageChangedException) {
            throw ProtocolError("PACKAGE_CHANGED", "Package bytes do not match sha256; not deleted")
        }
        onPackagesChanged()
        return JSONObject().put("deleted", true)
    }

    private fun randomToken(bytes: Int): String =
        Base64.getUrlEncoder().withoutPadding().encodeToString(ByteArray(bytes).also(random::nextBytes))

    private companion object {
        val KNOWN_METHODS = setOf("pair_begin", "auth", "device_status", "unpair") + BridgeProtocol.PACKAGE_CAPABILITIES + BrowserController.METHODS
    }
}
