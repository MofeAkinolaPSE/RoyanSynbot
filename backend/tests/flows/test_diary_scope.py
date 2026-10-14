"""Appointments and My Schedule are personal: a doctor sees what is booked to them; the desk sees all."""
import uuid

from src.routers import appointments as appt
from src.routers import calendar_tasks as cal


def test_doctor_sees_only_their_own_and_the_desk_sees_everyone(monkeypatch):
    me = str(uuid.uuid4())
    monkeypatch.setattr(appt, "_my_staff_id", lambda user: me)
    assert appt._doctor_scope({"sub": "u", "roles": ["doctor"]}) == me
    assert appt._doctor_scope({"sub": "u", "roles": ["receptionist"]}) is None
    assert appt._doctor_scope({"sub": "u", "roles": ["doctor", "admin"]}) is None          # admin runs the book
    assert appt._doctor_scope({"sub": "u", "roles": ["doctor", "admin"]}, mine=True) == me  # ... unless asking for theirs
    assert appt._doctor_scope({"sub": "u", "roles": ["nurse"]}, mine=True) == me


def test_doctor_without_hr_record_sees_nobody(monkeypatch):
    monkeypatch.setattr(appt, "_my_staff_id", lambda user: None)
    assert appt._doctor_scope({"sub": "u", "roles": ["doctor"]}) == appt._NOBODY   # never the whole hospital


def test_my_events_are_the_ones_i_attend_or_created():
    me = str(uuid.uuid4())
    assert cal._event_is_mine({"attendees": [me]}, me)
    assert cal._event_is_mine({"metadata": {"created_by": me}}, me)
    assert cal._event_is_mine({"metadata": '{"created_by": "%s"}' % me}, me)
    assert cal._event_is_mine({"event_type": "holiday"}, me)
    assert not cal._event_is_mine({"attendees": [str(uuid.uuid4())], "metadata": {}}, me)
