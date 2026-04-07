import math
import pytest
from hunter_grid import get_distance_3d

def test_zero_distance():
    """Test that calculating the distance to the exact same point yields 0."""
    dist = get_distance_3d(47.398, 8.546, 10.0, 47.398, 8.546, 10.0)
    assert math.isclose(dist, 0.0, abs_tol=0.1), f"Expected 0.0, got {dist}"

def test_vertical_movement_only():
    """Test that moving perfectly straight up 15 meters registers as a 15m distance."""
    # Same Lat/Lon, but altitude goes from 10.0 to 25.0
    dist = get_distance_3d(47.398, 8.546, 10.0, 47.398, 8.546, 25.0)
    assert math.isclose(dist, 15.0, abs_tol=0.1), f"Expected 15.0, got {dist}"

def test_horizontal_haversine():
    """Test standard 2D Haversine math. 0.0001 degrees of latitude is ~11.1 meters."""
    dist = get_distance_3d(47.3980, 8.546, 10.0, 47.3981, 8.546, 10.0)
    # Using a 0.2m tolerance because the Earth isn't a perfect sphere
    assert math.isclose(dist, 11.1, abs_tol=0.2), f"Expected ~11.1, got {dist}"

def test_full_3d_pythagorean():
    """Test the combination of Haversine and altitude using the Pythagorean theorem."""
    # Moving 11.1m horizontally (0.0001 lat) and 10m vertically.
    # $a^2 + b^2 = c^2$ -> $11.1^2 + 10^2$ = 123.21 + 100 = 223.21. 
    # $\sqrt{223.21} \approx 14.94$ meters.
    dist = get_distance_3d(47.3980, 8.546, 10.0, 47.3981, 8.546, 20.0)
    assert math.isclose(dist, 14.94, abs_tol=0.2), f"Expected ~14.94, got {dist}"
