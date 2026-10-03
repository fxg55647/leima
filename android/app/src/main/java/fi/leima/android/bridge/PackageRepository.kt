package fi.leima.android.bridge

import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile
import java.security.MessageDigest
import java.util.zip.ZipFile

data class StoredPackage(val packageId: String, val kind: String, val file: File, val size: Long, val createdAt: Long)

class PackageChangedException : Exception("Package bytes no longer match the given sha256")

/**
 * Finished evidence packages on the phone, for transfer to the PC (docs/RESEARCH_APPLIANCE_PACKAGES.md).
 * Only finished ZIPs are listed; `.partial` files and unfinished meeting sessions never are.
 * Takes the app's files directory as a plain [File] so it stays plain-JVM-testable.
 */
class PackageRepository(filesDir: File) {
    private data class Root(val prefix: String, val directory: File, val zipName: String)

    private val roots = listOf(
        Root("evidence", File(filesDir, "evidence"), "evidence.zip"),
        Root("meeting", File(filesDir, "meeting-sessions"), "meeting-session.zip"),
    )
    private val hashCache = HashMap<String, Pair<Long, String>>()

    fun list(): List<StoredPackage> = roots.flatMap { root ->
        (root.directory.listFiles() ?: emptyArray()).filter { it.isDirectory && SAFE_NAME.matches(it.name) }.mapNotNull { dir ->
            File(dir, root.zipName).takeIf { it.isFile }?.let { zip ->
                StoredPackage("${root.prefix}:${dir.name}", kindOf(zip), zip, zip.length(), zip.lastModified())
            }
        }
    }.sortedBy { it.createdAt }

    /** Resolves only ids of the form `<root>:<directory>` that point at a finished package. */
    fun find(packageId: String): StoredPackage? {
        val (prefix, name) = packageId.split(":", limit = 2).takeIf { it.size == 2 } ?: return null
        val root = roots.firstOrNull { it.prefix == prefix } ?: return null
        if (!SAFE_NAME.matches(name)) return null
        val zip = File(File(root.directory, name), root.zipName).takeIf { it.isFile } ?: return null
        return StoredPackage(packageId, kindOf(zip), zip, zip.length(), zip.lastModified())
    }

    @Synchronized fun sha256(pkg: StoredPackage): String {
        val stamp = pkg.file.lastModified() xor pkg.file.length()
        hashCache[pkg.file.path]?.let { (cachedStamp, hash) -> if (cachedStamp == stamp) return hash }
        val digest = MessageDigest.getInstance("SHA-256")
        pkg.file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) { val n = input.read(buffer); if (n < 0) break; digest.update(buffer, 0, n) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }.also { hashCache[pkg.file.path] = stamp to it }
    }

    fun read(pkg: StoredPackage, offset: Long, length: Int): ByteArray {
        require(offset >= 0 && length in 1..MAX_READ_BYTES) { "offset must be >= 0 and length 1..$MAX_READ_BYTES" }
        RandomAccessFile(pkg.file, "r").use { file ->
            if (offset >= file.length()) return ByteArray(0)
            val bytes = ByteArray(minOf(length.toLong(), file.length() - offset).toInt())
            file.seek(offset)
            file.readFully(bytes)
            return bytes
        }
    }

    /** Deletes the package's whole directory, but only if its bytes still hash to [expectedSha256]. */
    @Synchronized fun delete(pkg: StoredPackage, expectedSha256: String) {
        hashCache.remove(pkg.file.path)
        if (sha256(pkg) != expectedSha256.lowercase()) throw PackageChangedException()
        hashCache.remove(pkg.file.path)
        check(pkg.file.parentFile!!.deleteRecursively()) { "Could not delete ${pkg.packageId}" }
    }

    private fun kindOf(zip: File): String = runCatching {
        ZipFile(zip).use { archive ->
            val names = archive.entries().asSequence().map { it.name }.toSet()
            val manifest = archive.getEntry("manifest.json")?.let { entry ->
                JSONObject(archive.getInputStream(entry).readBytes().toString(Charsets.UTF_8))
            }
            manifest?.optString("kind").takeUnless { it.isNullOrEmpty() } ?: when {
                "signature.json" in names -> "meeting"
                "photo.jpg" in names -> "photo"
                "screenshot.png" in names -> "screenshot"
                else -> "unknown"
            }
        }
    }.getOrDefault("unknown")

    companion object {
        const val MAX_READ_BYTES = 256 * 1024
        private val SAFE_NAME = Regex("^[A-Za-z0-9-]{1,64}$")
    }
}
