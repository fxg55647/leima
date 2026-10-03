package fi.leima.android.bridge

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.URI
import java.net.URLDecoder
import java.security.SecureRandom
import java.time.Instant
import java.util.Base64
import java.util.UUID
import java.util.concurrent.atomic.AtomicReference

data class PageState(val url: String, val title: String, val loading: Boolean, val generation: Int, val canGoBack: Boolean)

data class MaskRect(val x: Double, val y: Double, val width: Double, val height: Double)

data class Screenshot(val png: ByteArray, val width: Int, val height: Int)

/** Who controls the phone browser (docs/RESEARCH_APPLIANCE_ARCHITECTURE.md, phase C). */
enum class ControlState { READY, RUNNING, HUMAN_ACTION_REQUIRED, CANCELLED, EXPIRED }

/** A handoff to the person. [requestedBy] is `agent` or `person`; [completed] is set by the phone's Jatka. */
data class Handoff(
    val id: String,
    val reason: String,
    val task: String,
    val requestedBy: String,
    val createdAt: Instant,
    val expiresAt: Instant,
    val completed: Boolean = false,
) {
    fun toJson(): JSONObject = JSONObject().put("handoff_id", id).put("reason", reason).put("task", task)
        .put("requested_by", requestedBy).put("created_at", createdAt.toString()).put("expires_at", expiresAt.toString())
        .put("completed_on_phone", completed)
}

data class ControlSnapshot(val state: ControlState, val sessionId: String, val handoff: Handoff?, val exportPolicy: ExportPolicy)

/**
 * The phone's WebView as seen by [BrowserController]. Implementations block the calling (bridge)
 * thread and do the WebView work on the main thread. Every method throws [ProtocolError] with
 * `BROWSER_UNAVAILABLE` when the browser tab is not shown or is busy with the person's own action.
 */
interface BrowserHost {
    fun state(): PageState
    /** Loads [url] and waits until the page finished loading or [timeoutMs] passed (then `loading = true`). */
    fun navigate(url: String, timeoutMs: Long): PageState
    /** Goes back one history entry, or returns null when there is none. */
    fun back(timeoutMs: Long): PageState?
    /** Waits up to [timeoutMs] for a navigation started by a page action to finish. */
    fun settle(timeoutMs: Long): PageState
    /** Runs `leima_page.js` with [command] and [args]; returns its JSON result. */
    fun pageCommand(command: String, args: JSONObject, timeoutMs: Long): JSONObject
    /** Visible WebView pixels with every [masks] rectangle (CSS px of a [cssWidth]-wide viewport) painted black. */
    fun screenshot(masks: List<MaskRect>, cssWidth: Double): Screenshot
    /** Certificate of the current page (`WebView.getCertificate()`), or null. */
    fun certificate(): JSONObject?
    /** `appVersion`, `webViewVersion`, `device`. */
    fun environment(): JSONObject
}

/**
 * Agent control of the phone browser (docs/RESEARCH_APPLIANCE_USB_PROTOCOL.md, `browser.*`).
 *
 * - One browser session per app run (`session_id`), independent of USB connections, so observation
 *   and element ids survive a reconnect.
 * - An observation is valid only until the next state-changing command or navigation; acting on an
 *   older one is `STALE_OBSERVATION`, never a click on some other element.
 * - State-changing commands carry a `request_id`; a repeated id returns the stored outcome instead of
 *   acting twice, and `command_status` reports it after a USB drop.
 * - Handoff (phase C): while a handoff is open every agent browser command except `command_status`,
 *   `browser.resume` and `browser.end_session` is refused. Only the phone's Jatka completes it; Keskeytä
 *   (or expiry) stops agent control until the person allows it again on the phone.
 */
