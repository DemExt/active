from django.contrib import admin
from .models import ActivityType, UserActivityLog, DailyQuest, UserProfile, ActivityCategory# импортируем твои модели

@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'points_per_unit', 'unit_name')

@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'quantity', 'total_points', 'created_at')

@admin.register(DailyQuest)
class DailyQuestAdmin(admin.ModelAdmin):
    list_display = ('title', 'activity_type', 'required_quantity', 'bonus_points')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'age', 'height', 'weight')

@admin.register(ActivityCategory)
class ActivityCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon')
