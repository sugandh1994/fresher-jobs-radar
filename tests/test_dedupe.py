from pipeline.dedupe import canonical_url, city_key, clean_company, dedupe, fingerprint
from pipeline.models import Job


def job(id, title="Software Engineer Intern", company="Acme Pvt Ltd", loc="Bangalore, Karnataka, India",
        url=None, desc="short", posted="2026-11-10", source="adzuna"):
    return Job(id=id, title=title, company=company, location_raw=loc, url=url or f"https://x.com/{id}",
               source=source, posted_at=posted, description=desc, sources=[source])


# --- helpers ---

def test_canonical_url_strips_tracking_and_slash():
    a = canonical_url("https://Jobs.Lever.co/acme/123/?utm_source=x&lever-source=LinkedIn")
    b = canonical_url("https://jobs.lever.co/acme/123")
    assert a == b


def test_canonical_url_keeps_meaningful_params():
    assert canonical_url("https://x.com/job?id=1") != canonical_url("https://x.com/job?id=2")


def test_clean_company_removes_legal_suffixes():
    assert clean_company("Acme Pvt. Ltd.") == clean_company("ACME Private Limited") == "acme"


def test_city_key_aliases():
    assert city_key("Bangalore, Karnataka") == "bengaluru"
    assert city_key("Gurgaon, Haryana, India") == "delhi ncr"
    assert city_key("Navi Mumbai") == "mumbai"
    assert city_key("Remote - India") == "remote"
    assert city_key("Kanpur, Uttar Pradesh") == "kanpur"


def test_fingerprint_ignores_case_punctuation_and_suffix():
    a = job("a", title="Software Engineer - Intern", company="Acme Pvt Ltd", loc="Bangalore")
    b = job("b", title="software engineer intern", company="ACME Limited", loc="Bengaluru, India")
    assert fingerprint(a) == fingerprint(b)


# --- the three rules ---

def test_rule1_same_url():
    kept, removed = dedupe([
        job("a", title="Data Analyst", url="https://x.com/j/1?utm_source=a"),
        job("b", title="Totally different title", url="https://x.com/j/1/"),
    ])
    assert len(kept) == 1 and removed[0].rule == "url"


def test_rule2_fingerprint():
    kept, removed = dedupe([job("a", company="Acme Pvt Ltd"), job("b", company="ACME Limited")])
    assert len(kept) == 1 and removed[0].rule == "fingerprint"


def test_rule3_fuzzy_same_company_and_city():
    kept, removed = dedupe([
        job("a", title="Software Engineer Intern - Backend"),
        job("b", title="Backend Software Engineer Intern"),
    ])
    assert len(kept) == 1 and removed[0].rule == "fuzzy"


def test_fuzzy_does_not_merge_different_levels():
    kept, _ = dedupe([
        job("a", title="Procure to Pay Operations New Associate", company="Accenture", loc="India"),
        job("b", title="Procure to Pay Operations Associate", company="Accenture", loc="India"),
    ])
    assert len(kept) == 2


def test_fuzzy_fresher_vs_freshers_still_merges():
    kept, _ = dedupe([
        job("a", title="Business Development Associate (Fresher)"),
        job("b", title="Business Development Associate (Freshers)"),
    ])
    assert len(kept) == 1


def test_fuzzy_needs_same_city():
    kept, _ = dedupe([job("a", loc="Pune"), job("b", title="Software Engineering Intern", loc="Chennai")])
    assert len(kept) == 2


def test_fuzzy_needs_same_company():
    kept, _ = dedupe([job("a", company="Acme"), job("b", company="Globex")])
    assert len(kept) == 2


def test_different_jobs_kept():
    kept, removed = dedupe([job("a", title="Data Analyst Intern"), job("b", title="HR Intern")])
    assert len(kept) == 2 and removed == []


# --- merge behaviour ---

def test_merge_keeps_longest_description_newest_date_all_sources():
    kept, _ = dedupe([
        job("a", desc="short", posted="2026-11-15", source="adzuna"),
        job("b", desc="a much longer description", posted="2026-11-01", source="lever"),
    ])
    (j,) = kept
    assert j.id == "b"
    assert j.posted_at == "2026-11-15"
    assert j.sources == ["adzuna", "lever"]
