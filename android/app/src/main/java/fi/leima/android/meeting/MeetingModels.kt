package fi.leima.android.meeting

/** Versioned enums shared by the meeting-proof v2 session, package and state machine. */

enum class Role(val jsonValue: String) { PHOTOGRAPHER("photographer"), WITNESS("witness") }

/** Session-level state machine (see android/docs/meeting_v2_schema.md and plan section 4). */
enum class SessionState(val jsonValue: String) {
    IDLE("idle"),
    PAIRING("pairing"),
    READY("ready"),
    RECORDING("recording"),
    CONFIRMING("confirming"),
    FINALIZING("finalizing"),
    COMPLETE("complete"),
    INTERRUPTED("interrupted"),
    CANCELLED("cancelled"),
    FAILED("failed"),
}

/** Per-capture state, separate from the session-level [SessionState]. */
enum class CaptureStatus(val jsonValue: String) { REQUESTED("requested"), SAVED("saved"), FAILED("failed") }

/** Status of one guided template step within an [ObservationPoint]. */
enum class StepStatus(val jsonValue: String) { CAPTURED("captured"), SKIPPED("skipped"), NOT_TAKEN("not_taken") }

/**
 * Which of a template's four guided slots a photo fills, or [EXTRA] for any photo not tied to a
 * guided step (additional shots, and all shots in the free-capture template).
 */
enum class ShotType(val jsonValue: String) {
    OVERVIEW("overview"),
    STRUCTURE("structure"),
    CLOSE_UP("close_up"),
    SUPPLEMENTARY("supplementary"),
    EXTRA("extra"),
}

enum class TemplateId(val jsonValue: String) { FIELD("field"), SITE("site"), FOREST("forest"), FREE("free") }

/** Forest-only capture purpose (plan section 3.2.1); other templates leave this unset. */
enum class ForestPurpose(val jsonValue: String) {
    OVERVIEW("overview"),
    TREE_CONDITION("tree_condition"),
    LOGGING_TRACE("logging_trace"),
    SEEDLINGS("seedlings"),
    OTHER("other"),
}
