package fi.leima.android.meeting

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MeetingStateMachineTest {
    @Test
    fun soloHappyPath() {
        var state = SessionState.IDLE
        state = MeetingStateMachine.transition(state, SessionCommand.ReadyToRecord)!!
        assertEquals(SessionState.READY, state)
        state = MeetingStateMachine.transition(state, SessionCommand.StartRecording)!!
        assertEquals(SessionState.RECORDING, state)
        state = MeetingStateMachine.transition(state, SessionCommand.FinishSolo)!!
        assertEquals(SessionState.FINALIZING, state)
        state = MeetingStateMachine.transition(state, SessionCommand.FinalizeComplete)!!
        assertEquals(SessionState.COMPLETE, state)
    }

    @Test
    fun pairedHappyPath() {
        var state = SessionState.RECORDING
        state = MeetingStateMachine.transition(state, SessionCommand.FinishPaired)!!
        assertEquals(SessionState.CONFIRMING, state)
        state = MeetingStateMachine.transition(state, SessionCommand.PairingConfirmed)!!
        assertEquals(SessionState.FINALIZING, state)
    }

    @Test
    fun doubleShutterDoesNotDoubleFinalize() {
        // FinishSolo is only legal from RECORDING; once FINALIZING, a repeated tap is rejected.
        val finalizing = MeetingStateMachine.transition(SessionState.RECORDING, SessionCommand.FinishSolo)
        assertEquals(SessionState.FINALIZING, finalizing)
        assertNull(MeetingStateMachine.transition(finalizing!!, SessionCommand.FinishSolo))
    }

    @Test
    fun captureAfterQrPhaseIsRejected() {
        // Once past RECORDING there is no legal path back to it.
        assertNull(MeetingStateMachine.transition(SessionState.CONFIRMING, SessionCommand.StartRecording))
        assertNull(MeetingStateMachine.transition(SessionState.FINALIZING, SessionCommand.StartRecording))
    }

    @Test
    fun lateCallbackCannotFinalizeFromWrongState() {
        assertNull(MeetingStateMachine.transition(SessionState.RECORDING, SessionCommand.FinalizeComplete))
        assertNull(MeetingStateMachine.transition(SessionState.CONFIRMING, SessionCommand.FinalizeComplete))
    }

    @Test
    fun interruptionAllowedWhileActiveNotFromIdleOrTerminal() {
        for (state in listOf(SessionState.READY, SessionState.RECORDING, SessionState.CONFIRMING, SessionState.FINALIZING)) {
            assertEquals(SessionState.INTERRUPTED, MeetingStateMachine.transition(state, SessionCommand.Interrupt))
        }
        assertNull(MeetingStateMachine.transition(SessionState.IDLE, SessionCommand.Interrupt))
        assertNull(MeetingStateMachine.transition(SessionState.COMPLETE, SessionCommand.Interrupt))
    }

    @Test
    fun cancelOnlyBeforeRecordingStarts() {
        assertEquals(SessionState.CANCELLED, MeetingStateMachine.transition(SessionState.IDLE, SessionCommand.Cancel))
        assertEquals(SessionState.CANCELLED, MeetingStateMachine.transition(SessionState.READY, SessionCommand.Cancel))
        assertNull(MeetingStateMachine.transition(SessionState.RECORDING, SessionCommand.Cancel))
    }

    @Test
    fun failNotAllowedFromTerminalStates() {
        for (state in listOf(SessionState.COMPLETE, SessionState.INTERRUPTED, SessionState.CANCELLED, SessionState.FAILED)) {
            assertNull(MeetingStateMachine.transition(state, SessionCommand.Fail))
        }
        assertEquals(SessionState.FAILED, MeetingStateMachine.transition(SessionState.RECORDING, SessionCommand.Fail))
    }

    @Test
    fun isActiveReflectsTerminalStates() {
        assertEquals(true, MeetingStateMachine.isActive(SessionState.RECORDING))
        assertEquals(false, MeetingStateMachine.isActive(SessionState.COMPLETE))
        assertEquals(false, MeetingStateMachine.isActive(SessionState.FAILED))
    }
}
