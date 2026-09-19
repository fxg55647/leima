package fi.leima.android.meeting

import java.io.File
import java.time.Instant
import org.json.JSONObject

/**
 * Append-only `events.jsonl` writer. After a process death the on-disk journal is the source of
 * truth for what a session had recorded (plan section 4); every state change and capture outcome
 * that matters for resuming or exporting a session is written here as it happens, not held only
 * in memory.
 *
 * `elapsedRealtimeNanos` is injected so this class stays plain-JVM testable: production code
 * passes `SystemClock::elapsedRealtimeNanos`, tests pass `System::nanoTime`.
 */
class SessionJournal(sessionDirectory: File, private val elapsedRealtimeNanos: () -> Long = System::nanoTime) {
    private val appender = JsonlAppender(File(sessionDirectory, "events.jsonl"), capacity = 2048)

    /** Appends one event. `type` is a stable event name, e.g. "capture_saved" or "interrupted". */
    fun record(type: String, fields: JSONObject = JSONObject()): Boolean = appender.offer(
        fields.put("type", type).put("atUtc", Instant.now().toString()).put("atElapsedRealtimeNs", elapsedRealtimeNanos()),
    )

    /** Number of events dropped because the write queue was full; expected to stay 0 in practice. */
    val droppedEventCount: Long get() = appender.droppedCount

    fun close(drainTimeoutMs: Long = 5_000) = appender.close(drainTimeoutMs)
}
