from pipeline.guard import check


def test_normal_day_publishes():
    assert check(480, 470)[0]


def test_first_run_publishes():
    assert check(None, 300)[0]


def test_big_drop_blocked():          # e.g. Adzuna down: 480 -> 22
    ok, reason = check(480, 22)
    assert not ok and "minimum" in reason


def test_more_than_half_lost_blocked():
    ok, reason = check(480, 200)
    assert not ok and "half" in reason


def test_missing_file_blocked():
    assert not check(480, None)[0]
