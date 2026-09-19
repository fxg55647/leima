package fi.leima.android.meeting

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import java.io.File

/**
 * Meeting-proof capture screen (plan sections 3.1–3.4): role selection, guided multi-photo
 * capture, and export/session-list, wired to [MeetingViewModel] and [MeetingCoordinator]. QR
 * pairing is not part of Vaihe 1; "Vahvista kohtaaminen" always takes the solo path.
 */
@Composable
fun MeetingScreen(onExport: (File) -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val viewModel: MeetingViewModel = viewModel()
    var cameraAllowed by remember {
        mutableStateOf(context.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        cameraAllowed = result[Manifest.permission.CAMERA] == true
    }

    // Plan section 4: backgrounding interrupts recording immediately, it does not continue
    // unnoticed; the on-disk journal is what makes the partial session exportable afterwards.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) viewModel.interrupt() }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Column(modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(viewModel.status, style = MaterialTheme.typography.bodyMedium)
        val coordinator = viewModel.coordinator
        when {
            coordinator == null -> RoleSelector { role ->
                if (!cameraAllowed) {
                    permissionLauncher.launch(
                        arrayOf(Manifest.permission.CAMERA, Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION),
                    )
                }
                viewModel.beginSession(role)
            }
            coordinator.state == SessionState.READY -> ReadyPanel(onStart = viewModel::startRecording)
            coordinator.state == SessionState.RECORDING -> RecordingPanel(viewModel, coordinator, cameraAllowed, onExport)
            coordinator.state == SessionState.FINALIZING || coordinator.state == SessionState.COMPLETE ->
                SummaryPanel(viewModel, coordinator, onExport)
            else -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Istunto päättyi tilaan: ${coordinator.state.jsonValue}")
                Button(onClick = viewModel::startNewSession) { Text("Uusi istunto") }
            }
        }
        HorizontalDivider(Modifier.padding(vertical = 4.dp))
        SavedSessionsList(viewModel, onExport)
    }
}

@Composable
private fun RoleSelector(onSelectRole: (Role) -> Unit) {
    Text("Valitse rooli", style = MaterialTheme.typography.titleMedium)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = { onSelectRole(Role.PHOTOGRAPHER) }) { Text("Aloita kuvaus") }
        OutlinedButton(onClick = { onSelectRole(Role.WITNESS) }) { Text("Liity todistajaksi") }
    }
}

@Composable
private fun ReadyPanel(onStart: () -> Unit) {
    Text("Istunto luotu. Sensorit ja sijainti tallentuvat käynnistyksestä lähtien.")
    Button(onClick = onStart) { Text("Käynnistä tallennus") }
}

@Composable
private fun RecordingPanel(viewModel: MeetingViewModel, coordinator: MeetingCoordinator, cameraAllowed: Boolean, onExport: (File) -> Unit) {
    val point = viewModel.currentObservationPoint()

    if (coordinator.role == Role.PHOTOGRAPHER) {
        if (!cameraAllowed) {
            Text("Kameralupa tarvitaan kuvien ottamiseen. Sensoriluonnos on silti mahdollinen.")
        } else {
            CameraPreview(coordinator)
        }
        if (point == null) {
            TemplatePicker(onCreate = viewModel::addObservationPoint)
        } else {
            StepPanel(viewModel, point, onNewObservationPoint = viewModel::promptNewObservationPoint)
        }
    } else {
        Text("Sensoritodistaja: sensorit ja sijainti tallentuvat. Kameraa ei käytetä kuvien tallennukseen.")
    }

    val hasSavedCapture = coordinator.captureList().any { it.status == CaptureStatus.SAVED }
    Button(
        modifier = Modifier.fillMaxWidth(),
        enabled = coordinator.role == Role.WITNESS || hasSavedCapture,
        onClick = { viewModel.finishAndExport()?.let(onExport) },
    ) { Text("Vahvista kohtaaminen") }
}

@Composable
private fun CameraPreview(coordinator: MeetingCoordinator) {
    val lifecycleOwner = LocalLifecycleOwner.current
    val context = LocalContext.current
    DisposableEffect(Unit) { onDispose { coordinator.camera.unbind() } }
    AndroidView(
        modifier = Modifier.fillMaxWidth().height(220.dp),
        factory = { viewContext ->
            PreviewView(viewContext).apply {
                coordinator.camera.bind(lifecycleOwner, this, context.mainExecutor, onReady = {}, onError = {})
            }
        },
    )
}

