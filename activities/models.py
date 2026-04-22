from django.db import models
from django.contrib.auth.models import User
from django.db.models import Max, Sum
from django.utils import timezone

class Notification(models.Model):
    TYPES = (
        ('like', 'Лайк'),
        ('comment', 'Комментарий'),
    )
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    notification_type = models.CharField(max_length=10, choices=TYPES)
    log = models.ForeignKey('UserActivityLog', on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class ActivityCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="Категория (напр. Турники)")
    icon = models.CharField(max_length=10, default="💪", verbose_name="Иконка (эмодзи)")

    def __str__(self):
        return f"{self.icon} {self.name}"
    
    def get_user_rank(self, user):
        exercises = self.exercises.all()
        if not exercises.exists():
            return "🌱 Новичок"

        percentage_scores = []
        
        for ex in exercises:
            # Общее кол-во уникальных участников в этом упражнении
            total_participants = User.objects.filter(logs__activity_type=ex).distinct().count()
            
            if total_participants == 0:
                percentage_scores.append(100) # Если никто не делал, ты на 100% (в хвосте)
                continue

            # Считаем место пользователя
            leaderboard = User.objects.filter(logs__activity_type=ex).annotate(
                score=models.Sum('logs__total_points')
            ).order_by('-score')
            
            place = 1
            user_place = total_participants + 1 # По умолчанию — за пределами списка
            
            for entry in leaderboard:
                if entry == user:
                    user_place = place
                    break
                place += 1
            
            # Считаем, в какой процент лучших входит юзер (например, 1-е место из 100 — это 1%)
            percent_pos = (user_place / total_participants) * 100
            percentage_scores.append(percent_pos)

        # Среднее арифметическое процентных позиций
        avg_percent = sum(percentage_scores) / len(percentage_scores)

        # Шкала рангов на основе процентов
        if avg_percent <= 1:   return "💎 Элита (Топ-1%)"
        if avg_percent <= 3:   return "🏆 Мастер (Топ-3%)"
        if avg_percent <= 10:  return "🥇 Профи (Топ-10%)"
        if avg_percent <= 25:  return "🥈 Атлет (Топ-25%)"
        if avg_percent <= 50:  return "🥉 Любитель (Топ-50%)"
        return "🌱 Новичок"
    
    def get_user_rank_value(self, user):
        exercises = self.exercises.all()
        if not exercises.exists():
            return 999
        
        places = []
        for ex in exercises:
            results = User.objects.filter(logs__activity_type=ex).annotate(
                best=Max('logs__quantity')
            ).order_by('-best')
            
            place = 1
            found = False
            for entry in results:
                if entry == user:
                    places.append(place)
                    found = True
                    break
                place += 1
            if not found:
                places.append(results.count() + 1)
                
        return sum(places) / len(places)

class ActivityType(models.Model):
    # Связываем упражнение с категорией
    category = models.ForeignKey(ActivityCategory, on_delete=models.CASCADE, related_name='exercises', null=True,
        blank=True, verbose_name="Категория")
    name = models.CharField(max_length=100, verbose_name="Упражнение")
    points_per_unit = models.IntegerField(default=10)
    unit_name = models.CharField(max_length=20, verbose_name="Ед. изм.")
    description = models.TextField(blank=True, verbose_name="Описание упражнения")

    def __str__(self):
        if self.category:
            return f"{self.category.name}: {self.name}"
        return f"Без категории: {self.name}"

class UserActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='logs')
    activity_type = models.ForeignKey(ActivityType, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    total_points = models.IntegerField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    video = models.FileField(
        upload_to='activity_videos/', 
        null=True, 
        blank=True, 
        verbose_name="Видео тренировки"
    )

    def save(self, *args, **kwargs):
        self.total_points = self.quantity * self.activity_type.points_per_unit
        super().save(*args, **kwargs)

# Модель профиля (оставляем без изменений)
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    age = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    streak = models.IntegerField(default=0, verbose_name="Серия дней")
    last_activity_date = models.DateField(null=True, blank=True)

    def is_online(self):
        if self.user.last_login:
            # Если заходил менее 15 минут назад
            return (timezone.now() - self.user.last_login).total_seconds() < 900
        return False

    def get_bmi(self):
        if self.height and self.weight:
            height_m = self.height / 100
            return round(float(self.weight) / (height_m ** 2), 1)
        return None
    
    def get_global_rank(self):
        # Используем твой новый метод для получения процента
        avg_global_percent = self.get_rank_position_percent()

        if avg_global_percent <= 1:   return "🌌 Легенда (Топ-1%)"
        if avg_global_percent <= 3:   return "👑 Чемпион (Топ-3%)"
        if avg_global_percent <= 10:  return "🏆 Элита (Топ-10%)"
        if avg_global_percent <= 25:  return "🏋️‍♂️ Атлет (Топ-25%)"
        if avg_global_percent <= 50:  return "🔥 Новичок (Топ-50%)"
        return "🌱 Стартующий"

    def get_category_percent(self, category):
        # Вспомогательный метод для расчёта чистого процента по категории
        exercises = category.exercises.all()
        if not exercises.exists(): return 100
        
        ex_percents = []
        total_users = User.objects.count() # Общее число атлетов в системе

        for ex in exercises:
            leaderboard = User.objects.filter(logs__activity_type=ex).annotate(
                score=models.Sum('logs__total_points')
            ).order_by('-score')
            
            user_place = total_users
            place = 1
            for entry in leaderboard:
                if entry == self.user:
                    user_place = place
                    break
                place += 1
            
            ex_percents.append((user_place / total_users) * 100)
        
        return sum(ex_percents) / len(ex_percents)
    
    def get_average_place(self):
        exercises = ActivityType.objects.all()
        if not exercises.exists():
            return 0
        
        total_places = 0
        counted_exercises = 0

        for ex in exercises:
            # Получаем рейтинг этого упражнения по рекордам
            results = User.objects.filter(logs__activity_type=ex).annotate(
                best=Max('logs__quantity')
            ).order_by('-best')
            
            place = 1
            user_found = False
            for entry in results:
                if entry == self.user:
                    total_places += place
                    user_found = True
                    break
                place += 1
            
            # Если юзер не делал упражнение, даем ему штрафное место (последний + 1)
            if not user_found:
                total_places += (results.count() + 1)
            
            counted_exercises += 1

        return round(total_places / counted_exercises, 2)
    
    def get_rank_position_percent(self):
        categories = ActivityCategory.objects.all()
        if not categories.exists():
            return 100.0

        all_category_percents = []
        for cat in categories:
            percent = self.get_category_percent(cat)
            all_category_percents.append(percent)

        # Возвращаем средний процент (твой реальный прогресс)
        return sum(all_category_percents) / len(all_category_percents)

    def get_rank_progress(self):
        top_percent = self.get_rank_position_percent()

        # Если ты хуже 50%, твоя цель — Новичок
        if top_percent > 50:
            return {'label': 'Путь к Новичку', 'start': 100, 'end': 50, 'current': top_percent, 'next': 'Новичок (50%)'}
        
        # Если ты уже Новичок (лучше 50%), твоя цель — Атлет
        elif top_percent > 25:
            return {'label': 'Путь к Атлету', 'start': 50, 'end': 25, 'current': top_percent, 'next': 'Атлет (25%)'}
        
        # Если ты уже Атлет, твоя цель — Элита
        elif top_percent > 10:
            return {'label': 'Путь к Элите', 'start': 25, 'end': 10, 'current': top_percent, 'next': 'Элита (10%)'}
        
        # Если ты уже Элита, твоя цель — Чемпион
        elif top_percent > 3:
            return {'label': 'Путь к Чемпиону', 'start': 10, 'end': 3, 'current': top_percent, 'next': 'Чемпион (3%)'}
        
        # Если ты Чемпион, финишная прямая к Легенде
        else:
            return {'label': 'Путь к Легенде', 'start': 3, 'end': 0, 'current': top_percent, 'next': 'Легенда (1%)'}
# Модель квестов (связываем с упражнением)
class DailyQuest(models.Model):
    title = models.CharField(max_length=200)
    activity_type = models.ForeignKey(ActivityType, on_delete=models.CASCADE)
    required_quantity = models.IntegerField()
    bonus_points = models.IntegerField()

class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    log = models.ForeignKey('UserActivityLog', on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'log') # Один пользователь — один лайк

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    log = models.ForeignKey('UserActivityLog', on_delete=models.CASCADE, related_name='comments')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)