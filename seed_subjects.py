"""Seed all MCA subjects across 4 semesters for COMP_APP department."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ['DJANGO_SETTINGS_MODULE'] = 'smartattendance.settings'

import django
django.setup()

from pymongo import MongoClient
from datetime import datetime, timezone

client = MongoClient('mongodb://localhost:27017', serverSelectionTimeoutMS=5000)
db = client['met_smart_attendance']
subjects = db['subjects']
users = db['users']

# Find the super admin to use as faculty_head_id
admin = users.find_one({'role': 'SUPER_ADMIN'})
faculty_head_id = str(admin['_id']) if admin else '000000000000000000000000'

# Clear existing subjects for MCA in COMP_APP
subjects.delete_many({'department': 'COMP_APP', 'course': 'MCA'})

mca_subjects = [
    # MCA Semester 1
    {'name': 'Programming in Java', 'code': 'MCA-101', 'semester': 'MCA_1', 'credits': 4},
    {'name': 'Discrete Mathematics', 'code': 'MCA-102', 'semester': 'MCA_1', 'credits': 4},
    {'name': 'Data Structures & Algorithms', 'code': 'MCA-103', 'semester': 'MCA_1', 'credits': 4},
    {'name': 'Computer Organization & Architecture', 'code': 'MCA-104', 'semester': 'MCA_1', 'credits': 3},
    {'name': 'Operating Systems', 'code': 'MCA-105', 'semester': 'MCA_1', 'credits': 3},
    {'name': 'Communication Skills', 'code': 'MCA-106', 'semester': 'MCA_1', 'credits': 2},
    # MCA Semester 2
    {'name': 'Advanced Java Programming', 'code': 'MCA-201', 'semester': 'MCA_2', 'credits': 4},
    {'name': 'Database Management Systems', 'code': 'MCA-202', 'semester': 'MCA_2', 'credits': 4},
    {'name': 'Computer Networks', 'code': 'MCA-203', 'semester': 'MCA_2', 'credits': 4},
    {'name': 'Software Engineering', 'code': 'MCA-204', 'semester': 'MCA_2', 'credits': 3},
    {'name': 'Optimization Techniques', 'code': 'MCA-205', 'semester': 'MCA_2', 'credits': 3},
    {'name': 'Research Methodology', 'code': 'MCA-206', 'semester': 'MCA_2', 'credits': 2},
    # MCA Semester 3
    {'name': 'Python Programming', 'code': 'MCA-301', 'semester': 'MCA_3', 'credits': 4},
    {'name': 'Machine Learning', 'code': 'MCA-302', 'semester': 'MCA_3', 'credits': 4},
    {'name': 'Web Technologies', 'code': 'MCA-303', 'semester': 'MCA_3', 'credits': 4},
    {'name': 'Cloud Computing', 'code': 'MCA-304', 'semester': 'MCA_3', 'credits': 3},
    {'name': 'Business Statistics', 'code': 'MCA-305', 'semester': 'MCA_3', 'credits': 3},
    {'name': 'Minor Project', 'code': 'MCA-306', 'semester': 'MCA_3', 'credits': 2},
    # MCA Semester 4
    {'name': 'Deep Learning', 'code': 'MCA-401', 'semester': 'MCA_4', 'credits': 4},
    {'name': 'Big Data Analytics', 'code': 'MCA-402', 'semester': 'MCA_4', 'credits': 4},
    {'name': 'Cyber Security', 'code': 'MCA-403', 'semester': 'MCA_4', 'credits': 3},
    {'name': 'Mobile Application Development', 'code': 'MCA-404', 'semester': 'MCA_4', 'credits': 3},
    {'name': 'Major Project / Dissertation', 'code': 'MCA-405', 'semester': 'MCA_4', 'credits': 6},
]

docs = []
for subj in mca_subjects:
    docs.append({
        'name': subj['name'],
        'code': subj['code'],
        'department': 'COMP_APP',
        'course': 'MCA',
        'semester': subj['semester'],
        'faculty_head_id': faculty_head_id,
        'description': f"{subj['name']} - MCA {subj['semester'].replace('_', ' ')}",
        'credits': subj.get('credits', 4),
        'is_active': True,
        'created_at': datetime.now(timezone.utc),
        'is_permanent': True,
    })

result = subjects.insert_many(docs)
print(f"✅ Seeded {len(result.inserted_ids)} MCA subjects successfully!")
print("\nSubjects added:")
for subj in mca_subjects:
    print(f"  {subj['semester']}: {subj['name']} ({subj['code']}) - {subj['credits']} credits")