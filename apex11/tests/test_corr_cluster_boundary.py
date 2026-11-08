import numpy as np
from apex.risk import limits


def test_correlation_exact_threshold_tolerates_rounding():
    # Covariance with off-diagonal numerically one ULP below 0.85.
    cov=np.array([[1.0, np.nextafter(0.85, 0.0)],
                  [np.nextafter(0.85, 0.0), 1.0]])
    assert limits.corr_clusters(["A", "B"], cov, threshold=0.85)==[["A", "B"]]


def test_genuinely_lower_correlation_is_not_accidentally_promoted():
    cov=np.array([[1.0, 0.849], [0.849, 1.0]])
    assert limits.corr_clusters(["A", "B"], cov, threshold=0.85)==[]
