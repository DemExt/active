
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
from django.db.models import OuterRef, Subquery, Count
from django.contrib import messages

from .models import ActivityType, UserActivityLog, DailyQuest, UserProfile, ActivityCategory, Like, Comment, Notification, RecordVote
from .serializers import ActivityLogSerializer

# --- ГЛАВНЫЕ СТРАНИЦЫ ---

@login_required(login_url='login')
def index_view(request):
    # 1. Список категорий (плитки)
    categories = ActivityCategory.objects.all()
    
    # 2. Глобальный лидерборд (по среднему месту среди всех упражнений)
    # Теперь в расчет рейтинга должны идти только проверенные логи
    all_users = User.objects.select_related('profile').filter(
        logs__is_verified=True # ВАЖНО: только те, у кого есть подтвержденные рекорды
    ).distinct()
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

    # 4. ЛЕНТА: разделяем на "Очередь" и "Проверенные"
    base_logs = UserActivityLog.objects.filter(
        video__isnull=False
    ).exclude(video='').select_related('user', 'user__profile', 'activity_type')

    # Неподтвержденные — ТЕПЕРЬ ОНИ БУДУТ ВВЕРХУ (pending_logs)
    pending_logs = base_logs.filter(is_verified=False).order_by('-created_at')[:10]
    
    # Подтвержденные (recent_logs)
    verified_logs = base_logs.filter(is_verified=True).order_by('-created_at')[:10]


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

    query = request.GET.get('search')
    if query:
        # Ищем пользователей, чей ник содержит введенный текст
        global_leaderboard = User.objects.filter(username__icontains=query).select_related('profile')[:10]
    else:
        # Твой обычный запрос для ТОП-10 (замени на свою логику рейтинга, если нужно)
        global_leaderboard = User.objects.all().select_related('profile')[:10]
        
    return render(request, 'activities/index.html', {
        'categories': categories,
        'global_leaderboard': global_leaderboard,
        'search_query': query,
        'today_points': today_points,
        'daily_goal': daily_goal,
        'progress_percent': progress_percent,
        'pending_logs': pending_logs,    # Новая переменная для верха ленты
        'verified_logs': verified_logs,   # Основная лента
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
    # Проверяем, смотрим ли мы страницу через чей-то профиль
    view_username = request.GET.get('view_user')
    # Сложный запрос: выбираем лучшие логи для каждого уникального пользователя
    # Мы берем последние записи, сгруппированные по юзеру, где количество максимально

    # 1. Подзапрос: ищем ID лучшего лога для каждого пользователя
    best_log_subquery = UserActivityLog.objects.filter(
        user=OuterRef('pk'),
        activity_type=exercise,
        is_verified=True
    ).order_by('-quantity', '-created_at').values('id')[:1]

    # 2. Основной запрос: используем 'logs' (как указано в ошибке Choices are: ..., logs, ...)
    leaderboard = UserActivityLog.objects.filter(
        id__in=Subquery(
            User.objects.filter(logs__activity_type=exercise, logs__is_verified=True) # Только юзеры с подтвержденными логами
            .distinct()
            .annotate(top_log_id=Subquery(best_log_subquery))
            .values('top_log_id')
        ),
        is_verified=True # И сам лог должен быть подтвержденным
    ).select_related('user', 'user__profile').order_by('-quantity')[:10]

    # ЛОГИ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ (для возможности удаления)
    # Определяем, чьи записи показывать в блоке "Последние записи"
    if view_username:
        display_user = get_object_or_404(User, username=view_username)
    else:
        display_user = request.user

    user_logs = UserActivityLog.objects.filter(
        user=display_user, 
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
        'exercise': exercise, 'leaderboard': leaderboard, 'user_logs': user_logs, 'quest': quest_status, 'view_mode': view_username, 'display_user': display_user  
    })

# --- ПРОФИЛЬ И ВХОД ---

@login_required
def profile_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Считаем топ-5 упражнений этого пользователя
    # Используем related_name='logs' из вашей модели UserActivityLog
    favorite_activities = request.user.logs.values('activity_type__name', 'activity_type__id').annotate(
        total_count=Count('id')
    ).order_by('-total_count')[:5]

    if request.method == "POST":
        age = request.POST.get('age')
        height = request.POST.get('height')
        weight = request.POST.get('weight')
        
        profile.age = int(age) if age and age.strip() else None
        profile.height = int(height) if height and height.strip() else None
        profile.weight = float(weight) if weight and weight.strip() else None
        
        if request.FILES.get('avatar'):
            profile.avatar = request.FILES.get('avatar')
            
        profile.save()
        return redirect('profile')

    return render(request, 'activities/profile.html', {
        'profile': profile,
        'favorite_activities': favorite_activities
    })

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
    # Ищем лог, который принадлежит именно этому пользователю
    log = get_object_or_404(UserActivityLog, pk=pk, user=request.user)
    
    if request.method == 'POST':
        activity_id = log.activity_type.id # Запоминаем ID упражнения для возврата
        log.delete()
        messages.success(request, "Запись успешно удалена")
        return redirect('exercise_detail', pk=activity_id)
        
    return redirect('home')

@login_required
def toggle_like(request, log_id):
    log = get_object_or_404(UserActivityLog, id=log_id)
    like, created = Like.objects.get_or_create(user=request.user, log=log)

    if created: 
        if log.user != request.user:
            Notification.objects.create(
                recipient=log.user,
                sender=request.user,
                notification_type='like',
                log=log
            )
        liked = True
    else:
        like.delete()
        liked = False
    
    return JsonResponse({'liked': liked, 'count': log.likes.count()})

@login_required
def add_comment(request, log_id):
    if request.method == "POST":
        log = get_object_or_404(UserActivityLog, id=log_id)
        text = request.POST.get('text')
        if text:
            comment = Comment.objects.create(user=request.user, log=log, text=text)
            
            if log.user != request.user:
                Notification.objects.create(
                    recipient=log.user,
                    sender=request.user,
                    notification_type='comment',
                    log=log
                )
                
            return JsonResponse({
                'status': 'ok',
                'username': comment.user.username,
                'text': comment.text
            })
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def mark_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok'})

@login_required
def get_notifications(request):
    notifications = request.user.notifications.all().order_by('-created_at')[:10]
    unread_count = request.user.notifications.filter(is_read=False).count()
    
    data = []
    for n in notifications:
        data.append({
            'id': n.id,
            'sender': n.sender.username,
            'type': n.notification_type,
            'log_name': n.log.activity_type.name,
            'is_read': n.is_read,
            'time': "только что" # В идеале передать naturaltime, но для теста так
        })
    
    return JsonResponse({'notifications': data, 'unread_count': unread_count})

@login_required
def public_profile_view(request, username):
    # Ищем пользователя по username
    user = get_object_or_404(User, username=username)
    profile = user.profile
    
    # Топ-5 упражнений этого атлета
    favorite_activities = user.logs.values(
        'activity_type__name', 
        'activity_type__id'
    ).annotate(
        total_count=Count('id')
    ).order_by('-total_count')[:5]

    return render(request, 'activities/public_profile.html', {
        'target_user': user,
        'profile': profile,
        'favorite_activities': favorite_activities
    })

def user_search_suggestions(request):
    query = request.GET.get('q', '')
    if len(query) < 1:
        return JsonResponse([], safe=False)
    
    # Ищем первых 5 подходящих пользователей
    users = User.objects.filter(username__icontains=query).values_list('username', flat=True)[:5]
    return JsonResponse(list(users), safe=False)

#Логика голосования
@login_required
def vote_record(request, log_id, choice):
    log = get_object_or_404(UserActivityLog, id=log_id)
    
    # Не даем голосовать за свой рекорд
    if log.user == request.user:
        return JsonResponse({'error': 'Нельзя голосовать за себя'}, status=400)

    vote, created = RecordVote.objects.get_or_create(user=request.user, log=log)
    vote.choice = choice
    vote.save()

    # Пересчитываем голоса
    yes_count = log.verification_votes.filter(choice='yes').count()
    no_count = log.verification_votes.filter(choice='no').count()
    total = yes_count + no_count

    # Логика подтверждения (Твои условия: 2 "Да" ИЛИ 80%)
    if yes_count >= 2: # Временное условие для теста
        if total > 0 and (yes_count / total) >= 0.8:
            log.is_verified = True
            log.save()

    return JsonResponse({
        'status': 'ok',
        'is_verified': log.is_verified,
        'yes': yes_count,
        'no': no_count
    })