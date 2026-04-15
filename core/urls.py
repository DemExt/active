from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from activities.views import (
    index_view, category_detail_view, exercise_detail_view,
    profile_view, register_view, login_view, logout_view, delete_log_view,
    web_log_create, leaderboard_view, user_stats_view, ActivityLogCreateView
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index_view, name='home'),
    path('category/<int:pk>/', category_detail_view, name='category_detail'),
    path('exercise/<int:pk>/', exercise_detail_view, name='exercise_detail'),
    path('profile/', profile_view, name='profile'),
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('logs/create/web/', web_log_create, name='web_log_create'),
    path('leaderboard/', leaderboard_view),
    path('stats/<str:username>/', user_stats_view),
    path('logs/create/', ActivityLogCreateView.as_view()),
    path('log/delete/<int:pk>/', delete_log_view, name='delete_log'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)