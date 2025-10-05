from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import RedirectView

urlpatterns = [
    # إعدادات المصادقة
    path('login/', LoginView.as_view(template_name='registration/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    
    # لوحة الإدارة
    path('admin/', admin.site.urls),
    
    # تطبيقات المشروع الأول
    path('', include('pages.urls')),
    path('students/', include('students.urls')),
    path('employ/', include('employ.urls')),
    # path('/', include('.urls')),    
    path('attendance/', include('attendance.urls')),
    path('grade/', include('grade.urls')),
    path('courses/', include('courses.urls')),
    path('classroom/', include('classroom.urls')),
    path('registration/', include('registration.urls')),
    
    # تطبيقات المشروع الثاني
    path('accounts/', include('accounts.urls')),
    
    # إعادة توجيه الصفحة الرئيسية
    path('', RedirectView.as_view(url='/', permanent=False)),
]