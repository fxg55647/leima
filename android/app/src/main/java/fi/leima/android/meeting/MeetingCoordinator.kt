package fi.leima.android.meeting

import android.content.Context
import android.os.Build
import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.exifinterface.media.ExifInterface
import fi.leima.android.BuildConfig
import java.io.File
import java.security.PublicKey
import java.time.Instant
import java.util.UUID
import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONArray
import org.json.JSONObject

/** One photo the user has taken or is taking, and its outcome, for the current session. */
data class CaptureInfo(
    val captureId: String,
    val sequenceNumber: Int,
    val observationPointId: String?,
    val shotType: ShotType,
    val status: CaptureStatus,
    val errorMessage: String? = null,
)

data class ObservationPointInfo(
    val id: String,
    val name: String,
    val templateId: TemplateId,
    val purpose: String?,
    val stepStatuses: Map<Int, StepStatus>,
)

/** The other device's identity, known once join pairing (or the finish exchange) has validated it. */
data class PartnerInfo(val role: Role, val keyId: String, val publicKey: PublicKey)

/**
 * Orchestrates one meeting-proof capture session on this device: pairing, recording lifecycle,
 * guided capture requests, observation points, the end-of-session QR exchange, and
 * finalize/export. [finish] takes the solo path straight to [SessionState.FINALIZING] when there
 * is no [partner] (plan section 3.1: "Kuvaus toimii myös yksin"), or the paired
 * challenge/response/ack path through [SessionState.CONFIRMING] otherwise.
 *
 * All session commands go through [MeetingStateMachine] rather than trusting the caller, so a
 * stale UI or a late camera/QR callback can never apply an illegal transition. Every QR envelope
 * is built and validated by [QrPairingProtocol]; this class only sequences *when* those calls
 * happen and what the result unlocks next.
 */
