package fi.leima.android.bridge

import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * Writes a `kind: browser` package in the shared envelope (docs/RESEARCH_APPLIANCE_PACKAGES.md):
 * content files, `manifest.json`, `manifest.sha256`, then `evidence.zip` via a `.partial` rename,
 * so an interrupted capture never looks finished to [PackageRepository].
 */
object BrowserCaptureStore {
    const val ZIP_NAME = "evidence.zip"
    private val REQUIRED = setOf("metadata.json", "observation.json", "dom.html", "visible-text.txt")
    private val OPTIONAL = setOf("screenshot.png")

    fun finish(directory: File, files: Map<String, ByteArray>): File {
        require(files.keys.containsAll(REQUIRED) && (files.keys - REQUIRED - OPTIONAL).isEmpty()) { "Unexpected capture files ${files.keys}" }
        directory.mkdirs()
        val manifestFiles = JSONObject()
        files.forEach { (name, bytes) ->
            File(directory, name).writeBytes(bytes)
            manifestFiles.put(name, sha256Hex(bytes))
        }
        val manifest = JSONObject().put("schemaVersion", 1).put("algorithm", "SHA-256").put("kind", "browser").put("files", manifestFiles)
            .toString(2).toByteArray(Charsets.UTF_8)
        val checksum = "${sha256Hex(manifest)}  manifest.json\n".toByteArray(Charsets.UTF_8)
        val partial = File(directory, "$ZIP_NAME.partial")
        ZipOutputStream(partial.outputStream()).use { zip ->
            (files + mapOf("manifest.json" to manifest, "manifest.sha256" to checksum)).forEach { (name, bytes) ->
                zip.putNextEntry(ZipEntry(name))
                zip.write(bytes)
                zip.closeEntry()
            }
        }
        val finished = File(directory, ZIP_NAME)
        Files.move(partial.toPath(), finished.toPath(), StandardCopyOption.ATOMIC_MOVE)
        return finished
    }

    fun sha256Hex(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    fun sha256Hex(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) { val n = input.read(buffer); if (n < 0) break; digest.update(buffer, 0, n) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
