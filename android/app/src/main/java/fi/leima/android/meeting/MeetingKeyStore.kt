package fi.leima.android.meeting

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.PublicKey
import java.security.spec.ECGenParameterSpec
import org.json.JSONObject

/**
 * One per-session P-256 signing key in the Android Keystore (plan section 8: "Istuntokohtainen
 * Android Keystore -avain allekirjoittaa sekä QR-viestit että oman manifestin"). The alias is
 * derived from the session id, so a key never outlives or is confused with another session's.
 *
 * If the device cannot back the key in secure hardware, Android silently falls back to a
 * software-backed key; [isHardwareBacked] reports which one actually happened rather than
 * assuming hardware attestation (plan section 8: "Ohjelmistossa suojattu avain voidaan hyväksyä
 * kokeilutilassa erillisellä turvatiedolla; sitä ei ilmoiteta laitteistossa varmennetuksi").
 */
class MeetingKeyStore(sessionId: String) {
    private val alias = "leima-meeting-$sessionId"
    private val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    val privateKey: PrivateKey
    val publicKey: PublicKey
    val isHardwareBacked: Boolean
    val keyId: String

    init {
        if (!keyStore.containsAlias(alias)) generate()
        val entry = keyStore.getEntry(alias, null) as KeyStore.PrivateKeyEntry
        privateKey = entry.privateKey
        publicKey = entry.certificate.publicKey
        isHardwareBacked = reportHardwareBacking()
        keyId = QrPairingProtocol.keyId(publicKey)
    }

    fun securityReport(): JSONObject = JSONObject()
        .put("keyId", keyId).put("hardwareBacked", isHardwareBacked)
        .put(
            "note",
            if (isHardwareBacked) "Key attested inside secure hardware" else "Software-backed key; not hardware attested (trial mode)",
        )

    /** Removes the Keystore entry once the session's package has been finalized/exported. */
    fun deleteKey() {
        runCatching { keyStore.deleteEntry(alias) }
    }

    private fun generate() {
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        generator.initialize(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                .build(),
        )
        generator.generateKeyPair()
    }

    @Suppress("DEPRECATION") // no minSdk-28-compatible replacement for isInsideSecureHardware
    private fun reportHardwareBacking(): Boolean = runCatching {
        val factory = KeyFactory.getInstance(privateKey.algorithm, "AndroidKeyStore")
        factory.getKeySpec(privateKey, KeyInfo::class.java).isInsideSecureHardware
    }.getOrDefault(false)
}
