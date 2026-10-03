package fi.leima.android.bridge

import java.time.Instant
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import kotlin.concurrent.thread

class HandoffTest {
    @get:Rule val tmp = TemporaryFolder()

    private class Host : BrowserHost {
        val commands = mutableListOf<String>()
        override fun state() = PageState("https://bank.example/login", "Login", false, 1, false)
        override fun navigate(url: String, timeoutMs: Long) = state()
        override fun back(timeoutMs: Long): PageState? = null
        override fun settle(timeoutMs: Long) = state()
        override fun pageCommand(command: String, args: JSONObject, timeoutMs: Long): JSONObject {
            commands += command
            return JSONObject().put("url", "https://bank.example/login").put("title", "Login").put("ready_state", "complete")
                .put("visible_text", "Log in").put("elements", JSONArray()).put("limitations", JSONArray())
                .put("human_action_hints", JSONArray().put(JSONObject().put("code", "LOGIN_FORM")))
        }
        override fun screenshot(masks: List<MaskRect>, cssWidth: Double) = Screenshot(ByteArray(1), 1, 1)
        override fun certificate(): JSONObject? = null
        override fun environment() = JSONObject()
    }

    private val host = Host()
    private var now = Instant.parse("2026-10-04T10:00:00Z")
    private val changes = mutableListOf<ControlState>()
    private fun controller() = BrowserController(host, tmp.newFolder(), clock = { now }, onControlChanged = { changes += it.state })

    private fun code(block: () -> Unit): String = try { block(); "none" } catch (e: ProtocolError) { e.code }
    private fun request(c: BrowserController, id: String = "h1") = c.requestHuman(
        JSONObject().put("reason", "LOGIN").put("task", "Kirjaudu pankkiin").put("request_id", id))
        .getJSONObject("handoff").getString("handoff_id")

    @Test
    fun handoffBlocksAgentUntilPhoneConfirmsThenResumesWithFreshObservation() {
        val c = controller()
        assertEquals("LOGIN_FORM", c.observe().getJSONArray("human_action_hints").getJSONObject(0).getString("code"))
        val id = request(c)
        assertEquals(ControlState.HUMAN_ACTION_REQUIRED, c.snapshot().state)
        val before = host.commands.size
        assertEquals("HUMAN_ACTION_PENDING", code { c.observe() })
        assertEquals("HUMAN_ACTION_PENDING", code { c.screenshot() })
        assertEquals("HUMAN_ACTION_PENDING", code { c.navigate(JSONObject().put("url", "https://x.org").put("request_id", "n1")) })
        assertEquals("HUMAN_ACTION_PENDING", code { c.capture(JSONObject().put("request_id", "c1")) })
        assertEquals(before, host.commands.size) // nothing reached the page during the handoff
        assertEquals("HUMAN_NOT_DONE", code { c.resume(JSONObject().put("handoff_id", id)) })

        c.personContinue()
        assertEquals("HUMAN_ACTION_PENDING", code { c.observe() }) // still needs an explicit resume
        val resumed = c.resume(JSONObject().put("handoff_id", id))
        assertEquals("READY", resumed.getString("state"))
        assertEquals(c.sessionId, resumed.getJSONObject("observation").getString("session_id"))
        assertEquals(ControlState.READY, c.snapshot().state)
        // repeating the resume after a USB drop is harmless
        assertEquals("READY", c.resume(JSONObject().put("handoff_id", id)).getString("state"))
        assertEquals("NO_HANDOFF", code { c.resume(JSONObject().put("handoff_id", "ho_other")) })
        assertTrue(ControlState.HUMAN_ACTION_REQUIRED in changes)
    }

    @Test
    fun resumeWaitsForJatkaFromAnotherThread() {
        val c = controller()
        val id = request(c)
        val presser = thread { Thread.sleep(300); c.personContinue() }
        val started = System.nanoTime()
        assertEquals("READY", c.resume(JSONObject().put("handoff_id", id).put("wait_s", 10)).getString("state"))
        assertTrue((System.nanoTime() - started) / 1_000_000 < 5_000)
        presser.join()
    }

