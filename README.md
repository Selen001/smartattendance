# MET Smart Attendance SaaS System

A state-of-the-art, secure, and multi-tenant Smart Attendance Management System designed for educational institutions (specifically tailored for **MET Institute of Management**). This platform leverages QR codes, geolocation geofencing, and advanced face recognition to completely eliminate proxy attendance.

---

## 🚀 Key Features

*   **Multi-Role Dashboards**:
    *   **Super Admin**: Manage system tiers, view global usage stats, manage departments/users, and oversee billing and configuration.
    *   **Faculty Head**: Access department-wide attendance logs, monitor subject trends, and manage subjects/staff.
    *   **Faculty Staff**: Generate dynamic, time-limited QR codes for classes, start attendance sessions, and view class trends.
    *   **Student**: Scan class QR codes, submit face verification photos, and view real-time personal attendance logs.
*   **Geofenced QR Code Check-in**:
    *   Generates secure, dynamic QR codes that expire after a configurable duration (default: 120 seconds).
    *   Enforces geographical limits (default: 15-meter geofence radius) to verify the student is physically present in the classroom.
*   **Face Recognition & Anti-Spoofing**:
    *   Uses **DeepFace** and **OpenCV** to match the check-in photo against stored student embeddings.
    *   Automatic mismatch alerting if face verification fails.
*   **Asynchronous Parent Alerts**:
    *   Asynchronously dispatches SMS and email notifications to parents when attendance is registered or when a suspicious mismatch occurs.
*   **Dynamic Analytics**:
    *   Interactive dashboards displaying subject trends, department metrics, and average attendance rates.

---

## 🛠️ Technology Stack

*   **Backend**: Python, Django, Django REST Framework (DRF)
*   **Database**: MongoDB (via `pymongo` with thread-safe connection pooling)
*   **Authentication & Security**: BCrypt (Password hashing), PyOTP (One-Time Password validation), Django Rate-limiting
*   **Computer Vision**: OpenCV, Pillow (PIL), DeepFace, TensorFlow
*   **Cache & Session Stores**: Redis (for secure QR token verification)
*   **Frontend**: HTML5, CSS3 (Vanilla Premium Dashboards), JavaScript (Fetch API integrations)
*   **Static Handling & Server**: WhiteNoise, Gunicorn

---

## 📂 Project Directory Structure

```text
smartattendance/
├── manage.py                  # Django CLI entrypoint
├── requirements.txt           # Python dependencies
├── seed_admin.py              # Script to seed the initial Super Admin user
├── seed_subjects.py           # Script to seed default subjects and departments
├── static/                    # Frontend assets (CSS, JS, Images)
├── templates/                 # Frontend dashboard views (HTML)
└── smartattendance/           # Core Django application folder
    ├── settings.py            # Global settings (configured for MongoDB and security constants)
    ├── urls.py                # REST API endpoints & page routes
    ├── views.py               # Authentication, User Management, QR, and Check-in API views
    ├── utils.py               # Face embedding, Password hashing, and Async alerting utils
    ├── models.py              # BSON data structures for MongoDB mapping
    └── db_config.py           # Thread-safe MongoDB Connection Pool manager
```

---

## ⚙️ Setup and Installation

### 1. Prerequisites
Ensure you have the following installed on your machine:
*   [Python 3.10+](https://www.python.org/downloads/)
*   [MongoDB](https://www.mongodb.com/try/download/community) (running locally or in the cloud)
*   [Redis](https://redis.io/docs/install/) (running on standard port `6379`)
*   [Git](https://git-scm.com/)

### 2. Clone the Repository
```bash
git clone <your-github-repo-url>
cd smartattendance
```

### 3. Create a Virtual Environment & Install Dependencies
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 4. Run Databases
*   Make sure **MongoDB** is running on `mongodb://localhost:27017` (or change `MONGO_URI` in `smartattendance/settings.py` / `.env` environment variables).
*   Make sure **Redis** is running on standard port `6379`.

### 5. Seed Initial Data
Run the seeding scripts to load the system administrator account, default departments, and subjects:
```bash
# Seed the Super Admin
python seed_admin.py

# Seed default subjects and departments
python seed_subjects.py
```

### 6. Run the Development Server
```bash
python manage.py runserver
```
Visit the application in your browser at `http://127.0.0.1:8000/`.

---

## 🔑 Seeded Credentials for Testing

Use these accounts to explore the various dashboards after running the seed scripts:

*   **Super Admin**:
    *   **Email**: `admin@met.edu`
    *   **Password**: `Admin@MET2026`

---

## 🔒 Security Best Practices

1.  **Secret Keys**: In production, do not commit raw keys. Populate `DJANGO_SECRET_KEY` and `MONGO_URI` via environment variables.
2.  **HTTPS**: Ensure HTTPS is enabled when deploying to secure geolocation and webcam feed inputs in browser windows.
