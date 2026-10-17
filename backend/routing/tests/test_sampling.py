from datetime import datetime, timedelta, timezone

import pytest

from routing.sampling import haversine_miles, sample_route


def test_samples_cover_start_interval_and_destination():
    coordinates = [[0.0, 0.0], [1.0, 0.0]]
    departure = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)
    duration = 7200
    samples = sample_route(coordinates, 25, departure, duration)

    total = haversine_miles(0, 0, 1, 0)
    assert [sample.mile for sample in samples] == pytest.approx([0, 25, 50, total])
    assert samples[0].eta == departure
    assert samples[-1].eta == departure + timedelta(seconds=duration)
    assert samples[1].eta == departure + timedelta(seconds=duration * 25 / total)
    assert samples[-1].segment_miles == 0
    assert sum(sample.segment_miles for sample in samples) == pytest.approx(total)
    assert samples[0].lat == pytest.approx(0)
    assert samples[-1].lon == pytest.approx(1)


def test_sample_inside_a_later_segment_keeps_the_line():
    coordinates = [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0]]
    departure = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)
    samples = sample_route(coordinates, 50, departure, 3600)

    midpoint = next(sample for sample in samples if sample.mile == pytest.approx(50))
    first_leg = haversine_miles(0, 0, 0.5, 0)
    assert first_leg < 50
    assert 0.5 < midpoint.lon < 1
    assert midpoint.lat == pytest.approx(0)


def test_very_short_route_is_start_and_end_only():
    coordinates = [[0.0, 0.0], [0.01, 0.0]]
    departure = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)
    samples = sample_route(coordinates, 25, departure, 600)
    assert len(samples) == 2
    assert samples[0].mile == 0
    assert samples[1].segment_miles == 0


def test_duplicate_coordinates_produce_one_checkpoint():
    departure = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)
    samples = sample_route([[-87.6, 41.8], [-87.6, 41.8]], 10, departure, 0)
    assert len(samples) == 1
    assert samples[0].mile == 0
    assert samples[0].segment_miles == 0
    assert samples[0].eta == departure
