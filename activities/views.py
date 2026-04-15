
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Max
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import ActivityType, UserActivityLog, DailyQuest, UserProfile, ActivityCategory
from .serializers import ActivityLogSerializer

# --- ГЛАВНЫЕ СТРАНИЦЫ ---

@login_required(login_url='login')
def index_view(request):
    # 1. Список категорий (плитки)
    categories = ActivityCategory.objects.all()
    
    # 2. Глобальный лидерборд (по среднему месту среди всех упражнений)
    # Сначала берем всех активных пользователей
    all_users = User.objects.select_related('profile').filter(logs__isnull=False).distinct()
    
    # Сортируем пользователей по результату метода get_average_place (из модели профиля)
    # Помним: чем меньше среднее место, тем выше пользователь в топе
    sorted_users = sorted(
        all_users, 
        key=lambda u: u.profile.get_average_place() if hasattr(u, 'profile') else 999
    )
    global_leaderboard = sorted_users[:10]
    
    # 3. Дневная активность (Цель: 100 очков)
    today = timezone.now().date()
    daily_goal = 100
    today_points = UserActivityLog.objects.filter(
        user=request.user,
        created_at__date=today
    ).aggregate(Sum('total_points'))['total_points__sum'] or 0
    
    progress_percent = min(int((today_points / daily_goal) * 100), 100)

    # 4. Лента последних 20 записей
    recent_logs = UserActivityLog.objects.select_related(
        'user', 'user__profile', 'activity_type'
    ).order_by('-created_at')[:20]

    # 5. Логика страйка (Огоньки)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    yesterday = today - timezone.timedelta(days=1)

    if today_points >= daily_goal:
        if profile.last_activity_date == yesterday:
            profile.streak += 1
            profile.last_activity_date = today
            profile.save()
        elif profile.last_activity_date != today:
            profile.streak = 1
            profile.last_activity_date = today
            profile.save()
    else:
        if profile.last_activity_date and profile.last_activity_date < yesterday:
            profile.streak = 0
            profile.save()
    
    return render(request, 'activities/index.html', {
        'categories': categories,
        'global_leaderboard': global_leaderboard,
        'recent_logs': recent_logs,
        'today_points': today_points,
        'daily_goal': daily_goal,
        'progress_percent': progress_percent,
        'streak': profile.streak,
    })

@login_required(login_url='login')
def category_detail_view(request, pk):
    category = get_object_or_404(ActivityCategory, pk=pk)
    exercises = category.exercises.all()
    
    # 1. Получаем всех пользователей, у которых есть хоть один лог в этой категории
    category_users = User.objects.filter(
        logs__activity_type__category=category
    ).distinct().select_related('profile')
    
    # 2. Сортируем их по среднему месту ВНУТРИ этой категории
    # Используем метод get_user_rank_value, который считает ср. место по упражнениям категории
    sorted_users = sorted(
        category_users, 
        key=lambda u: category.get_user_rank_value(u)
    )
    
    leaderboard_data = []
    for u in sorted_users[:10]:
        leaderboard_data.append({
            'user': u,
            'avg_place': category.get_user_rank_value(u)
        })
    user_rank = category.get_user_rank(request.user) # Текстовый ранг (Элита, Мастер...)

    return render(request, 'activities/category_detail.html', {
        'category': category,
        'exercises': exercises,
        'leaderboard': leaderboard_data,
        'user_rank': user_rank
    })

@login_required(login_url='login')
def exercise_detail_view(request, pk):
    exercise = get_object_or_404(ActivityType, pk=pk)
     # Считаем рекорд (Max) для каждого пользователя и называем его best_result
    leaderboard = User.objects.filter(logs__activity_type=exercise).annotate(
        best_result=Max('logs__quantity') 
    ).order_by('-best_result')[:10]

    # ЛОГИ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ (для возможности удаления)
    user_logs = UserActivityLog.objects.filter(
        user=request.user, 
        activity_type=exercise
    ).order_by('-created_at')[:5]
    
    # Прогресс квеста
    today = timezone.now().date()
    quest_obj = DailyQuest.objects.filter(activity_type=exercise).first()
    quest_status = None
    if quest_obj:
        done = UserActivityLog.objects.filter(
            user=request.user, activity_type=exercise, created_at__date=today
        ).aggregate(Sum('quantity'))['quantity__sum'] or 0
        quest_status = {'title': quest_obj.title, 'required': quest_obj.required_quantity, 'done': done}

    return render(request, 'activities/exercise_detail.html', {
        'exercise': exercise, 'leaderboard': leaderboard, 'user_logs': user_logs, 'quest': quest_status
    })

# --- ПРОФИЛЬ И ВХОД ---

@login_required
def profile_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == "POST":
        # Получаем данные
        age = request.POST.get('age')
        height = request.POST.get('height')
        weight = request.POST.get('weight')
        
        # Проверяем каждое поле: если пустая строка, то сохраняем None
        profile.age = int(age) if age and age.strip() else None
        profile.height = int(height) if height and height.strip() else None
        profile.weight = float(weight) if weight and weight.strip() else None
        
        # Обработка аватарки
        if request.FILES.get('avatar'):
            profile.avatar = request.FILES.get('avatar')
            
        profile.save()
        return redirect('profile')

    return render(request, 'activities/profile.html', {'profile': profile})

def register_view(request):
    if request.method == "POST":
        u, p = request.POST.get('username'), request.POST.get('password')
        if User.objects.filter(username=u).exists():
            return render(request, 'activities/register.html', {'error': 'Логин занят'})
        user = User.objects.create_user(username=u, password=p)
        login(request, user)
        return redirect('home')
    return render(request, 'activities/register.html')

def login_view(request):
    if request.method == "POST":
        u, p = request.POST.get('username'), request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user:
            login(request, user)
            return redirect('home')
        return render(request, 'activities/login.html', {'error': 'Ошибка входа'})
    return render(request, 'activities/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

# --- ЛОГИКА ДАННЫХ ---

def web_log_create(request):
    if request.method == "POST" and request.user.is_authenticated:
        act_id, qty = request.POST.get('activity_type'), request.POST.get('quantity')
        video = request.FILES.get('video') # Получаем файл видео
        try:
            activity = ActivityType.objects.get(id=act_id)
            UserActivityLog.objects.create(user=request.user, activity_type=activity, quantity=int(qty), video=video)
            return redirect('exercise_detail', pk=act_id)
        except: pass
    return redirect('home')

def leaderboard_view(request):
    users = User.objects.annotate(total_score=Sum('logs__total_points')).order_by('-total_score')
    data = [{"username": u.username, "score": u.total_score or 0} for u in users]
    return JsonResponse(data, safe=False)

def user_stats_view(request, username):
    user = get_object_or_404(User, username=username)
    stats = UserActivityLog.objects.filter(user=user).values('activity_type__name').annotate(
        total_qty=Sum('quantity'), total_pts=Sum('total_points')
    )
    return JsonResponse({"username": user.username, "activities": list(stats)})

class ActivityLogCreateView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = ActivityLogSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
@login_required
def delete_log_view(request, pk):
    # Ищем лог, который принадлежит именно текущему пользователю
    log = get_object_or_404(UserActivityLog, pk=pk, user=request.user)
    
    if request.method == "POST":
        exercise_id = log.activity_type.id
        log.delete()
        # Возвращаем пользователя на страницу упражнения
        return redirect('exercise_detail', pk=exercise_id)
    
    return redirect('home')