    @Test
    fun cancelStopsTheAgentUntilThePersonAllowsAgain() {
        val c = controller()
        val firstSession = c.sessionId
        val id = request(c)
        c.personCancel()
        assertEquals(ControlState.CANCELLED, c.snapshot().state)
        assertEquals("SESSION_CANCELLED", code { c.resume(JSONObject().put("handoff_id", id)) })
        assertEquals("SESSION_CANCELLED", code { c.observe() })
        assertEquals("SESSION_CANCELLED", code { c.requestHuman(JSONObject().put("reason", "OTHER").put("request_id", "h2")) })
        c.personAllowAgain()
        assertEquals(ControlState.READY, c.snapshot().state)
        assertNotEquals(firstSession, c.sessionId)
        assertEquals(c.sessionId, c.observe().getString("session_id"))
    }

    @Test
    fun unansweredHandoffExpires() {
        val c = controller()
        val id = c.requestHuman(JSONObject().put("reason", "CAPTCHA").put("timeout_s", 60).put("request_id", "h1"))
            .getJSONObject("handoff").getString("handoff_id")
        now = now.plusSeconds(61)
        assertEquals("HANDOFF_EXPIRED", code { c.observe() })
        assertEquals("HANDOFF_EXPIRED", code { c.resume(JSONObject().put("handoff_id", id)) })
        assertEquals(ControlState.EXPIRED, c.snapshot().state)
        assertTrue(ControlState.EXPIRED in changes)
    }

    @Test
    fun personCanTakeControlAnyTimeAndAgentMustResume() {
        val c = controller()
        c.observe()
        c.personTakeControl()
        val handoff = c.snapshot().handoff!!
        assertEquals("person", handoff.requestedBy)
        assertEquals("HUMAN_ACTION_PENDING", code { c.observe() })
        val status = c.status()
        assertEquals("HUMAN_ACTION_REQUIRED", status.getString("control"))
        assertEquals(handoff.id, status.getJSONObject("handoff").getString("handoff_id"))
        c.personContinue()
        assertEquals("READY", c.resume(JSONObject().put("handoff_id", handoff.id)).getString("state"))
    }

    @Test
    fun requestValidationAndEndSession() {
        val c = controller()
        assertEquals("BAD_REQUEST", code { c.requestHuman(JSONObject().put("reason", "PAY").put("request_id", "a")) })
        assertEquals("BAD_REQUEST", code { c.requestHuman(JSONObject().put("reason", "OTHER").put("task", "x".repeat(301)).put("request_id", "b")) })
        assertEquals("BAD_REQUEST", code { c.requestHuman(JSONObject().put("reason", "OTHER").put("timeout_s", 5).put("request_id", "c")) })
        val id = request(c, "d")
        assertEquals("HUMAN_ACTION_PENDING", code { request(c, "e") })
        val old = c.sessionId
        val ended = c.endSession()
        assertEquals(old, ended.getString("ended_session_id"))
        assertNotEquals(old, c.sessionId)
        // ending the session never ends the person's control
        assertEquals(ControlState.HUMAN_ACTION_REQUIRED, c.snapshot().state)
        assertEquals("HUMAN_ACTION_PENDING", code { c.observe() })
        assertEquals("HUMAN_ACTION_PENDING", code { c.navigate(JSONObject().put("url", "https://x.org").put("request_id", "f")) })
        c.personContinue()
        assertEquals("READY", c.resume(JSONObject().put("handoff_id", id)).getString("state"))
    }

    @Test
    fun endingTheSessionDoesNotUndoAStop() {
        val c = controller()
        request(c)
        c.personCancel()
        c.endSession()
        assertEquals(ControlState.CANCELLED, c.snapshot().state)
        assertEquals("SESSION_CANCELLED", code { c.observe() })
    }
}
