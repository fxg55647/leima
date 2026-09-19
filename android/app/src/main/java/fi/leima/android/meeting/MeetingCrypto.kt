package fi.leima.android.meeting

import java.security.KeyFactory
import java.security.PrivateKey
import java.security.PublicKey
import java.security.Signature
import java.security.interfaces.ECPublicKey
import java.security.spec.X509EncodedKeySpec

/**
 * Shared ECDSA P-256/SHA-256 signing scheme for the Leima meeting-proof v2 protocol.
 *
 * Every signed message (QR envelope or package manifest) is signed over
 * `domainSeparator(messageType) + 0x00 + payload` — never over a re-serialized
 * JSON object — so a verifier never has to reproduce the sender's exact JSON
 * encoding. The NUL delimiter after the separator means no separator string
 * can be a byte-for-byte prefix of another separator plus payload.
 *
 * Signature and public-key encodings match what the `cryptography` package's
 * defaults produce on the Python side: ASN.1 DER ECDSA signatures and DER
 * SubjectPublicKeyInfo public keys. See android/docs/meeting_v2_schema.md and
 * android/testdata/meeting_crypto_vectors.json for the cross-language test
 * vectors that pin this scheme.
 */
object MeetingCrypto {
    private const val DOMAIN_PREFIX = "leima-meeting-v2"
    private const val SIGNATURE_ALGORITHM = "SHA256withECDSA"
    private const val KEY_ALGORITHM = "EC"

    fun domainSeparator(messageType: String): ByteArray =
        "$DOMAIN_PREFIX:$messageType".toByteArray(Charsets.UTF_8)

    fun signedBytes(messageType: String, payload: ByteArray): ByteArray =
        domainSeparator(messageType) + byteArrayOf(0) + payload

    fun sign(privateKey: PrivateKey, messageType: String, payload: ByteArray): ByteArray =
        Signature.getInstance(SIGNATURE_ALGORITHM).run {
            initSign(privateKey)
            update(signedBytes(messageType, payload))
            sign()
        }

    fun verify(publicKey: PublicKey, messageType: String, payload: ByteArray, signature: ByteArray): Boolean =
        try {
            Signature.getInstance(SIGNATURE_ALGORITHM).run {
                initVerify(publicKey)
                update(signedBytes(messageType, payload))
                verify(signature)
            }
        } catch (_: java.security.GeneralSecurityException) {
            false
        }

    /** Decodes a DER SubjectPublicKeyInfo P-256 public key; rejects any other curve. */
    fun loadPublicKeyDer(der: ByteArray): PublicKey {
        val key = KeyFactory.getInstance(KEY_ALGORITHM).generatePublic(X509EncodedKeySpec(der))
        val fieldSize = (key as? ECPublicKey)?.params?.curve?.field?.fieldSize
        require(fieldSize == 256) { "expected a P-256 (secp256r1) EC public key" }
        return key
    }
}
