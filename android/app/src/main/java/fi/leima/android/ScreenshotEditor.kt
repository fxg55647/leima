package fi.leima.android

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import android.widget.ImageView
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.SecureFlagPolicy
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.*

data class PendingScreenshot(val bitmap: Bitmap, val metadata: JSONObject)

/** Only the returned bitmap may be persisted. No source pixels outside crop survive. */
object ScreenshotEdits {
    fun render(source: Bitmap, crop: Rect, masks: List<Rect>): Bitmap {
        require(crop.width() > 0 && crop.height() > 0)
        require(crop.left >= 0 && crop.top >= 0 && crop.right <= source.width && crop.bottom <= source.height)
        val output = Bitmap.createBitmap(crop.width(), crop.height(), Bitmap.Config.ARGB_8888)
        Canvas(output).apply {
            drawBitmap(source, crop, Rect(0, 0, output.width, output.height), null)
            val paint = Paint().apply { color = Color.BLACK; isAntiAlias = false }
            masks.forEach { mask ->
                val clipped = Rect(mask)
                if (clipped.intersect(crop)) {
                    clipped.offset(-crop.left, -crop.top)
                    drawRect(clipped, paint)
                }
            }
        }
        return output
    }

    fun metadata(original: JSONObject, crop: Rect, masks: List<Rect>, includePath: Boolean, includeTitle: Boolean, includeSensors: Boolean): JSONObject {
        val result = JSONObject(original.toString())
        val url = result.optString("url")
        val uri = android.net.Uri.parse(url)
        // Even when paths are included, query parameters, credentials and fragments are never exported.
        val publicUrl = if (uri.scheme == "https" && !uri.host.isNullOrBlank()) {
            uri.buildUpon().encodedAuthority(uri.host + if (uri.port != -1) ":${uri.port}" else "")
                .encodedPath(if (includePath) uri.encodedPath else "")
                .clearQuery().fragment(null).build().toString()
        } else ""
        result.put("url", publicUrl)
        if (!includeTitle) result.remove("title")
        if (!includeSensors) { result.remove("sensorsAtRequest"); result.remove("sensorsAtCompletion") }
        fun coordinates(rect: Rect) = JSONObject().put("left", rect.left).put("top", rect.top)
            .put("right", rect.right).put("bottom", rect.bottom)
        val visibleMasks = masks.mapNotNull { mask -> Rect(mask).takeIf { it.intersect(crop) } }
        result.put("edits", JSONObject().put("version", 1)
            .put("coordinateSpace", "source viewport pixels; right and bottom exclusive")
            .put("sourceWidth", original.getInt("width")).put("sourceHeight", original.getInt("height"))
            .put("crop", coordinates(crop)).put("opaqueBlackMasks", JSONArray(visibleMasks.map(::coordinates))))
        result.put("width", crop.width()).put("height", crop.height())
        result.put("privacy", JSONObject().put("urlScope", if (includePath) "origin_and_path" else "origin")
            .put("queryAndFragmentRemoved", true).put("titleIncluded", includeTitle)
            .put("sensorsIncluded", includeSensors).put("originalImageStored", false))
        return result
    }
}

