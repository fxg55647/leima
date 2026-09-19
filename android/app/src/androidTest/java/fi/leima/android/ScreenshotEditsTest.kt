package fi.leima.android

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Rect
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest
import java.util.zip.ZipFile

@RunWith(AndroidJUnit4::class)
class ScreenshotEditsTest {
    private fun original() = JSONObject().put("width", 6).put("height", 6)
        .put("url", "https://bank.example/account/private?token=secret#name")
        .put("title", "Private Name").put("sensorsAtRequest", JSONObject().put("location", "private"))

    @Test fun cropAndMasksAreFlattenedIntoExportedPixels() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val source = Bitmap.createBitmap(6, 6, Bitmap.Config.ARGB_8888).apply {
            eraseColor(Color.RED)
            for (y in 1..4) for (x in 1..4) setPixel(x, y, Color.GREEN)
        }
        val crop = Rect(1, 1, 5, 5)
        val masks = listOf(Rect(2, 2, 4, 4), Rect(0, 0, 2, 2))
        val output = ScreenshotEdits.render(source, crop, masks)
        val store = EvidenceStore(context)
        val directory = store.newDirectory()
        try {
            val media = File(directory, "screenshot.png")
            media.outputStream().use { assertTrue(output.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            val metadata = ScreenshotEdits.metadata(original(), crop, masks, false, false, false)
            val archive = store.finish(directory, media, metadata)
            ZipFile(archive).use { zip ->
                assertEquals(setOf("screenshot.png", "metadata.json", "manifest.json", "manifest.sha256"), zip.entries().asSequence().map { it.name }.toSet())
                val bytes = zip.getInputStream(zip.getEntry("screenshot.png")).use { it.readBytes() }
                val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                try {
                    assertEquals(4, decoded.width); assertEquals(4, decoded.height)
                    for (y in 0..3) for (x in 0..3) {
                        val covered = (x in 1..2 && y in 1..2) || (x == 0 && y == 0)
                        assertEquals(if (covered) Color.BLACK else Color.GREEN, decoded.getPixel(x, y))
                    }
                } finally { decoded.recycle() }
                val manifest = JSONObject(zip.getInputStream(zip.getEntry("manifest.json")).use { it.reader().readText() })
                val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
                assertEquals(hash, manifest.getJSONObject("files").getString("screenshot.png"))
                val details = zip.getInputStream(zip.getEntry("metadata.json")).use { it.reader().readText() }
                assertFalse(details.contains("secret")); assertFalse(details.contains("private")); assertFalse(details.contains("Private Name"))
            }
            // Editing never paints over the source; only the new output is persisted.
            assertEquals(Color.GREEN, source.getPixel(2, 2))
        } finally {
            output.recycle(); source.recycle()
            // Directory was created by this test under app-private evidence storage.
            directory.listFiles()?.forEach { it.delete() }; directory.delete()
        }
    }

    @Test fun optInStillRemovesUrlSecretsAndKeepsOriginalMetadataUnchanged() {
        val original = original()
        val result = ScreenshotEdits.metadata(original, Rect(0, 0, 6, 6), emptyList(), true, true, true)
        assertEquals("https://bank.example/account/private", result.getString("url"))
        assertTrue(result.has("title")); assertTrue(result.has("sensorsAtRequest"))
        assertTrue(original.getString("url").contains("token=secret"))
        assertFalse(original.has("edits"))
    }

    @Test fun defaultMetadataIncludesOriginOnlyAndNoSensorOrTitleFields() {
        val result = ScreenshotEdits.metadata(original(), Rect(1, 1, 5, 5), listOf(Rect(5, 5, 6, 6)), false, false, false)
        assertEquals("https://bank.example", result.getString("url"))
        assertFalse(result.has("title")); assertFalse(result.has("sensorsAtRequest"))
        assertEquals(0, result.getJSONObject("edits").getJSONArray("opaqueBlackMasks").length())
        assertEquals(4, result.getInt("width"))
    }

    @Test(expected = IllegalArgumentException::class) fun rejectsCropOutsideSource() {
        val source = Bitmap.createBitmap(2, 2, Bitmap.Config.ARGB_8888)
        try { ScreenshotEdits.render(source, Rect(-1, 0, 2, 2), emptyList()) }
        finally { source.recycle() }
    }
}
