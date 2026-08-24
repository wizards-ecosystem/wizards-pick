from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    # Microsecond precision keeps the audit trail exact and, because the offset is
    # always +00:00 and the width is fixed, the ISO strings sort correctly as plain
    # text — which is how sessions are ordered (see Storage.latest_session).
    return datetime.now(UTC).isoformat(timespec="microseconds")


class ExecutionMode(StrEnum):
    MANUAL = "manual"
    ASSISTED = "assisted"
    AUTOMATED = "automated"


class RiskLevel(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def from_text(cls, value: str | None) -> RiskLevel:
        normalized = (value or "").strip().lower().replace(" ", "_")
        aliases = {
            "info": cls.INFORMATIONAL,
            "informational": cls.INFORMATIONAL,
            "low": cls.LOW,
            "medium": cls.MEDIUM,
            "med": cls.MEDIUM,
            "high": cls.HIGH,
            "critical": cls.CRITICAL,
            "crit": cls.CRITICAL,
        }
        return aliases.get(normalized, cls.MEDIUM)


@dataclass(slots=True)
class Scope:
    target_type: str = "web app"
    authorized_targets: list[str] = field(default_factory=list)
    allowed_categories: list[str] = field(
        default_factory=lambda: ["recon", "scanning", "exploitation"]
    )
    notes: str = ""
    excluded_targets: list[str] = field(default_factory=list)
    testing_window: str = ""
    intensity: str = "standard"
    emergency_contact: str = ""
    authorization_hash: str = ""
    authorization_label: str = "provided during wizard"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scope:
        # Fallbacks mirror the field defaults above so a to_dict()/from_dict()
        # round-trip is stable and never invents "unknown"/"not specified" text.
        return cls(
            target_type=data.get("target_type", "web app"),
            authorized_targets=list(data.get("authorized_targets", [])),
            excluded_targets=list(data.get("excluded_targets", [])),
            testing_window=data.get("testing_window", ""),
            intensity=data.get("intensity", "standard"),
            allowed_categories=list(
                data.get("allowed_categories", ["recon", "scanning", "exploitation"])
            ),
            emergency_contact=data.get("emergency_contact", ""),
            authorization_hash=data.get("authorization_hash", ""),
            authorization_label=data.get("authorization_label", "provided during wizard"),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", utc_now()),
        )

    def summary(self) -> str:
        categories = ", ".join(self.allowed_categories) or "none"
        allowed = ", ".join(self.authorized_targets) or "none"
        excluded = ", ".join(self.excluded_targets) or "none"
        lines = [
            f"Target type: {self.target_type}",
            f"Targets/context: {allowed}",
            f"Excluded targets: {excluded}",
            f"Testing window: {self.testing_window or 'not specified'}",
            f"Focus areas: {categories}",
            f"Intensity: {self.intensity}",
            f"Authorization: {self.authorization_label or 'operator managed'}",
        ]
        if self.emergency_contact:
            lines.append(f"Emergency contact: {self.emergency_contact}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        return "\n".join(lines)


@dataclass(slots=True)
class Session:
    id: str
    name: str
    mode: ExecutionMode
    scope: Scope
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data


@dataclass(slots=True)
class CommandProposal:
    phase: str
    technique: str
    commands: list[str]
    risk_level: RiskLevel
    scope_check: str
    expected_outcome: str
    next_steps: str
    category: str = "recon"
    estimated_time: str = "unknown"
    impact: str = "not specified"
    auto_executable: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CommandProposal:
        commands = payload.get("commands") or payload.get("command") or []
        if isinstance(commands, str):
            commands = [commands]
        return cls(
            phase=str(payload.get("phase", "Recon")),
            technique=str(payload.get("technique", "Not specified")),
            commands=[str(command).strip() for command in commands if str(command).strip()],
            risk_level=RiskLevel.from_text(
                str(payload.get("risk_level", payload.get("risk", "medium")))
            ),
            scope_check=str(payload.get("scope_check", "model did not provide a scope statement")),
            expected_outcome=str(payload.get("expected_outcome", "")),
            next_steps=str(payload.get("next_steps", "")),
            category=str(payload.get("category", "recon")),
            estimated_time=str(payload.get("estimated_time", "unknown")),
            impact=str(payload.get("impact", "not specified")),
            auto_executable=bool(payload.get("auto_executable", False)),
            raw=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk_level"] = self.risk_level.value
        return data


@dataclass(slots=True)
class CommandResult:
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    started_at: str
    completed_at: str
    timed_out: bool = False

    def combined_output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout.strip())
        if self.stderr:
            parts.append(self.stderr.strip())
        return "\n".join(parts).strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Finding:
    title: str
    severity: RiskLevel
    evidence: str
    classification: str = ""
    difficulty: str = ""
    business_impact: str = ""
    reproduction_steps: str = ""
    remediation: str = ""
    verification: str = ""
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Finding:
        return cls(
            title=str(payload.get("title", "Untitled finding")),
            severity=RiskLevel.from_text(
                str(payload.get("severity", payload.get("risk_level", "medium")))
            ),
            evidence=str(payload.get("evidence", "")),
            classification=str(payload.get("classification", "")),
            difficulty=str(payload.get("difficulty", "")),
            business_impact=str(payload.get("business_impact", "")),
            reproduction_steps=str(payload.get("reproduction_steps", "")),
            remediation=str(payload.get("remediation", "")),
            verification=str(payload.get("verification", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data
