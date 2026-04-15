from rest_framework import serializers
from .models import UserActivityLog

class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivityLog
        fields = ['activity_type', 'quantity'] # Пользователь присылает только это

    def create(self, validated_data):
        # Автоматически подставляем текущего юзера при сохранении
        user = self.context['request'].user
        return UserActivityLog.objects.create(user=user, **validated_data)