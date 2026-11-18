from pipeline import filters
from pipeline.models import RawJob
from pipeline.normalize import normalize


def test_normalize_greenhouse():
    job = normalize(RawJob("greenhouse", {
        "id": 42, "title": "Software Engineer - New Grad",
        "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/42",
        "location": {"name": "Bengaluru, Karnataka, India"},
        "first_published": "2026-11-10T09:00:00-05:00",
        "updated_at": "2026-11-16T09:00:00-05:00",
        "content": "&lt;p&gt;Join us &amp;amp; build things.&lt;/p&gt;",
        "_company": "Acme", "_slug": "acme",
    }))
    assert job.id == "greenhouse:acme:42"
    assert job.posted_at == "2026-11-10"          # first published, not last edited
    assert job.description == "Join us & build things."
    assert filters.is_india(job) and filters.is_fresher(job)


def test_normalize_lever():
    job = normalize(RawJob("lever", {
        "id": "abc", "text": "Associate Intern",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "categories": {"location": "Pune", "allLocations": ["Pune", "Mumbai"]},
        "country": "IN", "workplaceType": "hybrid",
        "createdAt": 1763280000000,  # 2025-11-16
        "descriptionPlain": "Great role.",
        "lists": [{"text": "Requirements", "content": "<li>0-1 years</li>"}],
        "_company": "Acme", "_slug": "acme",
    }))
    assert job.id == "lever:acme:abc"
    assert job.location_raw == "Pune / Mumbai, India"
    assert job.posted_at == "2025-11-16"
    assert "0-1 years" in job.description


def test_remote_only_counts_for_india_only_sources():
    gh = normalize(RawJob("greenhouse", {"id": 1, "title": "Intern", "location": {"name": "Remote - US"},
                                         "_slug": "x"}))
    assert not filters.is_india(gh)
    gh_in = normalize(RawJob("greenhouse", {"id": 2, "title": "Intern", "location": {"name": "Remote - India"},
                                            "_slug": "x"}))
    assert filters.is_india(gh_in)
