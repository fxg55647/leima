package fi.leima.android.meeting

import java.security.MessageDigest
import java.security.PrivateKey
import java.security.PublicKey
import java.security.SecureRandom
import java.util.Base64
import java.util.UUID
import org.json.JSONException
import org.json.JSONObject
import org.json.JSONTokener

/**
 * Builds and validates the meeting-proof v2 QR envelopes (plan sections 3.2, 3.3, 6). Pure
 * `java.security` + `org.json`, no Android/CameraX/ZXing dependency — [QrAnalyzer] only feeds
 * decoded text in here, so the protocol logic itself is unit-testable without a device.
 *
 * Every builder signs `domainSeparator(type) + 0x00 + payloadBytes` via [MeetingCrypto] (never a
 * re-serialized envelope) and every validator rejects on: wrong session, wrong/absent sender or
 * receiver key id, bad signature, oversized/duplicate-keyed JSON, or (for finish_response/ack) a
 * stale challenge/response — matching plan section 6's rejection list directly.
 */
object QrPairingProtocol {
    const val PROTOCOL_VERSION = 2
    const val MAX_ENVELOPE_BYTES = 2048

    fun freshNonce(random: SecureRandom = SecureRandom()): ByteArray = ByteArray(16).also { random.nextBytes(it) } // 128 bit

    /** First 8 bytes (16 hex chars) of the public key's SHA-256, matching android/docs/meeting_v2_schema.md. */
    fun keyId(publicKey: PublicKey): String =
        MessageDigest.getInstance("SHA-256").digest(publicKey.encoded).copyOfRange(0, 8).joinToString("") { "%02x".format(it) }

    /** Hex SHA-256 of an already-built envelope's signed bytes, used for `inResponseToHash`. */
    fun envelopeHash(envelope: JSONObject): String =
        sha256Hex(MeetingCrypto.signedBytes(envelope.getString("type"), b64d(envelope.getString("payloadBase64"))))

