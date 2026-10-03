package fi.leima.android.bridge

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI

/**
 * What page content may leave the phone towards the agent (docs/RESEARCH_APPLIANCE_ARCHITECTURE.md
 * section 6). Chosen by the person on the phone, never by the agent.
 *
 * - [AUTO]: local-only on origins where the person has logged in or taken control on the phone
 *   ([PrivateOriginStore]), agent-readable elsewhere. Pages behind a login are likely private.
 * - [AGENT_READABLE]: page text, element names and screenshots go to the MCP client.
 * - [LOCAL_ONLY]: only structure, the URL's origin, hashes and package metadata leave the phone.
 */
enum class ExportPolicy { AUTO, AGENT_READABLE, LOCAL_ONLY }

/** Applies the effective policy to every browser result before it is sent to the bridge. */
object ExportFilter {
    /** Keys whose values are page content; dropped under LOCAL_ONLY. */
    private val CONTENT_KEYS = listOf("visible_text", "title")
    private val ELEMENT_CONTENT_KEYS = listOf("name", "value", "href")
    /** Nested results that are themselves browser results (browser.resume, command_status). */
    private val NESTED = listOf("observation", "result")

    /** Returns a filtered copy; [localOnly] is the effective policy. */
    fun apply(result: JSONObject, localOnly: Boolean): JSONObject {
        val out = JSONObject(result.toString())
        val redacted = filter(out, localOnly)
        out.put("export_policy", if (localOnly) "LOCAL_ONLY" else "AGENT_READABLE")
        if (redacted > 0) out.put("secrets_redacted", redacted)
        return out
    }

    private fun filter(obj: JSONObject, localOnly: Boolean): Int {
        var redacted = 0
        (obj.opt("url") as? String)?.let { url ->
            val (clean, count) = BrowserController.redactUrl(url)
            redacted += count
            obj.put("url", if (localOnly) originOf(url) else clean)
        }
        if (localOnly) {
            if (CONTENT_KEYS.any { obj.has(it) }) obj.put("content_withheld", true)
            CONTENT_KEYS.forEach { obj.remove(it) }
        } else {
            (obj.opt("visible_text") as? String)?.let { text ->
                val (clean, count) = SecretScrubber.scrub(text)
                redacted += count
                obj.put("visible_text", clean)
            }
        }
        (obj.opt("elements") as? JSONArray)?.let { elements ->
            for (i in 0 until elements.length()) {
                val element = elements.optJSONObject(i) ?: continue
                if (localOnly) {
                    ELEMENT_CONTENT_KEYS.forEach { element.remove(it) }
                } else {
                    (element.opt("href") as? String)?.let { href ->
                        val (clean, count) = BrowserController.redactUrl(href)
                        redacted += count
                        element.put("href", clean)
                    }
                    listOf("name", "value").forEach { key ->
                        (element.opt(key) as? String)?.let { text ->
                            val (clean, count) = SecretScrubber.scrub(text)
                            redacted += count
                            element.put(key, clean)
                        }
                    }
                }
            }
        }
        NESTED.forEach { key -> (obj.opt(key) as? JSONObject)?.let { redacted += filter(it, localOnly) } }
        return redacted
    }

    fun originOf(url: String): String = runCatching {
        val uri = URI(url)
        if (uri.scheme == null || uri.host == null) "" else "${uri.scheme}://${uri.host}${if (uri.port >= 0) ":${uri.port}" else ""}"
    }.getOrDefault("")
}

/**
 * Removes recognisable credentials from text sent to the agent. Pattern-based: it catches common
 * token formats, not every secret a page can show.
 */
object SecretScrubber {
    private val PATTERNS = listOf(
        "PRIVATE_KEY" to Regex("-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "JWT" to Regex("\\beyJ[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}"),
        "BEARER" to Regex("(?i)\\bbearer\\s+[A-Za-z0-9._~+/=-]{16,}"),
        "API_KEY" to Regex("\\b(?:sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})"),
        "AWS_KEY" to Regex("\\b(?:AKIA|ASIA)[0-9A-Z]{16}\\b"),
    )

    fun scrub(text: String): Pair<String, Int> {
        var count = 0
        var out = text
        PATTERNS.forEach { (kind, regex) ->
            out = regex.replace(out) { count++; "[REDACTED:$kind]" }
        }
        return out to count
    }
}