@Composable
private fun TemplatePicker(onCreate: (String, TemplateId, String?) -> Unit) {
    var name by remember { mutableStateOf("") }
    var templateId by remember { mutableStateOf<TemplateId?>(null) }
    var forestPurpose by remember { mutableStateOf<ForestPurpose?>(null) }
    var forestPurposeOther by remember { mutableStateOf("") }

    Text("Uusi havaintopaikka", style = MaterialTheme.typography.titleMedium)
    OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Paikan nimi (valinnainen)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CaptureTemplates.ALL.forEach { template ->
            FilterChip(selected = templateId == template.id, onClick = { templateId = template.id }, label = { Text(template.displayName) })
        }
    }
    if (templateId == TemplateId.FOREST) {
        Text("Metsän tarkoitus", style = MaterialTheme.typography.labelLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(
                ForestPurpose.OVERVIEW to "Yleiskatsaus", ForestPurpose.TREE_CONDITION to "Puuston kunto",
                ForestPurpose.LOGGING_TRACE to "Hakkuun jälki", ForestPurpose.SEEDLINGS to "Taimikko",
            ).forEach { (purpose, label) ->
                FilterChip(selected = forestPurpose == purpose, onClick = { forestPurpose = purpose }, label = { Text(label) })
            }
        }
        if (forestPurpose == null) {
            OutlinedTextField(
                value = forestPurposeOther, onValueChange = { forestPurposeOther = it }, label = { Text("Muu tarkoitus") },
                singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
        }
    }
    Button(
        enabled = templateId != null,
        onClick = {
            val purpose = when {
                templateId != TemplateId.FOREST -> null
                forestPurpose != null -> forestPurpose!!.jsonValue
                forestPurposeOther.isNotBlank() -> forestPurposeOther
                else -> ForestPurpose.OTHER.jsonValue
            }
            onCreate(name.ifBlank { "Paikka" }, templateId!!, purpose)
        },
    ) { Text("Lisää havaintopaikka") }
}

@Composable
private fun StepPanel(viewModel: MeetingViewModel, point: ObservationPointInfo, onNewObservationPoint: () -> Unit) {
    val view = LocalView.current
    val template = CaptureTemplates.byId(point.templateId)
    Text("Havaintopaikka: ${point.name}", style = MaterialTheme.typography.titleMedium)
    if (template.steps.isEmpty()) {
        Text("Vapaa kuvaus: ota kuvia ilman ohjattua järjestystä.", style = MaterialTheme.typography.bodySmall)
    } else {
        template.steps.forEach { step ->
            val status = point.stepStatuses[step.stepIndex] ?: StepStatus.NOT_TAKEN
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("${step.stepIndex}. ${step.instruction} [${status.jsonValue}]", Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                if (status != StepStatus.CAPTURED) {
                    TextButton(
                        enabled = !viewModel.captureBusy,
                        onClick = { viewModel.requestCapture(step.shotType, point.purpose, null, view.display?.rotation ?: 0) },
                    ) { Text("Ota kuva") }
                    TextButton(onClick = { viewModel.skipStep(step.stepIndex) }) { Text("Ohita") }
                }
            }
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        TextButton(
            enabled = !viewModel.captureBusy,
            onClick = { viewModel.requestCapture(ShotType.EXTRA, point.purpose, null, view.display?.rotation ?: 0) },
        ) { Text("Lisäkuva") }
        TextButton(onClick = onNewObservationPoint) { Text("Uusi havaintopaikka") }
    }
}

@Composable
private fun SummaryPanel(viewModel: MeetingViewModel, coordinator: MeetingCoordinator, onExport: (File) -> Unit) {
    Text("Istunto: ${coordinator.sessionId.take(8)}", style = MaterialTheme.typography.titleMedium)
    Text("Kuvia tallennettu: ${coordinator.captureList().count { it.status == CaptureStatus.SAVED }}")
    coordinator.observationPointList().forEach { point ->
        val done = point.stepStatuses.values.count { it == StepStatus.CAPTURED }
        val total = point.stepStatuses.size
        val progress = if (total > 0) "$done/$total vaihetta kuvattu" else "vapaa kuvaus"
        Text("• ${point.name} (${point.templateId.jsonValue}): $progress", style = MaterialTheme.typography.bodySmall)
    }
    if (coordinator.state == SessionState.COMPLETE) {
        val zip = viewModel.zipFile(coordinator.sessionId)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(enabled = zip != null, onClick = { zip?.let(onExport) }) { Text("Vie ZIP") }
            OutlinedButton(onClick = viewModel::startNewSession) { Text("Uusi istunto") }
        }
    } else {
        Text("Viimeistellään…", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun SavedSessionsList(viewModel: MeetingViewModel, onExport: (File) -> Unit) {
    val sessions = remember(viewModel.sessionListVersion) { viewModel.sessions() }
    Text("Tallennetut istunnot", style = MaterialTheme.typography.titleMedium)
    if (sessions.isEmpty()) {
        Text("Ei vielä istuntoja.", style = MaterialTheme.typography.bodySmall)
        return
    }
    LazyColumn(Modifier.heightIn(max = 200.dp)) {
        items(sessions, key = { it.sessionId }) { summary ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    "${summary.sessionId.take(8)} · ${if (summary.isFinalized) "valmis" else "kesken"}",
                    Modifier.weight(1f),
                    style = MaterialTheme.typography.bodySmall,
                )
                if (summary.isFinalized) {
                    TextButton(onClick = { viewModel.zipFile(summary.sessionId)?.let(onExport) }) { Text("Vie") }
                }
                TextButton(onClick = { viewModel.deleteSession(summary.sessionId) }) { Text("Poista") }
            }
        }
    }
}