    private fun newMessageId(): String = "m-" + UUID.randomUUID().toString().take(8)
    private fun b64(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)
    private fun b64d(value: String): ByteArray = Base64.getDecoder().decode(value)
    private fun sha256Hex(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    // ---- join_invite / join_response (plan section 3.2) --------------------------------------

    data class JoinEnvelope(val sessionId: String, val role: Role, val senderKeyId: String, val senderPublicKey: PublicKey, val messageId: String)

    fun buildJoinInvite(sessionId: String, role: Role, privateKey: PrivateKey, publicKey: PublicKey, messageId: String = newMessageId()): JSONObject {
        val payload = JSONObject().put("type", "join_invite").put("protocolVersion", PROTOCOL_VERSION)
            .put("sessionId", sessionId).put("role", role.jsonValue).put("messageId", messageId)
        return seal("join_invite", payload, privateKey, sessionId, keyId(publicKey), null, messageId, publicKey)
    }

    fun buildJoinResponse(
        sessionId: String,
        role: Role,
        privateKey: PrivateKey,
        publicKey: PublicKey,
        receiverKeyId: String,
        messageId: String = newMessageId(),
    ): JSONObject {
        val payload = JSONObject().put("type", "join_response").put("protocolVersion", PROTOCOL_VERSION)
            .put("sessionId", sessionId).put("role", role.jsonValue).put("messageId", messageId)
        return seal("join_response", payload, privateKey, sessionId, keyId(publicKey), receiverKeyId, messageId, publicKey)
    }

    /** Self-verifies: the embedded public key must match both the signature and the declared senderKeyId. */
    fun parseJoinEnvelope(raw: String, type: String, expectedSessionId: String? = null): JoinEnvelope? {
        val envelope = readEnvelope(raw) ?: return null
        if (envelope.optString("type") != type) return null
        if (envelope.optInt("protocolVersion", -1) != PROTOCOL_VERSION) return null
        val sessionId = envelope.optString("sessionId", "")
        if (sessionId.isBlank()) return null
        if (expectedSessionId != null && sessionId != expectedSessionId) return null
        val publicKeyDer = runCatching { b64d(envelope.getString("senderPublicKeySpkiDerBase64")) }.getOrNull() ?: return null
        val publicKey = runCatching { MeetingCrypto.loadPublicKeyDer(publicKeyDer) }.getOrNull() ?: return null
        if (envelope.optString("senderKeyId") != keyId(publicKey)) return null
        val payloadBytes = runCatching { b64d(envelope.getString("payloadBase64")) }.getOrNull() ?: return null
        val signature = runCatching { b64d(envelope.getString("signatureBase64Der")) }.getOrNull() ?: return null
        if (!MeetingCrypto.verify(publicKey, type, payloadBytes, signature)) return null
        val payload = runCatching { JSONObject(String(payloadBytes, Charsets.UTF_8)) }.getOrNull() ?: return null
        val role = Role.entries.firstOrNull { it.jsonValue == payload.optString("role") } ?: return null
        val messageId = envelope.optString("messageId", "")
        if (messageId.isBlank()) return null
        return JoinEnvelope(sessionId, role, envelope.getString("senderKeyId"), publicKey, messageId)
    }

    // ---- finish_challenge / finish_response / finish_ack (plan section 3.3) ------------------

    fun buildFinishChallenge(
        sessionId: String,
        privateKey: PrivateKey,
        publicKey: PublicKey,
        receiverKeyId: String,
        nonce: ByteArray,
        messageId: String = newMessageId(),
    ): JSONObject {
        val senderKeyId = keyId(publicKey)
        val payload = JSONObject().put("type", "finish_challenge").put("protocolVersion", PROTOCOL_VERSION)
            .put("sessionId", sessionId).put("senderKeyId", senderKeyId).put("receiverKeyId", receiverKeyId)
            .put("nonce", b64(nonce)).put("messageId", messageId)
        return seal("finish_challenge", payload, privateKey, sessionId, senderKeyId, receiverKeyId, messageId)
    }

    data class FinishChallengeInfo(val nonce: ByteArray, val messageId: String)

    fun validateFinishChallenge(raw: String, sessionId: String, senderPublicKey: PublicKey, expectedReceiverKeyId: String): FinishChallengeInfo? {
        val envelope = openSealed(raw, "finish_challenge", sessionId, keyId(senderPublicKey), expectedReceiverKeyId, senderPublicKey) ?: return null
        val payload = payloadOf(envelope) ?: return null
        val nonce = runCatching { b64d(payload.getString("nonce")) }.getOrNull() ?: return null
        return FinishChallengeInfo(nonce, envelope.getString("messageId"))
    }

    fun buildFinishResponse(
        sessionId: String,
        privateKey: PrivateKey,
        publicKey: PublicKey,
        receiverKeyId: String,
        challengeEnvelope: JSONObject,
        nonceA: ByteArray,
        nonceB: ByteArray,
        messageId: String = newMessageId(),
    ): JSONObject {
        val senderKeyId = keyId(publicKey)
        val payload = JSONObject().put("type", "finish_response").put("protocolVersion", PROTOCOL_VERSION)
            .put("sessionId", sessionId).put("senderKeyId", senderKeyId).put("receiverKeyId", receiverKeyId)
            .put("inResponseToHash", envelopeHash(challengeEnvelope))
            .put("nonceA", b64(nonceA)).put("nonceB", b64(nonceB)).put("messageId", messageId)
        return seal("finish_response", payload, privateKey, sessionId, senderKeyId, receiverKeyId, messageId)
    }

    data class FinishResponseInfo(val nonceB: ByteArray, val messageId: String)

    /** `expectedNonceA` and `sentChallenge` pin this response to the one specific challenge still pending; a reply to a stale or different challenge is rejected. */
    fun validateFinishResponse(
        raw: String,
        sessionId: String,
        senderPublicKey: PublicKey,
        expectedReceiverKeyId: String,
        sentChallenge: JSONObject,
        expectedNonceA: ByteArray,
    ): FinishResponseInfo? {
        val envelope = openSealed(raw, "finish_response", sessionId, keyId(senderPublicKey), expectedReceiverKeyId, senderPublicKey) ?: return null
        val payload = payloadOf(envelope) ?: return null
        if (payload.optString("inResponseToHash") != envelopeHash(sentChallenge)) return null
        val nonceA = runCatching { b64d(payload.getString("nonceA")) }.getOrNull() ?: return null
        if (!nonceA.contentEquals(expectedNonceA)) return null
        val nonceB = runCatching { b64d(payload.getString("nonceB")) }.getOrNull() ?: return null
        return FinishResponseInfo(nonceB, envelope.getString("messageId"))
    }

    fun buildFinishAck(
        sessionId: String,
        privateKey: PrivateKey,
        publicKey: PublicKey,
        receiverKeyId: String,
        responseEnvelope: JSONObject,
        nonceB: ByteArray,
        messageId: String = newMessageId(),
    ): JSONObject {
        val senderKeyId = keyId(publicKey)
        val payload = JSONObject().put("type", "finish_ack").put("protocolVersion", PROTOCOL_VERSION)
            .put("sessionId", sessionId).put("senderKeyId", senderKeyId).put("receiverKeyId", receiverKeyId)
            .put("inResponseToHash", envelopeHash(responseEnvelope))
            .put("nonceB", b64(nonceB)).put("messageId", messageId)
        return seal("finish_ack", payload, privateKey, sessionId, senderKeyId, receiverKeyId, messageId)
    }

    fun validateFinishAck(
        raw: String,
        sessionId: String,
        senderPublicKey: PublicKey,
        expectedReceiverKeyId: String,
        sentResponse: JSONObject,
        expectedNonceB: ByteArray,
    ): Boolean {
        val envelope = openSealed(raw, "finish_ack", sessionId, keyId(senderPublicKey), expectedReceiverKeyId, senderPublicKey) ?: return false
        val payload = payloadOf(envelope) ?: return false
        if (payload.optString("inResponseToHash") != envelopeHash(sentResponse)) return false
        val nonceB = runCatching { b64d(payload.getString("nonceB")) }.getOrNull() ?: return false
        return nonceB.contentEquals(expectedNonceB)
    }

    // ---- shared envelope plumbing -------------------------------------------------------------

    private fun seal(
        type: String,
        payload: JSONObject,
        privateKey: PrivateKey,
        sessionId: String,
        senderKeyId: String,
        receiverKeyId: String?,
        messageId: String,
        senderPublicKey: PublicKey? = null,
    ): JSONObject {
        val payloadBytes = payload.toString().toByteArray(Charsets.UTF_8)
        val signature = MeetingCrypto.sign(privateKey, type, payloadBytes)
        val envelope = JSONObject()
            .put("type", type).put("protocolVersion", PROTOCOL_VERSION).put("sessionId", sessionId)
            .put("senderKeyId", senderKeyId).put("receiverKeyId", receiverKeyId ?: JSONObject.NULL).put("messageId", messageId)
            .put("payloadBase64", b64(payloadBytes)).put("signatureBase64Der", b64(signature))
        if (senderPublicKey != null) envelope.put("senderPublicKeySpkiDerBase64", b64(senderPublicKey.encoded))
        val text = envelope.toString()
        check(text.toByteArray(Charsets.UTF_8).size <= MAX_ENVELOPE_BYTES) { "QR envelope for '$type' exceeds $MAX_ENVELOPE_BYTES bytes" }
        return envelope
    }

    private fun readEnvelope(raw: String): JSONObject? {
        if (raw.toByteArray(Charsets.UTF_8).size > MAX_ENVELOPE_BYTES) return null
        if (hasDuplicateTopLevelKeys(raw)) return null
        return runCatching { JSONObject(raw) }.getOrNull()
    }

    private fun openSealed(
        raw: String,
        type: String,
        sessionId: String,
        expectedSenderKeyId: String,
        expectedReceiverKeyId: String,
        senderPublicKey: PublicKey,
    ): JSONObject? {
        val envelope = readEnvelope(raw) ?: return null
        if (envelope.optString("type") != type) return null
        if (envelope.optInt("protocolVersion", -1) != PROTOCOL_VERSION) return null
        if (envelope.optString("sessionId") != sessionId) return null
        if (envelope.optString("senderKeyId") != expectedSenderKeyId) return null
        if (envelope.optString("receiverKeyId") != expectedReceiverKeyId) return null
        val payloadBytes = runCatching { b64d(envelope.getString("payloadBase64")) }.getOrNull() ?: return null
        val signature = runCatching { b64d(envelope.getString("signatureBase64Der")) }.getOrNull() ?: return null
        if (!MeetingCrypto.verify(senderPublicKey, type, payloadBytes, signature)) return null
        return envelope
    }

    private fun payloadOf(envelope: JSONObject): JSONObject? =
        runCatching { JSONObject(String(b64d(envelope.getString("payloadBase64")), Charsets.UTF_8)) }.getOrNull()

    /** Plan section 6: "Kiellettyjä ovat päällekkäiset JSON-avaimet". Our envelopes are flat, so a top-level scan is enough. */
    private fun hasDuplicateTopLevelKeys(raw: String): Boolean {
        val tokener = JSONTokener(raw)
        if (tokener.nextClean() != '{') return false // not an object; JSONObject(raw) will fail on its own
        if (tokener.nextClean() == '}') return false // empty object
        tokener.back()
        val seen = HashSet<String>()
        while (true) {
            val key = runCatching { tokener.nextValue() }.getOrNull() as? String ?: return false
            if (!seen.add(key)) return true
            if (tokener.nextClean() != ':') throw JSONException("expected ':' in QR envelope")
            runCatching { tokener.nextValue() }.getOrNull() ?: return false // skip the value; flat schema, never recursed
            when (tokener.nextClean()) {
                '}' -> return false
                ',' -> continue
                else -> throw JSONException("expected ',' or '}' in QR envelope")
            }
        }
    }
}
