package fi.leima.android.bridge

import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest

/**
 * Paired PC bridges, keyed by `bridge_id`. Only the SHA-256 of each token is stored, so reading
 * this file does not let anyone authenticate. Takes a plain [File] so it stays plain-JVM-testable;
 * in production the file lives under `Context.filesDir`.
 */
class PairingStore(private val file: File) {
    @Synchronized fun isPaired(bridgeId: String): Boolean = load().has(bridgeId)

    @Synchronized fun count(): Int = load().length()

    /** Stores [token]'s hash for [bridgeId], replacing any earlier pairing of the same bridge. */
    @Synchronized fun pair(bridgeId: String, bridgeName: String, token: String, pairedAt: String) {
        val bridges = load()
        bridges.put(bridgeId, JSONObject().put("name", bridgeName).put("tokenSha256", sha256Hex(token)).put("pairedAt", pairedAt))
        save(bridges)
    }

    @Synchronized fun verify(bridgeId: String, token: String): Boolean {
        val expected = load().optJSONObject(bridgeId)?.optString("tokenSha256") ?: return false
        return MessageDigest.isEqual(expected.toByteArray(Charsets.US_ASCII), sha256Hex(token).toByteArray(Charsets.US_ASCII))
    }

    @Synchronized fun unpair(bridgeId: String) {
        val bridges = load()
        if (bridges.remove(bridgeId) != null) save(bridges)
    }

    @Synchronized fun clear() { file.delete() }

    private fun load(): JSONObject =
        if (file.isFile) JSONObject(file.readText(Charsets.UTF_8)).optJSONObject("bridges") ?: JSONObject() else JSONObject()

    private fun save(bridges: JSONObject) {
        file.parentFile?.mkdirs()
        val temporary = File(file.parentFile, "${file.name}.partial")
        temporary.writeText(JSONObject().put("schemaVersion", 1).put("bridges", bridges).toString(2), Charsets.UTF_8)
        Files.move(temporary.toPath(), file.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
    }

    private fun sha256Hex(value: String): String =
        MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
}
