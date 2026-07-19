"""
High-Security Anti-Cheating Module
Implements compiled regex engines, Haversine geofencing,
biometric cosine similarity, and account protection.
"""
import re
import math
import logging
import numpy as np
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from threading import Lock

logger = logging.getLogger(__name__)


class SecurityExceptions:
    """Container for all security-related exception classes."""

    class GeofenceBreachException(Exception):
        """Raised when a user is outside the allowed geofence radius."""
        def __init__(self, distance_meters: float, max_allowed: float = 15):
            self.distance_meters = distance_meters
            self.max_allowed = max_allowed
            super().__init__(
                f"Geofence breach: {distance_meters:.2f}m exceeds {max_allowed}m limit"
            )

    class FaceMatchException(Exception):
        """Raised when facial similarity is below threshold."""
        def __init__(self, similarity: float, threshold: float = 0.85):
            self.similarity = similarity
            self.threshold = threshold
            super().__init__(
                f"Face match failed: similarity {similarity:.4f} < {threshold}"
            )

    class EmailValidationException(Exception):
        """Raised when email doesn't match *@met.edu pattern."""
        def __init__(self, email: str):
            self.email = email
            super().__init__(f"Email {email} does not belong to @met.edu domain")

    class RollNumberException(Exception):
        """Raised when roll number format is invalid."""
        def __init__(self, roll_number: str):
            self.roll_number = roll_number
            super().__init__(f"Invalid roll number format: {roll_number}")

    class AccountLockedException(Exception):
        """Raised when an account is locked due to failed attempts."""
        def __init__(self, email: str):
            self.email = email
            super().__init__(f"Account {email} is locked due to too many failed attempts")

    class SessionExpiredException(Exception):
        """Raised when a session or token has expired."""
        def __init__(self, token: str):
            self.token = token
            super().__init__(f"Session/Token expired: {token}")

    class SpoofingDetectedException(Exception):
        """Raised when photo spoofing or replay attack is detected."""
        def __init__(self, detail: str = "Potential spoofing detected"):
            self.detail = detail
            super().__init__(detail)


