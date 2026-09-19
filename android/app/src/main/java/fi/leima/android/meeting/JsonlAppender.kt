package fi.leima.android.meeting

import java.io.File
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import org.json.JSONObject

/**
 * Bounded-queue background writer for one JSONL file (plan section 5: samples are copied into a
 * bounded queue on the caller's thread; a separate writer thread appends them to disk, so a
 * session never accumulates unbounded memory over its duration).
 *
 * [offer] never blocks: when the queue is full the line is dropped and counted in
 * [droppedCount] rather than backing up the caller (a sensor callback thread) or growing memory.
 * Plain `java.io`/`java.util.concurrent` only, so this is exercised by a JVM unit test without
 * an Android device.
 */
class JsonlAppender(file: File, capacity: Int = 4096) {
    private val queue = ArrayBlockingQueue<String>(capacity)
    private val dropped = AtomicLong(0)
    @Volatile private var acceptingWrites = true
    @Volatile private var running = true
    private val writer = file.also { it.parentFile?.mkdirs() }.bufferedWriter(Charsets.UTF_8)
    private val thread = Thread({ drainLoop() }, "jsonl-appender-${file.name}").apply { isDaemon = true; start() }

    val droppedCount: Long get() = dropped.get()

    fun offer(line: String): Boolean {
        if (!acceptingWrites) return false
        val accepted = queue.offer(line)
        if (!accepted) dropped.incrementAndGet()
        return accepted
    }

    fun offer(json: JSONObject): Boolean = offer(json.toString())

    /** Stops accepting new lines, drains what is already queued (up to [drainTimeoutMs]), then closes the file. */
    fun close(drainTimeoutMs: Long = 5_000) {
        acceptingWrites = false
        val deadline = System.currentTimeMillis() + drainTimeoutMs
        while (queue.isNotEmpty() && System.currentTimeMillis() < deadline) Thread.sleep(5)
        running = false
        thread.interrupt()
        thread.join(1_000)
        writer.flush()
        writer.close()
    }

    private fun drainLoop() {
        while (running || queue.isNotEmpty()) {
            val line = try { queue.poll(200, TimeUnit.MILLISECONDS) } catch (_: InterruptedException) { null }
            if (line != null) {
                writer.write(line)
                writer.write("\n")
                writer.flush()
            }
        }
    }
}