@Composable
fun ScreenshotEditor(pending: PendingScreenshot, onCancel: () -> Unit, onSave: (Bitmap, JSONObject) -> Unit) {
    var editor by remember { mutableStateOf<CropEditorView?>(null) }
    var redact by remember { mutableStateOf(false) }
    var includePath by remember { mutableStateOf(false) }
    var includeTitle by remember { mutableStateOf(false) }
    var includeSensors by remember { mutableStateOf(false) }
    var preview by remember { mutableStateOf<Bitmap?>(null) }
    var metadata by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var submitted by remember { mutableStateOf(false) }
    DisposableEffect(pending) {
        onDispose { preview?.recycle(); pending.bitmap.recycle() }
    }
    Dialog(onDismissRequest = onCancel, properties = DialogProperties(usePlatformDefaultWidth = false, securePolicy = SecureFlagPolicy.SecureOn)) {
        Surface(Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().systemBarsPadding().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(if (preview == null) "Rajaa ja peitä" else "Tarkista tallennettava paketti", style = MaterialTheme.typography.titleLarge)
                if (preview == null) {
                    Text(if (redact) "Vedä peitettävän tiedon päälle musta suorakulmio." else "Siirrä rajausta sisältä. Venytä reunoista tai kulmista.")
                    Row {
                        TextButton(onClick = { redact = false }) { Text(if (!redact) "✓ Rajaa" else "Rajaa") }
                        TextButton(onClick = { redact = true }) { Text(if (redact) "✓ Peitä" else "Peitä") }
                        TextButton(onClick = { editor?.undoMask() }) { Text("Peru peitto") }
                        TextButton(onClick = { editor?.reset() }) { Text("Nollaa") }
                    }
                }
                // Keep the editor mounted under preview so Back preserves the exact edits.
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    AndroidView(modifier = Modifier.fillMaxSize(), factory = { CropEditorView(it, pending.bitmap).also { view -> editor = view } },
                        update = { it.redact = redact; it.visibility = if (preview == null) View.VISIBLE else View.INVISIBLE })
                    preview?.let { bitmap ->
                        AndroidView(modifier = Modifier.fillMaxSize(), factory = { ImageView(it).apply { scaleType = ImageView.ScaleType.FIT_CENTER } }, update = { it.setImageBitmap(bitmap) })
                    }
                }
                if (preview == null) {
                    Text("Mukana aina: verkkotunnus, kuvausajat ja laitetiedot. Osoitteen kyselyt ja ankkuri poistetaan.", style = MaterialTheme.typography.bodySmall)
                    Column(Modifier.heightIn(max = 160.dp).verticalScroll(rememberScrollState())) {
                        PrivacyOption("Lisää osoitteen polku (voi sisältää henkilötietoja)", includePath) { includePath = it }
                        PrivacyOption("Lisää sivun otsikko", includeTitle) { includeTitle = it }
                        PrivacyOption("Lisää sensorit ja mahdollinen sijainti", includeSensors) { includeSensors = it }
                    }
                } else {
                    Text("Vain yllä näkyvä kuva ja seuraavat metatiedot tallennetaan. Alkuperäistä kuvaa ei tallenneta.", style = MaterialTheme.typography.bodySmall)
                    Text(metadata!!.toString(2), modifier = Modifier.fillMaxWidth().heightIn(max = 160.dp).verticalScroll(rememberScrollState()), style = MaterialTheme.typography.bodySmall)
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(enabled = !submitted, onClick = onCancel) { Text("Peruuta") }
                    if (preview != null) TextButton(enabled = !submitted, onClick = { preview?.recycle(); preview = null; metadata = null }) { Text("Muokkaa") }
                    Button(enabled = !submitted, onClick = {
                        runCatching {
                            if (preview == null) {
                                val view = requireNotNull(editor)
                                val crop = view.cropPixels()
                                val masks = view.maskPixels()
                                metadata = ScreenshotEdits.metadata(pending.metadata, crop, masks, includePath, includeTitle, includeSensors)
                                preview = ScreenshotEdits.render(pending.bitmap, crop, masks)
                            } else {
                                // Transfer a separate bitmap to the writer; dialog disposal owns its preview.
                                val output = requireNotNull(preview!!.copy(Bitmap.Config.ARGB_8888, false))
                                submitted = true
                                onSave(output, requireNotNull(metadata))
                            }
                        }.onFailure { error = "Kuvan käsittely epäonnistui. Kokeile uudelleen."; submitted = false }
                    }) { Text(if (preview == null) "Esikatsele" else "Hyväksy ja tallenna") }
                }
            }
        }
    }
}

@Composable private fun PrivacyOption(label: String, checked: Boolean, change: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Checkbox(checked = checked, onCheckedChange = change)
        Text(label, style = MaterialTheme.typography.bodySmall)
    }
}

