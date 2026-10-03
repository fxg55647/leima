package fi.leima.android.bridge

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/**
 * Origins where the person has logged in (or taken control) on the phone. Under [ExportPolicy.AUTO]
 * their pages are local-only. Persisted because the WebView's cookies outlive a browser session;
 * only the person clears it (together with the cookies), never the agent.
 */
class PrivateOriginStore(private val file: File) {
    private var origins: MutableSet<String> = load()

    @Synchronized fun contains(origin: String): Boolean = origin.isNotEmpty() && origin in origins

    @Synchronized fun add(origin: String) {
        if (origin.isEmpty() || !origins.add(origin)) return
        save()
    }

    @Synchronized fun all(): Set<String> = origins.toSet()

    @Synchronized fun clear() {
        origins.clear()
        file.delete()
    }

    private fun load(): MutableSet<String> = runCatching {
        val list = JSONObject(file.readText(Charsets.UTF_8)).getJSONArray("origins")
        (0 until list.length()).map { list.getString(it) }.toMutableSet()
    }.getOrDefault(mutableSetOf())

    private fun save() {
        file.parentFile?.mkdirs()
        val partial = File(file.parentFile, "${file.name}.partial")
        partial.writeText(JSONObject().put("schemaVersion", 1).put("origins", JSONArray(origins.sorted())).toString(2), Charsets.UTF_8)
        Files.move(partial.toPath(), file.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
    }
}
