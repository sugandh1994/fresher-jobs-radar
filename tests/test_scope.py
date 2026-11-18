"""The scope step: jobs the model tagged role "Other" are hidden from the site."""
import json

from pipeline import run
from pipeline.models import Job


def job(id, role=None):
    return Job(id=id, title=f"Job {id}", company="Acme", location_raw="Pune, India",
               url=f"https://x/{id}", source="adzuna", posted_at="2026-11-10",
               description="d", role=role, city="Pune" if role else None)


def run_tag_and_write(tmp_path, monkeypatch, jobs, fallback_ids=()):
    monkeypatch.setattr(run, "JOBS_FILE", tmp_path / "jobs.json")
    monkeypatch.setattr(run, "RUN_LOG_FILE", tmp_path / "run_log.json")
    # Pretend tagging already happened (roles set on the jobs above).
    monkeypatch.setattr(run, "tag_jobs", lambda jobs, use_llm: {"fallback_ids": list(fallback_ids)})
    log = {"steps": {}, "sources": {}}
    run.tag_and_write(jobs, log, use_llm=False)
    return json.loads((tmp_path / "jobs.json").read_text()), log


def test_model_decided_other_is_hidden(tmp_path, monkeypatch):
    out, log = run_tag_and_write(tmp_path, monkeypatch,
                                 [job("a", "Data Analytics"), job("b", "Other")])
    assert [j["id"] for j in out["jobs"]] == ["a"]
    assert log["out_of_scope"]["hidden"] == 1


def test_untagged_and_fallback_jobs_are_kept(tmp_path, monkeypatch):
    out, _ = run_tag_and_write(tmp_path, monkeypatch,
                               [job("a", None), job("b", "Other")], fallback_ids=["b"])
    assert {j["id"] for j in out["jobs"]} == {"a", "b"}


def test_quality_is_measured_before_hiding(tmp_path, monkeypatch):
    _, log = run_tag_and_write(tmp_path, monkeypatch,
                               [job("a", "Data Analytics"), job("b", "Other")])
    assert log["quality"]["role_not_other"] == 1 and log["quality"]["total_tagged"] == 2


CITIES = ["Mumbai", "Pune", "Bengaluru", "Delhi NCR", "Remote", "Other India"]


def test_location_city_from_text():
    assert run.location_city("Bangalore, Karnataka, India", CITIES) == "Bengaluru"
    assert run.location_city("Gurgaon, Haryana", CITIES) == "Delhi NCR"
    assert run.location_city("Remote - India", CITIES) == "Remote"
    assert run.location_city("Kanpur, Uttar Pradesh, India", CITIES) == "Other India"
    assert run.location_city("India", CITIES) is None
    assert run.location_city("", CITIES) is None


def test_jobs_json_includes_city_from_location(tmp_path, monkeypatch):
    j = job("a", "Data Analytics")
    j.location_raw = "Navi Mumbai, Maharashtra"
    out, _ = run_tag_and_write(tmp_path, monkeypatch, [j])
    assert out["jobs"][0]["city_from_location"] == "Mumbai"


def test_page_dropdown_has_no_other_role(tmp_path, monkeypatch):
    out, _ = run_tag_and_write(tmp_path, monkeypatch, [job("a", "Data Analytics")])
    assert "Other" not in out["taxonomy"]["roles"]
    assert "Other India" in out["taxonomy"]["cities"]
