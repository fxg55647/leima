package fi.leima.android.meeting

/**
 * Every session-level transition (plan section 4: `IDLE → PAIRING → READY → RECORDING →
 * CONFIRMING → FINALIZING → COMPLETE`, plus the `INTERRUPTED`/`CANCELLED`/`FAILED` error states).
 * `PAIRING`/`CONFIRMING` are reserved for the Vaihe 2 QR exchange; Vaihe 1 only drives the solo
 * path (no [FinishPaired]/[PairingConfirmed]).
 *
 * Commands are validated here, not by disabling buttons in the UI, so a stale UI state or a
 * delayed callback can never apply an illegal transition (plan section 4: "Kaikki komennot
 * tarkistetaan tilakoneessa, ei pelkästään nappien enabled-tilassa").
 */
sealed class SessionCommand {
    object ReadyToRecord : SessionCommand()
    object StartRecording : SessionCommand()
    object FinishSolo : SessionCommand()
    object FinishPaired : SessionCommand()
    object PairingConfirmed : SessionCommand()
    object FinalizeComplete : SessionCommand()
    object Interrupt : SessionCommand()
    object Cancel : SessionCommand()
    object Fail : SessionCommand()
}

object MeetingStateMachine {
    private val interruptible = setOf(SessionState.READY, SessionState.RECORDING, SessionState.CONFIRMING, SessionState.FINALIZING)
    private val cancellable = setOf(SessionState.IDLE, SessionState.READY)
    private val terminal = setOf(SessionState.COMPLETE, SessionState.INTERRUPTED, SessionState.CANCELLED, SessionState.FAILED)

    fun isActive(state: SessionState): Boolean = state !in terminal

    /** Returns the resulting state, or null if `command` is not legal from `current`. */
    fun transition(current: SessionState, command: SessionCommand): SessionState? = when (command) {
        SessionCommand.ReadyToRecord -> onlyFrom(current, SessionState.IDLE, SessionState.READY)
        SessionCommand.StartRecording -> onlyFrom(current, SessionState.READY, SessionState.RECORDING)
        SessionCommand.FinishSolo -> onlyFrom(current, SessionState.RECORDING, SessionState.FINALIZING)
        SessionCommand.FinishPaired -> onlyFrom(current, SessionState.RECORDING, SessionState.CONFIRMING)
        SessionCommand.PairingConfirmed -> onlyFrom(current, SessionState.CONFIRMING, SessionState.FINALIZING)
        SessionCommand.FinalizeComplete -> onlyFrom(current, SessionState.FINALIZING, SessionState.COMPLETE)
        SessionCommand.Interrupt -> if (current in interruptible) SessionState.INTERRUPTED else null
        SessionCommand.Cancel -> if (current in cancellable) SessionState.CANCELLED else null
        SessionCommand.Fail -> if (current !in terminal) SessionState.FAILED else null
    }

    private fun onlyFrom(current: SessionState, required: SessionState, next: SessionState): SessionState? =
        if (current == required) next else null
}
