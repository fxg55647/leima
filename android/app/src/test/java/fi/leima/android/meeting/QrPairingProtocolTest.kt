package fi.leima.android.meeting

import java.security.KeyPairGenerator
import java.security.spec.ECGenParameterSpec
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QrPairingProtocolTest {
    private fun generateKeyPair() = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()

    @Test
    fun joinInviteRoundTrips() {
        val a = generateKeyPair()
        val envelope = QrPairingProtocol.buildJoinInvite("session-1", Role.PHOTOGRAPHER, a.private, a.public)
        val parsed = QrPairingProtocol.parseJoinEnvelope(envelope.toString(), "join_invite", expectedSessionId = "session-1")
        assertNotNull(parsed)
        assertEquals("session-1", parsed!!.sessionId)
        assertEquals(Role.PHOTOGRAPHER, parsed.role)
        assertEquals(QrPairingProtocol.keyId(a.public), parsed.senderKeyId)
    }

    @Test
    fun joinInviteWithWrongExpectedSessionIsRejected() {
        val a = generateKeyPair()
        val envelope = QrPairingProtocol.buildJoinInvite("session-1", Role.WITNESS, a.private, a.public)
        assertNull(QrPairingProtocol.parseJoinEnvelope(envelope.toString(), "join_invite", expectedSessionId = "session-2"))
    }

    @Test
    fun joinInviteWithTamperedPayloadIsRejected() {
        val a = generateKeyPair()
        val envelope = QrPairingProtocol.buildJoinInvite("session-1", Role.WITNESS, a.private, a.public)
        val tampered = JSONObject(envelope.toString())
        val payload = JSONObject(String(java.util.Base64.getDecoder().decode(tampered.getString("payloadBase64"))))
        payload.put("sessionId", "session-9000")
        tampered.put("payloadBase64", java.util.Base64.getEncoder().encodeToString(payload.toString().toByteArray()))
        assertNull(QrPairingProtocol.parseJoinEnvelope(tampered.toString(), "join_invite"))
    }

    @Test
    fun joinInviteWithSwappedKeyIsRejected() {
        val a = generateKeyPair()
        val b = generateKeyPair()
        val envelope = QrPairingProtocol.buildJoinInvite("session-1", Role.WITNESS, a.private, a.public)
        // Swap in a different sender public key: senderKeyId/signature no longer match the embedded key.
        val swapped = JSONObject(envelope.toString())
            .put("senderPublicKeySpkiDerBase64", java.util.Base64.getEncoder().encodeToString(b.public.encoded))
        assertNull(QrPairingProtocol.parseJoinEnvelope(swapped.toString(), "join_invite"))
    }

    @Test
    fun oversizedEnvelopeIsRejected() {
        val a = generateKeyPair()
        val huge = JSONObject(QrPairingProtocol.buildJoinInvite("session-1", Role.WITNESS, a.private, a.public).toString())
            .put("padding", "x".repeat(4096))
        assertNull(QrPairingProtocol.parseJoinEnvelope(huge.toString(), "join_invite"))
    }

    @Test
    fun duplicateTopLevelKeysAreRejected() {
        val raw = """{"type":"join_invite","type":"join_invite","protocolVersion":2,"sessionId":"s","messageId":"m","payloadBase64":"AA==","signatureBase64Der":"AA=="}"""
        assertNull(QrPairingProtocol.parseJoinEnvelope(raw, "join_invite"))
    }

    @Test
    fun fullFinishHandshakeSucceeds() {
        val a = generateKeyPair()
        val b = generateKeyPair()
        val sessionId = "session-42"
        val aKeyId = QrPairingProtocol.keyId(a.public)
        val bKeyId = QrPairingProtocol.keyId(b.public)

        // 1. A -> B: finish_challenge
        val nonceA = QrPairingProtocol.freshNonce()
        val challenge = QrPairingProtocol.buildFinishChallenge(sessionId, a.private, a.public, bKeyId, nonceA)
        val challengeInfo = QrPairingProtocol.validateFinishChallenge(challenge.toString(), sessionId, a.public, bKeyId)
        assertNotNull(challengeInfo)
        assertTrue(nonceA.contentEquals(challengeInfo!!.nonce))

        // 2. B -> A: finish_response
        val nonceB = QrPairingProtocol.freshNonce()
        val response = QrPairingProtocol.buildFinishResponse(sessionId, b.private, b.public, aKeyId, challenge, nonceA, nonceB)
        val responseInfo = QrPairingProtocol.validateFinishResponse(response.toString(), sessionId, b.public, aKeyId, challenge, nonceA)
        assertNotNull(responseInfo)
        assertTrue(nonceB.contentEquals(responseInfo!!.nonceB))

        // 3. A -> B: finish_ack
        val ack = QrPairingProtocol.buildFinishAck(sessionId, a.private, a.public, bKeyId, response, nonceB)
        assertTrue(QrPairingProtocol.validateFinishAck(ack.toString(), sessionId, a.public, bKeyId, response, nonceB))
    }

    @Test
    fun staleResponseAgainstDifferentChallengeIsRejected() {
        val a = generateKeyPair()
        val b = generateKeyPair()
        val sessionId = "session-1"
        val bKeyId = QrPairingProtocol.keyId(b.public)
        val aKeyId = QrPairingProtocol.keyId(a.public)

        val oldChallenge = QrPairingProtocol.buildFinishChallenge(sessionId, a.private, a.public, bKeyId, QrPairingProtocol.freshNonce())
        val newNonceA = QrPairingProtocol.freshNonce()
        val newChallenge = QrPairingProtocol.buildFinishChallenge(sessionId, a.private, a.public, bKeyId, newNonceA)
        val response = QrPairingProtocol.buildFinishResponse(sessionId, b.private, b.public, aKeyId, newChallenge, newNonceA, QrPairingProtocol.freshNonce())

        // A is still holding the *old* challenge as "the one it sent" -> response must be rejected.
        assertNull(QrPairingProtocol.validateFinishResponse(response.toString(), sessionId, b.public, aKeyId, oldChallenge, newNonceA))
    }

    @Test
    fun wrongSessionIsRejected() {
        val a = generateKeyPair()
        val b = generateKeyPair()
        val bKeyId = QrPairingProtocol.keyId(b.public)
        val challenge = QrPairingProtocol.buildFinishChallenge("session-1", a.private, a.public, bKeyId, QrPairingProtocol.freshNonce())
        assertNull(QrPairingProtocol.validateFinishChallenge(challenge.toString(), "session-2", a.public, bKeyId))
    }

    @Test
    fun ownMessageEchoedBackIsRejected() {
        // Party A must not accept its own finish_challenge as if it came from B (wrong sender key).
        val a = generateKeyPair()
        val bKeyId = "0000000000000000"
        val challenge = QrPairingProtocol.buildFinishChallenge("session-1", a.private, a.public, bKeyId, QrPairingProtocol.freshNonce())
        assertNull(QrPairingProtocol.validateFinishChallenge(challenge.toString(), "session-1", a.public, "not-b-key-id"))
    }

    @Test
    fun mismatchedNonceAIsRejected() {
        val a = generateKeyPair()
        val b = generateKeyPair()
        val sessionId = "session-1"
        val aKeyId = QrPairingProtocol.keyId(a.public)
        val bKeyId = QrPairingProtocol.keyId(b.public)
        val nonceA = QrPairingProtocol.freshNonce()
        val challenge = QrPairingProtocol.buildFinishChallenge(sessionId, a.private, a.public, bKeyId, nonceA)
        val response = QrPairingProtocol.buildFinishResponse(sessionId, b.private, b.public, aKeyId, challenge, nonceA, QrPairingProtocol.freshNonce())
        val wrongExpectedNonceA = QrPairingProtocol.freshNonce()
        assertFalse(nonceA.contentEquals(wrongExpectedNonceA))
        assertNull(QrPairingProtocol.validateFinishResponse(response.toString(), sessionId, b.public, aKeyId, challenge, wrongExpectedNonceA))
    }
}
