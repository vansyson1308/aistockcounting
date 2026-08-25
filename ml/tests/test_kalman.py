import pytest

from ml.track.kalman import CenterKalman


def test_constant_velocity_convergence():
    kf = CenterKalman(0.0, 0.0)
    for i in range(1, 30):
        kf.predict()
        kf.update(2.0 * i, -1.0 * i)
    assert kf.velocity[0] == pytest.approx(2.0, abs=0.2)
    assert kf.velocity[1] == pytest.approx(-1.0, abs=0.2)
    predicted = kf.predict()
    assert predicted[0] == pytest.approx(2.0 * 30, abs=1.0)
    assert predicted[1] == pytest.approx(-1.0 * 30, abs=1.0)


def test_prediction_coasts_through_gap():
    kf = CenterKalman(0.0, 100.0)
    for i in range(1, 20):
        kf.predict()
        kf.update(3.0 * i, 100.0)
    for _ in range(5):  # occlusion: predict only
        center = kf.predict()
    assert center[0] == pytest.approx(3.0 * 24, abs=2.0)
    assert center[1] == pytest.approx(100.0, abs=2.0)