class BrowserController(
    private val host: BrowserHost,
    private val captureRoot: File,
    private val random: SecureRandom = SecureRandom(),
    private val clock: () -> Instant = Instant::now,
    private val elapsedNanos: () -> Long = System::nanoTime,
    private val onActivity: (String) -> Unit = {},
    private val onControlChanged: (ControlSnapshot) -> Unit = {},
    private val privateOrigins: PrivateOriginStore? = null,
    initialExportPolicy: ExportPolicy = ExportPolicy.AUTO,
) {
    /** Set by the person on the phone; the agent cannot change it. */
    @Volatile var exportPolicy: ExportPolicy = initialExportPolicy
        set(value) { field = value; changed() }

    @Volatile var sessionId = "bs_" + token(12)
        private set
    /**
     * Guards [handoff], [stopped], [lastResumedHandoff]; waited on by [resume]. Lock order is
     * [lock] then [control]; code holding [control] never takes [lock], so the phone UI thread is never
     * blocked by a running browser command.
     */
    private val control = Object()
    private var handoff: Handoff? = null
    private var stopped: ControlState? = null
    private var lastResumedHandoff: String? = null
    private val lock = Any()
    /** Volatile, not guarded by [lock]: the phone UI thread clears it without waiting for a running command. */
    @Volatile private var observationId: String? = null
    private var observationGeneration = -1
    private var lastRequestedUrl: String? = null
    private val running = AtomicReference<String?>(null)
    private val outcomes = object : LinkedHashMap<String, JSONObject>(16, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, JSONObject>?) = size > MAX_OUTCOMES
    }

    fun status(): JSONObject {
        val snap = snapshot()
        val base = runCatching { host.state() }.fold(
            { JSONObject().put("state", "AVAILABLE").put("url", it.url) },
            { JSONObject().put("state", "NOT_AVAILABLE") },
        )
        val url = base.opt("url") as? String
        val local = url != null && isLocalOnly(url)
        return ExportFilter.apply(base.put("session_id", snap.sessionId).put("control", snap.state.name)
            .put("handoff", snap.handoff?.toJson() ?: JSONObject.NULL)
            .put("export_policy_setting", exportPolicy.name), local)
    }

    /** Whether page content of [url] stays on the phone under the current setting. Safe on any thread. */
    fun isLocalOnly(url: String): Boolean = when (exportPolicy) {
        ExportPolicy.LOCAL_ONLY -> true
        ExportPolicy.AGENT_READABLE -> false
        ExportPolicy.AUTO -> privateOrigins?.contains(ExportFilter.originOf(url)) == true
    }

    /**
     * Filters a browser result for export to the agent. Local-only applies if either the page the
     * result describes or the page now shown is local-only.
     */
    fun exportView(result: JSONObject): JSONObject {
        val current = runCatching { host.state().url }.getOrNull()
        val described = (result.opt("url") as? String) ?: (result.optJSONObject("observation")?.opt("url") as? String)
            ?: (result.optJSONObject("result")?.opt("url") as? String)
        val local = listOfNotNull(current, described).any(::isLocalOnly) || exportPolicy == ExportPolicy.LOCAL_ONLY
        return ExportFilter.apply(result, local)
    }

    fun snapshot(): ControlSnapshot = synchronized(control) {
        expireIfDue()
        val state = stopped ?: when {
            handoff != null -> ControlState.HUMAN_ACTION_REQUIRED
            running.get() != null -> ControlState.RUNNING
            else -> ControlState.READY
        }
        ControlSnapshot(state, sessionId, handoff, exportPolicy)
    }

    fun observe(): JSONObject {
        ensureAgentAllowed()
        return observeNow()
    }

    private fun observeNow(): JSONObject = synchronized(lock) {
        val state = host.state()
        val id = "obs_" + token(9)
        val page = pageCommand("observe", JSONObject().put("observation_id", id))
        observationId = id
        observationGeneration = state.generation
        onActivity("luki sivun ${hostOf(state.url)}")
        JSONObject().put("session_id", sessionId).put("observation_id", id)
            .put("url", page.optString("url", state.url)).put("title", page.optString("title", state.title))
            .put("loading", state.loading || page.optString("ready_state") != "complete")
            .put("visible_text", page.optString("visible_text"))
            .put("elements", page.optJSONArray("elements") ?: JSONArray())
            .put("limitations", page.optJSONArray("limitations") ?: JSONArray())
            .put("human_action_hints", page.optJSONArray("human_action_hints") ?: JSONArray())
    }

    fun navigate(params: JSONObject): JSONObject = mutating(params) {
        val url = params.opt("url") as? String ?: throw ProtocolError("BAD_REQUEST", "url is required")
        if (!isSafeUrl(url)) throw ProtocolError("URL_NOT_ALLOWED", "Only https:// URLs without credentials are allowed")
        lastRequestedUrl = url
        onActivity("avaa ${hostOf(url)}")
        pageResult(host.navigate(url, NAVIGATION_TIMEOUT_MS))
    }

    fun click(params: JSONObject): JSONObject = mutating(params) {
        val element = requireObservation(params)
        val result = pageCommand("click", JSONObject().put("observation_id", observationId).put("element_id", element))
        onActivity("klikkasi elementtiä")
        pageResult(host.settle(SETTLE_TIMEOUT_MS)).put("method", result.optString("method"))
    }

    fun type(params: JSONObject): JSONObject = mutating(params) {
        val element = requireObservation(params)
        val text = params.opt("text") as? String ?: throw ProtocolError("BAD_REQUEST", "text is required")
        if (text.length > MAX_TYPE_CHARS) throw ProtocolError("BAD_REQUEST", "text is limited to $MAX_TYPE_CHARS characters")
        val replace = params.optBoolean("replace", true)
        val result = pageCommand("type", JSONObject().put("observation_id", observationId).put("element_id", element)
            .put("text", text).put("replace", replace))
        onActivity("kirjoitti tekstikenttään")
        pageResult(host.settle(SETTLE_TIMEOUT_MS)).put("method", result.optString("method"))
    }

    fun back(params: JSONObject): JSONObject = mutating(params) {
        val state = host.back(NAVIGATION_TIMEOUT_MS) ?: throw ProtocolError("NO_HISTORY", "There is no previous page")
        onActivity("palasi edelliselle sivulle")
        pageResult(state)
    }

    fun screenshot(): JSONObject {
        ensureAgentAllowed()
        if (exportPolicy == ExportPolicy.LOCAL_ONLY || isLocalOnly(host.state().url)) {
            throw ProtocolError("CONTENT_WITHHELD", "This page is local-only on the phone; screenshots are not exported. browser_capture still stores it on the phone.")
        }
        return screenshotNow()
    }

    private fun screenshotNow(): JSONObject = synchronized(lock) {
        val state = host.state()
        val shot = maskedScreenshot()
        onActivity("otti kuvakaappauksen")
        JSONObject().put("url", state.url).put("width", shot.first.width).put("height", shot.first.height)
            .put("masked_regions", shot.second).put("png_base64", Base64.getEncoder().encodeToString(shot.first.png))
    }

    fun capture(params: JSONObject): JSONObject = mutating(params) { captureNow() }

    // ---- handoff (phase C) ----------------------------------------------------------------------

    /** Agent asks the person to act on the phone. Blocks further agent commands until resumed. */
    fun requestHuman(params: JSONObject): JSONObject = mutating(params) {
        val reason = params.opt("reason") as? String
        if (reason !in HANDOFF_REASONS) throw ProtocolError("BAD_REQUEST", "reason must be one of $HANDOFF_REASONS")
        val task = (params.opt("task") as? String)?.trim().orEmpty()
        if (task.length > MAX_TASK_CHARS) throw ProtocolError("BAD_REQUEST", "task is limited to $MAX_TASK_CHARS characters")
        val timeout = params.optLong("timeout_s", DEFAULT_HANDOFF_S)
        if (timeout !in 30..MAX_HANDOFF_S) throw ProtocolError("BAD_REQUEST", "timeout_s must be 30..$MAX_HANDOFF_S")
        val opened = synchronized(control) {
            ensureAgentAllowedLocked()
            val now = clock()
            Handoff("ho_" + token(9), reason!!, task, "agent", now, now.plusSeconds(timeout)).also { handoff = it }
        }
        onActivity("pyytää apuasi")
        changed()
        JSONObject().put("state", ControlState.HUMAN_ACTION_REQUIRED.name).put("handoff", opened.toJson())
    }

    /**
     * Returns control to the agent after the person pressed Jatka, with a fresh observation. Waits up
     * to `wait_s` seconds for Jatka. Repeating it for the handoff that was just resumed is harmless.
     */
    fun resume(params: JSONObject): JSONObject {
        val id = params.opt("handoff_id") as? String ?: throw ProtocolError("BAD_REQUEST", "handoff_id is required")
        val waitS = params.optLong("wait_s", 0)
        if (waitS !in 0..MAX_RESUME_WAIT_S) throw ProtocolError("BAD_REQUEST", "wait_s must be 0..$MAX_RESUME_WAIT_S")
        val deadline = System.nanoTime() + waitS * 1_000_000_000
        synchronized(control) {
            while (true) {
                expireIfDue()
                stoppedError()?.let { throw it }
                val open = handoff
                if (open == null) {
                    if (lastResumedHandoff == id) break
                    throw ProtocolError("NO_HANDOFF", "There is no open handoff $id")
                }
                if (open.id != id) throw ProtocolError("NO_HANDOFF", "The open handoff is ${open.id}, not $id")
                if (open.completed) {
                    handoff = null
                    lastResumedHandoff = id
                    break
                }
                val remainingMs = (deadline - System.nanoTime()) / 1_000_000
                if (remainingMs <= 0) {
                    throw ProtocolError("HUMAN_NOT_DONE", "The person has not pressed Jatka on the phone yet")
                }
                control.wait(minOf(remainingMs, 1_000))
            }
        }
        changed()
        onActivity("jatkaa")
        return JSONObject().put("state", ControlState.READY.name).put("handoff_id", id).put("observation", observeNow())
    }

    /** Ends the agent's browser session: new session id, observation and stored outcomes dropped. */
    fun endSession(): JSONObject {
        val ended = synchronized(control) {
            val old = sessionId
            handoff = null
            sessionId = "bs_" + token(12)
            observationId = null
            synchronized(outcomes) { outcomes.clear() }
            control.notifyAll()
            old
        }
        onActivity("lopetti selainistunnon")
        changed()
        return JSONObject().put("ended_session_id", ended).put("session_id", sessionId)
    }

    /** Phone: the person takes control at any time. */
    fun personTakeControl() {
        synchronized(control) {
            if (stopped != null || handoff != null) return
            val now = clock()
            handoff = Handoff("ho_" + token(9), "PERSON_TOOK_CONTROL", "", "person", now, now.plusSeconds(MAX_HANDOFF_S))
            observationId = null
        }
        changed()
    }

    /**
     * Phone: Jatka. [pageUrl] is the page shown when the person pressed it: after a login, MFA or
     * the person's own control its origin becomes local-only under [ExportPolicy.AUTO].
     */
    fun personContinue(pageUrl: String? = null) {
        val reason = synchronized(control) {
            val open = handoff ?: return
            handoff = open.copy(completed = true)
            control.notifyAll()
            open.reason
        }
        if (reason in PRIVATE_AFTER && pageUrl != null) privateOrigins?.add(ExportFilter.originOf(pageUrl))
        changed()
    }

    /** Phone: Keskeytä. Stops agent control until [personAllowAgain]. */
    fun personCancel() {
        synchronized(control) {
            stopped = ControlState.CANCELLED
            handoff = null
            observationId = null
            control.notifyAll()
        }
        changed()
    }

    /** Phone: let the agent in again after Keskeytä or expiry; starts a new browser session. */
    fun personAllowAgain() {
        synchronized(control) {
            if (stopped == null) return
            stopped = null
            sessionId = "bs_" + token(12)
            synchronized(outcomes) { outcomes.clear() }
        }
        changed()
    }

    /** Phone UI calls this periodically so an expired handoff shows as expired. */
    fun refreshExpiry() { if (synchronized(control) { expireIfDue() }) changed() }

    private fun expireIfDue(): Boolean {
        val open = handoff ?: return false
        if (open.completed || clock().isBefore(open.expiresAt)) return false
        handoff = null
        stopped = ControlState.EXPIRED
        observationId = null
        control.notifyAll()
        return true
    }

    private fun stoppedError(): ProtocolError? = when (stopped) {
        ControlState.CANCELLED -> ProtocolError("SESSION_CANCELLED", "The person stopped agent control on the phone; they must allow it again there")
        ControlState.EXPIRED -> ProtocolError("HANDOFF_EXPIRED", "The handoff expired without an answer; the person must allow agent control again on the phone")
        else -> null
    }

    private fun ensureAgentAllowed() {
        var expired = false
        try {
            synchronized(control) { expired = expireIfDue(); ensureAgentAllowedLocked() }
        } finally {
            if (expired) changed()
        }
    }

    private fun ensureAgentAllowedLocked() {
        stoppedError()?.let { throw it }
        handoff?.let { open ->
            val next = if (open.completed) "call browser.resume with handoff_id ${open.id}" else "wait for the person to press Jatka, then call browser.resume"
            throw ProtocolError("HUMAN_ACTION_PENDING", "The person is in control on the phone (${open.reason}); $next")
        }
    }

    private fun changed() { onControlChanged(snapshot()) }

    fun commandStatus(params: JSONObject): JSONObject {
        val id = requestId(params)
        if (running.get() == id) return JSONObject().put("request_id", id).put("state", "running")
        val outcome = synchronized(outcomes) { outcomes[id] } ?: return JSONObject().put("request_id", id).put("state", "unknown")
        return JSONObject(outcome.toString()).put("request_id", id).put("state", "done")
    }

    // ---- internals ------------------------------------------------------------------------------

    private fun mutating(params: JSONObject, action: () -> JSONObject): JSONObject {
        val id = requestId(params)
        synchronized(outcomes) { outcomes[id] }?.let { return replay(it) }
        ensureAgentAllowed()
        if (!running.compareAndSet(null, id)) {
            throw ProtocolError("COMMAND_IN_PROGRESS", "Another browser command (${running.get()}) is still running")
        }
        try {
            val outcome = try {
                synchronized(lock) {
                    try { JSONObject().put("result", action()) } finally { observationId = null }
                }
            } catch (e: ProtocolError) {
                JSONObject().put("error", JSONObject().put("code", e.code).put("message", e.message))
            }
            synchronized(outcomes) { outcomes[id] = outcome }
            return replay(outcome, replayed = false)
        } finally {
            running.set(null)
        }
    }

    private fun replay(outcome: JSONObject, replayed: Boolean = true): JSONObject {
        outcome.optJSONObject("error")?.let { throw ProtocolError(it.getString("code"), it.optString("message")) }
        return JSONObject(outcome.getJSONObject("result").toString()).also { if (replayed) it.put("replayed", true) }
    }

    private fun requestId(params: JSONObject): String {
        val id = params.opt("request_id") as? String
        if (id == null || !REQUEST_ID.matches(id)) throw ProtocolError("BAD_REQUEST", "request_id must be 1-64 characters [A-Za-z0-9_-]")
        return id
    }

    private fun requireObservation(params: JSONObject): String {
        if (params.opt("session_id") != sessionId) throw ProtocolError("STALE_SESSION", "session_id does not match the phone's browser session")
        val observation = params.opt("observation_id") as? String ?: throw ProtocolError("BAD_REQUEST", "observation_id is required")
        val element = params.opt("element_id") as? String ?: throw ProtocolError("BAD_REQUEST", "element_id is required")
        if (observation != observationId || host.state().generation != observationGeneration) {
            throw ProtocolError("STALE_OBSERVATION", "Observation is out of date; call browser.observe again")
        }
        return element
    }

    private fun pageCommand(command: String, args: JSONObject): JSONObject {
        val result = host.pageCommand(command, args, SCRIPT_TIMEOUT_MS)
        result.optString("error").takeIf { it.isNotEmpty() }?.let { code ->
            val message = when (code) {
                "STALE_OBSERVATION" -> "Observation is out of date; call browser.observe again"
                "UNKNOWN_ELEMENT" -> "No such element in this observation"
                "ELEMENT_DISABLED" -> "Element is disabled or read-only"
                "SENSITIVE_FIELD" -> "Password and one-time-code fields are filled in by the person, not the agent"
                "NOT_TEXT_INPUT" -> "Element is not a text field"
                else -> result.optString("detail", "Page script failed")
            }
            throw ProtocolError(code, message)
        }
        return result
    }

    private fun pageResult(state: PageState) =
        JSONObject().put("url", state.url).put("title", state.title).put("loading", state.loading)

    /** Returns the masked screenshot and the number of masked regions, or throws SCREENSHOT_BLOCKED. */
    private fun maskedScreenshot(): Pair<Screenshot, Int> {
        val masks = pageCommand("masks", JSONObject())
        if (masks.optInt("visible_cross_origin_iframes") > 0) {
            throw ProtocolError("SCREENSHOT_BLOCKED", "A cross-origin frame is visible; its secret fields cannot be masked, so no screenshot is exported")
        }
        val rects = masks.optJSONArray("rects") ?: JSONArray()
        val list = (0 until rects.length()).map { rects.getJSONObject(it) }
            .map { MaskRect(it.getDouble("x"), it.getDouble("y"), it.getDouble("width"), it.getDouble("height")) }
        val cssWidth = masks.getJSONObject("viewport").getDouble("width")
        return host.screenshot(list, cssWidth) to list.size
    }

    private fun captureNow(): JSONObject {
        val startedAt = clock()
        val startedNanos = elapsedNanos()
        val state = host.state()
        onActivity("tallentaa lähteen ${hostOf(state.url)}")
        val observation = pageCommand("observe", JSONObject().put("observation_id", "cap_" + token(6)))
        val dom = pageCommand("dom", JSONObject())
        val missing = JSONArray()
        val files = linkedMapOf<String, ByteArray>()
        files["dom.html"] = dom.getString("html").toByteArray(Charsets.UTF_8)
        files["visible-text.txt"] = observation.optString("visible_text").toByteArray(Charsets.UTF_8)
        files["observation.json"] = JSONObject().put("url", redactUrl(observation.optString("url")).first)
            .put("title", observation.optString("title")).put("elements", observation.optJSONArray("elements") ?: JSONArray())
            .put("limitations", observation.optJSONArray("limitations") ?: JSONArray()).toString(2).toByteArray(Charsets.UTF_8)
        var masked = 0
        try {
            val (shot, count) = maskedScreenshot()
            files["screenshot.png"] = shot.png
            masked = count
        } catch (e: ProtocolError) {
            missing.put(JSONObject().put("file", "screenshot.png").put("reason", e.code).put("detail", e.message))
        }
        val completedAt = clock()
        val (url, urlRedactions) = redactUrl(state.url)
        val environment = host.environment()
        val metadata = JSONObject()
            .put("schemaVersion", 1).put("kind", "browser")
            .put("captureStatus", if (missing.length() == 0) "complete" else "partial").put("missing", missing)
            .put("requestedAt", startedAt.toString()).put("completedAt", completedAt.toString())
            .put("durationMs", (elapsedNanos() - startedNanos) / 1_000_000)
            .put("clock", JSONObject().put("source", "device_wall_clock").put("verified", false))
            .put("url", url).put("requestedUrl", lastRequestedUrl?.let { redactUrl(it).first } ?: JSONObject.NULL)
            .put("title", state.title)
            .put("certificate", host.certificate() ?: JSONObject.NULL)
            .put("appVersion", environment.opt("appVersion")).put("webViewVersion", environment.opt("webViewVersion"))
            .put("device", environment.optJSONObject("device") ?: JSONObject())
            .put("browserSession", sessionId)
            .put("captureMethod", JSONObject()
                .put("dom.html", "Serialization of the live DOM (attributes, not typed field values); not the original HTTP response")
                .put("visible-text.txt", "document.body.innerText")
                .put("observation.json", "Interactive elements as listed by leima_page.js")
                .put("screenshot.png", "PixelCopy of the visible WebView area, secret fields painted black"))
            .put("redactions", JSONObject(dom.getJSONObject("redactions").toString())
                .put("urlParameters", urlRedactions).put("maskedScreenshotRegions", masked))
            .put("timing", "Files are captured one after another; the package is not an atomic snapshot")
            .put("scope", "Integrity of these bytes only. Not proof of origin, server response, time or truth.")
        files["metadata.json"] = metadata.toString(2).toByteArray(Charsets.UTF_8)
        val zip = BrowserCaptureStore.finish(File(captureRoot, UUID.randomUUID().toString()), files)
        return JSONObject().put("package_id", "evidence:${zip.parentFile!!.name}").put("kind", "browser")
            .put("capture_status", metadata.getString("captureStatus")).put("missing", missing)
            .put("size", zip.length()).put("sha256", BrowserCaptureStore.sha256Hex(zip))
    }

    private fun token(bytes: Int) = Base64.getUrlEncoder().withoutPadding().encodeToString(ByteArray(bytes).also(random::nextBytes))

    companion object {
        const val NAVIGATION_TIMEOUT_MS = 30_000L
        const val SETTLE_TIMEOUT_MS = 5_000L
        const val SCRIPT_TIMEOUT_MS = 10_000L
        const val MAX_TYPE_CHARS = 2000
        const val MAX_OUTCOMES = 64
        const val DEFAULT_HANDOFF_S = 600L
        const val MAX_HANDOFF_S = 1800L
        const val MAX_RESUME_WAIT_S = 120L
        const val MAX_TASK_CHARS = 300
        val HANDOFF_REASONS = setOf("LOGIN", "MFA", "CAPTCHA", "CONFIRMATION", "OTHER")
        /** Handoffs after which the page's origin is treated as logged in. */
        private val PRIVATE_AFTER = setOf("LOGIN", "MFA", "PERSON_TOOK_CONTROL")
        val METHODS = listOf("browser.navigate", "browser.observe", "browser.click", "browser.type",
            "browser.back", "browser.screenshot", "browser.capture", "command_status",
            "browser.request_human", "browser.resume", "browser.end_session")
        private val REQUEST_ID = Regex("^[A-Za-z0-9_-]{1,64}$")
        private val SECRET_PARAM = Regex("(token|key|secret|pass|session|auth|code|sig|jwt|otp|nonce|state)", RegexOption.IGNORE_CASE)

        fun isSafeUrl(value: String): Boolean = runCatching {
            val uri = URI(value)
            uri.scheme.equals("https", ignoreCase = true) && !uri.host.isNullOrBlank() && uri.rawUserInfo == null
        }.getOrDefault(false)

        /** Drops the fragment and blanks query values whose names look secret. Returns (url, redacted count). */
        fun redactUrl(value: String): Pair<String, Int> = runCatching {
            val uri = URI(value)
            var count = if (uri.rawFragment != null) 1 else 0
            val query = uri.rawQuery?.split("&")?.joinToString("&") { part ->
                val name = URLDecoder.decode(part.substringBefore("="), "UTF-8")
                if ("=" in part && SECRET_PARAM.containsMatchIn(name)) { count++; part.substringBefore("=") + "=REDACTED" } else part
            }
            val base = "${uri.scheme}://${uri.rawAuthority}${uri.rawPath ?: ""}"
            (if (query != null) "$base?$query" else base) to count
        }.getOrDefault("" to 1)

        private fun hostOf(url: String) = runCatching { URI(url).host }.getOrNull() ?: "sivun"
    }
}