class RegexCompiledEngine:
    """
    Compiled Regex Engines for strict enforcement patterns.
    Thread-safe pre-compiled patterns for performance.
    """
    _lock = Lock()
    _instances = {}

    @classmethod
    def get_pattern(cls, name: str) -> re.Pattern:
        """Get a compiled regex pattern by name (cached)."""
        if name not in cls._instances:
            with cls._lock:
                if name not in cls._instances:
                    cls._compile_patterns()
        return cls._instances.get(name)

    @classmethod
    def _compile_patterns(cls):
        """Pre-compile all regex patterns."""
        cls._instances['email_met'] = re.compile(
            r'^[a-zA-Z0-9._%+-]+@met\.edu$', re.IGNORECASE
        )
        cls._instances['roll_number'] = re.compile(
            r'^STU-\d{4}-(MCA|BCA|BBA|MBA)-\d{4}$'
        )
        cls._instances['phone'] = re.compile(
            r'^\+?[1-9]\d{9,14}$'
        )
        cls._instances['name'] = re.compile(
            r"^[a-zA-Z\s'-]{2,100}$"
        )
        cls._instances['subject_code'] = re.compile(
            r'^[A-Z]{2,4}-\d{3}$'
        )
        cls._instances['semester'] = re.compile(
            r'^(MCA|BCA|BBA|MBA)_[1-9]$'
        )
        cls._instances['password_strength'] = re.compile(
            r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,32}$'
        )
        cls._instances['latitude'] = re.compile(
            r'^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?)$'
        )
        cls._instances['longitude'] = re.compile(
            r'^[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$'
        )

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email follows *@met.edu pattern."""
        pattern = RegexCompiledEngine.get_pattern('email_met')
        return bool(pattern.match(email))

    @staticmethod
    def validate_roll_number(roll_number: str) -> bool:
        """Validate roll number format: STU-XXXX-COURSE-XXXX."""
        pattern = RegexCompiledEngine.get_pattern('roll_number')
        return bool(pattern.match(roll_number))

    @staticmethod
    def validate_password(password: str) -> bool:
        """Validate password strength requirements."""
        pattern = RegexCompiledEngine.get_pattern('password_strength')
        return bool(pattern.match(password))

    @staticmethod
    def extract_roll_number_parts(roll_number: str) -> Optional[Dict[str, str]]:
        """Extract course and sequence from a valid roll number."""
        pattern = RegexCompiledEngine.get_pattern('roll_number')
        match = pattern.match(roll_number)
        if match:
            return {
                'full': match.group(0),
                'course': match.group(1),
            }
        return None


class HaversineGeofence:
    """
    15-Meter Haversine Geofencing implementation.
    Computes great-circle spherical distance between two GPS coordinates.
    """

    EARTH_RADIUS_METERS = 6371000.0

    @staticmethod
    def to_radians(degrees: float) -> float:
        """Convert degrees to radians."""
        return degrees * (math.pi / 180.0)

    @staticmethod
    def calculate_distance(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """
        Calculate the Haversine distance between two GPS points in meters.

        Args:
            lat1, lon1: Coordinates of point 1 (in degrees)
            lat2, lon2: Coordinates of point 2 (in degrees)

        Returns:
            Distance in meters
        """
        d_lat = HaversineGeofence.to_radians(lat2 - lat1)
        d_lon = HaversineGeofence.to_radians(lon2 - lon1)

        lat1_rad = HaversineGeofence.to_radians(lat1)
        lat2_rad = HaversineGeofence.to_radians(lat2)

        a = (
            math.sin(d_lat / 2.0) ** 2 +
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

        distance = HaversineGeofence.EARTH_RADIUS_METERS * c
        return distance

    @staticmethod
    def validate_proximity(
        student_lat: float,
        student_lon: float,
        faculty_lat: float,
        faculty_lon: float,
        max_distance_meters: float = 15.0,
    ) -> Tuple[bool, float]:
        """
        Validate that a student is within the geofence of the faculty.

        Args:
            student_lat, student_lon: Student's GPS coordinates
            faculty_lat, faculty_lon: Faculty's GPS coordinates
            max_distance_meters: Maximum allowed distance (default: 15m)

        Returns:
            Tuple of (is_within_bounds, distance_in_meters)

        Raises:
            GeofenceBreachException if outside bounds
        """
        distance = HaversineGeofence.calculate_distance(
            student_lat, student_lon, faculty_lat, faculty_lon
        )

        if distance > max_distance_meters:
            raise SecurityExceptions.GeofenceBreachException(
                distance_meters=distance, max_allowed=max_distance_meters
            )

        return True, distance


class BiometricCosineSimilarity:
    """
    Biometric verification using cosine similarity between face embeddings.
    Includes anti-spoofing tracking indicators.
    """

    @staticmethod
    def cosine_similarity(vector_a: List[float], vector_b: List[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vector_a: First embedding vector (128-dimensional)
            vector_b: Second embedding vector (128-dimensional)

        Returns:
            Cosine similarity score between -1 and 1
        """
        a = np.array(vector_a, dtype=np.float64)
        b = np.array(vector_b, dtype=np.float64)

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        dot_product = np.dot(a, b)
        similarity = dot_product / (norm_a * norm_b)
        return float(similarity)

    @staticmethod
    def verify_face(
        live_embedding: List[float],
        stored_embedding: List[float],
        threshold: float = 0.85,
    ) -> Tuple[bool, float]:
        """
        Verify a live face embedding against the stored master profile.

        Args:
            live_embedding: Captured live face embedding (128-dim)
            stored_embedding: Master profile embedding from DB (128-dim)
            threshold: Minimum similarity threshold (default: 0.85)

        Returns:
            Tuple of (is_match, similarity_score)

        Raises:
            FaceMatchException if similarity below threshold
        """
        if len(live_embedding) != 128 or len(stored_embedding) != 128:
            raise ValueError(
                f"Embeddings must be 128-dimensional. "
                f"Got {len(live_embedding)} and {len(stored_embedding)}"
            )

        similarity = BiometricCosineSimilarity.cosine_similarity(
            live_embedding, stored_embedding
        )

        if similarity < threshold:
            raise SecurityExceptions.FaceMatchException(
                similarity=similarity, threshold=threshold
            )

        return True, similarity

    @staticmethod
    def detect_spoofing(
        embedding_variance: float,
        liveness_score: float,
        embedding_quality: float,
    ) -> bool:
        """
        Anti-spoofing detection using embedding quality metrics.

        Args:
            embedding_variance: Variance within the embedding vector
            liveness_score: Liveness detection score (0-1)
            embedding_quality: Quality score of the captured image (0-1)

        Returns:
            True if spoofing is suspected

        Raises:
            SpoofingDetectedException if spoofing indicators found
        """
        spoofing_indicators = []

        if embedding_variance < 0.001:
            spoofing_indicators.append("Low embedding variance (possible static image)")
        if liveness_score < 0.3:
            spoofing_indicators.append("Low liveness score (possible photo)")
        if embedding_quality < 0.4:
            spoofing_indicators.append("Poor embedding quality (possible spoof)")

        if len(spoofing_indicators) >= 2:
            raise SecurityExceptions.SpoofingDetectedException(
                "; ".join(spoofing_indicators)
            )

        return False