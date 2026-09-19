package fi.leima.android.meeting

import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class JsonlAppenderTest {
    @get:Rule val tmp = TemporaryFolder()

    @Test
    fun writesLinesInOrderAndClosesCleanly() {
        val file = File(tmp.newFolder(), "events.jsonl")
        val appender = JsonlAppender(file, capacity = 4096)
        repeat(50) { i -> assertTrue(appender.offer(JSONObject().put("i", i))) }
        appender.close()
        val lines = file.readLines()
        assertEquals(50, lines.size)
        lines.forEachIndexed { index, line -> assertEquals(index, JSONObject(line).getInt("i")) }
        assertEquals(0, appender.droppedCount)
    }

    @Test
    fun overflowDropsInsteadOfGrowingUnbounded() {
        val file = File(File(tmp.newFolder(), "sensors"), "imu.jsonl")
        // A writer thread that never gets scheduled would still bound memory: capacity 1, never drained.
        val appender = JsonlAppender(file, capacity = 1)
        var accepted = 0
        repeat(1000) { i -> if (appender.offer(JSONObject().put("i", i))) accepted++ }
        appender.close()
        assertTrue("expected some drops under a tiny queue", appender.droppedCount > 0)
        assertEquals(1000L, accepted + appender.droppedCount)
    }

    @Test
    fun offerAfterCloseIsRejected() {
        val file = File(tmp.newFolder(), "events.jsonl")
        val appender = JsonlAppender(file)
        appender.close()
        assertTrue(!appender.offer(JSONObject().put("late", true)))
    }
}