class MeetingCoordinator(
    private val context: Context,
    val sessionDirectory: File,
    val role: Role,
    private val participantId: String = UUID.randomUUID().toString(),
) {
    companion object {
        // Plan section 9 (trial limits, to be confirmed by two-phone measurements).
        const val MAX_CAPTURES = 20
        const val MAX_RECORDING_DURATION_MS = 10 * 60 * 1000L

        // Plan section 6: "Prototyypin paikallinen vastausaikaraja on 120 sekuntia per odotettu vastaus."
        const val FINISH_EXCHANGE_TIMEOUT_MS = 120 * 1000L
    }

    // The Keystore alias is tied to the *local* directory name, which never changes, unlike the
    // logical `sessionId` below (the joiner adopts the initiator's id once pairing starts).
    val keyStore = MeetingKeyStore(sessionDirectory.name)

    private var sessionIdField: String = sessionDirectory.name
    val sessionId: String get() = sessionIdField
    val camera = CameraCaptureController(context)

    // Compose-observable: MeetingScreen reads `state`/`observationPointList()`/`captureList()`
    // directly, so every mutation here must go through Compose state, not a plain field/List/Map.
    var state: SessionState by mutableStateOf(SessionState.IDLE)
        private set

    private var partnerField: PartnerInfo? = null
    val partner: PartnerInfo? get() = partnerField
    var isPairingInitiator: Boolean = false
        private set
    private val pairingLog = mutableListOf<JSONObject>()

    private var pendingChallenge: JSONObject? = null
    private var pendingChallengeNonce: ByteArray? = null
    private var pendingResponse: JSONObject? = null
    private var pendingResponseNonceB: ByteArray? = null
    private var finishExchangeStartedElapsedRealtimeNs: Long? = null

    private val startedAtUtc: String = Instant.now().toString()
    private val journal = SessionJournal(sessionDirectory, elapsedRealtimeNanos = SystemClock::elapsedRealtimeNanos)
    private val sensorRecorder = SessionSensorRecorder(context, sessionDirectory, journal)
    private val observationPoints = mutableStateMapOf<String, ObservationPointInfo>()
    private val captures = mutableStateListOf<CaptureInfo>()
    private var sequenceCounter = 0
    private val captureInFlight = AtomicBoolean(false)
    private var recordingStartedElapsedRealtimeNs: Long? = null

    /** True once the trial 10-minute recording budget (plan section 9) has been used up. */
    val isOverTimeBudget: Boolean
        get() {
            val startedNs = recordingStartedElapsedRealtimeNs ?: return false
            return (SystemClock.elapsedRealtimeNanos() - startedNs) / 1_000_000 > MAX_RECORDING_DURATION_MS
        }

    // SnapshotStateMap does not guarantee insertion order, so sort explicitly by the stable
    // sequential id ("op-001", "op-002", …) instead of relying on iteration order for display.
    fun observationPointList(): List<ObservationPointInfo> = observationPoints.values.sortedBy { it.id }
    fun captureList(): List<CaptureInfo> = captures.toList()
    val isCaptureInFlight: Boolean get() = captureInFlight.get()

    private fun apply(command: SessionCommand): Boolean {
        val next = MeetingStateMachine.transition(state, command) ?: return false
        state = next
        return true
    }

    // ---- Solo path (plan section 3.1) ---------------------------------------------------------

    /** IDLE -> READY directly, no partner. Call once, before [startRecording]. */
    fun prepare(): Boolean {
        if (!apply(SessionCommand.ReadyToRecord)) return false
        journal.record("session_created", JSONObject().put("sessionId", sessionId).put("role", role.jsonValue).put("participantId", participantId))
        return true
    }

    // ---- Join pairing (plan section 3.2) ------------------------------------------------------

    /** IDLE -> PAIRING. `asInitiator` decides who shows join_invite first and who drives the later finish exchange. */
    fun beginPairing(asInitiator: Boolean): Boolean {
        if (!apply(SessionCommand.BeginPairing)) return false
        isPairingInitiator = asInitiator
        journal.record("pairing_started", JSONObject().put("asInitiator", asInitiator).put("role", role.jsonValue))
        return true
    }

    /** Initiator only: builds this device's join_invite QR envelope to show the partner. */
    fun buildJoinInvite(): JSONObject? {
        if (state != SessionState.PAIRING || !isPairingInitiator) return null
        val envelope = QrPairingProtocol.buildJoinInvite(sessionId, role, keyStore.privateKey, keyStore.publicKey)
        recordPairingMessage("sent", envelope)
        return envelope
    }

    /** Joiner only: call after scanning the initiator's join_invite QR text. Adopts the shared session id. */
    fun acceptJoinInvite(raw: String): PartnerInfo? {
        if (state != SessionState.PAIRING || isPairingInitiator) return null
        val invite = QrPairingProtocol.parseJoinEnvelope(raw, "join_invite") ?: return null
        sessionIdField = invite.sessionId
        val info = PartnerInfo(invite.role, invite.senderKeyId, invite.senderPublicKey)
        partnerField = info
        recordPairingMessage("received", runCatching { JSONObject(raw) }.getOrDefault(JSONObject()))
        journal.record(
            "join_invite_accepted",
            JSONObject().put("sessionId", invite.sessionId).put("partnerRole", invite.role.jsonValue).put("partnerKeyId", invite.senderKeyId),
        )
        return info
    }

    /** Joiner only: builds this device's join_response QR envelope, once [acceptJoinInvite] succeeded. */
    fun buildJoinResponse(): JSONObject? {
        if (state != SessionState.PAIRING || isPairingInitiator) return null
        val partnerKeyId = partnerField?.keyId ?: return null
        val envelope = QrPairingProtocol.buildJoinResponse(sessionId, role, keyStore.privateKey, keyStore.publicKey, partnerKeyId)
        recordPairingMessage("sent", envelope)
        return envelope
    }

    /** Joiner only: call once the join_response QR has been shown. B does not need to wait for A's confirmation. */
    fun confirmJoinResponseShown(): Boolean {
        if (isPairingInitiator || partnerField == null) return false
        return completePairing()
    }

    /** Initiator only: call after scanning the partner's join_response QR text. Completes pairing on this side. */
    fun acceptJoinResponse(raw: String): Boolean {
        if (state != SessionState.PAIRING || !isPairingInitiator) return false
        val response = QrPairingProtocol.parseJoinEnvelope(raw, "join_response", expectedSessionId = sessionId) ?: return false
        partnerField = PartnerInfo(response.role, response.senderKeyId, response.senderPublicKey)
        recordPairingMessage("received", runCatching { JSONObject(raw) }.getOrDefault(JSONObject()))
        journal.record(
            "join_response_accepted",
            JSONObject().put("partnerRole", response.role.jsonValue).put("partnerKeyId", response.senderKeyId),
        )
        return completePairing()
    }

    private fun completePairing(): Boolean {
        val moved = apply(SessionCommand.PairingEstablished)
        if (moved) journal.record("pairing_established", JSONObject().put("sessionId", sessionId).put("partnerKeyId", partnerField?.keyId))
        return moved
    }

    // ---- Recording (plan section 3.2, unchanged since Vaihe 1) ---------------------------------

    /** READY -> RECORDING and starts continuous sensor logging. Camera preview binds separately in the UI. */
    fun startRecording(): Boolean {
        if (!apply(SessionCommand.StartRecording)) return false
        recordingStartedElapsedRealtimeNs = SystemClock.elapsedRealtimeNanos()
        sensorRecorder.start()
        journal.record("recording_started")
        return true
    }

    /** Adds a new observation point and returns it, or null if not currently [SessionState.RECORDING]. */
    fun addObservationPoint(name: String, templateId: TemplateId, purpose: String? = null): ObservationPointInfo? {
        if (state != SessionState.RECORDING) return null
        val id = "op-%03d".format(observationPoints.size + 1)
        val steps = CaptureTemplates.byId(templateId).steps.associate { it.stepIndex to StepStatus.NOT_TAKEN }
        val info = ObservationPointInfo(id, name, templateId, purpose, steps)
        observationPoints[id] = info
        journal.record(
            "observation_point_added",
            JSONObject().put("observationPointId", id).put("name", name).put("templateId", templateId.jsonValue)
                .put("purpose", purpose ?: JSONObject.NULL),
        )
        return info
    }

    /** Marks a guided step as deliberately skipped; it stays distinguishable from "not reached yet" in the summary. */
    fun skipStep(observationPointId: String, stepIndex: Int) {
        val point = observationPoints[observationPointId] ?: return
        if (point.stepStatuses[stepIndex] == StepStatus.CAPTURED) return
        observationPoints[observationPointId] = point.copy(stepStatuses = point.stepStatuses + (stepIndex to StepStatus.SKIPPED))
        journal.record("step_skipped", JSONObject().put("observationPointId", observationPointId).put("stepIndex", stepIndex))
    }

    /**
     * Requests one photo. Rejects a second concurrent request outright (plan section 4:
     * "Päällekkäiset suljinpainallukset eivät käynnistä rinnakkaista tallennusta") by returning
     * null without touching the camera. `onResult` is delivered through `executor`; because every
     * write below is keyed on the `captureId` this closure captured, a callback for a capture the
     * coordinator has moved on from can never corrupt a later one.
     */
    fun requestCapture(
        observationPointId: String?,
        shotType: ShotType,
        purpose: String?,
        overviewCaptureId: String?,
        targetRotation: Int,
        executor: Executor,
        onResult: (CaptureInfo) -> Unit,
    ): String? {
        if (state != SessionState.RECORDING) return null
        if (captures.size >= MAX_CAPTURES || isOverTimeBudget) return null
        if (!captureInFlight.compareAndSet(false, true)) return null

        // Matches the package structure in plan section 8: captures/000001.jpg, captures/000001.json.
        val captureId = "%06d".format(++sequenceCounter)
        val point = observationPointId?.let { observationPoints[it] }
        val templateId = point?.templateId ?: TemplateId.FREE
        val templateVersion = CaptureTemplates.byId(templateId).version
        val requestedAtUtc = Instant.now().toString()
        val requestedElapsedRealtimeNs = SystemClock.elapsedRealtimeNanos()
        captures.add(CaptureInfo(captureId, sequenceCounter, observationPointId, shotType, CaptureStatus.REQUESTED))
        journal.record(
            "capture_requested",
            JSONObject().put("captureId", captureId).put("observationPointId", observationPointId ?: JSONObject.NULL)
                .put("shotType", shotType.jsonValue),
        )

        val captureDir = File(sessionDirectory, "captures").apply { mkdirs() }
        val photoFile = File(captureDir, "$captureId.jpg")
        camera.takePhoto(
            photoFile,
            targetRotation,
            executor,
            onSaved = {
                val metadata = JSONObject()
                    .put("captureId", captureId).put("sessionId", sessionId).put("participantId", participantId)
                    .put("sequenceNumber", sequenceCounter).put("observationPointId", observationPointId ?: JSONObject.NULL)
                    .put("templateId", templateId.jsonValue).put("templateVersion", templateVersion)
                    .put("purpose", purpose ?: JSONObject.NULL).put("shotType", shotType.jsonValue)
                    .put("overviewCaptureId", overviewCaptureId ?: JSONObject.NULL)
                    .put("requestedAtUtc", requestedAtUtc).put("requestedElapsedRealtimeNs", requestedElapsedRealtimeNs)
                    .put("completedAtUtc", Instant.now().toString()).put("completedElapsedRealtimeNs", SystemClock.elapsedRealtimeNanos())
                    .put("status", CaptureStatus.SAVED.jsonValue).put("cameraExif", readExif(photoFile))
                File(captureDir, "$captureId.json").writeText(metadata.toString(2), Charsets.UTF_8)
                updateCapture(captureId) { it.copy(status = CaptureStatus.SAVED) }
                if (observationPointId != null) markStepCaptured(observationPointId, shotType)
                journal.record("capture_saved", JSONObject().put("captureId", captureId))
                captureInFlight.set(false)
                onResult(captures.first { it.captureId == captureId })
            },
            onError = { error ->
                photoFile.delete()
                val message = error.localizedMessage ?: "unknown error"
                updateCapture(captureId) { it.copy(status = CaptureStatus.FAILED, errorMessage = message) }
                journal.record("capture_failed", JSONObject().put("captureId", captureId).put("message", message))
                captureInFlight.set(false)
                onResult(captures.first { it.captureId == captureId })
            },
        )
        return captureId
    }

    private fun updateCapture(captureId: String, transform: (CaptureInfo) -> CaptureInfo) {
        val index = captures.indexOfFirst { it.captureId == captureId }
        if (index >= 0) captures[index] = transform(captures[index])
    }

    private fun markStepCaptured(observationPointId: String, shotType: ShotType) {
        val point = observationPoints[observationPointId] ?: return
        val template = CaptureTemplates.byId(point.templateId)
        val stepIndex = template.steps.firstOrNull { it.shotType == shotType }?.stepIndex ?: return
        observationPoints[observationPointId] = point.copy(stepStatuses = point.stepStatuses + (stepIndex to StepStatus.CAPTURED))
    }

    private fun readExif(file: File): JSONObject {
        val fields = JSONObject()
        runCatching {
            val exif = ExifInterface(file)
            listOf(
                ExifInterface.TAG_EXPOSURE_TIME, ExifInterface.TAG_F_NUMBER, ExifInterface.TAG_PHOTOGRAPHIC_SENSITIVITY,
                ExifInterface.TAG_FOCAL_LENGTH, ExifInterface.TAG_DATETIME_ORIGINAL, ExifInterface.TAG_ORIENTATION,
                ExifInterface.TAG_IMAGE_WIDTH, ExifInterface.TAG_IMAGE_LENGTH,
            ).forEach { fields.put(it, exif.getAttribute(it) ?: JSONObject.NULL) }
        }
        return fields
    }

    // ---- Finish (plan section 3.3) --------------------------------------------------------------

    /** User tapped "Vahvista kohtaaminen". Solo (no partner) goes straight to FINALIZING; a paired session enters the finish QR exchange. */
    fun finish(): Boolean = if (partnerField != null) apply(SessionCommand.FinishPaired) else apply(SessionCommand.FinishSolo)

    /** Initiator (A) only, once CONFIRMING: builds a finish_challenge QR to show the partner. Safe to call again to retry with a fresh nonce. */
    fun buildFinishChallenge(): JSONObject? {
        val partnerKeyId = partnerField?.keyId ?: return null
        if (state != SessionState.CONFIRMING || !isPairingInitiator) return null
        if (pendingChallenge != null) {
            journal.record("finish_challenge_retry", JSONObject().put("previousMessageId", pendingChallenge?.optString("messageId")))
        }
        val nonce = QrPairingProtocol.freshNonce()
        val challenge = QrPairingProtocol.buildFinishChallenge(sessionId, keyStore.privateKey, keyStore.publicKey, partnerKeyId, nonce)
        pendingChallenge = challenge
        pendingChallengeNonce = nonce
        finishExchangeStartedElapsedRealtimeNs = SystemClock.elapsedRealtimeNanos()
        recordPairingMessage("sent", challenge)
        return challenge
    }

    /** Joiner (B) only: call after scanning A's finish_challenge QR text. Returns the finish_response QR to show back. */
    fun acceptFinishChallengeAndBuildResponse(raw: String): JSONObject? {
        val partner = partnerField ?: return null
        if (state != SessionState.CONFIRMING || isPairingInitiator) return null
        val info = QrPairingProtocol.validateFinishChallenge(raw, sessionId, partner.publicKey, keyStore.keyId) ?: return null
        val challengeEnvelope = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        recordPairingMessage("received", challengeEnvelope)
        val nonceB = QrPairingProtocol.freshNonce()
        val response = QrPairingProtocol.buildFinishResponse(
            sessionId, keyStore.privateKey, keyStore.publicKey, partner.keyId, challengeEnvelope, info.nonce, nonceB,
        )
        pendingResponse = response
        pendingResponseNonceB = nonceB
        journal.record("finish_challenge_accepted", JSONObject().put("messageId", info.messageId))
        recordPairingMessage("sent", response)
        return response
    }

    /** Initiator (A) only: call after scanning B's finish_response QR text. Returns the finish_ack QR and advances to FINALIZING. */
    fun acceptFinishResponseAndBuildAck(raw: String): JSONObject? {
        val partner = partnerField ?: return null
        val challenge = pendingChallenge ?: return null
        val nonceA = pendingChallengeNonce ?: return null
        if (state != SessionState.CONFIRMING || !isPairingInitiator) return null
        if (isFinishExchangeTimedOut()) return null
        val info = QrPairingProtocol.validateFinishResponse(raw, sessionId, partner.publicKey, keyStore.keyId, challenge, nonceA) ?: return null
        val responseEnvelope = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        recordPairingMessage("received", responseEnvelope)
        val ack = QrPairingProtocol.buildFinishAck(sessionId, keyStore.privateKey, keyStore.publicKey, partner.keyId, responseEnvelope, info.nonceB)
        journal.record("finish_response_accepted", JSONObject().put("messageId", info.messageId))
        recordPairingMessage("sent", ack)
        apply(SessionCommand.PairingConfirmed)
        return ack
    }

    /** Joiner (B) only: call after scanning A's finish_ack QR text. Advances to FINALIZING. */
    fun acceptFinishAck(raw: String): Boolean {
        val partner = partnerField ?: return false
        val response = pendingResponse ?: return false
        val nonceB = pendingResponseNonceB ?: return false
        if (state != SessionState.CONFIRMING || isPairingInitiator) return false
        val ok = QrPairingProtocol.validateFinishAck(raw, sessionId, partner.publicKey, keyStore.keyId, response, nonceB)
        if (!ok) return false
        recordPairingMessage("received", runCatching { JSONObject(raw) }.getOrDefault(JSONObject()))
        journal.record("finish_ack_accepted")
        return apply(SessionCommand.PairingConfirmed)
    }

    // A holds the "started" timestamp because A owns the retry decision; B is purely reactive and
    // simply will not complete if A never returns, which needs no separate timeout of its own.
    private fun isFinishExchangeTimedOut(): Boolean {
        val startedNs = finishExchangeStartedElapsedRealtimeNs ?: return false
        return (SystemClock.elapsedRealtimeNanos() - startedNs) / 1_000_000 > FINISH_EXCHANGE_TIMEOUT_MS
    }

    private fun recordPairingMessage(direction: String, envelope: JSONObject) {
        pairingLog.add(JSONObject(envelope.toString()).put("direction", direction))
    }

    // ---- Finalize --------------------------------------------------------------------------------

    /** Stops sensor recording and builds session.json/pairing.json/manifest/signature/ZIP. Call after [finish] succeeds. */
    fun finalizeSession(): File? {
        if (state != SessionState.FINALIZING) return null
        sensorRecorder.stop()
        writePairingFile()
        val session = JSONObject()
            .put("sessionId", sessionId).put("participantId", participantId).put("role", role.jsonValue)
            .put("protocolVersion", 2).put("startedAtUtc", startedAtUtc).put("endedAtUtc", Instant.now().toString())
            .put("completionStatus", SessionState.COMPLETE.jsonValue)
            .put("appVersion", BuildConfig.VERSION_NAME)
            .put(
                "device",
                JSONObject().put("manufacturer", Build.MANUFACTURER).put("model", Build.MODEL)
                    .put("androidApi", Build.VERSION.SDK_INT).put("androidRelease", Build.VERSION.RELEASE),
            )
            .put("keySecurity", keyStore.securityReport())
            .put(
                "pairing",
                JSONObject().put("isPaired", partnerField != null).put("partnerRole", partnerField?.role?.jsonValue ?: JSONObject.NULL)
                    .put("partnerKeyId", partnerField?.keyId ?: JSONObject.NULL),
            )
            .put("sensorInventory", sensorRecorder.sensorInventory())
            .put("observationPoints", observationPointsJson())
            .put("droppedEventCount", journal.droppedEventCount)
        journal.record("finalize_started")
        journal.close()
        return runCatching { MeetingEvidenceStore.finalizeSession(sessionDirectory, session, keyStore.privateKey, keyStore.publicKey) }
            .onSuccess { apply(SessionCommand.FinalizeComplete) }
            .onFailure { apply(SessionCommand.Fail) }
            .getOrNull()
    }

    private fun writePairingFile() {
        val partnerInfo = partnerField ?: return
        val messages = JSONArray()
        pairingLog.forEach { messages.put(it) }
        val pairing = JSONObject()
            .put("schemaVersion", 2).put("sessionId", sessionId).put("isInitiator", isPairingInitiator)
            .put("partnerRole", partnerInfo.role.jsonValue).put("partnerKeyId", partnerInfo.keyId)
            .put("messages", messages)
        File(sessionDirectory, "pairing.json").writeText(pairing.toString(2), Charsets.UTF_8)
    }

    private fun observationPointsJson(): JSONArray {
        val array = JSONArray()
        observationPoints.values.forEach { point ->
            val stepsJson = JSONObject()
            point.stepStatuses.forEach { (index, status) -> stepsJson.put(index.toString(), status.jsonValue) }
            array.put(
                JSONObject().put("id", point.id).put("name", point.name).put("templateId", point.templateId.jsonValue)
                    .put("templateVersion", CaptureTemplates.byId(point.templateId).version)
                    .put("purpose", point.purpose ?: JSONObject.NULL).put("steps", stepsJson),
            )
        }
        return array
    }

    /** App went to background: recording stops immediately (plan section 4); state moves to INTERRUPTED. */
    fun interrupt(): Boolean {
        camera.unbind()
        sensorRecorder.stop()
        val moved = apply(SessionCommand.Interrupt)
        if (moved) journal.record("interrupted")
        journal.close()
        return moved
    }

    fun cancel(): Boolean {
        val moved = apply(SessionCommand.Cancel)
        if (moved) { journal.record("cancelled"); journal.close() }
        return moved
    }
}
