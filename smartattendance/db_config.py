"""
Unified Multi-Tenant DB Schema & Configurations
Connection pool management for MongoDB with BSON object mapping.
MET Institute of Management - Smart Attendance SaaS
"""
import os
import logging
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo.collection import Collection
from pymongo.database import Database
from threading import Lock
from django.conf import settings

logger = logging.getLogger(__name__)


class MongoDBConnectionPool:
    """
    Thread-safe MongoDB connection pool manager with automatic
    connection retry and collection initialization.
    """
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self._client = None
        self._db = None
        self._collections = {}
        self._connected = False
        self._connection_lock = Lock()

    def connect(self) -> bool:
        """Establish connection to MongoDB with retry logic."""
        if self._connected and self._client:
            return True
        with self._connection_lock:
            if self._connected:
                return True
            try:
                mongo_uri = getattr(settings, 'MONGO_URI', 'mongodb://localhost:27017')
                mongo_db_name = getattr(settings, 'MONGO_DB_NAME', 'met_smart_attendance')
                self._client = MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=3000,
                    connectTimeoutMS=3000,
                    socketTimeoutMS=3000,
                    maxPoolSize=50,
                    minPoolSize=5,
                    maxIdleTimeMS=30000,
                    retryWrites=True,
                    w='majority',
                )
                # Test connection with ping (ismaster is deprecated)
                self._client.admin.command('ping')
                self._db = self._client[mongo_db_name]
                self._initialize_collections()
                self._seed_departments()
                self._create_indexes()
                self._connected = True
                logger.info(f"Connected to MongoDB: {mongo_db_name}")
                return True
            except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
                logger.error(f"MongoDB connection failed: {exc}")
                self._connected = False
                return False
            except Exception as exc:
                logger.error(f"MongoDB connection error: {exc}")
                self._connected = False
                return False

    def get_db(self) -> Database:
        """Get the database handle."""
        if not self._connected:
            self.connect()
        return self._db

    def get_collection(self, name: str) -> Collection:
        """Get a collection by name with lazy initialization."""
        if not self._connected:
            self.connect()
        if name not in self._collections:
            self._collections[name] = self._db[name]
        return self._collections[name]

    def _initialize_collections(self):
        """Initialize all required collections if they don't exist."""
        required_collections = [
            'departments', 'users', 'attendance_logs',
            'sessions', 'subjects', 'qr_tokens'
        ]
        existing = self._db.list_collection_names()
        for coll in required_collections:
            if coll not in existing:
                self._db.create_collection(coll)
                logger.info(f"Created collection: {coll}")

    def _create_indexes(self):
        """Create all required indexes for performance optimization."""
        db = self._db
        db['users'].create_index([('email', ASCENDING)], unique=True, sparse=True)
        # Roll number index: unique only for documents that HAVE a roll_number (students)
        # This allows faculty/admin to have null roll_number without conflicts
        try:
            db['users'].drop_index('roll_number_1')
        except:
            pass
        db['users'].create_index(
            [('roll_number', ASCENDING)],
            unique=True,
            partialFilterExpression={'roll_number': {'$type': 'string'}}
        )
        db['users'].create_index([('department', ASCENDING), ('course', ASCENDING), ('semester', ASCENDING)])
        db['attendance_logs'].create_index([('student_id', ASCENDING), ('timestamp', DESCENDING)])
        db['attendance_logs'].create_index([('timestamp', DESCENDING)])
        db['attendance_logs'].create_index([('subject', ASCENDING), ('timestamp', DESCENDING)])
        db['attendance_logs'].create_index([('student_id', ASCENDING), ('subject', ASCENDING), ('timestamp', DESCENDING)])
        db['sessions'].create_index([('token', ASCENDING)], unique=True)
        db['sessions'].create_index([('created_at', ASCENDING)], expireAfterSeconds=900)
        db['qr_tokens'].create_index([('token', ASCENDING)], unique=True)
        db['qr_tokens'].create_index([('expires_at', ASCENDING)], expireAfterSeconds=0)
        db['departments'].create_index([('code', ASCENDING)], unique=True)

    def _seed_departments(self):
        """
        Seed the exact institutional layout for MET Institute of Management.
        Department of Computer Application & Department of Business Administration.
        """
        db = self._db
        departments_coll = db['departments']
        if departments_coll.count_documents({}) > 0:
            return

        departments_data = [
            {
                'code': 'COMP_APP',
                'name': 'Department of Computer Application',
                'courses': {
                    'BCA': {
                        'duration_years': 3,
                        'semesters': ['BCA_1', 'BCA_2', 'BCA_3', 'BCA_4', 'BCA_5', 'BCA_6'],
                        'description': 'Bachelor of Computer Application'
                    },
                    'MCA': {
                        'duration_years': 2,
                        'semesters': ['MCA_1', 'MCA_2', 'MCA_3', 'MCA_4'],
                        'description': 'Master of Computer Application'
                    }
                },
                'created_at': datetime.now(timezone.utc),
                'is_active': True
            },
            {
                'code': 'BUS_ADMIN',
                'name': 'Department of Business Administration',
                'courses': {
                    'BBA': {
                        'duration_years': 3,
                        'semesters': ['BBA_1', 'BBA_2', 'BBA_3', 'BBA_4', 'BBA_5', 'BBA_6'],
                        'description': 'Bachelor of Business Administration'
                    },
                    'MBA': {
                        'duration_years': 2,
                        'semesters': ['MBA_1', 'MBA_2', 'MBA_3', 'MBA_4'],
                        'description': 'Master of Business Administration'
                    }
                },
                'created_at': datetime.now(timezone.utc),
                'is_active': True
            }
        ]
        departments_coll.insert_many(departments_data)
        logger.info("Seeded departments collection with MET Institute layout")

    def is_connected(self) -> bool:
        """Check if the connection is alive."""
        try:
            if self._client:
                self._client.admin.command('ping')
                return True
        except Exception:
            self._connected = False
        return False

    def close(self):
        """Close all connections in the pool."""
        if self._client:
            self._client.close()
            self._connected = False
            self._client = None
            self._db = None
            self._collections = {}
            logger.info("MongoDB connection pool closed")


# Singleton instance
db_pool = MongoDBConnectionPool()


def get_db() -> Database:
    """Convenience function to get database handle."""
    return db_pool.get_db()


def get_collection(name: str) -> Collection:
    """Convenience function to get a collection."""
    return db_pool.get_collection(name)