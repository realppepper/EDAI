"""
Pytest integration for Web Studio GUI End-to-End User Scenarios.
Ensures that full browser interaction, PDG rendering, timeline playback,
and security sandboxing pass in automated CI/CD runs.
"""
from e2e_gui_scenario_runner import WebStudioGUIScenarioRunner


def test_web_studio_gui_e2e_scenarios_lm393():
    """Runs full GUI scenario verification on LM393 (Interactive PDG, timeline, security, library)."""
    runner = WebStudioGUIScenarioRunner(
        port=8768,
        ic_name="LM393",
        headless=True,
        generate_iters=0  # PDG + Timeline + Security + Library
    )
    result = runner.run_all_scenarios()
    assert result["all_passed"] is True
    assert len(result["screenshots"]) >= 4
    assert result["console_errors_count"] == 0


def test_web_studio_gui_e2e_scenarios_fresh_ic():
    """Runs GUI scenario on a fresh IC (LM311) to confirm robust generalized rendering."""
    runner = WebStudioGUIScenarioRunner(
        port=8769,
        ic_name="LM311",
        headless=True,
        generate_iters=0
    )
    result = runner.run_all_scenarios()
    assert result["all_passed"] is True
    assert len(result["screenshots"]) >= 4
