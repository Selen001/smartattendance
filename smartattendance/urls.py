"""
URL Configuration for Smart Attendance SaaS
MET Institute of Management - Route mappings for all REST APIs and dashboards.
"""
from django.urls import path, re_path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # Template Views
    path('', views.index, name='index'),
    path('dashboard/super_admin/', views.super_admin_dashboard, name='super_admin_dashboard'),
    path('dashboard/faculty_head/', views.faculty_head_dashboard, name='faculty_head_dashboard'),
    path('dashboard/faculty_staff/', views.faculty_staff_dashboard, name='faculty_staff_dashboard'),
    path('dashboard/student/', views.student_dashboard, name='student_dashboard'),
    path('checkin/', views.qr_checkin_page, name='qr_checkin'),

    # Authentication APIs
    path('api/login/', views.login_view, name='api_login'),
    path('api/logout/', views.LogoutAPI.as_view(), name='api_logout'),
    path('api/validate-session/', views.ValidateSessionAPI.as_view(), name='api_validate_session'),

    # User Management APIs
    path('api/users/create/', views.CreateUserAPI.as_view(), name='api_create_user'),
    path('api/users/<str:user_id>/', views.GetUserAPI.as_view(), name='api_get_user'),
    path('api/users/<str:user_id>/delete/', views.DeleteUserAPI.as_view(), name='api_delete_user'),
    path('api/users/', views.ListUsersAPI.as_view(), name='api_list_users'),
    path('api/attendance/<str:log_id>/delete/', views.DeleteAttendanceLogAPI.as_view(), name='api_delete_attendance'),
    path('api/users/face-embedding/', views.UpdateFaceEmbeddingAPI.as_view(), name='api_update_face_embedding'),

    # Department APIs
    path('api/departments/', views.GetDepartmentsAPI.as_view(), name='api_get_departments'),

    # Subject Management APIs
    path('api/subjects/create/', views.CreateSubjectAPI.as_view(), name='api_create_subject'),
    path('api/subjects/', views.GetSubjectsAPI.as_view(), name='api_get_subjects'),
    path('api/subjects/<str:subject_id>/delete/', views.DeleteSubjectAPI.as_view(), name='api_delete_subject'),

    # QR Token APIs
    path('api/qr/generate/', views.GenerateQRTokenAPI.as_view(), name='api_generate_qr'),
    path('api/qr/validate/', views.ValidateQRTokenAPI.as_view(), name='api_validate_qr'),

    # Attendance APIs
    path('api/attendance/checkin/', views.ProcessSmartAttendanceCheckInAPI.as_view(), name='api_attendance_checkin'),
    path('api/attendance/student/<str:student_id>/', views.StudentAttendanceAPI.as_view(), name='api_student_attendance'),
    path('api/attendance/department/', views.DepartmentAttendanceAPI.as_view(), name='api_department_attendance'),
    path('api/attendance/trend/', views.SubjectAttendanceTrendAPI.as_view(), name='api_attendance_trend'),

    # Face Verification API
    path('api/face/verify/', views.VerifyFaceAPI.as_view(), name='api_face_verify'),

    # Utility APIs
    path('api/health/', views.HealthCheckAPI.as_view(), name='api_health'),
    path('api/hostname/', views.HostnameAPI.as_view(), name='api_hostname'),
    path('api/pricing/', views.GetPricingTiersAPI.as_view(), name='api_pricing'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])