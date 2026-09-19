package fi.leima.android

import android.content.Context
import android.os.Build
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class EvidenceStore(private val context: Context) {
    fun newDirectory(): File = File(context.filesDir, "evidence/${UUID.randomUUID()}").apply { mkdirs() }

    fun prepareMetadata(metadata: JSONObject): JSONObject =
        metadata.put("schemaVersion", 1).put("appVersion", BuildConfig.VERSION_NAME)
            .put("device", JSONObject().put("manufacturer", Build.MANUFACTURER)
                .put("model", Build.MODEL).put("androidApi", Build.VERSION.SDK_INT)
                .put("androidRelease", Build.VERSION.RELEASE))
            .put("trust", "Local unsigned capture; device clocks and sensors are not independently verified")

    fun finish(directory: File, media: File, metadata: JSONObject): File {
        prepareMetadata(metadata)
        val details = File(directory, "metadata.json").apply { writeText(metadata.toString(2), Charsets.UTF_8) }
        val manifest = File(directory, "manifest.json").apply {
            writeText(JSONObject().put("schemaVersion", 1).put("algorithm", "SHA-256")
                .put("files", JSONObject().put(media.name, sha256(media)).put(details.name, sha256(details)))
                .toString(2), Charsets.UTF_8)
        }
        val checksum = File(directory, "manifest.sha256").apply {
            writeText("${sha256(manifest)}  manifest.json\n", Charsets.UTF_8)
        }
        val temporary = File(directory, "evidence.zip.partial")
        ZipOutputStream(temporary.outputStream()).use { zip ->
            listOf(media, details, manifest, checksum).forEach { file ->
                zip.putNextEntry(ZipEntry(file.name))
                file.inputStream().use { it.copyTo(zip) }
                zip.closeEntry()
            }
        }
        return File(directory, "evidence.zip").also { check(temporary.renameTo(it)) }
    }
    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(8192)
            while (true) { val count = input.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
