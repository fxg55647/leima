package fi.leima.android.meeting

import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class SessionJournalTest {
    @get:Rule val tmp = TemporaryFolder()

    @Test
    fun recordsEventsWithTypeAndTimestamps() {
        val dir = tmp.newFolder()
        val journal = SessionJournal(dir)
        journal.record("session_created", JSONObject().put("sessionId", "s-1"))
        journal.record("capture_saved", JSONObject().put("captureId", "c-1"))
        journal.close()

        val lines = File(dir, "events.jsonl").readLines()
        assertEquals(2, lines.size)
        val first = JSONObject(lines[0])
        assertEquals("session_created", first.getString("type"))
        assertEquals("s-1", first.getString("sessionId"))
        assertTrue(first.has("atUtc"))
        assertTrue(first.has("atElapsedRealtimeNs"))
        assertEquals("capture_saved", JSONObject(lines[1]).getString("type"))
    }

    @Test
    fun noDropsUnderNormalLoad() {
        val journal = SessionJournal(tmp.newFolder())
        repeat(500) { journal.record("tick") }
        journal.close()
        assertEquals(0L, journal.droppedEventCount)
    }
}
