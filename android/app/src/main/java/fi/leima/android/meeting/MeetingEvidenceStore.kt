package fi.leima.android.meeting

import java.io.File
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.PublicKey
import java.util.Base64
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import org.json.JSONObject

/**
 * Builds the meeting-proof v2 package: writes `session.json` (and `pairing.json`, already on
 * disk if the caller wrote one), computes a SHA-256 manifest over every content file, signs the
 * manifest, and zips the session directory atomically (write to a `.partial` file, then rename —
 * plan section 8's write order).
 *
 * `signature.json` signs `manifest.json`'s exact bytes with `messageType = "manifest"` via
 * [MeetingCrypto] (android/docs/meeting_v2_schema.md section 4) using the session's
 * [MeetingKeyStore] key — solo and paired sessions are signed the same way; only the presence of
 * `pairing.json` and its `messages` distinguishes a witnessed meeting from a solo capture.
 */
object MeetingEvidenceStore {
    const val SCHEMA_VERSION = 2
    const val ZIP_NAME = "meeting-session.zip"
    private val RESERVED_NAMES = setOf("manifest.json", "manifest.sha256", "signature.json", ZIP_NAME, "$ZIP_NAME.partial")

    /**
     * `session` is the caller-built session.json content; this function adds `schemaVersion` and
     * `kind` and writes it into `sessionDirectory`. Every other file already present in
     * `sessionDirectory` (events.jsonl, sensors JSONL logs, captures, pairing.json) is treated as
     * package content and included in the manifest. Returns the finished, immutable ZIP file.
     */
    fun finalizeSession(sessionDirectory: File, session: JSONObject, privateKey: PrivateKey, publicKey: PublicKey): File {
        session.put("schemaVersion", SCHEMA_VERSION).put("kind", "meeting_session")
        File(sessionDirectory, "session.json").writeText(session.toString(2), Charsets.UTF_8)

        val contentFiles = collectContentFiles(sessionDirectory)
        val manifestFiles = JSONObject()
        contentFiles.forEach { file -> manifestFiles.put(relativePath(sessionDirectory, file), sha256Hex(file)) }
        val manifest = JSONObject().put("schemaVersion", SCHEMA_VERSION).put("algorithm", "SHA-256").put("files", manifestFiles)
        val manifestFile = File(sessionDirectory, "manifest.json").apply { writeText(manifest.toString(2), Charsets.UTF_8) }
        File(sessionDirectory, "manifest.sha256").writeText("${sha256Hex(manifestFile)}  manifest.json\n", Charsets.UTF_8)

        val signature = MeetingCrypto.sign(privateKey, "manifest", manifestFile.readBytes())
        val signatureJson = JSONObject().put("algorithm", "SHA256withECDSA").put("curve", "P-256")
            .put("publicKeySpkiDerBase64", Base64.getEncoder().encodeToString(publicKey.encoded))
            .put("signatureBase64Der", Base64.getEncoder().encodeToString(signature))
        val signatureFile = File(sessionDirectory, "signature.json").apply { writeText(signatureJson.toString(2), Charsets.UTF_8) }

        val allFiles = (contentFiles + manifestFile + File(sessionDirectory, "manifest.sha256") + signatureFile)
            .sortedBy { relativePath(sessionDirectory, it) }
        val partial = File(sessionDirectory, "$ZIP_NAME.partial")
        ZipOutputStream(partial.outputStream()).use { zip ->
            allFiles.forEach { file ->
                zip.putNextEntry(ZipEntry(relativePath(sessionDirectory, file)))
                file.inputStream().use { it.copyTo(zip) }
                zip.closeEntry()
            }
        }
        val finished = File(sessionDirectory, ZIP_NAME)
        check(partial.renameTo(finished)) { "could not finalize ${finished.name}" }
        return finished
    }

    private fun collectContentFiles(sessionDirectory: File): List<File> =
        sessionDirectory.walkTopDown().filter { it.isFile }.filterNot { it.name in RESERVED_NAMES }.toList()

    private fun relativePath(root: File, file: File): String = file.relativeTo(root).path.replace(File.separatorChar, '/')

    private fun sha256Hex(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(8192)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
