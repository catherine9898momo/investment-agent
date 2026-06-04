from pathlib import Path

from src.company_research.monitor import collect_monitoring_data, load_company_pack, render_report, write_outputs


def test_mu_fixture_report_contains_monitoring_sections(tmp_path: Path) -> None:
    pack = load_company_pack("MU")
    payload = collect_monitoring_data(pack, "fixture")
    report = render_report(payload)

    assert "Micron Technology (MU) Monitoring Report" in report
    assert "## Thesis Monitor" in report
    assert "HBM4/HBM4E progress" in report
    assert "not investment advice" in report

    paths = write_outputs(pack, payload, report, tmp_path)
    assert paths["markdown"].exists()
    assert paths["json"].exists()
