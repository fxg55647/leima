package fi.leima.android.meeting

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * UI-facing state and commands for the meeting capture screens. A real [AndroidViewModel] (not a
 * plain class held by a Composable) is what survives configuration changes such as screen
 * rotation (plan section 4: "Näytön kierto säilyttää istuntotilan ViewModelissa"); the on-disk
 * journal remains the source of truth after a process death.
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

    /** Bumped whenever the on-disk session list changes, so a Composable can key off it to refresh [sessions]. */
    var sessionListVersion by mutableStateOf(0)
        private set

    fun currentObservationPoint(): ObservationPointInfo? =
        currentObservationPointId?.let { id -> coordinator?.observationPointList()?.firstOrNull { it.id == id } }

    fun beginSession(role: Role) {
        val directory = repository.newSessionDirectory()
        val newCoordinator = MeetingCoordinator(getApplication(), directory, role)
        newCoordinator.prepare()
        coordinator = newCoordinator
        currentObservationPointId = null
        sessionListVersion++
        status = "Istunto luotu. Käynnistä tallennus kun olet valmis."
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
        status = "Valitse rooli aloittaaksesi."
    }

    fun startRecording() {
        status = if (coordinator?.startRecording() == true) "Tallennus käynnissä." else "Tallennuksen käynnistys epäonnistui."
    }

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

    fun finishAndExport(): File? {
        val current = coordinator ?: return null
        if (!current.finish()) {
            status = "Kohtaamisen vahvistus ei onnistunut nyt."
            return null
        }
        val zip = current.finalizeSession()
        status = if (zip != null) "Paketti valmis. Voit viedä sen ZIP-tiedostona." else "Paketin viimeistely epäonnistui."
        if (zip != null) sessionListVersion++
        return zip
    }

    fun interrupt() {
        coordinator?.interrupt()
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
