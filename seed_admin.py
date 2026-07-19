"""Standalone script to seed the SUPER_ADMIN user. Run: python seed_admin.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ['DJANGO_SETTINGS_MODULE'] = 'smartattendance.settings'

import django
django.setup()

from pymongo import MongoClient
from smartattendance.utils import PasswordHasher
from smartattendance.models import UserDocument

client = MongoClient('mongodb://localhost:27017', serverSelectionTimeoutMS=5000)
db = client['met_smart_attendance']
users = db['users']

existing = users.find_one({'email': 'admin@met.edu'})
if existing:
    print("Super Admin already exists!")
    print(f"  Email:    admin@met.edu")
    print(f"  Password: Admin@MET2026")
else:
    pwd_hash = PasswordHasher.hash_password('Admin@MET2026', rounds=12)
    doc = UserDocument.create_faculty('System Administrator', 'admin@met.edu', pwd_hash, 'SUPER_ADMIN', None)
    doc['is_verified'] = True
    result = users.insert_one(doc)
    print("Super Admin created successfully!")
    print(f"  Email:    admin@met.edu")
    print(f"  Password: Admin@MET2026")
    print("  KEEP THESE CREDENTIALS SAFE!")