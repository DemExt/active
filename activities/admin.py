from django.contrib import admin
from .models import ActivityType, UserActivityLog, DailyQuest, UserProfile, ActivityCategory# импортируем твои модели

@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'points_per_unit', 'unit_name')
    search_fields = ('name',)

@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'quantity', 'total_points', 'created_at')
    list_filter = ('activity_type', 'created_at')

    def quantity_display(self, obj):
        if obj.activity_type.name == "Бег 100м":
            return f"{obj.quantity} сек."
        return f"{obj.quantity} {obj.activity_type.unit_name}"
    
    quantity_display.short_description = "Результат"

@admin.register(DailyQuest)
class DailyQuestAdmin(admin.ModelAdmin):
    list_display = ('title', 'activity_type', 'required_quantity', 'bonus_points')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'age', 'height', 'weight')

@admin.register(ActivityCategory)
class ActivityCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon')
