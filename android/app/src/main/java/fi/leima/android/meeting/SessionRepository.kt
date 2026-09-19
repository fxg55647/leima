package fi.leima.android.meeting

import java.io.File
import java.util.UUID

data class SessionSummary(val sessionId: String, val directory: File, val isFinalized: Boolean, val lastModified: Long)

/**
 * Manages meeting-session directories under one root (in production,
 * `Context.filesDir/meeting-sessions`). Takes a plain [File] rather than a `Context` so this
 * stays a plain-JVM-testable class; the `Context`-to-root mapping lives in the caller.
 *
 * Covers plan section 3.4: "Sovellukseen lisätään valmiiden istuntojen lista, uudelleenvienti ja
 * käyttäjän tekemä poisto."
 */
class SessionRepository(private val root: File) {
    fun newSessionDirectory(sessionId: String = UUID.randomUUID().toString()): File = File(root, sessionId).apply { mkdirs() }

    fun list(): List<SessionSummary> =
        (root.listFiles()?.filter { it.isDirectory } ?: emptyList()).map { dir ->
            SessionSummary(
                sessionId = dir.name,
                directory = dir,
                isFinalized = File(dir, MeetingEvidenceStore.ZIP_NAME).isFile,
                lastModified = dir.walkTopDown().filter { it.isFile }.maxOfOrNull { it.lastModified() } ?: dir.lastModified(),
            )
        }.sortedByDescending { it.lastModified }

    /** The finished ZIP for re-export, or null if the session is unfinished or unknown. */
    fun zipFile(sessionId: String): File? = File(File(root, sessionId), MeetingEvidenceStore.ZIP_NAME).takeIf { it.isFile }

    fun delete(sessionId: String): Boolean = File(root, sessionId).deleteRecursively()
}
