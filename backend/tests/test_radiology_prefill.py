"""The Scancare report pre-fill must never carry an earlier patient's details onto a new report."""
from src.services.radiology_prefill import blank_measurements, with_indication


def test_measurements_dates_and_personal_lines_are_blanked():
    t = blank_measurements(
        "LIVER: SIZE (ABOUT 134.1MM CRANIO-CAUDALLY)\n"
        "KIDNEYS: RIGHT 91.1X38.4MM, LEFT 98.7X44.2MM\n"
        "FHR= 148BPM. AFI= 12.24CM. GA: 19WEEKS, 4DAYS. VOLUME 23.99CM3. 60% STENOSIS\n"
        "EDD: 07/10/2025 (DD/MM/YYYY)\nGENDER: XY\nLEVEL L4-L5 DISC")
    for leak in ("134.1", "91.1", "38.4", "98.7", "148", "12.24", "19WEEKS", "23.99", "60%", "07/10/2025", "XY"):
        assert leak not in t, leak
    assert "___X___MM" in t and "GENDER: ___" in t and "EDD: ___ (DD/MM/YYYY)" in t
    assert "L4-L5" in t                                   # not a measurement


def test_indication_is_this_patients():
    prior = "INDICATIONS:\nLEFT-SIDED ABDOMINAL PAIN.\nTECHNIQUE:\nPROBES;\nFINDINGS:\nNORMAL"
    t = with_indication(prior, "Right upper quadrant pain")
    assert "LEFT-SIDED" not in t and "RIGHT UPPER QUADRANT PAIN" in t and "TECHNIQUE:" in t and "FINDINGS:" in t
    t = with_indication("CLINICAL HISTORY\nHx OF HEADACHE\nFINDINGS:\nNORMAL", None)
    assert "HEADACHE" not in t and "___" in t
