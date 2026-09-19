package fi.leima.android

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
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject

/** Foreground-only, bounded sensor window. All callbacks and snapshots run on main. */
class SensorRecorder(private val context: Context) : SensorEventListener, LocationListener {
    private val sensors = context.getSystemService(SensorManager::class.java)
    private val locations = context.getSystemService(LocationManager::class.java)
    private val samples = ArrayDeque<JSONObject>()
    private var inventory = JSONArray()
    private var location: Location? = null
    private var locationStatus = "not_requested"

    fun start() {
        stop()
        samples.clear()
        location = null
        inventory = JSONArray()
        sensors.getSensorList(Sensor.TYPE_ALL).forEach { sensor ->
            val registered = runCatching {
                sensors.registerListener(this, sensor, SensorManager.SENSOR_DELAY_NORMAL)
            }.getOrDefault(false)
            inventory.put(JSONObject().put("name", sensor.name).put("type", sensor.type)
                .put("stringType", sensor.stringType).put("vendor", sensor.vendor)
                .put("resolution", sensor.resolution).put("maximumRange", sensor.maximumRange)
                .put("registered", registered))
        }
        locationStatus = "permission_denied"
        if (context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            var subscribed = false
            locations.getProviders(true).filter { it != LocationManager.PASSIVE_PROVIDER }.forEach { provider ->
                runCatching { locations.requestLocationUpdates(provider, 1000L, 0f, this) }
                    .onSuccess { subscribed = true }
            }
            locationStatus = if (subscribed) "waiting_for_fix" else "no_accessible_provider"
        }
    }

    fun stop() { sensors.unregisterListener(this); locations.removeUpdates(this) }
    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
    override fun onSensorChanged(event: SensorEvent) {
        samples.addLast(JSONObject().put("type", event.sensor.type).put("name", event.sensor.name)
            .put("elapsedRealtimeNs", event.timestamp).put("accuracy", event.accuracy)
            .put("values", JSONArray(event.values.map { if (it.isFinite()) it else JSONObject.NULL })))
        trim()
    }
    private fun trim() {
        val cutoff = SystemClock.elapsedRealtimeNanos() - 5_000_000_000L
        while (samples.isNotEmpty() && (samples.size > 2000 || samples.first().getLong("elapsedRealtimeNs") < cutoff)) {
            samples.removeFirst()
        }
    }
    override fun onLocationChanged(value: Location) { location = Location(value); locationStatus = "available" }
    override fun onProviderEnabled(provider: String) = Unit
    override fun onProviderDisabled(provider: String) {
        if (location?.provider == provider) { location = null; locationStatus = "provider_disabled" }
    }
    @Deprecated("Required for Android 9 compatibility")
    override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) = Unit
    fun snapshot(): JSONObject {
        trim()
        val fix = location?.let {
            JSONObject().put("latitude", it.latitude).put("longitude", it.longitude)
                .put("accuracyMeters", it.accuracy).put("provider", it.provider)
                .put("wallTimeMs", it.time).put("elapsedRealtimeNs", it.elapsedRealtimeNanos)
                .put("ageMs", (SystemClock.elapsedRealtimeNanos() - it.elapsedRealtimeNanos) / 1_000_000)
                .put("isMock", it.isFromMockProvider)
                .put("altitudeMeters", if (it.hasAltitude()) it.altitude else JSONObject.NULL)
                .put("speedMetersPerSecond", if (it.hasSpeed()) it.speed else JSONObject.NULL)
                .put("bearingDegrees", if (it.hasBearing()) it.bearing else JSONObject.NULL)
        }
        return JSONObject().put("inventory", inventory).put("samples", JSONArray(samples.toList()))
            .put("windowSeconds", 5).put("maximumSamples", 2000)
            .put("locationStatus", locationStatus).put("location", fix ?: JSONObject.NULL)
            .put("scope", "Foreground standard sensor listeners; trigger and permission-restricted sensors may be unavailable")
    }
}