/** Editor coordinates stay in source pixels, independently of letterboxing or display size. */
class CropEditorView(context: Context, private val source: Bitmap) : View(context) {
    var redact = false
    private val crop = RectF(0f, 0f, source.width.toFloat(), source.height.toFloat())
    private val masks = mutableListOf<RectF>()
    private val paint = Paint()
    private var scale = 1f
    private var ox = 0f
    private var oy = 0f
    private var downX = 0f
    private var downY = 0f
    private var initial = RectF(crop)
    private var edges = 0
    private var drawingMask: RectF? = null
    private var dragging = false
    init { contentDescription = "Kuvan rajaus. Vedä reunoja tai kulmia; peittotilassa piirrä peitto." }
    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        scale = min(w.toFloat() / source.width, h.toFloat() / source.height).coerceAtLeast(0.001f)
        ox = (w - source.width * scale) / 2; oy = (h - source.height * scale) / 2
    }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(Color.DKGRAY)
        canvas.save(); canvas.translate(ox, oy); canvas.scale(scale, scale)
        paint.reset(); canvas.drawBitmap(source, 0f, 0f, paint)
        paint.color = Color.BLACK
        masks.forEach { canvas.drawRect(it, paint) }; drawingMask?.let { canvas.drawRect(it, paint) }
        paint.color = 0x99000000.toInt()
        canvas.drawRect(0f, 0f, source.width.toFloat(), crop.top, paint)
        canvas.drawRect(0f, crop.bottom, source.width.toFloat(), source.height.toFloat(), paint)
        canvas.drawRect(0f, crop.top, crop.left, crop.bottom, paint)
        canvas.drawRect(crop.right, crop.top, source.width.toFloat(), crop.bottom, paint)
        paint.color = Color.WHITE; paint.style = Paint.Style.STROKE; paint.strokeWidth = 2 * resources.displayMetrics.density / scale
        canvas.drawRect(crop, paint)
        paint.style = Paint.Style.FILL
        val radius = 5 * resources.displayMetrics.density / scale
        listOf(crop.left to crop.top, crop.right to crop.top, crop.left to crop.bottom, crop.right to crop.bottom,
            crop.centerX() to crop.top, crop.centerX() to crop.bottom, crop.left to crop.centerY(), crop.right to crop.centerY()).forEach {
            canvas.drawCircle(it.first, it.second, radius, paint)
        }
        canvas.restore()
    }
    override fun onTouchEvent(event: MotionEvent): Boolean {
        val x = ((event.x - ox) / scale).coerceIn(0f, source.width.toFloat())
        val y = ((event.y - oy) / scale).coerceIn(0f, source.height.toFloat())
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (event.x < ox || event.x > ox + source.width * scale || event.y < oy || event.y > oy + source.height * scale) return false
                downX = x; downY = y; initial = RectF(crop); edges = 0
                val hit = min(24 * resources.displayMetrics.density / scale, min(crop.width(), crop.height()) / 3)
                if (redact) drawingMask = RectF(x, y, x, y) else {
                    if (!RectF(crop).apply { inset(-hit, -hit) }.contains(x, y)) return false
                    if (abs(x - crop.left) <= hit) edges = edges or 1
                    if (abs(x - crop.right) <= hit) edges = edges or 2
                    if (abs(y - crop.top) <= hit) edges = edges or 4
                    if (abs(y - crop.bottom) <= hit) edges = edges or 8
                }
                dragging = true; parent?.requestDisallowInterceptTouchEvent(true)
            }
            MotionEvent.ACTION_MOVE, MotionEvent.ACTION_UP -> {
                if (!dragging) return false
                if (drawingMask != null) drawingMask = RectF(min(downX, x), min(downY, y), max(downX, x), max(downY, y))
                else {
                    val dx = x - downX; val dy = y - downY
                    val minimum = min(24f, min(source.width, source.height).toFloat())
                    if (edges == 0) {
                        crop.set(initial); crop.offset(dx.coerceIn(-initial.left, source.width - initial.right), dy.coerceIn(-initial.top, source.height - initial.bottom))
                    } else {
                        if (edges and 1 != 0) crop.left = (initial.left + dx).coerceIn(0f, initial.right - minimum)
                        if (edges and 2 != 0) crop.right = (initial.right + dx).coerceIn(initial.left + minimum, source.width.toFloat())
                        if (edges and 4 != 0) crop.top = (initial.top + dy).coerceIn(0f, initial.bottom - minimum)
                        if (edges and 8 != 0) crop.bottom = (initial.bottom + dy).coerceIn(initial.top + minimum, source.height.toFloat())
                    }
                }
                if (event.actionMasked == MotionEvent.ACTION_UP) {
                    drawingMask?.let { if (it.width() >= 1 && it.height() >= 1) masks.add(RectF(it)) }
                    drawingMask = null; dragging = false; performClick(); parent?.requestDisallowInterceptTouchEvent(false)
                }
            }
            MotionEvent.ACTION_CANCEL -> { crop.set(initial); drawingMask = null; dragging = false; parent?.requestDisallowInterceptTouchEvent(false) }
            else -> return true
        }
        invalidate(); return true
    }
    override fun performClick(): Boolean { super.performClick(); return true }
    fun cropPixels() = Rect(ceil(crop.left).toInt(), ceil(crop.top).toInt(), floor(crop.right).toInt(), floor(crop.bottom).toInt())
    fun maskPixels() = masks.map { Rect(floor(it.left).toInt(), floor(it.top).toInt(), ceil(it.right).toInt(), ceil(it.bottom).toInt()) }
    fun undoMask() { if (masks.isNotEmpty()) masks.removeAt(masks.lastIndex); invalidate() }
    fun reset() { crop.set(0f, 0f, source.width.toFloat(), source.height.toFloat()); masks.clear(); invalidate() }
}
