package fi.leima.android.meeting

import java.io.File
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.spec.ECGenParameterSpec
import java.util.Base64
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Verifies Kotlin's [MeetingCrypto] against the same test vectors that
 * test_meeting_crypto.py checks on the Python side, proving the two
 * languages construct and verify identical signed byte sequences.
 */
class MeetingCryptoTest {
    private fun loadVectors(): JSONObject {
        val dir = System.getProperty("meetingTestVectorsDir")
            ?: error("meetingTestVectorsDir system property not set (see app/build.gradle.kts)")
        val file = File(dir, "meeting_crypto_vectors.json")
        return JSONObject(file.readText(Charsets.UTF_8))
    }

    private fun b64d(value: String): ByteArray = Base64.getDecoder().decode(value)

    @Test
    fun sharedVectorsVerify() {
        val data = loadVectors()
        assertEquals("SHA256withECDSA", data.getString("signatureAlgorithm"))
        val publicKey = MeetingCrypto.loadPublicKeyDer(b64d(data.getString("testPublicKeySpkiDerBase64")))
        val vectors = data.getJSONArray("vectors")
        assertTrue(vectors.length() >= 1)
        for (i in 0 until vectors.length()) {
            val vector = vectors.getJSONObject(i)
            val messageType = vector.getString("messageType")
            val payload = b64d(vector.getString("payloadBase64"))
            val signature = b64d(vector.getString("signatureBase64Der"))
            assertEquals(
                String(MeetingCrypto.domainSeparator(messageType), Charsets.UTF_8),
                vector.getString("domainSeparator"),
            )
            assertTrue(
                "vector '$messageType' must verify",
                MeetingCrypto.verify(publicKey, messageType, payload, signature),
            )
        }
    }

    @Test
    fun tamperedPayloadIsRejected() {
        val data = loadVectors()
        val publicKey = MeetingCrypto.loadPublicKeyDer(b64d(data.getString("testPublicKeySpkiDerBase64")))
        val vector = data.getJSONArray("vectors").getJSONObject(0)
        val payload = b64d(vector.getString("payloadBase64"))
        payload[payload.size - 1] = (payload[payload.size - 1].toInt() xor 0x01).toByte()
        val signature = b64d(vector.getString("signatureBase64Der"))
        assertFalse(MeetingCrypto.verify(publicKey, vector.getString("messageType"), payload, signature))
    }

    @Test
    fun wrongMessageTypeIsRejected() {
        val data = loadVectors()
        val publicKey = MeetingCrypto.loadPublicKeyDer(b64d(data.getString("testPublicKeySpkiDerBase64")))
        val vectors = data.getJSONArray("vectors")
        val challenge = (0 until vectors.length()).map { vectors.getJSONObject(it) }
            .first { it.getString("messageType") == "finish_challenge" }
        val response = (0 until vectors.length()).map { vectors.getJSONObject(it) }
            .first { it.getString("messageType") == "finish_response" }
        val payload = b64d(challenge.getString("payloadBase64"))
        val signature = b64d(challenge.getString("signatureBase64Der"))
        assertFalse(MeetingCrypto.verify(publicKey, response.getString("messageType"), payload, signature))
    }

    @Test
    fun roundTripWithFreshlyGeneratedKey() {
        val keyPair = KeyPairGenerator.getInstance("EC").apply {
            initialize(ECGenParameterSpec("secp256r1"))
        }.generateKeyPair()
        val payload = """{"hello":"world"}""".toByteArray(Charsets.UTF_8)
        val signature = MeetingCrypto.sign(keyPair.private, "finish_challenge", payload)
        assertTrue(MeetingCrypto.verify(keyPair.public, "finish_challenge", payload, signature))
    }

    @Test
    fun nonP256KeyIsRejected() {
        val keyPair = KeyPairGenerator.getInstance("EC").apply {
            initialize(ECGenParameterSpec("secp384r1"))
        }.generateKeyPair()
        val factory = KeyFactory.getInstance("EC")
        val der = factory.getKeySpec(keyPair.public, java.security.spec.X509EncodedKeySpec::class.java).encoded
        try {
            MeetingCrypto.loadPublicKeyDer(der)
            throw AssertionError("expected IllegalArgumentException for non-P-256 key")
        } catch (_: IllegalArgumentException) {
            // expected
        }
    }
}
