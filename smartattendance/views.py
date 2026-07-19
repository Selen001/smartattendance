"""
Full-Stack Controllers & Routing REST APIs
Django REST Framework (DRF) views governing the SaaS operation.
MET Institute of Management - Smart Attendance System
"""
import json
import logging
from typing import Dict, Any
from datetime import datetime, timezone
from bson import ObjectId, json_util
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .db_config import get_collection, db_pool
from .models import (
    UserDocument, AttendanceLogDocument,
    SessionDocument, QrTokenDocument, SubjectDocument
)
from .security import (
    RegexCompiledEngine, HaversineGeofence,
    BiometricCosineSimilarity, SecurityExceptions
)
from .utils import (
    PasswordHasher, AsyncParentAlertDispatcher,
    AttendanceAnalytics
)
from .core import (
    AuthenticationService, UserManagementService,
    SubjectManagementService, QRTokenService,
    AttendanceProcessingPipeline
)

logger = logging.getLogger(__name__)


def index(request):
    """Landing page - redirect to appropriate dashboard based on role."""
    return render(request, 'index.html')


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a MongoDB document for JSON response."""
    if doc and '_id' in doc:
        if isinstance(doc['_id'], ObjectId):
            doc['_id'] = str(doc['_id'])
    return doc


def serialize_docs(docs: list) -> list:
    """Serialize a list of MongoDB documents."""
    return [serialize_doc(doc) for doc in docs]


# ============================================================
# ============================================================
# Template Views - All protected with session validation
# ============================================================

def _get_session_user(request):
    """
    Extract user from session token in request.
    Returns user dict or None if unauthorized.
    """
    try:
        token = request.headers.get('X-Session-Token') or request.GET.get('token') or ''
        if not token:
            return None
        from .core import AuthenticationService, UserManagementService
        session = AuthenticationService.validate_session(token)
        if not session:
            return None
        user = UserManagementService.get_user_by_id(session['user_id'])
        return user
    except Exception:
        return None


def super_admin_dashboard(request):
    """Super Admin dashboard view - PROTECTED."""
    user = _get_session_user(request)
    if not user or user.get('role') != 'SUPER_ADMIN':
        return render(request, 'index.html', {'error': 'Unauthorized. Please login as Super Admin.'})
    return render(request, 'super_admin_dashboard.html')


def faculty_head_dashboard(request):
    """Faculty Head (HOD) dashboard view - PROTECTED."""
    user = _get_session_user(request)
    if not user or user.get('role') not in ['FACULTY_HEAD', 'SUPER_ADMIN']:
        return render(request, 'index.html', {'error': 'Unauthorized. Please login as Faculty Head.'})
    return render(request, 'faculty_head_dashboard.html')


def faculty_staff_dashboard(request):
    """Faculty Staff dashboard view - PROTECTED."""
    user = _get_session_user(request)
    if not user or user.get('role') not in ['FACULTY_STAFF', 'FACULTY_HEAD', 'SUPER_ADMIN']:
        return render(request, 'index.html', {'error': 'Unauthorized.'})
    return render(request, 'faculty_staff_dashboard.html')


def student_dashboard(request):
    """Student dashboard view - PROTECTED."""
    user = _get_session_user(request)
    if not user or user.get('role') not in ['STUDENT', 'SUPER_ADMIN']:
        return render(request, 'index.html', {'error': 'Unauthorized.'})
    return render(request, 'student_dashboard.html')


def qr_checkin_page(request):
    """Dedicated QR check-in page - no auth required, login happens on page."""
    return render(request, 'qr_checkin.html')


# ============================================================
# Authentication APIs (Using csrf_exempt + JSONResponse for reliability)
# ============================================================

@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    """
    POST /api/login/
    Authenticate user and create session.
    """
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not email or not password:
            return JsonResponse({'error': 'Email and password are required'}, status=400)

        if not RegexCompiledEngine.validate_email(email):
            return JsonResponse({'error': 'Only @met.edu emails are allowed'}, status=400)

        # Ensure MongoDB connected
        db_pool.connect()

        users_coll = get_collection(UserDocument.COLLECTION_NAME)
        user = users_coll.find_one({'email': email})
        if not user:
            return JsonResponse({'error': 'Invalid email or password'}, status=401)

        if user.get('account_locked', False):
            return JsonResponse({'error': 'Account locked due to multiple failed attempts. Contact admin.'}, status=423)

        if not PasswordHasher.verify_password(password, user['password_hash']):
            failed = user.get('failed_attempts', 0) + 1
            update = {'failed_attempts': failed}
            if failed >= 5:
                update['account_locked'] = True
            users_coll.update_one({'_id': user['_id']}, {'$set': update})
            return JsonResponse({'error': 'Invalid email or password'}, status=401)

        users_coll.update_one(
            {'_id': user['_id']},
            {'$set': {'failed_attempts': 0, 'last_login': datetime.now(timezone.utc)}}
        )

        # Create session
        sessions_coll = get_collection(SessionDocument.COLLECTION_NAME)
        session_doc = SessionDocument.create_document(
            user_id=str(user['_id']),
            session_type='LOGIN',
        )
        result = sessions_coll.insert_one(session_doc)

        user['_id'] = str(user['_id'])
        user.pop('password_hash', None)
        user.pop('face_embedding', None)

        role_lower = user.get('role', '').lower()
        return JsonResponse({
            'success': True,
            'user': user,
            'session_token': session_doc['token'],
            'redirect_url': f"/dashboard/{role_lower}/",
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as exc:
        logger.error(f"Login error: {exc}", exc_info=True)
        return JsonResponse({'error': f'Login failed: {str(exc)}'}, status=500)


class LogoutAPI(APIView):
    """
    POST /api/logout/
    Invalidate session token.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            token = data.get('session_token', '')
            if token:
                AuthenticationService.invalidate_session(token)
            return Response({'success': True})
        except Exception as exc:
            logger.error(f"Logout error: {exc}")
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ValidateSessionAPI(APIView):
    """
    POST /api/validate-session/
    Validate a session token.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            token = data.get('session_token', '')
            session = AuthenticationService.validate_session(token)
            if not session:
                return Response(
                    {'valid': False, 'error': 'Session expired'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            user = UserManagementService.get_user_by_id(session['user_id'])
            return Response({'valid': True, 'user': user})
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================
# User Management APIs
# ============================================================

class CreateUserAPI(APIView):
    """
    POST /api/users/create/
    Create a new user (Super Admin, Faculty Head).
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            user = UserManagementService.create_user(data)
            return Response({'success': True, 'user': user}, status=status.HTTP_201_CREATED)
        except (SecurityExceptions.EmailValidationException,
                SecurityExceptions.RollNumberException) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
        except Exception as exc:
            logger.error(f"Create user error: {exc}", exc_info=True)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetUserAPI(APIView):
    """
    GET /api/users/<user_id>/
    Get a user by ID.
    """

    def get(self, request, user_id):
        try:
            user = UserManagementService.get_user_by_id(user_id)
            if not user:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            return Response({'user': user})
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteUserAPI(APIView):
    """
    DELETE /api/users/<user_id>/delete/
    Delete a user (soft delete - sets is_active=false).
    Faculty Head can delete staff/students in their department.
    """

    def delete(self, request, user_id):
        try:
            data = json.loads(request.body)
            requesting_role = data.get('role', '')
            requesting_dept = data.get('department', '')
            
            if requesting_role not in ['FACULTY_HEAD', 'SUPER_ADMIN']:
                return Response({'error': 'Only Faculty Head and Super Admin can delete users'}, status=status.HTTP_403_FORBIDDEN)

            users_coll = get_collection(UserDocument.COLLECTION_NAME)
            user = users_coll.find_one({'_id': ObjectId(user_id)})
            if not user:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

            # Faculty Head can only delete users in their own department
            if requesting_role == 'FACULTY_HEAD' and user.get('department') != requesting_dept:
                return Response({'error': 'Cannot delete users from other departments'}, status=status.HTTP_403_FORBIDDEN)

            users_coll.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {'is_active': False, 'deleted_at': datetime.now(timezone.utc)}}
            )
            return Response({'success': True, 'message': 'User deleted successfully'})
        except Exception as exc:
            logger.error(f"Delete user error: {exc}", exc_info=True)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteAttendanceLogAPI(APIView):
    """
    DELETE /api/attendance/<log_id>/delete/
    Delete a single attendance log.
    """

    def delete(self, request, log_id):
        try:
            logs_coll = get_collection(AttendanceLogDocument.COLLECTION_NAME)
            result = logs_coll.delete_one({'_id': ObjectId(log_id)})
            if result.deleted_count > 0:
                return Response({'success': True, 'message': 'Attendance record deleted'})
            return Response({'error': 'Record not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ListUsersAPI(APIView):
    """
    GET /api/users/?role=STUDENT&department=COMP_APP&course=MCA&semester=MCA_1
    List users with filters.
    """

    def get(self, request):
        try:
            role = request.GET.get('role')
            department = request.GET.get('department')
            course = request.GET.get('course')
            semester = request.GET.get('semester')

            if not role:
                return Response(
                    {'error': 'Role parameter is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            users = UserManagementService.get_users_by_role(
                role=role, department=department,
                course=course, semester=semester,
            )
            return Response({'users': users, 'count': len(users)})
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateFaceEmbeddingAPI(APIView):
    """
    POST /api/users/face-embedding/
    Update a student's face embedding (captured via webcam during registration).
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            user_id = data.get('user_id')
            embedding = data.get('face_embedding', [])

            if not user_id or not embedding:
                return Response(
                    {'error': 'user_id and face_embedding are required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            success = UserManagementService.update_user_face_embedding(user_id, embedding)
            if success:
                return Response({'success': True, 'message': 'Face embedding updated'})
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================
# Department APIs
# ============================================================

class GetDepartmentsAPI(APIView):
    """
    GET /api/departments/
    Get all departments with course/semester structure.
    """

    def get(self, request):
        try:
            dept_coll = get_collection('departments')
            departments = list(dept_coll.find({}, {'_id': 0}))
            return Response({'departments': departments})
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================
# Subject Management APIs
# ============================================================

class CreateSubjectAPI(APIView):
    """
    POST /api/subjects/create/
    Create a subject (Faculty Head only).
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            subject = SubjectManagementService.create_subject(
                name=data['name'],
                code=data['code'],
                department=data['department'],
                course=data['course'],
                semester=data['semester'],
                faculty_head_id=data['faculty_head_id'],
                description=data.get('description'),
                credits=data.get('credits', 4),
            )
            return Response({'success': True, 'subject': subject}, status=status.HTTP_201_CREATED)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetSubjectsAPI(APIView):
    """
    GET /api/subjects/?department=COMP_APP&course=MCA&semester=MCA_1
    Get subjects with optional filters.
    """

    def get(self, request):
        try:
            department = request.GET.get('department')
            course = request.GET.get('course')
            semester = request.GET.get('semester')

            subjects = SubjectManagementService.get_subjects(
                department=department, course=course, semester=semester,
            )
            return Response({'subjects': subjects, 'count': len(subjects)})
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteSubjectAPI(APIView):
    """
    DELETE /api/subjects/<subject_id>/delete/
    Delete a subject (Faculty Head / Super Admin only).
    """

    def delete(self, request, subject_id):
        try:
            data = json.loads(request.body)
            user_role = data.get('user_role', '')

            success = SubjectManagementService.delete_subject(subject_id, user_role)
            if success:
                return Response({'success': True, 'message': 'Subject deactivated'})
            return Response({'error': 'Subject not found'}, status=status.HTTP_404_NOT_FOUND)
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================
# QR Token APIs
# ============================================================

class GenerateQRTokenAPI(APIView):
    """
    POST /api/qr/generate/
    Generate a QR token for a faculty's attendance session.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            qr_data = QRTokenService.generate_qr_token(
                faculty_id=data['faculty_id'],
                subject=data['subject'],
                department=data['department'],
                course=data['course'],
                semester=data['semester'],
                latitude=float(data['latitude']),
                longitude=float(data['longitude']),
                expiry_seconds=data.get('expiry_seconds', 120),
            )
            return Response({
                'success': True,
                'qr_token': qr_data['token'],
                'expires_at': qr_data['expires_at'],
            })
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ValidateQRTokenAPI(APIView):
    """
    POST /api/qr/validate/
    Validate a QR token.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            token = data.get('token', '')
            qr_data = QRTokenService.validate_qr_token(token)
            if not qr_data:
                return Response(
                    {'valid': False, 'error': 'QR token expired or invalid'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response({'valid': True, 'qr_data': qr_data})
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================
# ProcessSmartAttendanceCheckInAPI - The Core Endpoint
# ============================================================

class ProcessSmartAttendanceCheckInAPI(APIView):
    """
    POST /api/attendance/checkin/
    The primary tracking endpoint processing inbound student scans.
    Chains: Regex Match -> Dual Token Active Handshake ->
    15m Geofence Validation -> Facial Feature Verification ->
    MongoDB Entry Generation.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)

            # Extract all required fields
            student_id = data.get('student_id', '').strip()
            qr_token = data.get('qr_token', '').strip()
            live_embedding = data.get('live_embedding', [])
            student_lat = float(data.get('latitude', 0))
            student_lon = float(data.get('longitude', 0))
            liveness_score = float(data.get('liveness_score', 0.5))
            embedding_quality = float(data.get('embedding_quality', 0.5))

            # Validate required fields
            if not student_id or not qr_token or not live_embedding:
                return Response(
                    {'error': 'student_id, qr_token, and live_embedding are required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if len(live_embedding) != 128:
                return Response(
                    {'error': 'live_embedding must be 128-dimensional'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Execute the full processing pipeline
            attendance_doc = AttendanceProcessingPipeline.process_checkin(
                student_id=student_id,
                qr_token=qr_token,
                live_embedding=live_embedding,
                student_lat=student_lat,
                student_lon=student_lon,
                liveness_score=liveness_score,
                embedding_quality=embedding_quality,
            )

            serialized = serialize_doc(attendance_doc)
            return Response({
                'success': True,
                'message': 'Attendance recorded successfully',
                'attendance': serialized,
            })

        except SecurityExceptions.SessionExpiredException as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except SecurityExceptions.RollNumberException as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except SecurityExceptions.GeofenceBreachException as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except SecurityExceptions.SpoofingDetectedException as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except SecurityExceptions.FaceMatchException as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(f"Check-in error: {exc}", exc_info=True)
            return Response(
                {'error': 'Internal server error during check-in processing'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ============================================================
# Attendance Analytics APIs
# ============================================================

class StudentAttendanceAPI(APIView):
    """
    GET /api/attendance/student/<student_id>/?subject=SUB-001
    Get attendance analytics for a specific student.
    """

    def get(self, request, student_id):
        try:
            subject = request.GET.get('subject')
            start_date_str = request.GET.get('start_date')
            end_date_str = request.GET.get('end_date')

            start_date = None
            end_date = None
            if start_date_str:
                start_date = datetime.fromisoformat(start_date_str)
            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str)

            analytics = AttendanceAnalytics.get_student_attendance(
                student_id=student_id,
                subject=subject,
                start_date=start_date,
                end_date=end_date,
            )
            return Response(analytics)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DepartmentAttendanceAPI(APIView):
    """
    GET /api/attendance/department/?department=COMP_APP&course=MCA&semester=MCA_1
    Get attendance summary for a department/semester.
    """

    def get(self, request):
        try:
            department = request.GET.get('department', '')
            course = request.GET.get('course', '')
            semester = request.GET.get('semester', '')

            if not all([department, course, semester]):
                return Response(
                    {'error': 'department, course, and semester are required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            summary = AttendanceAnalytics.get_department_attendance_summary(
                department=department, course=course, semester=semester,
            )
            return Response(summary)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SubjectAttendanceTrendAPI(APIView):
    """
    GET /api/attendance/trend/?subject=CS-101&department=COMP_APP&course=MCA&semester=MCA_1&days=30
    Get attendance trend for a subject.
    """

    def get(self, request):
        try:
            subject = request.GET.get('subject', '')
            department = request.GET.get('department', '')
            course = request.GET.get('course', '')
            semester = request.GET.get('semester', '')
            days = int(request.GET.get('days', 30))

            if not all([subject, department, course, semester]):
                return Response(
                    {'error': 'subject, department, course, and semester are required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            trend = AttendanceAnalytics.get_subject_attendance_trend(
                subject=subject, department=department,
                course=course, semester=semester, days=days,
            )
            return Response({'trend': trend})
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================
# Database Health Check
# ============================================================

class VerifyFaceAPI(APIView):
    """
    POST /api/face/verify/
    Verify a live face embedding against the student's stored face embedding in DB.
    Request: { student_id, live_embedding }
    """
    def post(self, request):
        try:
            data = json.loads(request.body)
            student_id = data.get('student_id', '').strip()
            live_embedding = data.get('live_embedding', [])

            if not student_id or not live_embedding:
                return Response({'verified': False, 'error': 'student_id and live_embedding required'}, status=status.HTTP_400_BAD_REQUEST)
            if len(live_embedding) != 128:
                return Response({'verified': False, 'error': 'Embedding must be 128-dim'}, status=status.HTTP_400_BAD_REQUEST)

            users_coll = get_collection(UserDocument.COLLECTION_NAME)
            student = users_coll.find_one({'_id': ObjectId(student_id)})
            if not student:
                return Response({'verified': False, 'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

            stored = student.get('face_embedding', [])
            if not stored or len(stored) != 128:
                return Response({'verified': False, 'error': 'No face registered for this student. Register face first via Faculty Head.'}, status=status.HTTP_400_BAD_REQUEST)

            from .security import BiometricCosineSimilarity, SecurityExceptions
            try:
                match, similarity = BiometricCosineSimilarity.verify_face(
                    live_embedding=live_embedding,
                    stored_embedding=stored,
                    threshold=getattr(settings, 'FACE_SIMILARITY_THRESHOLD', 0.85),
                )
                return Response({'verified': True, 'similarity': round(similarity, 4), 'message': 'Face matched successfully!'})
            except SecurityExceptions.FaceMatchException as exc:
                return Response({'verified': False, 'similarity': round(exc.similarity, 4), 'error': f'Face mismatch. Similarity: {exc.similarity:.2f} < {exc.threshold}'})

        except Exception as exc:
            logger.error(f"Face verify error: {exc}", exc_info=True)
            return Response({'verified': False, 'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class HealthCheckAPI(APIView):
    """
    GET /api/health/
    Check database connectivity.
    """

    def get(self, request):
        try:
            connected = db_pool.is_connected()
            if not connected:
                connected = db_pool.connect()
            return Response({
                'status': 'healthy' if connected else 'unhealthy',
                'database': 'connected' if connected else 'disconnected',
            })
        except Exception as exc:
            return Response(
                {'status': 'unhealthy', 'error': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


# ============================================================
# Hostname API (for QR code generation with network IP)
# ============================================================

import socket

class HostnameAPI(APIView):
    """
    GET /api/hostname/
    Returns the server's network IP address for QR code scanning.
    """

    def get(self, request):
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            return Response({'hostname': hostname, 'ip': ip})
        except Exception as exc:
            return Response({'ip': '127.0.0.1', 'error': str(exc)})


# ============================================================
# Pricing Tiers API
# ============================================================

class GetPricingTiersAPI(APIView):
    """
    GET /api/pricing/
    Get available pricing tier configurations.
    """

    def get(self, request):
        try:
            tiers = getattr(settings, 'PRICING_TIERS', {})
            return Response({'pricing_tiers': tiers})
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)