from datetime import date

from pipeline import filters
from pipeline.models import Job, RawJob
from pipeline.normalize import normalize, strip_html


def make_job(title="Software Trainee", desc="", loc="Bangalore, Karnataka, India", posted="2026-11-10"):
    return Job(id="x", title=title, company="Acme", location_raw=loc, url="https://e.x",
               source="adzuna", posted_at=posted, description=desc)


def test_strip_html():
    assert strip_html("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"


def test_normalize_adzuna():
    raw = RawJob("adzuna", {
        "id": "123", "title": "<strong>Data</strong> Analyst Intern",
        "company": {"display_name": "Acme Pvt Ltd"},
        "location": {"display_name": "Pune, Maharashtra", "area": ["India", "Maharashtra", "Pune"]},
        "redirect_url": "https://www.adzuna.in/land/ad/123",
        "created": "2026-11-15T08:00:00Z",
        "description": "Freshers welcome, 0-1 years experience.",
    })
    job = normalize(raw)
    assert job.id == "adzuna:123"
    assert job.title == "Data Analyst Intern"
    assert job.location_raw == "Pune, Maharashtra, India"
    assert job.posted_at == "2026-11-15"
    assert job.experience_hint == "0-1 years"


def test_fresher_keyword_in_title():
    assert filters.is_fresher(make_job("Graduate Engineer Trainee"))


def test_fresher_by_experience():
    assert filters.is_fresher(make_job("Backend Developer", "Experience: 0-1 years"))


def test_senior_title_rejected():
    assert not filters.is_fresher(make_job("Senior Developer", "Graduate degree required"))


def test_experienced_rejected():
    assert not filters.is_fresher(make_job("Backend Developer", "3-5 years experience. Graduate."))


import pytest


@pytest.mark.parametrize("title, desc", [
    # real examples that slipped through before the 2026-11-17 fix
    ("Electrical Engineering", "Provides guidance to entry level engineers."),
    ("Associate Program Coordinator", "Location: IIDE Andheri Campus Office"),
    ("Executive", "Experience: 1-3 Years Qualification: Graduate (Any Discipline)"),
    ("International Voice Process Executive", "Experience: Minimum 1 year (JL2A)"),
    ("Chef de Partie", "leading a team of junior chefs"),
    ("Analyst", "Mentor junior SDETs and QA engineers."),
    ("Team Leader", "Must Be a Graduate. Growth mindset."),
    ("Sales Executive", "Freshers need not apply. 2 years required."),
    ("Systems Engineering Associate", "Our interns and new graduates work on real projects."),
])
def test_not_fresher_examples(title, desc):
    assert not filters.is_fresher(make_job(title, desc))


@pytest.mark.parametrize("title, desc", [
    ("Lab Tech", "Experience: Fresher / 1–3 Years"),               # says fresher -> keep
    ("Customer Support Executive", "Experience: 0–2 Years (Freshers can apply)"),
    ("Marketing Associate", "We want a Marketing & Brand Intern who is eager to learn"),
    ("Client Onboard Analyst 1", "The Client Onboard Analyst 1 is a trainee professional role."),
    ("Jr. Analyst – HR Operations", ""),
    ("Quantexa Developer", "Junior Quantexa Developer Role Overview"),
    ("Commis - Bakery", "In this entry-level kitchen position, you will work"),
    ("Sales Executive", "an excellent opportunity for early-career professionals"),
    ("Content Writer", "We are a 15 years old agency. Freshers welcome."),
])
def test_fresher_examples(title, desc):
    assert filters.is_fresher(make_job(title, desc))


def test_india_check():
    assert filters.is_india(make_job(loc="Gurgaon, Haryana, India"))
    assert not filters.is_india(make_job(loc="London, UK"))


def test_recent():
    assert filters.is_recent(make_job(posted="2026-11-01"), today=date(2026, 11, 17))
    assert not filters.is_recent(make_job(posted="2026-09-01"), today=date(2026, 11, 17))


def test_company_boards_skip_age_rule():
    old = make_job(posted="2026-08-01")
    old.source = "lever"
    assert filters.is_recent(old, today=date(2026, 11, 17))
