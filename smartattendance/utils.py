"""
Core Utility Module
Implements asynchronous parent alerts, list comprehension analytics,
password hashing, and helper functions for the Smart Attendance SaaS.
"""
import bcrypt
import logging
import threading
import requests
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
from django.conf import settings
from .db_config import get_collection
from .models import UserDocument, AttendanceLogDocument

logger = logging.getLogger(__name__)


class PasswordHasher:
    """Password hashing and verification using bcrypt."""

    @staticmethod
    def hash_password(password: str, rounds: int = 12) -> str:
        """
        Hash a password using bcrypt with configurable rounds.

        Args:
            password: Plain text password
            rounds: Bcrypt rounds (default: 12)

        Returns:
            Hashed password string
        """
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt(rounds=rounds)
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            password: Plain text password to verify
            hashed: Stored bcrypt hash

        Returns:
            True if password matches
        """
        password_bytes = password.encode('utf-8')
        hashed_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)


class AsyncParentAlertDispatcher:
    """
    Asynchronous Parent Alerts using Python's threading module.
    Dispatches background attendee mismatch alerts to parents
    without causing response delays for the HTTP user thread.
    """

    @staticmethod
    def _send_sms_alert(parent_phone: str, student_name: str, message: str):
        """
        Background thread target for sending SMS alerts.
        Uses threading to avoid blocking the main request thread.
        """
        try:
            logger.info(
                f"PARENT ALERT [SMS] -> {parent_phone}: "
                f"{student_name} - {message}"
            )
            # Integration point for SMS gateway API (e.g., Twilio, MSG91)
            # Example: requests.post(SMS_GATEWAY_URL, json=payload)
            pass
        except Exception as exc:
            logger.error(f"Failed to send SMS alert to {parent_phone}: {exc}")

    @staticmethod
    def _send_email_alert(parent_email: str, student_name: str, message: str):
        """
        Background thread target for sending email alerts.
        """
        try:
            logger.info(
                f"PARENT ALERT [EMAIL] -> {parent_email}: "
                f"{student_name} - {message}"
            )
            # Integration point for email service (e.g., SendGrid, SMTP)
            pass
        except Exception as exc:
            logger.error(f"Failed to send email alert to {parent_email}: {exc}")

    @classmethod
    def dispatch_attendance_alert(
        cls,
        parent_phone: Optional[str],
        parent_email: Optional[str],
        student_name: str,
        subject: str,
        status: str,
        timestamp: datetime,
    ):
        """
        Dispatch attendance alert to parent in a background thread.

        This method returns immediately; the actual alert dispatch
        happens in a separate daemon thread.
        """
        message = (
            f"Attendance Update for {student_name}: "
            f"Status '{status}' for subject '{subject}' "
            f"at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        if parent_phone:
            thread = threading.Thread(
                target=cls._send_sms_alert,
                args=(parent_phone, student_name, message),
                daemon=True,
            )
            thread.start()

        if parent_email:
            thread = threading.Thread(
                target=cls._send_email_alert,
                args=(parent_email, student_name, message),
                daemon=True,
            )
            thread.start()

    @classmethod
    def dispatch_mismatch_alert(
        cls,
        parent_phone: Optional[str],
        parent_email: Optional[str],
        student_name: str,
        expected_roll: str,
        actual_details: str,
    ):
        """
        Dispatch a mismatch alert when attendance verification fails.
        """
        message = (
            f"ALERT: Attendance verification mismatch for {student_name} "
            f"(Roll: {expected_roll}). Details: {actual_details}. "
            f"Please contact the institute immediately."
        )

        if parent_phone:
            thread = threading.Thread(
                target=cls._send_sms_alert,
                args=(parent_phone, student_name, message),
                daemon=True,
            )
            thread.start()

        if parent_email:
            thread = threading.Thread(
                target=cls._send_email_alert,
                args=(parent_email, student_name, message),
                daemon=True,
            )
            thread.start()


class AttendanceAnalytics:
    """
    Student attendance analytics and trends calculated dynamically
    across semesters via list comprehension filters.
    """

    @staticmethod
    def get_student_attendance(
        student_id: str,
        subject: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Calculate attendance analytics for a student using list comprehensions.

        Args:
            student_id: MongoDB ObjectId of the student
            subject: Optional subject filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with attendance metrics
        """
        logs_coll = get_collection(AttendanceLogDocument.COLLECTION_NAME)

        query = {'student_id': student_id}
        if subject:
            query['subject'] = subject
        if start_date or end_date:
            query['timestamp'] = {}
            if start_date:
                query['timestamp']['$gte'] = start_date
            if end_date:
                query['timestamp']['$lte'] = end_date

        all_logs = list(logs_coll.find(query).sort('timestamp', -1))

        # List comprehension: filter present records
        present_logs = [
            log for log in all_logs
            if log.get('status') == AttendanceLogDocument.STATUS_PRESENT
        ]

        # List comprehension: filter absent records
        absent_logs = [
            log for log in all_logs
            if log.get('status') == AttendanceLogDocument.STATUS_ABSENT
        ]

        # List comprehension: extract unique subjects
        unique_subjects = list(set(
            log.get('subject', '') for log in all_logs
        ))

        total = len(all_logs)
        present = len(present_logs)
        absent = len(absent_logs)

        attendance_percentage = (present / total * 100) if total > 0 else 0.0

        # List comprehension: per-subject breakdown
        subject_breakdown = [
            {
                'subject': subj,
                'total': len([l for l in all_logs if l.get('subject') == subj]),
                'present': len([l for l in present_logs if l.get('subject') == subj]),
                'absent': len([l for l in absent_logs if l.get('subject') == subj]),
            }
            for subj in unique_subjects
        ]

        return {
            'student_id': student_id,
            'total_classes': total,
            'present_count': present,
            'absent_count': absent,
            'attendance_percentage': round(attendance_percentage, 2),
            'subject_breakdown': subject_breakdown,
            'recent_logs': all_logs[:10] if all_logs else [],
        }

    @staticmethod
    def get_department_attendance_summary(
        department: str,
        course: str,
        semester: str,
    ) -> Dict[str, Any]:
        """
        Get attendance summary for an entire department/semester.

        Uses list comprehensions to aggregate across all students.
        """
        users_coll = get_collection(UserDocument.COLLECTION_NAME)
        logs_coll = get_collection(AttendanceLogDocument.COLLECTION_NAME)

        students = list(users_coll.find({
            'role': UserDocument.ROLE_STUDENT,
            'department': department,
            'course': course,
            'semester': semester,
            'is_active': True,
        }))

        student_ids = [str(s['_id']) for s in students]

        all_logs = list(logs_coll.find({
            'student_id': {'$in': student_ids},
        }))

        # List comprehension: aggregate per student
        student_summaries = [
            {
                'student_id': sid,
                'name': next(
                    (s.get('name', '') for s in students if str(s.get('_id')) == sid),
                    'Unknown'
                ),
                'roll_number': next(
                    (s.get('roll_number', '') for s in students if str(s.get('_id')) == sid),
                    ''
                ),
                'total': len([l for l in all_logs if l.get('student_id') == sid]),
                'present': len([
                    l for l in all_logs
                    if l.get('student_id') == sid
                    and l.get('status') == AttendanceLogDocument.STATUS_PRESENT
                ]),
            }
            for sid in student_ids
        ]

        return {
            'department': department,
            'course': course,
            'semester': semester,
            'total_students': len(students),
            'student_summaries': student_summaries,
        }

    @staticmethod
    def get_subject_attendance_trend(
        subject: str,
        department: str,
        course: str,
        semester: str,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get attendance trend for a subject over a period.

        Uses list comprehension to filter and aggregate daily attendance.
        """
        logs_coll = get_collection(AttendanceLogDocument.COLLECTION_NAME)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        logs = list(logs_coll.find({
            'subject': subject,
            'department': department,
            'course': course,
            'semester': semester,
            'timestamp': {'$gte': cutoff},
        }).sort('timestamp', 1))

        # List comprehension: group by date
        date_groups = list(set(
            log['timestamp'].strftime('%Y-%m-%d') for log in logs
        ))

        trend_data = [
            {
                'date': date_str,
                'total': len([l for l in logs if l['timestamp'].strftime('%Y-%m-%d') == date_str]),
                'present': len([
                    l for l in logs
                    if l['timestamp'].strftime('%Y-%m-%d') == date_str
                    and l.get('status') == AttendanceLogDocument.STATUS_PRESENT
                ]),
            }
            for date_str in sorted(date_groups)
        ]

        return trend_data