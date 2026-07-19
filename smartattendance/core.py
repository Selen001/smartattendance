"""
Core Business Logic Module
Implements the primary attendance processing pipeline and
authentication workflows for the Smart Attendance SaaS.
"""
import json
import logging
import uuid
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from bson import ObjectId
from django.conf import settings

from .db_config import get_collection
from .models import (
    UserDocument, AttendanceLogDocument,
    SessionDocument, QrTokenDocument, SubjectDocument
)
from .security import (
    RegexCompiledEngine, HaversineGeofence,
    BiometricCosineSimilarity, SecurityExceptions
)
from .utils import PasswordHasher, AsyncParentAlertDispatcher, AttendanceAnalytics

logger = logging.getLogger(__name__)


class AuthenticationService:
    """
    Handles user authentication, session management, and role-based access.
    """

    @staticmethod
    def authenticate_user(email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate a user by email and password.

        Args:
            email: User's email (*@met.edu)
            password: Plain text password

        Returns:
            User document dict (without password_hash)

        Raises:
            SecurityExceptions.EmailValidationException
            SecurityExceptions.AccountLockedException
            ValueError on invalid credentials
        """
        if not RegexCompiledEngine.validate_email(email):
            raise SecurityExceptions.EmailValidationException(email)

        users_coll = get_collection(UserDocument.COLLECTION_NAME)
        user = users_coll.find_one({'email': email.lower()})

        if not user:
            raise ValueError("Invalid email or password")

        if user.get('account_locked', False):
            raise SecurityExceptions.AccountLockedException(email)

        if not PasswordHasher.verify_password(password, user['password_hash']):
            failed = user.get('failed_attempts', 0) + 1
            update_data = {'failed_attempts': failed}
            if failed >= 5:
                update_data['account_locked'] = True
            users_coll.update_one(
                {'_id': user['_id']},
                {'$set': update_data}
            )
            raise ValueError("Invalid email or password")

        users_coll.update_one(
            {'_id': user['_id']},
            {'$set': {
                'failed_attempts': 0,
                'last_login': datetime.now(timezone.utc),
            }}
        )

        user['_id'] = str(user['_id'])
        user.pop('password_hash', None)
        user.pop('face_embedding', None)
        return user

    @staticmethod
    def create_session(user_id: str, session_type: str = 'LOGIN') -> Dict[str, Any]:
        """Create a new session for an authenticated user."""
        sessions_coll = get_collection(SessionDocument.COLLECTION_NAME)
        session = SessionDocument.create_document(
            user_id=user_id,
            session_type=session_type,
        )
        result = sessions_coll.insert_one(session)
        session['_id'] = str(result.inserted_id)
        return session

    @staticmethod
    def validate_session(token: str) -> Optional[Dict[str, Any]]:
        """Validate a session token and return the session data."""
        sessions_coll = get_collection(SessionDocument.COLLECTION_NAME)
        session = sessions_coll.find_one({
            'token': token,
            'is_active': True,
        })
        if not session:
            return None
        session['_id'] = str(session['_id'])
        return session

    @staticmethod
    def invalidate_session(token: str):
        """Invalidate a session by token."""
        sessions_coll = get_collection(SessionDocument.COLLECTION_NAME)
        sessions_coll.update_one(
            {'token': token},
            {'$set': {'is_active': False}}
        )


class UserManagementService:
    """
    Handles user CRUD operations with role-based access control.
    """

    @staticmethod
    def create_user(user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user in the system."""
        users_coll = get_collection(UserDocument.COLLECTION_NAME)

        if not RegexCompiledEngine.validate_email(user_data.get('email', '')):
            raise SecurityExceptions.EmailValidationException(user_data.get('email', ''))

        existing = users_coll.find_one({'email': user_data['email'].lower()})
        if existing:
            raise ValueError(f"User with email {user_data['email']} already exists")

        password_hash = PasswordHasher.hash_password(
            user_data['password'],
            rounds=getattr(settings, 'BCRYPT_ROUNDS', 12)
        )

        role = user_data.get('role', UserDocument.ROLE_STUDENT)

        if role == UserDocument.ROLE_STUDENT:
            if not RegexCompiledEngine.validate_roll_number(user_data.get('roll_number', '')):
                raise SecurityExceptions.RollNumberException(user_data.get('roll_number', ''))
            doc = UserDocument.create_student(
                name=user_data['name'],
                email=user_data['email'],
                password_hash=password_hash,
                department=user_data['department'],
                course=user_data['course'],
                semester=user_data['semester'],
                roll_number=user_data['roll_number'],
                face_embedding=user_data.get('face_embedding'),
                phone=user_data.get('phone'),
                parent_phone=user_data.get('parent_phone'),
            )
            # Mark verified if face_embedding was provided
            if user_data.get('face_embedding') and len(user_data['face_embedding']) == 128:
                doc['is_verified'] = True
        else:
            doc = UserDocument.create_faculty(
                name=user_data['name'],
                email=user_data['email'],
                password_hash=password_hash,
                role=role,
                department=user_data.get('department'),
                phone=user_data.get('phone'),
            )

        result = users_coll.insert_one(doc)
        doc['_id'] = str(result.inserted_id)
        doc.pop('password_hash', None)
        doc.pop('face_embedding', None)
        return doc

    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by their MongoDB ObjectId."""
        users_coll = get_collection(UserDocument.COLLECTION_NAME)
        try:
            user = users_coll.find_one({'_id': ObjectId(user_id)})
        except Exception:
            return None
        if user:
            user['_id'] = str(user['_id'])
            user.pop('password_hash', None)
            user.pop('face_embedding', None)
        return user

    @staticmethod
    def get_users_by_role(
        role: str,
        department: Optional[str] = None,
        course: Optional[str] = None,
        semester: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get active users filtered by role and optional department/course/semester."""
        users_coll = get_collection(UserDocument.COLLECTION_NAME)
        query = {'role': role, 'is_active': True}
        if department:
            query['department'] = department
        if course:
            query['course'] = course
        if semester:
            query['semester'] = semester

        users = list(users_coll.find(query).sort('name', 1))
        for user in users:
            user['_id'] = str(user['_id'])
            user.pop('password_hash', None)
            user.pop('face_embedding', None)
        return users

    @staticmethod
    def update_user_face_embedding(user_id: str, embedding: List[float]) -> bool:
        """Update a student's face embedding."""
        if len(embedding) != 128:
            raise ValueError("Face embedding must be 128-dimensional")
        users_coll = get_collection(UserDocument.COLLECTION_NAME)
        result = users_coll.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {
                'face_embedding': embedding,
                'embedding_dimension': 128,
                'is_verified': True,
                'updated_at': datetime.now(timezone.utc),
            }}
        )
        return result.modified_count > 0


