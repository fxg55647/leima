package fi.leima.android.meeting

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import org.json.JSONObject

/**
 * UI-facing state and commands for the meeting capture screens. A real [AndroidViewModel] (not a
 * plain class held by a Composable) is what survives configuration changes such as screen
 * rotation (plan section 4: "Näytön kierto säilyttää istuntotilan ViewModelissa"); the on-disk
 * journal remains the source of truth after a process death.
 *
 * The QR pairing/finish exchange is strictly sequential — show a code, then read a code, never
 * both at once (plan section 3.3: "Vaiheittainen käyttöliittymä kertoo aina Näytä koodi tai Lue
 * toisen koodi") — so [pendingOutgoingQr] and [awaitingScan] are never true/non-null together, and
 * [continuePastPendingQr] is the one place that decides what the next step is from
 * [MeetingCoordinator.state]/[MeetingCoordinator.isPairingInitiator].
 */
class MeetingViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = SessionRepository(File(application.filesDir, "meeting-sessions"))

    /** Held here (not `remember`-ed in a Composable) so it survives configuration changes and is shut down exactly once. */
    val captureExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    var coordinator: MeetingCoordinator? by mutableStateOf(null)
        private set
    var status by mutableStateOf("Valitse rooli aloittaaksesi.")
        private set
    var lastCapture: CaptureInfo? by mutableStateOf(null)
        private set
    var captureBusy by mutableStateOf(false)
        private set
    var currentObservationPointId: String? by mutableStateOf(null)
        private set

    var pendingOutgoingQr: JSONObject? by mutableStateOf(null)
        private set
    var awaitingScan by mutableStateOf(false)
        private set
    var pairingError: String? by mutableStateOf(null)
        private set

    // Distinguishes, for a non-initiator during CONFIRMING, whether the next scanned code should
    // be treated as finish_challenge (first) or finish_ack (second) — both start from the same
    // `awaitingScan = true` UI state.
    private var joinerAwaitingFinalAck = false

    /** Bumped whenever the on-disk session list changes, so a Composable can key off it to refresh [sessions]. */
    var sessionListVersion by mutableStateOf(0)
        private set

    fun currentObservationPoint(): ObservationPointInfo? =
        currentObservationPointId?.let { id -> coordinator?.observationPointList()?.firstOrNull { it.id == id } }

    // ---- Starting a session -------------------------------------------------------------------

    fun beginSolo(role: Role) {
        val directory = repository.newSessionDirectory()
        val newCoordinator = MeetingCoordinator(getApplication(), directory, role)
        newCoordinator.prepare()
        resetPairingUi()
        coordinator = newCoordinator
        currentObservationPointId = null
        sessionListVersion++
        status = "Istunto luotu. Käynnistä tallennus kun olet valmis."
    }

    fun beginPairingAsInitiator(role: Role) {
        val directory = repository.newSessionDirectory()
        val newCoordinator = MeetingCoordinator(getApplication(), directory, role)
        newCoordinator.beginPairing(asInitiator = true)
        resetPairingUi()
        coordinator = newCoordinator
        currentObservationPointId = null
        pendingOutgoingQr = newCoordinator.buildJoinInvite()
        sessionListVersion++
        status = "Näytä kutsukoodi toiselle puhelimelle."
    }

    fun beginPairingAsJoiner(role: Role) {
        val directory = repository.newSessionDirectory()
        val newCoordinator = MeetingCoordinator(getApplication(), directory, role)
        newCoordinator.beginPairing(asInitiator = false)
        resetPairingUi()
        coordinator = newCoordinator
        currentObservationPointId = null
        awaitingScan = true
        sessionListVersion++
        status = "Skannaa toisen puhelimen kutsukoodi."
    }

    private fun resetPairingUi() {
        pendingOutgoingQr = null
        awaitingScan = false
        pairingError = null
        joinerAwaitingFinalAck = false
    }

    /** Clears the current observation point so the UI shows the template picker for a new one. */
    fun promptNewObservationPoint() {
        currentObservationPointId = null
    }

    /** Returns to role selection so the user can start a fresh session after COMPLETE/INTERRUPTED/CANCELLED/FAILED. */
    fun startNewSession() {
        coordinator?.let { if (MeetingStateMachine.isActive(it.state)) it.interrupt() }
        coordinator = null
        currentObservationPointId = null
        resetPairingUi()
        status = "Valitse rooli aloittaaksesi."
    }

    fun startRecording() {
        status = if (coordinator?.startRecording() == true) "Tallennus käynnissä." else "Tallennuksen käynnistys epäonnistui."
    }

    // ---- QR pairing / finish exchange ----------------------------------------------------------

    /**
     * Feeds one decoded QR text into whichever step of pairing/finishing is currently active.
     * Guarded on [awaitingScan]: once a scan succeeds it flips to false and the screen swaps away
     * from the camera, but a frame already in flight can still deliver one more decode before the
     * camera actually unbinds — without this guard that stray frame would be reprocessed as if it
     * were the *next* expected message and rejected with a confusing transient error.
     */
    fun onQrScanned(raw: String) {
        if (!awaitingScan) return
        val current = coordinator ?: return
        pairingError = null
        when (current.state) {
            SessionState.PAIRING -> onQrScannedDuringPairing(current, raw)
            SessionState.CONFIRMING -> onQrScannedDuringConfirming(current, raw)
            else -> Unit
        }
    }

    private fun onQrScannedDuringPairing(current: MeetingCoordinator, raw: String) {
        if (current.partner == null) {
            // Joiner's first scan: the initiator's join_invite.
            val partner = current.acceptJoinInvite(raw)
            if (partner != null) {
                pendingOutgoingQr = current.buildJoinResponse()
                awaitingScan = false
                status = "Näytä liittymisvastaus toiselle puhelimelle."
            } else {
                pairingError = "Kutsukoodia ei voitu lukea. Yritä uudelleen."
            }
        } else {
            // Initiator's scan: the joiner's join_response.
            if (current.acceptJoinResponse(raw)) {
                awaitingScan = false
                status = "Pariutuminen onnistui. Käynnistä tallennus."
            } else {
                pairingError = "Liittymisvastausta ei voitu vahvistaa. Yritä uudelleen."
            }
        }
    }

    private fun onQrScannedDuringConfirming(current: MeetingCoordinator, raw: String) {
        if (current.isPairingInitiator) {
            // Initiator's only scan here: the partner's finish_response.
            val ack = current.acceptFinishResponseAndBuildAck(raw)
            if (ack != null) {
                pendingOutgoingQr = ack
                awaitingScan = false
                status = "Näytä kuittauskoodi toiselle puhelimelle."
            } else {
                pairingError = "Vastauskoodia ei voitu vahvistaa. Yritä uudelleen."
            }
            return
        }
        if (!joinerAwaitingFinalAck) {
            val response = current.acceptFinishChallengeAndBuildResponse(raw)
            if (response != null) {
                pendingOutgoingQr = response
                awaitingScan = false
                joinerAwaitingFinalAck = true
                status = "Näytä vastauskoodi toiselle puhelimelle."
            } else {
                pairingError = "Haastekoodia ei voitu vahvistaa. Yritä uudelleen."
            }
        } else {
            if (current.acceptFinishAck(raw)) {
                awaitingScan = false
                joinerAwaitingFinalAck = false
                finalizeAndReport(current)
            } else {
                pairingError = "Kuittausta ei voitu vahvistaa. Yritä uudelleen."
            }
        }
    }

    /** The single "Jatka" action after a shown QR code; what happens next depends on where the coordinator is. */
    fun continuePastPendingQr() {
        val current = coordinator ?: return
        pendingOutgoingQr = null
        pairingError = null
        when {
            current.state == SessionState.PAIRING && current.isPairingInitiator -> awaitingScan = true // now scan their join_response
            current.state == SessionState.PAIRING && !current.isPairingInitiator -> {
                if (current.confirmJoinResponseShown()) status = "Pariutuminen onnistui. Käynnistä tallennus."
            }
            current.state == SessionState.CONFIRMING && !current.isPairingInitiator -> awaitingScan = true // now scan their finish_ack
            current.state == SessionState.FINALIZING -> finalizeAndReport(current) // initiator just showed finish_ack
        }
    }

    // ---- Recording ------------------------------------------------------------------------------

    fun addObservationPoint(name: String, templateId: TemplateId, purpose: String? = null) {
        val point = coordinator?.addObservationPoint(name, templateId, purpose)
        if (point != null) {
            currentObservationPointId = point.id
            status = "Havaintopaikka '${point.name}' lisätty."
        } else {
            status = "Havaintopaikkaa ei voitu lisätä nyt."
        }
    }

    fun skipStep(stepIndex: Int) {
        val pointId = currentObservationPointId ?: return
        coordinator?.skipStep(pointId, stepIndex)
    }

    fun requestCapture(shotType: ShotType, purpose: String?, overviewCaptureId: String?, targetRotation: Int) {
        val current = coordinator ?: return
        if (captureBusy) return
        if (current.captureList().size >= MeetingCoordinator.MAX_CAPTURES) {
            status = "Istunnon kuvaraja (${MeetingCoordinator.MAX_CAPTURES}) täynnä. Vahvista kohtaaminen tai aloita uusi istunto."
            return
        }
        if (current.isOverTimeBudget) {
            status = "Istunnon 10 minuutin kokeiluraja täynnä. Vahvista kohtaaminen tai aloita uusi istunto."
            return
        }
        captureBusy = true
        val started = current.requestCapture(currentObservationPointId, shotType, purpose, overviewCaptureId, targetRotation, captureExecutor) { result ->
            lastCapture = result
            captureBusy = false
            status = when (result.status) {
                CaptureStatus.SAVED -> "Kuva tallennettu (${result.sequenceNumber})."
                CaptureStatus.FAILED -> "Kuvaus epäonnistui: ${result.errorMessage}"
                CaptureStatus.REQUESTED -> status
            }
        }
        if (started == null) captureBusy = false
    }

    // ---- Finish / finalize ------------------------------------------------------------------------

    /** "Vahvista kohtaaminen". Solo finalizes immediately; a paired session enters the finish QR exchange. */
    fun confirmMeeting() {
        val current = coordinator ?: return
        if (!current.finish()) {
            status = "Kohtaamisen vahvistus ei onnistunut nyt."
            return
        }
        if (current.state == SessionState.CONFIRMING) {
            if (current.isPairingInitiator) {
                pendingOutgoingQr = current.buildFinishChallenge()
                status = "Näytä haastekoodi toiselle puhelimelle."
            } else {
                awaitingScan = true
                status = "Skannaa toisen puhelimen haastekoodi."
            }
            return
        }
        finalizeAndReport(current)
    }

    private fun finalizeAndReport(current: MeetingCoordinator) {
        val zip = current.finalizeSession()
        status = if (zip != null) "Paketti valmis. Voit viedä sen ZIP-tiedostona." else "Paketin viimeistely epäonnistui."
        if (zip != null) sessionListVersion++
    }

    fun interrupt() {
        coordinator?.interrupt()
        resetPairingUi()
        status = "Tallennus keskeytyi. Voit viedä keskeneräisen aineiston tai aloittaa uuden istunnon."
    }

    fun sessions() = repository.list()
    fun zipFile(sessionId: String) = repository.zipFile(sessionId)
    fun deleteSession(sessionId: String) {
        repository.delete(sessionId)
        sessionListVersion++
    }

    override fun onCleared() {
        coordinator?.let { if (MeetingStateMachine.isActive(it.state)) it.interrupt() }
        captureExecutor.shutdown()
    }
}
