# Leima Mobile

**Field evidence for work that happens beyond paperwork.**

Leima Mobile is an open-source Android application for collecting structured visual evidence in the field. It combines guided photographs, timestamps, optional location, device sensor logs, and a tamper-evident manifest into one exportable evidence package.

The aim is practical accountability. A report can say that a well was drilled, a school was repaired, or supplies reached a community. Leima Mobile is being built to preserve the observations behind that report: what was visible, when it was recorded, which files belong to the same session, and whether the package has changed since capture.

The Android source is part of this repository under [`android/`](android/). See the [Android developer guide](android/README.md) for build instructions and the current technical limits.

---

## A well project, recorded as it progresses

A donor-funded well does not need to be treated as one unverifiable promise followed by one final payment. It can be divided into observable milestones:

1. The site and starting conditions are recorded.
2. Excavation or drilling begins, with the equipment and current depth documented.
3. Water is reached and the observed flow is measured.
4. The well and pump are completed, followed by a water-quality test.
5. A later visit confirms that the well still works and serves its intended community.

Each milestone can produce its own evidence session. Funding can then be released in stages after the relevant evidence has been reviewed. The same pattern applies to construction, agricultural support, forest restoration, donated equipment, and delivery of humanitarian supplies.

Leima does not turn a photograph into unquestionable truth. A photograph may be staged, a device clock may be wrong, and a location reading may be inaccurate. The value comes from making observations structured, internally consistent, harder to alter silently, and easier for another person to review alongside contracts, measurements, receipts, and follow-up visits.

---

## What the current prototype does

The current Android prototype supports two complementary capture modes.

### Single capture

- Capture a camera photo or the visible area of a page in the built-in HTTPS browser.
- Crop a browser screenshot and permanently cover sensitive areas before saving it.
- Choose whether the page path, title, sensors, and location are included.
- Export the final media, metadata, a SHA-256 manifest, and the manifest checksum as a ZIP package.
- Verify the package independently with the repository's Python verification tool.

The original unredacted screenshot is not written into the evidence package. The crop and opaque masks are applied before the final image is saved and hashed.

### Multi-photo field session

- Record several observation points in one session.
- Use guided capture templates for a field, worksite, forest, or free-form observation.
- Take overview, structural, close-up, and supporting photographs, or explicitly skip a suggested step.
- Record available motion sensors and optional location continuously during the session.
- Keep an append-only event journal and capture metadata alongside the photographs.
- Finalize the session into a deterministic ZIP with SHA-256 hashes for its contents.
- Keep completed and interrupted sessions in private application storage for later export or deletion.

The guided sequence helps reviewers understand how close-ups relate to their surroundings. It is guidance rather than an automatic claim that two images depict the same place.

---

## Evidence package

A field session produces a package shaped like this:

```text
meeting-session.zip
├── session.json
├── events.jsonl
├── sensors/
│   └── imu.jsonl
├── captures/
│   ├── 000001.jpg
│   ├── 000001.json
│   └── ...
├── manifest.json
└── manifest.sha256
```

`manifest.json` binds the exact bytes of the session files with SHA-256 hashes. `manifest.sha256` detects changes to the manifest itself. The event and sensor logs are written incrementally so an interrupted session can remain inspectable instead of disappearing from the record.

The present package is **tamper-evident but unsigned**. If a file is changed after finalization, verification can detect the mismatch. Because the package does not yet carry a hardware-backed device signature, someone could still replace the complete package with a newly fabricated one. The application records this limitation explicitly rather than presenting a checksum as proof of origin.

---

## How this connects to Leima

The intended complete flow is:

```text
field observation
      ↓
mobile evidence package
      ↓
integrity and device-signature verification
      ↓
AI-assisted assessment against a specific milestone or claim
      ↓
human review and funding decision
      ↓
permanent Leima stamp
```

The human decision remains important. A useful outcome is not only “approved” or “rejected”; the assessment can also identify missing measurements, inconsistent evidence, or the need for another visit.

Server submission and permanent stamping are not yet connected to the new multi-photo session format. The existing Leima server can receive and validate the older single-capture package format. Support for multi-photo field sessions is a separate implementation stage.

---

## Trust, privacy, and safety

Field evidence can expose people as well as projects. Faces, homes, precise coordinates, health information, and relationships between local participants may be sensitive. The design therefore treats data minimisation as part of evidence quality:

- Location is permission-based and its absence is recorded rather than filled with an invented value.
- Browser captures allow irreversible cropping and black masks before storage.
- Query strings and URL fragments are removed from browser metadata.
- Android automatic backup is disabled and packages remain in private app storage until export.
- An interrupted recording is stopped when the application moves to the background.
- Missing sensors and permissions appear as limitations in the record.

Future deployments should define who may capture, receive, inspect, retain, and publish each part of a package. Public accountability does not require publishing the identity or exact location of every participant.

---

## Current status and roadmap

Leima Mobile is an early prototype, currently version `0.1.0`, requiring Android 9 or later. The multi-photo session core has automated JVM tests and has been compiled as a debug APK. Long sessions, camera behaviour, permissions, battery use, and sensor behaviour still require acceptance testing on real devices.

The next major stages are:

1. Pair two nearby phones through a mutual QR exchange so one device can act as photographer and the other as a sensor witness.
2. Sign session roots with Android Keystore keys and verify supported device attestation on the server.
3. Add server parsing and validation for multi-photo session packages.
4. Submit verified sessions for Leima analysis and permanent stamping.
5. Add project and milestone definitions, review workflows, and follow-up observations for staged funding.

Until those stages are complete, the application should be used for development and field trials, not as the sole basis for releasing funds or making high-stakes decisions.

---

## Build and inspect

Open the [`android/`](android/) directory as a project in Android Studio. The project uses Kotlin, Jetpack Compose, CameraX, Android SDK 36, and JDK 17.

```bash
# Windows
gradlew.bat :app:testDebugUnitTest :app:assembleDebug :app:lintDebug

# Linux or macOS
./gradlew :app:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

The complete setup, package format, privacy behaviour, verification command, and device test checklist are documented in [`android/README.md`](android/README.md).
