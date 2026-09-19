package fi.leima.android.meeting

import java.io.File
import java.security.KeyPairGenerator
import java.security.spec.ECGenParameterSpec
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class SessionRepositoryTest {
    @get:Rule val tmp = TemporaryFolder()

    @Test
    fun listsFinalizedAndUnfinishedSessionsAndSupportsExportAndDelete() {
        val repo = SessionRepository(tmp.newFolder())

        val keyPair = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        val finished = repo.newSessionDirectory("finished-1")
        MeetingEvidenceStore.finalizeSession(finished, JSONObject().put("sessionId", "finished-1"), keyPair.private, keyPair.public)

        val unfinished = repo.newSessionDirectory("unfinished-1")
        File(unfinished, "events.jsonl").writeText("{}\n")

        val summaries = repo.list().associateBy { it.sessionId }
        assertEquals(2, summaries.size)
        assertTrue(summaries.getValue("finished-1").isFinalized)
        assertFalse(summaries.getValue("unfinished-1").isFinalized)

        assertNotNull(repo.zipFile("finished-1"))
        assertNull(repo.zipFile("unfinished-1"))
        assertNull(repo.zipFile("does-not-exist"))

        assertTrue(repo.delete("finished-1"))
        assertEquals(1, repo.list().size)
    }
}
