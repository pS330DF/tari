# Compliance, integrity, and privacy

TARI is a coaching tool. Its live spatial and tactical coaching is developed
and validated in the **TARI Training Lab**, a separate environment TARI owns.
VALORANT match integration requires Riot's authorization and is disabled.

## What TARI does not do

- Does not read or write game memory, inject code into any process, hook
  rendering, or interact with Vanguard.
- Does not generate mouse, keyboard or controller input, and does not control
  the player's character. (The Lab's autotest mode moves the Lab's *own*
  simulated camera for validation recordings; it produces no OS input and is
  active only when the Lab page is opened with `?autotest=`.)
- Does not upload screen frames or audio. Frames go from the capture worker to
  the local engine over loopback and are discarded after analysis; only derived
  measurements are stored, in a local SQLite file.
- Does not use the microphone in this build (permission requests are denied by
  the main process unless the user enables it; speech input is not implemented).
- Does not claim that screen capture makes otherwise prohibited assistance
  acceptable.

## How live coaching is gated

`services/state-engine/tari_state/policy.py`

1. Every frame first runs only the environment check: an ArUco fiducial that the
   Training Lab draws in its HUD cluster.
2. Full analysis (HUD, crosshair, targets, view motion), coaching, voice and
   spatial overlays run only while the Lab is **observed** (confirmed fiducial,
   1.5 s grace). Otherwise the mode is `restricted`; the UI shows why.
3. A capture source whose title looks like VALORANT produces an explicit notice:
   live coaching in matches requires Riot authorization and is disabled.
4. `IntegrationPolicy` accepts an `AuthorizationVerifier`. The shipped
   `NoRiotAuthorization` always returns "not authorized". There is no code path
   that enables live analysis of VALORANT matches in this build.
5. The engine reports `riot_integration: "disabled_pending_authorization"` in its
   capabilities.

Tests: `tests/unit/test_state_engine.py::test_unverified_source_is_restricted_and_not_analyzed`,
`test_policy_requires_observed_lab_and_never_grants_riot_access`,
`tests/integration/test_engine_stream.py::test_valorant_source_is_restricted_with_notice`.

## Before any VALORANT integration

- Obtain Riot's written approval for the specific features and contexts
  (e.g. post-match review vs. in-match). Review Riot's current third-party
  application policies; they change over time.
- Implement a verifier that checks that approval, scoped to approved features
  only, and keep in-match assistance limited to what is approved.
- Re-run the privacy review for any new data flow.

## Local security

- Engine binds `127.0.0.1` only and requires a random per-launch token (WebSocket
  query parameter / `x-tari-token` header); CORS allows only TARI's own origins.
- Electron: `contextIsolation`, `sandbox`, no `nodeIntegration`, allow-listed IPC
  channels with sender-origin checks and input validation, navigation and
  window-open blocked, strict CSP in production builds.
- TARI's own windows use content protection so they are excluded from screen
  capture (prevents the analyzer from seeing its own output).

## Privacy checklist (current build)

| Item | Status |
| --- | --- |
| Screen frames leave the device | No |
| Audio captured | No |
| Stored data | session rows, coaching events (measurements), recommendations, performance snapshots — under the app's user data folder (`engine/tari.db`) |
| Logs | JSON lines under the user data folder (`logs/`), no frame data |
| Cloud LLM | not integrated; the settings schema keeps it off by default |
| Deleting history | delete `engine/tari.db` (a UI action is not implemented yet) |