class SubjectManagementService:
    """
    Manages subjects with strict role-based access.
    Faculty Heads can add/edit/delete subjects.
    Subjects are permanent and cannot be deleted by Faculty Staff or Students.
    """

    @staticmethod
    def create_subject(
        name: str,
        code: str,
        department: str,
        course: str,
        semester: str,
        faculty_head_id: str,
        description: Optional[str] = None,
        credits: int = 4,
    ) -> Dict[str, Any]:
        """Create a new subject (Faculty Head only)."""
        subjects_coll = get_collection(SubjectDocument.COLLECTION_NAME)

        existing = subjects_coll.find_one({'code': code, 'department': department})
        if existing:
            raise ValueError(f"Subject with code {code} already exists in {department}")

        doc = SubjectDocument.create_document(
            name=name, code=code, department=department,
            course=course, semester=semester,
            faculty_head_id=faculty_head_id,
            description=description, credits=credits,
        )
        result = subjects_coll.insert_one(doc)
        doc['_id'] = str(result.inserted_id)
        return doc

    @staticmethod
    def get_subjects(
        department: Optional[str] = None,
        course: Optional[str] = None,
        semester: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get subjects with optional filters."""
        subjects_coll = get_collection(SubjectDocument.COLLECTION_NAME)
        query = {'is_active': True}
        if department:
            query['department'] = department
        if course:
            query['course'] = course
        if semester:
            query['semester'] = semester

        subjects = list(subjects_coll.find(query).sort('name', 1))
        for subj in subjects:
            subj['_id'] = str(subj['_id'])
        return subjects

    @staticmethod
    def delete_subject(subject_id: str, requesting_user_role: str) -> bool:
        """
        Delete a subject. Only Faculty Heads and Super Admins can delete.
        """
        if requesting_user_role not in [UserDocument.ROLE_FACULTY_HEAD, UserDocument.ROLE_SUPER_ADMIN]:
            raise PermissionError("Only Faculty Heads and Super Admins can delete subjects")

        subjects_coll = get_collection(SubjectDocument.COLLECTION_NAME)
        result = subjects_coll.update_one(
            {'_id': ObjectId(subject_id)},
            {'$set': {'is_active': False}}
        )
        return result.modified_count > 0


class QRTokenService:
    """
    Manages time-locked dynamic QR tokens for attendance sessions.
    """

    @staticmethod
    def generate_qr_token(
        faculty_id: str,
        subject: str,
        department: str,
        course: str,
        semester: str,
        latitude: float,
        longitude: float,
        expiry_seconds: int = 120,
    ) -> Dict[str, Any]:
        """Generate a new time-locked QR token."""
        qr_coll = get_collection(QrTokenDocument.COLLECTION_NAME)
        doc = QrTokenDocument.create_document(
            faculty_id=faculty_id, subject=subject,
            department=department, course=course,
            semester=semester, latitude=latitude,
            longitude=longitude, expiry_seconds=expiry_seconds,
        )
        result = qr_coll.insert_one(doc)
        doc['_id'] = str(result.inserted_id)
        return doc

    @staticmethod
    def validate_qr_token(token: str) -> Optional[Dict[str, Any]]:
        """Validate a QR token and return its data if valid."""
        qr_coll = get_collection(QrTokenDocument.COLLECTION_NAME)
        now = datetime.now(timezone.utc).timestamp()

        qr_data = qr_coll.find_one({
            'token': token,
            'is_active': True,
            'expires_at': {'$gt': now},
        })

        if not qr_data:
            return None

        qr_data['_id'] = str(qr_data['_id'])
        return qr_data

    @staticmethod
    def invalidate_qr_token(token: str):
        """Invalidate a QR token after use."""
        qr_coll = get_collection(QrTokenDocument.COLLECTION_NAME)
        qr_coll.update_one(
            {'token': token},
            {'$set': {'is_active': False}}
        )


class AttendanceProcessingPipeline:
    """
    Primary attendance processing pipeline.
    Chains: Regex Match -> Dual Token Active Handshake ->
    15m Geofence Validation -> Facial Feature Verification ->
    MongoDB Entry Generation.
    """

    @staticmethod
    def process_checkin(
        student_id: str,
        qr_token: str,
        live_embedding: List[float],
        student_lat: float,
        student_lon: float,
        liveness_score: float = 0.5,
        embedding_quality: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Process a complete smart attendance check-in.

        Args:
            student_id: MongoDB ObjectId of the student
            qr_token: QR token string from the faculty's session
            live_embedding: 128-dim face embedding captured live
            student_lat: Student's GPS latitude
            student_lon: Student's GPS longitude
            liveness_score: Anti-spoofing liveness score (0-1)
            embedding_quality: Quality score of captured embedding (0-1)

        Returns:
            Attendance log document

        Raises:
            Various SecurityExceptions on validation failures
        """
        # Step 1: Validate QR Token (Dual Token Active Handshake)
        qr_data = QRTokenService.validate_qr_token(qr_token)
        if not qr_data:
            raise SecurityExceptions.SessionExpiredException(qr_token)

        # Step 2: Get student data
        users_coll = get_collection(UserDocument.COLLECTION_NAME)
        student = users_coll.find_one({'_id': ObjectId(student_id)})
        if not student:
            raise ValueError(f"Student not found: {student_id}")

        # Step 3: Regex Match - Validate roll number
        roll_number = student.get('roll_number', '')
        if not RegexCompiledEngine.validate_roll_number(roll_number):
            raise SecurityExceptions.RollNumberException(roll_number)

        # Step 4: 15m Geofence Validation
        HaversineGeofence.validate_proximity(
            student_lat=student_lat,
            student_lon=student_lon,
            faculty_lat=qr_data['latitude'],
            faculty_lon=qr_data['longitude'],
            max_distance_meters=getattr(settings, 'GEOFENCE_RADIUS_METERS', 15),
        )

        # Step 5: Anti-spoofing check
        stored_embedding = student.get('face_embedding', [])
        if not stored_embedding or len(stored_embedding) != 128:
            raise ValueError("Student has no registered face embedding")

        embedding_variance = BiometricCosineSimilarity.cosine_similarity(
            live_embedding, [0.0] * 128
        )
        BiometricCosineSimilarity.detect_spoofing(
            embedding_variance=abs(embedding_variance),
            liveness_score=liveness_score,
            embedding_quality=embedding_quality,
        )

        # Step 6: Facial Feature Verification
        match_result, similarity = BiometricCosineSimilarity.verify_face(
            live_embedding=live_embedding,
            stored_embedding=stored_embedding,
            threshold=getattr(settings, 'FACE_SIMILARITY_THRESHOLD', 0.85),
        )

        # Step 7: Invalidate QR token (single use)
        QRTokenService.invalidate_qr_token(qr_token)

        # Step 8: Create attendance log
        logs_coll = get_collection(AttendanceLogDocument.COLLECTION_NAME)
        attendance_doc = AttendanceLogDocument.create_document(
            student_id=student_id,
            roll_number=roll_number,
            subject=qr_data['subject'],
            faculty_id=qr_data['faculty_id'],
            department=qr_data['department'],
            course=qr_data['course'],
            semester=qr_data['semester'],
            status=AttendanceLogDocument.STATUS_PRESENT,
            verification_method='FACE_QR',
            latitude=student_lat,
            longitude=student_lon,
            similarity_score=similarity,
        )
        result = logs_coll.insert_one(attendance_doc)
        attendance_doc['_id'] = str(result.inserted_id)

        # Step 9: Async parent alert (background thread)
        parent_phone = student.get('parent_phone')
        if parent_phone:
            AsyncParentAlertDispatcher.dispatch_attendance_alert(
                parent_phone=parent_phone,
                parent_email=None,
                student_name=student.get('name', ''),
                subject=qr_data['subject'],
                status=AttendanceLogDocument.STATUS_PRESENT,
                timestamp=attendance_doc['timestamp'],
            )

        return attendance_doc