"""Tagger tests use a fake client — no real API calls, no key needed."""
import json
from types import SimpleNamespace

from pipeline.dedupe import fingerprint
from pipeline.models import Job
from pipeline.tagger import Tagger, load_taxonomy, parse_answer, tag_jobs

ROLES, CITIES, NOTES = load_taxonomy()


def job(id, title="Data Analyst Intern", loc="Pune, India"):
    return Job(id=id, title=title, company="Acme", location_raw=loc, url=f"https://x/{id}",
               source="adzuna", posted_at="2026-11-10", description="desc")


class FakeClient:
    """Returns queued answers; records what was sent."""
    def __init__(self, answers):
        self.answers = list(answers)
        self.sent = []
        self.messages = self

    def create(self, **kwargs):
        self.sent.append(kwargs)
        answer = self.answers.pop(0)
        text = answer if isinstance(answer, str) else json.dumps({"tags": answer})
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )


def make_tagger(answers):
    return Tagger(client=FakeClient(answers), taxonomy=(ROLES, CITIES, NOTES))


def test_taxonomy_parsed_from_doc():
    assert "Data Analytics" in ROLES and ROLES[-1] == "Other"
    assert "Delhi NCR" in CITIES and "Other India" in CITIES  # parenthetical stripped
    assert "Bangalore" in NOTES


def test_parse_answer_replaces_unknown_values_and_ignores_unknown_ids():
    text = json.dumps({"tags": [
        {"id": "a", "role": "Astronaut", "city": "Pune"},
        {"id": "zzz", "role": "Data Analytics", "city": "Pune"},
    ]})
    assert parse_answer(text, {"a"}, ROLES, CITIES) == {"a": {"role": "Other", "city": "Pune"}}


def test_tags_and_caches(tmp_path):
    cache = tmp_path / "cache.json"
    jobs = [job("a")]
    tagger = make_tagger([[{"id": "a", "role": "Data Analytics", "city": "Pune"}]])
    stats = tag_jobs(jobs, tagger=tagger, cache_path=cache)
    assert (jobs[0].role, jobs[0].city) == ("Data Analytics", "Pune")
    assert stats["newly_tagged"] == 1
    assert json.loads(cache.read_text())[fingerprint(jobs[0])]["role"] == "Data Analytics"


def test_cached_jobs_are_not_sent_again(tmp_path):
    cache = tmp_path / "cache.json"
    tag_jobs([job("a")], tagger=make_tagger([[{"id": "a", "role": "Data Analytics", "city": "Pune"}]]),
             cache_path=cache)
    fresh = make_tagger([])  # would crash if called
    jobs = [job("a")]
    stats = tag_jobs(jobs, tagger=fresh, cache_path=cache)
    assert stats["from_cache"] == 1 and fresh.client.sent == []
    assert jobs[0].role == "Data Analytics"


def test_invalid_json_retries_once_then_falls_back_uncached(tmp_path):
    cache = tmp_path / "cache.json"
    tagger = make_tagger(["not json", "still not json"])
    jobs = [job("a")]
    stats = tag_jobs(jobs, tagger=tagger, cache_path=cache)
    assert len(tagger.client.sent) == 2
    assert (jobs[0].role, jobs[0].city) == ("Other", "Other India")
    assert stats["fallback"] == 1
    assert json.loads(cache.read_text()) == {}  # fallback not cached -> retried next run


def test_retry_only_resends_missing_jobs(tmp_path):
    tagger = make_tagger([
        [{"id": "a", "role": "Data Analytics", "city": "Pune"}],          # "b" missing
        [{"id": "b", "role": "HR / Recruitment", "city": "Pune"}],
    ])
    jobs = [job("a"), job("b", title="HR Intern")]
    tag_jobs(jobs, tagger=tagger, cache_path=tmp_path / "c.json")
    second = json.loads(tagger.client.sent[1]["messages"][0]["content"].split("\n", 1)[1])
    assert [j["id"] for j in second] == ["b"]
    assert jobs[1].role == "HR / Recruitment"


def test_batches_of_20_and_trimmed_description(tmp_path):
    jobs = [job(str(i), title=f"Role {i}") for i in range(45)]
    for j in jobs:
        j.description = "x" * 2000
    answers = [[{"id": j.id, "role": "Other", "city": "Pune"} for j in jobs[i:i + 20]]
               for i in range(0, 45, 20)]
    tagger = make_tagger(answers)
    tag_jobs(jobs, tagger=tagger, cache_path=tmp_path / "c.json")
    assert len(tagger.client.sent) == 3
    first = json.loads(tagger.client.sent[0]["messages"][0]["content"].split("\n", 1)[1])
    assert len(first) == 20 and len(first[0]["description"]) == 600
    assert set(first[0]) == {"id", "title", "company", "location_raw", "description"}


def test_account_error_stops_after_first_batch_and_leaves_jobs_untagged(tmp_path):
    import anthropic
    import httpx2

    class BrokeClient(FakeClient):
        def create(self, **kwargs):
            self.sent.append(kwargs)
            req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.BadRequestError(
                "credit balance is too low", response=httpx2.Response(400, request=req), body=None)

    tagger = Tagger(client=BrokeClient([]), taxonomy=(ROLES, CITIES, NOTES))
    jobs = [job(str(i)) for i in range(45)]
    stats = tag_jobs(jobs, tagger=tagger, cache_path=tmp_path / "c.json")
    assert len(tagger.client.sent) == 1                  # didn't hammer the API
    assert stats["untagged"] == 45 and "credit" in stats["error"]
    assert all(j.role is None for j in jobs)             # not falsely marked "Other"


def test_no_llm_uses_cache_only(tmp_path):
    jobs = [job("a")]
    stats = tag_jobs(jobs, use_llm=False, cache_path=tmp_path / "c.json")
    assert stats["untagged"] == 1 and jobs[0].role is None
