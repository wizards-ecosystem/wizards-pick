from __future__ import annotations

from wizards_pick import methodology
from wizards_pick.methodology import (
    PHASE_GUIDES,
    format_methodology,
    matching_guides,
    tool_inventory,
)
from wizards_pick.models import Scope


def test_matching_guides_filters_by_allowed_categories(scope: Scope):
    names = [guide.name for guide in matching_guides(scope)]
    # scope allows recon + scanning; reporting is always included.
    assert "recon" in names
    assert "scanning" in names
    assert "reporting" in names
    assert "identity" not in names


def test_matching_guides_specific_phase():
    scope = Scope(allowed_categories=["recon", "scanning", "web"])
    guides = matching_guides(scope, "recon")
    assert [g.name for g in guides] == ["recon"]


def test_matching_guides_all_keyword_equivalent_to_none():
    scope = Scope(allowed_categories=[])  # no filter -> every guide
    assert matching_guides(scope, "all") == matching_guides(scope, None) == list(PHASE_GUIDES)


def test_format_methodology_unknown_phase_lists_available(scope: Scope):
    out = format_methodology(scope, "does-not-exist")
    assert "No matching phase found" in out
    assert "recon" in out


def test_format_methodology_renders_sections(scope: Scope):
    out = format_methodology(scope, "recon")
    assert out.startswith("# Assessment Plan")
    assert "## Recon" in out
    assert "Evidence to capture:" in out
    assert "Decision points:" in out


def test_tool_inventory_reports_installed_and_missing(monkeypatch):
    monkeypatch.setattr(
        methodology.shutil,
        "which",
        lambda tool: "/usr/bin/nmap" if tool == "nmap" else "",
    )
    inventory = {item.name: item for item in tool_inventory()}
    assert inventory["nmap"].installed is True
    assert inventory["nmap"].path == "/usr/bin/nmap"
    assert inventory["sqlmap"].installed is False
    assert inventory["sqlmap"].path == ""
    # Every catalogued tool is reported exactly once.
    assert len(tool_inventory()) == sum(len(v) for v in methodology.TOOL_CATALOG.values())
