package fi.leima.android.meeting

import android.content.Context
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.lifecycle.LifecycleOwner
import java.io.File
import java.util.concurrent.Executor

/**
 * CameraX Preview + ImageCapture lifecycle for the meeting capture screen. Kept separate from QR
 * analysis (Vaihe 2 [QrAnalyzer]): if Preview + ImageCapture + ImageAnalysis together prove
 * unreliable bound at once on some device, the two capture modes can be time-sliced through this
 * class without changing QR code (plan section 6).
 */
class CameraCaptureController(private val context: Context) {
    private var provider: ProcessCameraProvider? = null
    private var imageCapture: ImageCapture? = null

    val isReady: Boolean get() = imageCapture != null

    /** Binds the camera to `owner`'s lifecycle and the given preview surface. */
    fun bind(owner: LifecycleOwner, previewView: PreviewView, executor: Executor, onReady: () -> Unit, onError: (Throwable) -> Unit) {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            runCatching {
                val cameraProvider = future.get()
                val preview = Preview.Builder().build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
                val capture = ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY).build()
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, capture)
                provider = cameraProvider
                imageCapture = capture
            }.fold({ onReady() }, { onError(it) })
        }, executor)
    }

    fun unbind() {
        provider?.unbindAll()
        provider = null
        imageCapture = null
    }

    /** Takes one photo to `outputFile`. `targetRotation` should come from the current display rotation. */
    fun takePhoto(outputFile: File, targetRotation: Int, executor: Executor, onSaved: () -> Unit, onError: (ImageCaptureException) -> Unit) {
        val capture = imageCapture
        if (capture == null) {
            onError(ImageCaptureException(ImageCapture.ERROR_UNKNOWN, "camera not bound", null))
            return
        }
        capture.targetRotation = targetRotation
        capture.takePicture(
            ImageCapture.OutputFileOptions.Builder(outputFile).build(),
            executor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onError(exception: ImageCaptureException) = onError(exception)
                override fun onImageSaved(output: ImageCapture.OutputFileResults) = onSaved()
            },
        )
    }
}
