package fi.leima.android.meeting

import android.graphics.Bitmap
import android.graphics.Color
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import org.json.JSONObject

/** Renders a [QrPairingProtocol] envelope as a displayable QR bitmap. Decoding lives in [QrAnalyzer]. */
object QrCodec {
    private val writer = QRCodeWriter()

    fun encode(envelope: JSONObject, sizePx: Int = 720): Bitmap {
        val text = envelope.toString()
        check(text.toByteArray(Charsets.UTF_8).size <= QrPairingProtocol.MAX_ENVELOPE_BYTES) {
            "QR envelope exceeds ${QrPairingProtocol.MAX_ENVELOPE_BYTES} bytes"
        }
        val hints = mapOf(EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M, EncodeHintType.MARGIN to 1)
        val matrix = writer.encode(text, BarcodeFormat.QR_CODE, sizePx, sizePx, hints)
        val bitmap = Bitmap.createBitmap(matrix.width, matrix.height, Bitmap.Config.RGB_565)
        for (x in 0 until matrix.width) {
            for (y in 0 until matrix.height) {
                bitmap.setPixel(x, y, if (matrix.get(x, y)) Color.BLACK else Color.WHITE)
            }
        }
        return bitmap
    }
}
