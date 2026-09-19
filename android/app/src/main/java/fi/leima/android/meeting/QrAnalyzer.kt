package fi.leima.android.meeting

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.NotFoundException
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader

/**
 * Decodes QR codes from the camera's luma (Y) plane only — chroma is never read, and no frame is
 * ever written to disk or handed anywhere else (plan section 6: "QR-lukijan kameraruudut
 * käsitellään muistissa eikä niitä sisällytetä todistajan pakettiin"). The bound [ImageAnalysis]
 * use case must set `STRATEGY_KEEP_ONLY_LATEST`; every [ImageProxy] is closed here, including on
 * decode failure, so a slow analyzer can never stall the camera pipeline.
 *
 * QR's own finder patterns make ZXing tolerant of in-plane rotation, so the luma buffer is read
 * as-is without correcting for `imageInfo.rotationDegrees`.
 */
class QrAnalyzer(private val onDecoded: (String) -> Unit) : ImageAnalysis.Analyzer {
    private val reader = QRCodeReader()
    private val hints = mapOf(DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE))

    override fun analyze(image: ImageProxy) {
        try {
            val plane = image.planes[0]
            val luma = extractLuma(plane.buffer, image.width, image.height, plane.rowStride, plane.pixelStride)
            val source = PlanarYUVLuminanceSource(luma, image.width, image.height, 0, 0, image.width, image.height, false)
            val bitmap = BinaryBitmap(HybridBinarizer(source))
            val result = reader.decode(bitmap, hints)
            onDecoded(result.text)
        } catch (_: NotFoundException) {
            // No QR code in this frame; expected on most frames while aiming the camera.
        } catch (_: Exception) {
            // Corrupt or unreadable frame; drop it and wait for the next one.
        } finally {
            reader.reset()
            image.close()
        }
    }

    private fun extractLuma(buffer: java.nio.ByteBuffer, width: Int, height: Int, rowStride: Int, pixelStride: Int): ByteArray {
        val data = ByteArray(buffer.remaining())
        buffer.get(data)
        if (pixelStride == 1 && rowStride == width) return data
        val out = ByteArray(width * height)
        for (row in 0 until height) {
            val rowStart = row * rowStride
            for (col in 0 until width) out[row * width + col] = data[rowStart + col * pixelStride]
        }
        return out
    }
}
