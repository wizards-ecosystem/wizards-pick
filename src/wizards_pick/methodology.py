from __future__ import annotations

import shutil
from dataclasses import dataclass

from .models import Scope


@dataclass(frozen=True, slots=True)
class PhaseGuide:
    name: str
    categories: tuple[str, ...]
    objective: str
    evidence: tuple[str, ...]
    decision_points: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolStatus:
    name: str
    category: str
    installed: bool
    path: str


PHASE_GUIDES: tuple[PhaseGuide, ...] = (
    PhaseGuide(
        name="recon",
        categories=("recon",),
        objective="Build an accurate target map, ownership notes, exposed services, and technology fingerprints.",
        evidence=("target list", "DNS/host records", "service banners", "application technologies"),
        decision_points=(
            "Which hosts and services are in scope?",
            "Which exposed surfaces deserve deeper enumeration?",
        ),
    ),
    PhaseGuide(
        name="scanning",
        categories=("scanning",),
        objective="Enumerate reachable services, versions, directories, endpoints, and known vulnerability leads.",
        evidence=(
            "port and service results",
            "HTTP routes",
            "version fingerprints",
            "candidate CVEs or CWEs",
        ),
        decision_points=(
            "Which findings are only version-based leads?",
            "Which checks can validate impact cleanly?",
        ),
    ),
    PhaseGuide(
        name="web",
        categories=("web", "web_testing", "api_testing", "exploitation"),
        objective="Validate application behavior, authentication boundaries, input handling, and API trust assumptions.",
        evidence=(
            "requests and responses",
            "auth state",
            "parameter names",
            "proof of impact screenshots or excerpts",
        ),
        decision_points=(
            "Is the behavior reproducible?",
            "Can impact be demonstrated without unnecessary data access?",
        ),
    ),
    PhaseGuide(
        name="identity",
        categories=("credential_testing", "ad", "internal", "lateral_movement"),
        objective="Assess identity exposure, authentication policy, privilege boundaries, and directory relationships.",
        evidence=(
            "account policy",
            "share and permission listings",
            "directory graph notes",
            "validated access paths",
        ),
        decision_points=(
            "Which credentials or principals were explicitly approved for testing?",
            "What privilege boundary was crossed?",
        ),
    ),
    PhaseGuide(
        name="post_exploitation",
        categories=("post_exploitation", "data_access_validation"),
        objective="Confirm business impact, collect minimal proof, and preserve remediation detail after validation.",
        evidence=(
            "current user and host context",
            "minimal data access proof",
            "persistence of evidence",
            "cleanup notes",
        ),
        decision_points=(
            "What evidence proves impact with the least exposure?",
            "What cleanup or containment notes belong in the report?",
        ),
    ),
    PhaseGuide(
        name="reporting",
        categories=("reporting", "remediation"),
        objective="Convert evidence into clear findings, affected assets, severity rationale, and verification steps.",
        evidence=(
            "finding title",
            "severity rationale",
            "reproduction steps",
            "remediation",
            "verification command or procedure",
        ),
        decision_points=(
            "Is each finding validated?",
            "Can the owner reproduce and verify the fix?",
        ),
    ),
)


TOOL_CATALOG: dict[str, tuple[str, ...]] = {
    "recon": ("dig", "host", "whois", "amass", "subfinder", "httpx", "whatweb"),
    "scanning": ("nmap", "rustscan", "naabu", "nuclei", "nikto"),
    "web": ("curl", "jq", "ffuf", "feroxbuster", "gobuster", "sqlmap", "wpscan"),
    "identity": (
        "smbclient",
        "enum4linux-ng",
        "netexec",
        "crackmapexec",
        "rpcclient",
        "ldapsearch",
    ),
    "post_exploitation": ("impacket-secretsdump", "bloodhound-python", "neo4j", "python3"),
    "reporting": ("tee", "script", "pandoc"),
}


def matching_guides(scope: Scope, phase: str | None = None) -> list[PhaseGuide]:
    normalized_phase = (phase or "").strip().lower().replace("-", "_")
    if normalized_phase in {"", "all"}:
        normalized_phase = ""

    allowed = {
        item.strip().lower().replace("-", "_") for item in scope.allowed_categories if item.strip()
    }
    guides: list[PhaseGuide] = []
    for guide in PHASE_GUIDES:
        if normalized_phase and normalized_phase != guide.name:
            continue
        if allowed and guide.name != "reporting" and not allowed.intersection(guide.categories):
            continue
        guides.append(guide)
    return guides


def format_methodology(scope: Scope, phase: str | None = None) -> str:
    guides = matching_guides(scope, phase)
    if not guides:
        available = ", ".join(guide.name for guide in PHASE_GUIDES)
        return f"No matching phase found. Available phases: {available}"

    lines = ["# Assessment Plan", ""]
    lines.append(f"Target type: {scope.target_type}")
    lines.append(f"Targets/context: {', '.join(scope.authorized_targets) or 'not specified'}")
    lines.append(f"Focus areas: {', '.join(scope.allowed_categories) or 'not specified'}")
    lines.append("")

    for guide in guides:
        lines.append(f"## {guide.name.replace('_', ' ').title()}")
        lines.append("")
        lines.append(guide.objective)
        lines.append("")
        lines.append("Evidence to capture:")
        lines.extend(f"- {item}" for item in guide.evidence)
        lines.append("")
        lines.append("Decision points:")
        lines.extend(f"- {item}" for item in guide.decision_points)
        lines.append("")
    return "\n".join(lines).strip()


def tool_inventory() -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    for category, tools in TOOL_CATALOG.items():
        for tool in tools:
            path = shutil.which(tool) or ""
            statuses.append(
                ToolStatus(name=tool, category=category, installed=bool(path), path=path)
            )
    return statuses
