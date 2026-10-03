package fi.leima.android.bridge

import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

data class PendingPairing(val bridgeName: String, val code: String, internal val answer: CompletableFuture<Boolean>)

/** Bridges the protocol thread's blocking [requestApproval] to a Compose dialog on the main thread. */
class PairingPrompt : PairingApprover {
    private val main = Handler(Looper.getMainLooper())
    var pending by mutableStateOf<PendingPairing?>(null)
        private set
    private var open: PendingPairing? = null

    override fun requestApproval(bridgeName: String, code: String, timeoutMs: Long): PairingDecision {
        val request = synchronized(this) {
            if (open != null) return PairingDecision.BUSY
            PendingPairing(bridgeName, code, CompletableFuture()).also { open = it }
        }
        main.post { pending = request }
        return try {
            if (request.answer.get(timeoutMs, TimeUnit.MILLISECONDS)) PairingDecision.APPROVED else PairingDecision.REJECTED
        } catch (e: TimeoutException) {
            PairingDecision.TIMEOUT
        } finally {
            synchronized(this) { open = null }
            main.post { if (pending === request) pending = null }
        }
    }

    /** Called from the dialog. */
    fun answer(request: PendingPairing, approved: Boolean) {
        request.answer.complete(approved)
        if (pending === request) pending = null
    }
}
