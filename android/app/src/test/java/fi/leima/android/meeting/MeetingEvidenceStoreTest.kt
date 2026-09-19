package fi.leima.android.meeting

import java.io.File
import java.security.MessageDigest
import java.util.zip.ZipFile
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class MeetingEvidenceStoreTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @Test
    fun buildsManifestAndZipCoveringAllContentFiles() {
        val dir = tmp.newFolder()
        File(dir, "events.jsonl").writeText("{\"type\":\"session_created\"}\n")
        File(dir, "sensors").mkdirs()
        File(dir, "sensors/imu.jsonl").writeText("{\"type\":\"accel\"}\n")
        File(dir, "captures").mkdirs()
        val photoBytes = byteArrayOf(1, 2, 3, 4, 5)
        File(dir, "captures/000001.jpg").writeBytes(photoBytes)
        File(dir, "captures/000001.json").writeText("{\"captureId\":\"c-1\"}")

        val session = JSONObject().put("sessionId", "s-1").put("role", "photographer")
        val zip = MeetingEvidenceStore.finalizeSession(dir, session)

        assertEquals("meeting-session.zip", zip.name)
        assertFalse(File(dir, "meeting-session.zip.partial").exists())

        val sessionJson = JSONObject(File(dir, "session.json").readText())
        assertEquals(2, sessionJson.getInt("schemaVersion"))
        assertEquals("meeting_session", sessionJson.getString("kind"))
        assertEquals("s-1", sessionJson.getString("sessionId"))

        val manifest = JSONObject(File(dir, "manifest.json").readText())
        val files = manifest.getJSONObject("files")
        assertEquals(sha256Hex(photoBytes), files.getString("captures/000001.jpg"))
        assertTrue(files.has("session.json"))
        assertTrue(files.has("events.jsonl"))
        assertTrue(files.has("sensors/imu.jsonl"))
        assertTrue(files.has("captures/000001.json"))
        // Manifest never lists itself or the checksum/zip control files.
        assertFalse(files.has("manifest.json"))
        assertFalse(files.has("manifest.sha256"))
        assertFalse(files.has("meeting-session.zip"))

        val checksumLine = File(dir, "manifest.sha256").readText().trim()
        assertTrue(checksumLine.endsWith("  manifest.json"))
        assertEquals(sha256Hex(File(dir, "manifest.json").readBytes()), checksumLine.substringBefore("  "))

        ZipFile(zip).use { archive ->
            val names = archive.entries().asSequence().map { it.name }.toSet()
            assertEquals(setOf("session.json", "events.jsonl", "sensors/imu.jsonl", "captures/000001.jpg", "captures/000001.json", "manifest.json", "manifest.sha256"), names)
        }
    }

    @Test
    fun tamperingAfterFinalizeIsDetectableViaManifestHash() {
        val dir = tmp.newFolder()
        File(dir, "captures").mkdirs()
        File(dir, "captures/000001.jpg").writeBytes(byteArrayOf(9, 9, 9))
        MeetingEvidenceStore.finalizeSession(dir, JSONObject().put("sessionId", "s-2"))

        val manifest = JSONObject(File(dir, "manifest.json").readText())
        val recordedHash = manifest.getJSONObject("files").getString("captures/000001.jpg")

        File(dir, "captures/000001.jpg").writeBytes(byteArrayOf(1, 1, 1))
        val actualHash = sha256Hex(File(dir, "captures/000001.jpg").readBytes())
        assertFalse(recordedHash == actualHash)
    }
}
