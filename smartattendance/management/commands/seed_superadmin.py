"""
Management command to seed the initial SUPER_ADMIN user for MET Institute.
Run: python manage.py seed_superadmin
Creates a super admin with protected credentials.
"""
from django.core.management.base import BaseCommand
from smartattendance.db_config import get_collection, db_pool
from smartattendance.models import UserDocument
from smartattendance.utils import PasswordHasher
from smartattendance.security import RegexCompiledEngine


class Command(BaseCommand):
    help = 'Seeds the SUPER_ADMIN user for MET Smart Attendance System'

    SUPER_ADMIN_EMAIL = 'admin@met.edu'
    SUPER_ADMIN_PASSWORD = 'Admin@MET2026'
    SUPER_ADMIN_NAME = 'System Administrator'

    def handle(self, *args, **options):
        self.stdout.write("Connecting to MongoDB...")
        connected = db_pool.connect()
        if not connected:
            self.stdout.write(self.style.ERROR("Failed to connect to MongoDB. Make sure MongoDB is running."))
            return

        users_coll = get_collection(UserDocument.COLLECTION_NAME)

        existing = users_coll.find_one({'email': self.SUPER_ADMIN_EMAIL})
        if existing:
            self.stdout.write(self.style.WARNING(f"Super Admin already exists: {self.SUPER_ADMIN_EMAIL}"))
            self.stdout.write(self.style.SUCCESS(f"Login with: {self.SUPER_ADMIN_EMAIL} / {self.SUPER_ADMIN_PASSWORD}"))
            return

        password_hash = PasswordHasher.hash_password(self.SUPER_ADMIN_PASSWORD, rounds=12)

        doc = UserDocument.create_faculty(
            name=self.SUPER_ADMIN_NAME,
            email=self.SUPER_ADMIN_EMAIL,
            password_hash=password_hash,
            role=UserDocument.ROLE_SUPER_ADMIN,
            department=None,
        )
        doc['is_verified'] = True
        doc['failed_attempts'] = 0
        doc['account_locked'] = False

        result = users_coll.insert_one(doc)
        self.stdout.write(self.style.SUCCESS(f"Super Admin created successfully!"))
        self.stdout.write(self.style.SUCCESS(f"  Email:    {self.SUPER_ADMIN_EMAIL}"))
        self.stdout.write(self.style.SUCCESS(f"  Password: {self.SUPER_ADMIN_PASSWORD}"))
        self.stdout.write(self.style.WARNING("Keep these credentials safe. Change password after first login."))