package fi.leima.android.meeting

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.SystemClock
import java.io.File
import org.json.JSONArray
import org.json.JSONObject

/**
 * Continuous IMU + location logger for one meeting session, writing straight to disk instead of
 * holding samples in memory for the session's duration (plan sections 5/9: a 10-minute session
 * must not grow memory with its length). Requested sampling rates (50 Hz accel/gyro, 20 Hz
 * magnetometer/rotation, ~1 Hz location) are targets, not guarantees; [sensorInventory] reports
 * what the device actually registered, for `session.json`.
 */
class SessionSensorRecorder(
    private val context: Context,
    sessionDirectory: File,
    private val journal: SessionJournal,
) : SensorEventListener, LocationListener {
    private val sensorManager = context.getSystemService(SensorManager::class.java)
    private val locationManager = context.getSystemService(LocationManager::class.java)
    private val imuLog = JsonlAppender(File(sessionDirectory, "sensors/imu.jsonl"), capacity = 8192)
    private val locationLog = JsonlAppender(File(sessionDirectory, "sensors/location.jsonl"), capacity = 512)
    private var inventory = JSONArray()
    private var locationStatus = "not_requested"
    @Volatile private var running = false
    private var lastReportedImuDrops = 0L
    private var lastReportedLocationDrops = 0L

    private val trackedTypes = mapOf(
        Sensor.TYPE_ACCELEROMETER to 20_000, // 50 Hz
        Sensor.TYPE_GYROSCOPE to 20_000, // 50 Hz
        Sensor.TYPE_MAGNETIC_FIELD to 50_000, // 20 Hz
        Sensor.TYPE_ROTATION_VECTOR to 50_000, // 20 Hz
    )

    fun start() {
        check(!running) { "SessionSensorRecorder is already recording" }
        running = true
        inventory = JSONArray()
        trackedTypes.forEach { (type, periodUs) ->
            val sensor = sensorManager.getDefaultSensor(type)
            val registered = sensor != null && runCatching { sensorManager.registerListener(this, sensor, periodUs) }.getOrDefault(false)
            inventory.put(
                JSONObject().put("requestedType", type).put("available", sensor != null).put("registered", registered)
                    .put("name", sensor?.name ?: JSONObject.NULL).put("vendor", sensor?.vendor ?: JSONObject.NULL)
                    .put("resolution", sensor?.resolution ?: JSONObject.NULL).put("maximumRange", sensor?.maximumRange ?: JSONObject.NULL)
                    .put("requestedPeriodUs", periodUs),
            )
        }
        locationStatus = "permission_denied"
        if (context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            var subscribed = false
            locationManager.getProviders(true).filter { it != LocationManager.PASSIVE_PROVIDER }.forEach { provider ->
                runCatching { locationManager.requestLocationUpdates(provider, 1000L, 0f, this) }.onSuccess { subscribed = true }
            }
            locationStatus = if (subscribed) "waiting_for_fix" else "no_accessible_provider"
        }
        journal.record("sensor_recording_started", JSONObject().put("inventory", inventory).put("locationStatus", locationStatus))
    }

    /** Stops registrations and closes both JSONL files, draining any queued samples first. Idempotent. */
    fun stop() {
        if (!running) return
        running = false
        sensorManager.unregisterListener(this)
        locationManager.removeUpdates(this)
        reportDrops()
        imuLog.close()
        locationLog.close()
    }

    fun sensorInventory(): JSONObject = JSONObject().put("requested", inventory).put("locationStatus", locationStatus)
        .put("scope", "Foreground standard sensor listeners; trigger and permission-restricted sensors are not requested")

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    override fun onSensorChanged(event: SensorEvent) {
        val accepted = imuLog.offer(
            JSONObject().put("sensorType", event.sensor.type).put("sensorName", event.sensor.name)
                .put("sensorElapsedRealtimeNs", event.timestamp).put("receivedElapsedRealtimeNs", SystemClock.elapsedRealtimeNanos())
                .put("accuracy", event.accuracy).put("values", sanitize(event.values)),
        )
        if (!accepted && imuLog.droppedCount - lastReportedImuDrops >= 100) reportDrops()
    }

    @Suppress("DEPRECATION") // no minSdk-28-compatible replacement for isFromMockProvider
    override fun onLocationChanged(location: Location) {
        locationStatus = "available"
        locationLog.offer(
            JSONObject().put("provider", location.provider).put("latitude", location.latitude).put("longitude", location.longitude)
                .put("accuracyMeters", location.accuracy).put("wallTimeMs", location.time)
                .put("elapsedRealtimeNs", location.elapsedRealtimeNanos).put("isMock", location.isFromMockProvider)
                .put("altitudeMeters", if (location.hasAltitude()) location.altitude else JSONObject.NULL)
                .put("speedMetersPerSecond", if (location.hasSpeed()) location.speed else JSONObject.NULL)
                .put("bearingDegrees", if (location.hasBearing()) location.bearing else JSONObject.NULL),
        )
    }

    override fun onProviderEnabled(provider: String) = Unit
    override fun onProviderDisabled(provider: String) {
        if (locationStatus == "available") locationStatus = "provider_disabled"
    }

    @Deprecated("Required for Android 9 compatibility")
    override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit

    private fun sanitize(values: FloatArray): JSONArray {
        val array = JSONArray()
        values.forEach { array.put(if (it.isFinite()) it.toDouble() else JSONObject.NULL) }
        return array
    }

    private fun reportDrops() {
        if (imuLog.droppedCount > lastReportedImuDrops) {
            journal.record("dropped_samples", JSONObject().put("channel", "imu").put("droppedCount", imuLog.droppedCount))
            lastReportedImuDrops = imuLog.droppedCount
        }
        if (locationLog.droppedCount > lastReportedLocationDrops) {
            journal.record("dropped_samples", JSONObject().put("channel", "location").put("droppedCount", locationLog.droppedCount))
            lastReportedLocationDrops = locationLog.droppedCount
        }
    }
}
