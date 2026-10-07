from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_renders_queue():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    labels = [e.label for e in at.expander]
    assert sum("Review required" in x for x in labels) >= 8
    assert any("No candidate found" in x for x in labels)
    assert any("Model number needed" in x for x in labels)


def test_single_device_flips_with_serial():
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["view"] = "device"
    at.run()
    assert "Review required" in at.expander[0].label
    at.text_input[4].set_value("6000062118").run()
    assert "Outside recall scope" in at.expander[0].label
