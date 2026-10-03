package fi.leima.android.bridge

import fi.leima.android.meeting.MeetingEvidenceStore
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.spec.ECGenParameterSpec
import java.util.Base64
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class PackageTransferTest {
    @get:Rule val tmp = TemporaryFolder()

    private val bridgeId = "b_" + "0123456789abcdef".repeat(2)

    private fun zip(entries: Map<String, ByteArray>): ByteArray = ByteArrayOutputStream().also { out ->
        ZipOutputStream(out).use { z -> entries.forEach { (name, data) -> z.putNextEntry(ZipEntry(name)); z.write(data); z.closeEntry() } }
    }.toByteArray()

    private fun sha256(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    private fun photoPackage(filesDir: File, dir: String, payload: ByteArray = ByteArray(700_000).also { java.util.Random(1).nextBytes(it) }): File =
        File(filesDir, "evidence/$dir").apply { mkdirs() }.let { d ->
            File(d, "evidence.zip").apply { writeBytes(zip(mapOf("photo.jpg" to payload, "manifest.json" to "{}".toByteArray()))) }
        }

    /** An authenticated connection with package access. */
    private fun connection(filesDir: File, changed: MutableList<Unit> = mutableListOf()): BridgeConnection {
        val store = PairingStore(File(filesDir, "bridge/pairings.json"))
        val c = BridgeConnection(store, { _, _, _ -> PairingDecision.APPROVED }, { JSONObject() }, "0.1.0",
            packages = PackageRepository(filesDir), onPackagesChanged = { changed += Unit })
        c.call(1, "hello", JSONObject().put("protocol_versions", listOf(1)).put("bridge_id", bridgeId).put("bridge_name", "PC"))
        val token = c.call(2, "pair_begin", JSONObject().put("code", "123456")).getJSONObject("result").getString("token")
        c.call(3, "auth", JSONObject().put("token", token))
        return c
    }

    private fun BridgeConnection.call(id: Int, method: String, params: JSONObject = JSONObject()): JSONObject =
        JSONObject(handle(JSONObject().put("id", id).put("method", method).put("params", params).toString()))

    private fun JSONObject.errorCode(): String? = optJSONObject("error")?.optString("code")

    @Test
    fun listsReadsInChunksAndDeletesAfterHashCheck() {
        val filesDir = tmp.newFolder()
        val zipFile = photoPackage(filesDir, "11111111-aaaa")
        File(filesDir, "evidence/22222222-bbbb").mkdirs()
        File(filesDir, "evidence/22222222-bbbb/evidence.zip.partial").writeBytes(ByteArray(10))
        val changed = mutableListOf<Unit>()
        val c = connection(filesDir, changed)

        assertTrue(c.call(4, "device_status").getJSONObject("result").getJSONArray("capabilities").toString().contains("packages.delete"))
        val list = c.call(5, "packages.list").getJSONObject("result").getJSONArray("packages")
        assertEquals(1, list.length())
        val entry = list.getJSONObject(0)
        assertEquals("evidence:11111111-aaaa", entry.getString("package_id"))
        assertEquals("photo", entry.getString("kind"))
        assertEquals(zipFile.length(), entry.getLong("size"))
        assertEquals(sha256(zipFile.readBytes()), entry.getString("sha256"))

        val received = ByteArrayOutputStream()
        var offset = 0L
        var id = 6
        while (true) {
            val chunk = c.call(id++, "packages.read", JSONObject().put("package_id", entry.getString("package_id"))
                .put("offset", offset).put("length", PackageRepository.MAX_READ_BYTES)).getJSONObject("result")
            val bytes = Base64.getDecoder().decode(chunk.getString("data_base64"))
            received.write(bytes)
            offset += bytes.size
            if (chunk.getBoolean("eof")) break
        }
        assertTrue(id > 8) // more than one chunk
        assertArrayEquals(zipFile.readBytes(), received.toByteArray())

        assertEquals("PACKAGE_CHANGED", c.call(20, "packages.delete", JSONObject().put("package_id", entry.getString("package_id"))
            .put("sha256", "0".repeat(64))).errorCode())
        assertTrue(zipFile.isFile)
        assertTrue(c.call(21, "packages.delete", JSONObject().put("package_id", entry.getString("package_id"))
            .put("sha256", entry.getString("sha256"))).getJSONObject("result").getBoolean("deleted"))
        assertFalse(zipFile.parentFile!!.exists())
        assertEquals(1, changed.size)
        assertEquals("PACKAGE_NOT_FOUND", c.call(22, "packages.read", JSONObject().put("package_id", entry.getString("package_id"))
            .put("offset", 0).put("length", 10)).errorCode())
    }

    @Test
    fun deleteRefusesWhenBytesChangedAfterListing() {
        val filesDir = tmp.newFolder()
        val zipFile = photoPackage(filesDir, "33333333-cccc", payload = "a".toByteArray())
        val c = connection(filesDir)
        val sha = c.call(4, "packages.list").getJSONObject("result").getJSONArray("packages").getJSONObject(0).getString("sha256")
        zipFile.writeBytes(zip(mapOf("photo.jpg" to "b".toByteArray(), "manifest.json" to "{}".toByteArray())))
        zipFile.setLastModified(zipFile.lastModified() + 5_000)
        assertEquals("PACKAGE_CHANGED", c.call(5, "packages.delete", JSONObject().put("package_id", "evidence:33333333-cccc")
            .put("sha256", sha)).errorCode())
        assertTrue(zipFile.isFile)
    }

    @Test
    fun listsMeetingPackagesWithKindFromManifest() {
        val filesDir = tmp.newFolder()
        val keyPair = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        val dir = File(filesDir, "meeting-sessions/0b2b0b8f-1a4b").apply { mkdirs() }
        MeetingEvidenceStore.finalizeSession(dir, JSONObject().put("sessionId", "0b2b0b8f-1a4b"), keyPair.private, keyPair.public)
        File(filesDir, "meeting-sessions/unfinished-1").mkdirs()
        val list = connection(filesDir).call(4, "packages.list").getJSONObject("result").getJSONArray("packages")
        assertEquals(1, list.length())
        assertEquals("meeting:0b2b0b8f-1a4b", list.getJSONObject(0).getString("package_id"))
        assertEquals("meeting", list.getJSONObject(0).getString("kind"))
    }

    @Test
    fun rejectsIdsOutsideThePackageRoots() {
        val filesDir = tmp.newFolder()
        photoPackage(filesDir, "44444444-dddd")
        File(filesDir, "secret").apply { mkdirs(); File(this, "evidence.zip").writeText("x") }
        val c = connection(filesDir)
        for ((i, id) in listOf("evidence:../secret", "evidence:", "bridge:x", "evidence:44444444-dddd/../../secret", "nocolon").withIndex()) {
            assertEquals(id, "PACKAGE_NOT_FOUND", c.call(10 + i, "packages.read", JSONObject().put("package_id", id)
                .put("offset", 0).put("length", 10)).errorCode())
        }
        assertEquals("BAD_REQUEST", c.call(20, "packages.read", JSONObject().put("package_id", "evidence:44444444-dddd")
            .put("offset", 0).put("length", PackageRepository.MAX_READ_BYTES + 1)).errorCode())
    }

    @Test
    fun packageMethodsNeedAuthentication() {
        val filesDir = tmp.newFolder()
        val c = BridgeConnection(PairingStore(File(filesDir, "p.json")), { _, _, _ -> PairingDecision.REJECTED }, { JSONObject() }, "0.1.0",
            packages = PackageRepository(filesDir))
        c.call(1, "hello", JSONObject().put("protocol_versions", listOf(1)).put("bridge_id", bridgeId).put("bridge_name", "PC"))
        assertEquals("NOT_AUTHENTICATED", c.call(2, "packages.list").errorCode())
    }
}
