"""Integration policy: decides what live analysis and coaching are permitted.

Live analysis and coaching are enabled only when the TARI Training Lab is
*observed* in the frame (its fiducial marker). VALORANT match integration
requires Riot authorization; this build contains no authorization mechanism,
so that path always evaluates to "not authorized" and stays restricted.
Screen capture does not make otherwise prohibited assistance compliant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from tari_schema import EnvironmentObservation, TextField

GRACE_MS = 1500.0


@dataclass(frozen=True)
class AuthorizationResult:
    authorized: bool
    reason: str


class AuthorizationVerifier(Protocol):
    def verify(self, source_label: str) -> AuthorizationResult: ...


class NoRiotAuthorization:
    """Default verifier. There is no approved Riot integration in this build."""

    def verify(self, source_label: str) -> AuthorizationResult:
        return AuthorizationResult(False, "No Riot authorization is configured; VALORANT match integration is disabled.")


@dataclass(frozen=True)
class PolicyDecision:
    mode: str
    reason: str
    analysis_allowed: bool
    live_coaching_allowed: bool
    spatial_overlays_allowed: bool
    notices: tuple[str, ...] = field(default_factory=tuple)


def looks_like_valorant(label: str) -> bool:
    return "valorant" in label.lower()


class IntegrationPolicy:
    def __init__(self, verifier: AuthorizationVerifier | None = None):
        self.verifier = verifier or NoRiotAuthorization()

    def allows_analysis(self, env_obs: EnvironmentObservation | None, env_field: TextField | None) -> bool:
        """Gate run right after the environment check, before full perception."""
        if env_obs is not None and env_obs.kind == "training_lab" and env_obs.confidence >= 0.6:
            return True
        return env_field is not None and env_field.value == "training_lab" and env_field.status == "observed"

    def evaluate(self, env_field: TextField, source_label: str, now_ms: float) -> PolicyDecision:
        lab_recent = (env_field.value == "training_lab" and env_field.updated_ts_ms is not None
                      and now_ms - env_field.updated_ts_ms <= GRACE_MS)
        if lab_recent:
            return PolicyDecision("live_training", "TARI Training Lab verified by fiducial marker.", True, True, True)
        auth = self.verifier.verify(source_label)
        if auth.authorized:
            return PolicyDecision("live_authorized", auth.reason, True, True, True)
        notices = []
        if looks_like_valorant(source_label):
            notices.append("VALORANT detected as the capture source. Live coaching in matches requires Riot "
                           "authorization and is disabled. Use the TARI Training Lab for live coaching.")
        reason = "Source not verified as TARI Training Lab; live analysis paused. " + auth.reason
        return PolicyDecision("restricted", reason, False, False, False, tuple(notices))
