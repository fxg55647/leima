package fi.leima.android.bridge

import android.net.LocalServerSocket
import android.net.LocalSocket
import android.net.LocalSocketAddress
import android.util.Log
import java.io.IOException
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * Listens on the abstract socket [BridgeProtocol.SOCKET_NAME], which the PC reaches through
 * `adb forward tcp:0 localabstract:fi.leima.android.bridge`. Phone loopback is shared by every
 * app, so no TCP port is opened; instead each peer's uid must be adbd's (shell or root).
 * Serves one connection at a time.
 */
class BridgeServer(private val newConnection: () -> BridgeConnection) {
    @Volatile private var running = false
    private var server: LocalServerSocket? = null
    private val busy = AtomicBoolean(false)
    @Volatile private var client: LocalSocket? = null

    @Synchronized fun start() {
        if (running) return
        val socket = LocalServerSocket(BridgeProtocol.SOCKET_NAME)
        server = socket
        running = true
        thread(name = "leima-bridge-accept", isDaemon = true) { acceptLoop(socket) }
    }

    @Synchronized fun stop() {
        if (!running) return
        running = false
        // LocalServerSocket.close() does not reliably unblock accept(); a throwaway self-connection
        // does. It is refused by the uid check like any other non-adb peer.
        runCatching { LocalSocket().use { it.connect(LocalSocketAddress(BridgeProtocol.SOCKET_NAME)) } }
        runCatching { server?.close() }
        runCatching { client?.close() }
        server = null
    }

    val isRunning: Boolean get() = running

    private fun acceptLoop(socket: LocalServerSocket) {
        while (running) {
            val peer = try { socket.accept() } catch (e: IOException) { if (running) Log.w(TAG, "accept failed", e); break }
            if (!running) { runCatching { peer.close() }; break }
            val uid = runCatching { peer.peerCredentials.uid }.getOrDefault(-1)
            if (uid !in BridgeProtocol.ALLOWED_PEER_UIDS) {
                Log.w(TAG, "Refused bridge connection from uid $uid")
                runCatching { peer.close() }
                continue
            }
            if (!busy.compareAndSet(false, true)) {
                runCatching {
                    peer.outputStream.write((BridgeProtocol.error(null, "BUSY", "Phone is already serving another bridge connection") + "\n").toByteArray())
                    peer.close()
                }
                continue
            }
            thread(name = "leima-bridge-client", isDaemon = true) {
                try { serve(peer) } finally { client = null; busy.set(false) }
            }
        }
    }

    private fun serve(peer: LocalSocket) {
        client = peer
        val connection = newConnection()
        peer.use {
            val input = peer.inputStream.buffered()
            val output = peer.outputStream
            try {
                while (running && !connection.closeRequested) {
                    val line = BridgeProtocol.readLine(input) ?: break
                    output.write((connection.handle(line) + "\n").toByteArray(Charsets.UTF_8))
                    output.flush()
                }
            } catch (e: LineTooLongException) {
                Log.w(TAG, "Closing bridge connection: ${e.message}")
            } catch (e: IOException) {
                Log.i(TAG, "Bridge connection ended: ${e.message}")
            }
        }
    }

    private companion object { const val TAG = "LeimaBridge" }
}
