"""
Models and BSON object mapping for Smart Attendance SaaS.
Defines the document structures for all MongoDB collections.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any


class UserDocument:
    """
    Schema definition for the 'users' collection.
    Fields: name, email, password_hash, role, department, course,
    semester, roll_number, face_embedding, created_at, is_active.
    Email regex locked to *@met.edu enforced at validation layer.
    """

    COLLECTION_NAME = 'users'

    # Role constants
    ROLE_SUPER_ADMIN = 'SUPER_ADMIN'
    ROLE_FACULTY_HEAD = 'FACULTY_HEAD'
    ROLE_FACULTY_STAFF = 'FACULTY_STAFF'
    ROLE_STUDENT = 'STUDENT'

    VALID_ROLES = [ROLE_SUPER_ADMIN, ROLE_FACULTY_HEAD, ROLE_FACULTY_STAFF, ROLE_STUDENT]

    @staticmethod
    def create_document(
        name: str,
        email: str,
        password_hash: str,
        role: str,
        department: Optional[str] = None,
        course: Optional[str] = None,
        semester: Optional[str] = None,
        roll_number: Optional[str] = None,
        face_embedding: Optional[List[float]] = None,
        phone: Optional[str] = None,
        parent_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a user document dictionary matching the schema."""
        if role not in UserDocument.VALID_ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of {UserDocument.VALID_ROLES}")

        doc = {
            'name': name,
            'email': email.lower(),
            'password_hash': password_hash,
            'role': role,
            'department': department,
            'course': course,
            'semester': semester,
            'roll_number': roll_number,
            'phone': phone,
            'parent_phone': parent_phone,
            'face_embedding': face_embedding or [],
            'embedding_dimension': len(face_embedding) if face_embedding else 0,
            'is_active': True,
            'is_verified': False,
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
            'last_login': None,
            'failed_attempts': 0,
            'account_locked': False,
        }
        return doc

    @staticmethod
    def create_student(
        name: str,
        email: str,
        password_hash: str,
        department: str,
        course: str,
        semester: str,
        roll_number: str,
        face_embedding: Optional[List[float]] = None,
        phone: Optional[str] = None,
        parent_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a student document."""
        return UserDocument.create_document(
            name=name, email=email, password_hash=password_hash,
            role=UserDocument.ROLE_STUDENT, department=department,
            course=course, semester=semester, roll_number=roll_number,
            face_embedding=face_embedding, phone=phone, parent_phone=parent_phone
        )

    @staticmethod
    def create_faculty(
        name: str,
        email: str,
        password_hash: str,
        role: str,
        department: str,
        phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a faculty document (HEAD or STAFF)."""
        return UserDocument.create_document(
            name=name, email=email, password_hash=password_hash,
            role=role, department=department, phone=phone
        )


class AttendanceLogDocument:
    """
    Schema definition for the 'attendance_logs' collection.
    Tracks: student_id, roll_number, subject, timestamp, status,
    department, course, semester, verification_method, faculty_id, location.
    """

    COLLECTION_NAME = 'attendance_logs'

    STATUS_PRESENT = 'PRESENT'
    STATUS_ABSENT = 'ABSENT'
    STATUS_LATE = 'LATE'

    @staticmethod
    def create_document(
        student_id: str,
        roll_number: str,
        subject: str,
        faculty_id: str,
        department: str,
        course: str,
        semester: str,
        status: str = 'PRESENT',
        verification_method: str = 'QR_SCAN',
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        similarity_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create an attendance log document."""
        return {
            'student_id': student_id,
            'roll_number': roll_number,
            'subject': subject,
            'faculty_id': faculty_id,
            'department': department,
            'course': course,
            'semester': semester,
            'timestamp': datetime.now(timezone.utc),
            'status': status,
            'verification_method': verification_method,
            'latitude': latitude,
            'longitude': longitude,
            'similarity_score': similarity_score,
            'metadata': {},
        }


class SessionDocument:
    """
    Schema for the 'sessions' collection.
    Manages temporary state mapping for rolling QR verification tokens.
    """

    COLLECTION_NAME = 'sessions'

    @staticmethod
    def create_document(
        user_id: str,
        token: Optional[str] = None,
        session_type: str = 'LOGIN',
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Create a session document."""
        return {
            'user_id': user_id,
            'token': token or str(uuid.uuid4()),
            'session_type': session_type,
            'metadata': metadata or {},
            'created_at': datetime.now(timezone.utc),
            'expires_at': datetime.now(timezone.utc),
            'is_active': True,
        }


class QrTokenDocument:
    """
    Schema for the 'qr_tokens' collection.
    Time-locked dynamic QR tokens for attendance sessions.
    """

    COLLECTION_NAME = 'qr_tokens'

    @staticmethod
    def create_document(
        faculty_id: str,
        subject: str,
        department: str,
        course: str,
        semester: str,
        latitude: float,
        longitude: float,
        expiry_seconds: int = 120,
    ) -> Dict[str, Any]:
        """Create a QR token document with time-locked expiry."""
        now = datetime.now(timezone.utc)
        return {
            'token': str(uuid.uuid4()),
            'faculty_id': faculty_id,
            'subject': subject,
            'department': department,
            'course': course,
            'semester': semester,
            'latitude': latitude,
            'longitude': longitude,
            'created_at': now,
            'expires_at': now.timestamp() + expiry_seconds,
            'is_active': True,
            'scan_count': 0,
        }


class SubjectDocument:
    """
    Schema for the 'subjects' collection.
    Managed by Faculty Heads; permanent - not deletable by staff/students.
    """

    COLLECTION_NAME = 'subjects'

    @staticmethod
    def create_document(
        name: str,
        code: str,
        department: str,
        course: str,
        semester: str,
        faculty_head_id: str,
        description: Optional[str] = None,
        credits: int = 4,
    ) -> Dict[str, Any]:
        """Create a subject document."""
        return {
            'name': name,
            'code': code,
            'department': department,
            'course': course,
            'semester': semester,
            'faculty_head_id': faculty_head_id,
            'description': description or '',
            'credits': credits,
            'is_active': True,
            'created_at': datetime.now(timezone.utc),
            'is_permanent': True,
        }