package fi.leima.android.meeting

/** One guided step within a [CaptureTemplate]. `stepIndex` is 1-based and matches session.json. */
data class TemplateStep(val stepIndex: Int, val shotType: ShotType, val instruction: String)

data class CaptureTemplate(val id: TemplateId, val version: Int, val displayName: String, val steps: List<TemplateStep>)

/**
 * Versioned capture-guidance templates from the meeting-proof plan section 3.2.1. Bumping a
 * template's wording requires bumping [CaptureTemplate.version]; already-exported sessions keep
 * referencing the version they were captured with.
 */
object CaptureTemplates {
    val FIELD = CaptureTemplate(
        id = TemplateId.FIELD,
        version = 1,
        displayName = "Pelto",
        steps = listOf(
            TemplateStep(1, ShotType.OVERVIEW, "Pelto ja ympäristön maamerkkejä"),
            TemplateStep(2, ShotType.STRUCTURE, "Kasvusto lähempää: peittävyys, tasaisuus ja näkyvä kunto"),
            TemplateStep(3, ShotType.CLOSE_UP, "Kasvi, lehdet, tähkä tai hedelmä; tarvittaessa näkyvä vaurio"),
            TemplateStep(4, ShotType.SUPPLEMENTARY, "Maanpinta ja kasvien tyvi, esimerkiksi taimet, rikkakasvit tai näkyvä märkyys"),
        ),
    )

    val SITE = CaptureTemplate(
        id = TemplateId.SITE,
        version = 1,
        displayName = "Työmaa",
        steps = listOf(
            TemplateStep(1, ShotType.OVERVIEW, "Työmaa ja sen ympäristö"),
            TemplateStep(2, ShotType.STRUCTURE, "Dokumentoitava työkohde tai työvaihe"),
            TemplateStep(3, ShotType.CLOSE_UP, "Olennainen rakenne, liitos tai havaittu vaurio"),
            TemplateStep(4, ShotType.SUPPLEMENTARY, "Toinen kuvakulma tai yksityiskohta näkyvän mitta-asteikon kanssa"),
        ),
    )

    val FOREST = CaptureTemplate(
        id = TemplateId.FOREST,
        version = 1,
        displayName = "Metsä",
        steps = listOf(
            TemplateStep(1, ShotType.OVERVIEW, "Metsikkö avarasta kohdasta, ympäristö ja aukot"),
            TemplateStep(2, ShotType.STRUCTURE, "Useita puita mahdollisuuksien mukaan tyveltä latvaan"),
            TemplateStep(3, ShotType.CLOSE_UP, "Lehdet, neulaset, kuori tai havaittu vaurio"),
            TemplateStep(4, ShotType.SUPPLEMENTARY, "Aluskasvillisuus, taimet, puiden tyvet tai näkyvät maastovauriot"),
        ),
    )

    /** Vapaa kuvaus: no guided steps, every photo is [ShotType.EXTRA]. */
    val FREE = CaptureTemplate(id = TemplateId.FREE, version = 1, displayName = "Vapaa kuvaus", steps = emptyList())

    val ALL = listOf(FIELD, SITE, FOREST, FREE)

    fun byId(id: TemplateId): CaptureTemplate = ALL.first { it.id == id }
}

/**
 * Overrides the forest template's step-3 close-up instruction depending on the chosen
 * [ForestPurpose] (plan section 3.2.1). Other templates ignore forest purpose entirely.
 */
object ForestPurposeGuidance {
    private val closeUpInstructions = mapOf(
        ForestPurpose.OVERVIEW to "Lehdet, neulaset, kuori tai havaittu vaurio",
        ForestPurpose.TREE_CONDITION to "Havaittu vaurio tai tarkasteltava puun osa",
        ForestPurpose.LOGGING_TRACE to "Kannot ja ajourat",
        ForestPurpose.SEEDLINGS to "Taimet ja niiden lähiympäristö",
    )

    /** Null for [ForestPurpose.OTHER]: the app shows the user's own free-text purpose instead. */
    fun closeUpInstructionFor(purpose: ForestPurpose): String? = closeUpInstructions[purpose]
}
