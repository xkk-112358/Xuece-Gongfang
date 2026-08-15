import re
import random
import os
import threading
import PyPDF2
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from django.db import transaction
from django.db.models import Q
from .models import Profile, Follow, Notification, Upload, QuestionBank, UploadLike, Post, PostLike, Comment, CommentInteraction, UserModelConfig, QuestionList, QuestionListItem, TestResult, TestResultItem, ApiInstance, ApiInstanceFile
from .utils import decrypt_id, encrypt_id, add_user_id_to_url
from docx import Document


PASSWORD_REGEX = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,16}$'

def home(request):
    tab = request.GET.get('tab', 'all')
    user_liked_upload_ids = set()
    user_liked_post_ids = set()
    user_favorited_post_ids = set()
    user_favorited_upload_ids = set()
    user_school = ''
    
    if request.user.is_authenticated:
        user_liked_upload_ids = set(UploadLike.objects.filter(user=request.user).values_list('upload_id', flat=True))
        user_liked_post_ids = set(PostLike.objects.filter(user=request.user).values_list('post_id', flat=True))
        user_favorited_post_ids = set(Post.objects.filter(favorited_by=request.user).values_list('id', flat=True))
        user_favorited_upload_ids = set(Upload.objects.filter(favorited_by=request.user).values_list('id', flat=True))
        profile = getattr(request.user, 'profile', None)
        if profile:
            user_school = profile.school

    uploads_data = []
    posts_data = []
    folders_data = []
    api_data = []
    
    if tab == 'all':
        # 获取共享的文件夹（顶层文件夹，所有文件都共享）
        all_shared_uploads = Upload.objects.filter(is_shared=True).select_related('user__profile')
        folder_paths = all_shared_uploads.values_list('folder_path', flat=True).distinct()
        
        for folder_path in folder_paths:
            if folder_path and '/' not in folder_path:  # 只处理顶层文件夹
                folder_uploads = all_shared_uploads.filter(folder_path=folder_path)
                # 也统计子文件夹中的文件
                subfolder_uploads = all_shared_uploads.filter(folder_path__startswith=folder_path + '/')
                total_file_count = folder_uploads.count() + subfolder_uploads.count()
                if folder_uploads.exists():
                    first_upload = folder_uploads.first()
                    # 检查文件夹下所有文件是否都被当前用户收藏
                    is_fav = False
                    all_folder_files_list = []
                    if request.user.is_authenticated:
                        all_folder_files = Upload.objects.filter(
                            user=first_upload.user,
                            is_shared=True
                        ).filter(
                            Q(folder_path=folder_path) | Q(folder_path__startswith=folder_path + '/')
                        )
                        all_folder_files_list = list(all_folder_files)
                        # 只要有一个文件被收藏就算已收藏
                        any_fav = any(f.id in user_favorited_upload_ids for f in all_folder_files)
                        is_fav = any_fav
                    # 计算收藏数：收藏了文件夹下所有文件的用户数
                    fav_count = 0
                    if all_folder_files_list:
                        user_id_sets = [set(f.favorited_by.values_list('id', flat=True)) for f in all_folder_files_list]
                        if user_id_sets:
                            common_user_ids = set.intersection(*user_id_sets)
                            fav_count = len(common_user_ids)
                    folders_data.append({
                        'folder_path': folder_path,
                        'folder_name': folder_path.split('/')[-1] if '/' in folder_path else folder_path,
                        'user': first_upload.user,
                        'profile': getattr(first_upload.user, 'profile', None),
                        'description': first_upload.description,
                        'file_count': total_file_count,
                        'uploaded_at': first_upload.uploaded_at,
                        'is_favorited': is_fav,
                        'favorite_count': fav_count,
                        'first_upload_id': first_upload.id,
                        'like_count': first_upload.likes.count(),
                        'comment_count': first_upload.comments.count(),
                        'is_liked': first_upload.id in user_liked_upload_ids,
                    })
        
        # 获取不在文件夹中的共享文件
        uploads = Upload.objects.filter(is_shared=True, folder_path='').order_by('-uploaded_at').select_related('user__profile').prefetch_related('likes', 'comments')
        for u in uploads:
            uploads_data.append({
                'id': u.id,
                'user': u.user,
                'profile': getattr(u.user, 'profile', None),
                'file_name': u.file_name,
                'description': u.description,
                'uploaded_at': u.uploaded_at,
                'like_count': u.likes.count(),
                'comment_count': u.comments.count(),
                'is_liked': u.id in user_liked_upload_ids,
                'is_favorited': u.id in user_favorited_upload_ids,
                'favorite_count': u.favorited_by.count(),
                'download_count': u.download_count,
            })
        posts = Post.objects.all().order_by('-created_at').select_related('user__profile').prefetch_related('likes')
        for p in posts:
            posts_data.append({
                'id': p.id,
                'user': p.user,
                'profile': getattr(p.user, 'profile', None),
                'content': p.content,
                'image': p.image.url if p.image else None,
                'link_url': p.link_url,
                'created_at': p.created_at,
                'like_count': p.likes.count(),
                'comment_count': p.comments.count(),
                'is_liked': p.id in user_liked_post_ids,
                'is_favorited': p.id in user_favorited_post_ids,
                'favorite_count': p.favorited_by.count(),
            })
    
    elif tab == 'hot':
        # 获取共享的文件夹（顶层文件夹）
        all_shared_uploads = Upload.objects.filter(is_shared=True).select_related('user__profile')
        folder_paths = all_shared_uploads.values_list('folder_path', flat=True).distinct()
        
        for folder_path in folder_paths:
            if folder_path and '/' not in folder_path:  # 只处理顶层文件夹
                folder_uploads = all_shared_uploads.filter(folder_path=folder_path)
                subfolder_uploads = all_shared_uploads.filter(folder_path__startswith=folder_path + '/')
                total_file_count = folder_uploads.count() + subfolder_uploads.count()
                if folder_uploads.exists():
                    first_upload = folder_uploads.first()
                    # 检查文件夹下所有文件是否都被当前用户收藏
                    is_fav = False
                    all_folder_files_list = []
                    if request.user.is_authenticated:
                        all_folder_files = Upload.objects.filter(
                            user=first_upload.user,
                            is_shared=True
                        ).filter(
                            Q(folder_path=folder_path) | Q(folder_path__startswith=folder_path + '/')
                        )
                        all_folder_files_list = list(all_folder_files)
                        # 只要有一个文件被收藏就算已收藏
                        any_fav = any(f.id in user_favorited_upload_ids for f in all_folder_files)
                        is_fav = any_fav
                    # 计算收藏数：收藏了文件夹下所有文件的用户数
                    fav_count = 0
                    if all_folder_files_list:
                        user_id_sets = [set(f.favorited_by.values_list('id', flat=True)) for f in all_folder_files_list]
                        if user_id_sets:
                            common_user_ids = set.intersection(*user_id_sets)
                            fav_count = len(common_user_ids)
                    folders_data.append({
                        'folder_path': folder_path,
                        'folder_name': folder_path.split('/')[-1] if '/' in folder_path else folder_path,
                        'user': first_upload.user,
                        'profile': getattr(first_upload.user, 'profile', None),
                        'description': first_upload.description,
                        'file_count': total_file_count,
                        'uploaded_at': first_upload.uploaded_at,
                        'is_favorited': is_fav,
                        'favorite_count': fav_count,
                        'first_upload_id': first_upload.id,
                        'like_count': first_upload.likes.count(),
                        'comment_count': first_upload.comments.count(),
                        'is_liked': first_upload.id in user_liked_upload_ids,
                    })
        
        # 获取不在文件夹中的共享文件
        uploads = Upload.objects.filter(is_shared=True, folder_path='').select_related('user__profile').prefetch_related('likes', 'comments')
        # 排序优先级：收藏数目 > 喜欢数目 > 评论数目
        uploads = sorted(uploads, key=lambda u: (u.favorited_by.count(), u.likes.count(), u.comments.count()), reverse=True)
        for u in uploads:
            uploads_data.append({
                'id': u.id,
                'user': u.user,
                'profile': getattr(u.user, 'profile', None),
                'file_name': u.file_name,
                'description': u.description,
                'uploaded_at': u.uploaded_at,
                'like_count': u.likes.count(),
                'comment_count': u.comments.count(),
                'is_liked': u.id in user_liked_upload_ids,
                'is_favorited': u.id in user_favorited_upload_ids,
                'favorite_count': u.favorited_by.count(),
                'download_count': u.download_count,
            })
    
    elif tab == 'school' and user_school:
        # 获取共享的文件夹（顶层文件夹）
        all_shared_uploads = Upload.objects.filter(is_shared=True, user__profile__school=user_school).select_related('user__profile')
        folder_paths = all_shared_uploads.values_list('folder_path', flat=True).distinct()
        
        for folder_path in folder_paths:
            if folder_path and '/' not in folder_path:  # 只处理顶层文件夹
                folder_uploads = all_shared_uploads.filter(folder_path=folder_path)
                subfolder_uploads = all_shared_uploads.filter(folder_path__startswith=folder_path + '/')
                total_file_count = folder_uploads.count() + subfolder_uploads.count()
                if folder_uploads.exists():
                    first_upload = folder_uploads.first()
                    # 检查文件夹下所有文件是否都被当前用户收藏
                    is_fav = False
                    all_folder_files_list = []
                    if request.user.is_authenticated:
                        all_folder_files = Upload.objects.filter(
                            user=first_upload.user,
                            is_shared=True,
                            user__profile__school=user_school
                        ).filter(
                            Q(folder_path=folder_path) | Q(folder_path__startswith=folder_path + '/')
                        )
                        all_folder_files_list = list(all_folder_files)
                        # 只要有一个文件被收藏就算已收藏
                        any_fav = any(f.id in user_favorited_upload_ids for f in all_folder_files)
                        is_fav = any_fav
                    # 计算收藏数：收藏了文件夹下所有文件的用户数
                    fav_count = 0
                    if all_folder_files_list:
                        user_id_sets = [set(f.favorited_by.values_list('id', flat=True)) for f in all_folder_files_list]
                        if user_id_sets:
                            common_user_ids = set.intersection(*user_id_sets)
                            fav_count = len(common_user_ids)
                    folders_data.append({
                        'folder_path': folder_path,
                        'folder_name': folder_path.split('/')[-1] if '/' in folder_path else folder_path,
                        'user': first_upload.user,
                        'profile': getattr(first_upload.user, 'profile', None),
                        'description': first_upload.description,
                        'file_count': total_file_count,
                        'uploaded_at': first_upload.uploaded_at,
                        'is_favorited': is_fav,
                        'favorite_count': fav_count,
                        'first_upload_id': first_upload.id,
                        'like_count': first_upload.likes.count(),
                        'comment_count': first_upload.comments.count(),
                        'is_liked': first_upload.id in user_liked_upload_ids,
                    })
        
        # 获取不在文件夹中的共享文件
        uploads = Upload.objects.filter(is_shared=True, folder_path='', user__profile__school=user_school).order_by('-uploaded_at').select_related('user__profile').prefetch_related('likes', 'comments')
        for u in uploads:
            uploads_data.append({
                'id': u.id,
                'user': u.user,
                'profile': getattr(u.user, 'profile', None),
                'file_name': u.file_name,
                'description': u.description,
                'uploaded_at': u.uploaded_at,
                'like_count': u.likes.count(),
                'comment_count': u.comments.count(),
                'is_liked': u.id in user_liked_upload_ids,
                'is_favorited': u.id in user_favorited_upload_ids,
                'favorite_count': u.favorited_by.count(),
                'download_count': u.download_count,
            })
    
    elif tab == 'post':
        posts = Post.objects.all().order_by('-created_at').select_related('user__profile').prefetch_related('likes')
        for p in posts:
            posts_data.append({
                'id': p.id,
                'user': p.user,
                'profile': getattr(p.user, 'profile', None),
                'content': p.content,
                'image': p.image.url if p.image else None,
                'link_url': p.link_url,
                'created_at': p.created_at,
                'like_count': p.likes.count(),
                'comment_count': p.comments.count(),
                'is_liked': p.id in user_liked_post_ids,
                'is_favorited': p.id in user_favorited_post_ids,
                'favorite_count': p.favorited_by.count(),
            })
    
    elif tab == 'api':
        api_instances = ApiInstance.objects.filter(is_active=True).order_by('-created_at').select_related('user__profile')
        api_data = []
        for inst in api_instances:
            api_data.append({
                'instance': inst,
                'user': inst.user,
                'profile': getattr(inst.user, 'profile', None),
            })

    # 计算全站统计
    shared_uploads = Upload.objects.filter(is_shared=True)
    total_downloads = shared_uploads.aggregate(total=Sum('download_count'))['total'] or 0
    total_files = shared_uploads.count()
    total_file_size = 0
    for u in shared_uploads.only('id', 'file'):
        try:
            if u.file and u.file.name:
                total_file_size += u.file.size
        except:
            pass
    if total_file_size >= 1073741824:
        formatted_size = f'{total_file_size/1073741824:.2f} GB'
    elif total_file_size >= 1048576:
        formatted_size = f'{total_file_size/1048576:.2f} MB'
    elif total_file_size >= 1024:
        formatted_size = f'{total_file_size/1024:.2f} KB'
    else:
        formatted_size = f'{total_file_size} B'

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = ''
        if tab in ('all', 'hot', 'school'):
            # 先渲染文件夹卡片
            for item in folders_data:
                html += render_folder_card(request, item)
            # 再渲染文件卡片
            for item in uploads_data:
                html += render_upload_card(request, item)
        elif tab == 'post':
            for item in posts_data:
                html += render_post_card(request, item)
        elif tab == 'api':
            for item in api_data:
                html += render_api_card(request, item)
        return JsonResponse({'success': True, 'html': html, 'tab': tab})
    
    return render(request, 'home.html', {
        'uploads_data': uploads_data,
        'posts_data': posts_data,
        'api_data': api_data,
        'user_liked_upload_ids': user_liked_upload_ids,
        'user_liked_post_ids': user_liked_post_ids,
        'active_tab': tab,
        'user_school': user_school,
        'total_downloads': total_downloads,
        'total_files': total_files,
        'total_file_size': formatted_size,
    })

def render_upload_card(request, item):
    from django.template.loader import render_to_string
    return render_to_string('home_upload_card.html', {'item': item, 'user': request.user})

def render_folder_card(request, item):
    from django.template.loader import render_to_string
    return render_to_string('home_folder_card.html', {'item': item, 'user': request.user})

def render_post_card(request, item):
    from django.template.loader import render_to_string
    return render_to_string('home_post_card.html', {'item': item, 'user': request.user})

def render_api_card(request, item):
    from django.template.loader import render_to_string
    return render_to_string('home_api_card.html', {'item': item, 'user': request.user})

@login_required
def parse_direct_text(request):
    """直接输入文本解析题目"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    text = data.get('text', '').strip()
    subject = data.get('subject', '').strip()
    description = data.get('description', '').strip()
    file_name = data.get('file_name', '').strip() or '直接输入'
    
    if not text:
        return JsonResponse({'success': False, 'message': '请输入题目内容'})
    
    try:
        import os, uuid
        from app1.models import Upload
        # 创建 Upload 记录
        upload = Upload()
        upload.user = request.user
        upload.file_name = file_name
        upload.description = description
        upload.subject = subject or '未分类'
        upload.processing_status = 'pending'
        upload.folder_path = ''
        
        # 将文本保存为临时 .md 文件
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', 'direct_input')
        os.makedirs(temp_dir, exist_ok=True)
        temp_name = f'direct_input_{uuid.uuid4().hex[:12]}.md'
        temp_path = os.path.join(temp_dir, temp_name)
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        # 保存文件到 upload
        from django.core.files import File
        with open(temp_path, 'rb') as f:
            upload.file.save(f'direct_input/{temp_name}', File(f))
        upload.save()
        
        # 后台处理
        import threading
        thread = threading.Thread(target=process_upload_in_background, args=(upload.id, request.user.id), daemon=True)
        thread.start()
        
        return JsonResponse({'success': True, 'message': '开始解析', 'upload_id': upload.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
def create_post(request):
    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        link_url = request.POST.get('link_url', '').strip()
        image = request.FILES.get('image')
        if not content and not image and not link_url:
            return JsonResponse({'success': False, 'message': '请填写内容'})
        try:
            post = Post.objects.create(
                user=request.user,
                content=content,
                image=image,
                link_url=link_url,
            )
            return JsonResponse({'success': True, 'post_id': post.id, 'message': '发布成功'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})


@login_required
def get_upload_question_ids(request):
    """AJAX 获取上传文件的题目ID列表"""
    upload_id = request.GET.get('upload_id', '')
    if not upload_id:
        return JsonResponse({'success': False, 'message': '参数错误'})
    try:
        upload = Upload.objects.get(id=upload_id)
        # 检查权限：本人或共享
        if upload.user != request.user and not upload.is_shared:
            return JsonResponse({'success': False, 'message': '无权访问'})
    except Upload.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文件不存在'})
    questions = QuestionBank.objects.filter(upload=upload).values('id', 'content')
    qlist = [{'id': q['id'], 'content_preview': q['content'][:50]} for q in questions]
    return JsonResponse({'success': True, 'questions': qlist, 'total': len(qlist)})


def serve_katex_file(request, filename):
    """提供静态文件，绕过 Nginx staticfiles 权限限制"""
    from django.http import HttpResponse, Http404
    import os
    
    # 只允许白名单中的文件（使用 CDN 的 KaTeX 文件已不再本地分发）
    allowed = {
        'js/pages-account-settings-account.js': 'application/javascript',
    }
    
    if filename not in allowed:
        raise Http404('File not allowed')
    
    file_path = os.path.join(settings.BASE_DIR, 'static', filename)
    
    if not os.path.exists(file_path):
        raise Http404('File not found')
    
    with open(file_path, 'rb') as f:
        content = f.read()
    
    return HttpResponse(content, content_type=allowed[filename])

def post_detail(request, post_id):
    try:
        post_id = decrypt_id(post_id)
        if post_id is None:
            return render(request, 'post_detail.html', {'post': None})
        post = Post.objects.get(id=post_id)
        is_liked = request.user.is_authenticated and PostLike.objects.filter(post=post, user=request.user).exists()
        is_favorited = request.user.is_authenticated and request.user in post.favorited_by.all()
        comments = Comment.objects.filter(post=post, parent__isnull=True).order_by('-created_at')
        total_comments = Comment.objects.filter(post=post).count()
        
        user_comment_interactions = {}
        can_delete_comments = set()
        if request.user.is_authenticated:
            for ci in CommentInteraction.objects.filter(comment__post=post, user=request.user):
                user_comment_interactions[ci.comment_id] = ci.is_like
            if request.user.is_superuser:
                can_delete_comments = set(Comment.objects.filter(post=post).values_list('id', flat=True))
            else:
                can_delete_comments = set(Comment.objects.filter(post=post, user=request.user).values_list('id', flat=True))
        
        return render(request, 'post_detail.html', {
            'post': post,
            'is_liked': is_liked,
            'like_count': post.likes.count(),
            'is_favorited': is_favorited,
            'favorite_count': post.favorited_by.count(),
            'comments': comments,
            'total_comments': total_comments,
            'user_comment_interactions': user_comment_interactions,
            'can_delete_comments': can_delete_comments,
        })
    except Post.DoesNotExist:
        return render(request, 'post_detail.html', {'post': None})

@login_required
def toggle_post_like(request):
    if request.method == 'POST':
        post_id = request.POST.get('post_id')
        post_id = decrypt_id(post_id)
        if post_id is None:
            return JsonResponse({'success': False, 'message': '无效的帖子ID'})
        try:
            post = Post.objects.get(id=post_id)
            like, created = PostLike.objects.get_or_create(post=post, user=request.user)
            if not created:
                like.delete()
                return JsonResponse({'success': True, 'liked': False, 'count': post.likes.count()})
            return JsonResponse({'success': True, 'liked': True, 'count': post.likes.count()})
        except Post.DoesNotExist:
            return JsonResponse({'success': False, 'message': '帖子不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def delete_post(request):
    if request.method == 'POST':
        post_id = request.POST.get('post_id')
        post_id = decrypt_id(post_id)
        if post_id is None:
            return JsonResponse({'success': False, 'message': '无效的帖子ID'})
        try:
            post = Post.objects.get(id=post_id)
            if post.user == request.user:
                post.delete()
                return JsonResponse({'success': True, 'message': '帖子已删除'})
            else:
                return JsonResponse({'success': False, 'message': '无权删除'})
        except Post.DoesNotExist:
            return JsonResponse({'success': False, 'message': '帖子不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def toggle_post_favorite(request):
    if request.method == 'POST':
        post_id = request.POST.get('post_id')
        post_id = decrypt_id(post_id)
        if post_id is None:
            return JsonResponse({'success': False, 'message': '无效的帖子ID'})
        try:
            post = Post.objects.get(id=post_id)
            if request.user in post.favorited_by.all():
                post.favorited_by.remove(request.user)
                is_fav = False
            else:
                post.favorited_by.add(request.user)
                is_fav = True
            return JsonResponse({'success': True, 'is_favorited': is_fav, 'favorite_count': post.favorited_by.count()})
        except Post.DoesNotExist:
            return JsonResponse({'success': False, 'message': '帖子不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

def index(request):
    next_url = request.GET.get('next', '/home/')
    return render(request, 'index.html', {'next_url': next_url})

def search(request):
    keyword = request.GET.get('keyword', '').strip()
    search_type = request.GET.get('type', 'all')
    school = request.GET.get('school', '').strip()
    subject = request.GET.get('subject', '').strip()
    selected_tags = request.GET.getlist('tags', [])
    
    # 预设学科列表（与文件管理中的一致）
    default_subjects = ['程序设计(C)', '程序设计(C++)', '程序设计(Java)', '程序设计(Python)', '思想道德与法治', '心理健康与职业发展', '高等数学', '大学物理', '离散数学', '通用英语', '中国近代史纲要', '数学文化']
    
    # 获取用户已使用的学科
    user_subjects = list(Upload.objects.exclude(subject='').values_list('subject', flat=True).distinct())
    
    # 合并并去重，保持顺序（预设学科在前，用户自定义学科在后）
    all_subjects_list = []
    seen = set()
    
    # 添加预设学科
    for subj in default_subjects:
        if subj not in seen:
            all_subjects_list.append(subj)
            seen.add(subj)
    
    # 添加用户自定义学科（排除已在预设列表中的）
    for subj in user_subjects:
        if subj not in seen:
            all_subjects_list.append(subj)
            seen.add(subj)
    
    tag_groups = {
        '章节': ['函数', '导数', '数列', '不等式', '向量', '立体几何', '解析几何', '概率统计', '极限', '积分', '力学', '电磁学', '热学', '光学', '原子物理', '化学反应', '有机化学', '无机化学', '细胞', '遗传', '进化', '生态系统', '数据结构', '算法', '编程', '数据库', '网络', '操作系统'],
        '难度': ['基础', '进阶', '压轴', '难题', '易错', '高频', '创新'],
        '模块': ['选择题', '填空题', '解答题', '计算题', '证明题', '作图题', '编程题', '应用题']
    }
    
    all_tags = set()
    all_subjects = set()
    results = {
        'posts': [],
        'folders': [],
        'uploads': [],
        'questions': [],
        'users': [],
        'api': [],
    }
    
    keyword_lower = keyword.lower() if keyword else ''
    
    if search_type in ['all', 'post']:
        posts = Post.objects.all().select_related('user__profile')
        if school:
            posts = posts.filter(user__profile__school=school)
        for p in posts:
            score = 1
            if keyword_lower:
                content_match = p.content.lower()
                if keyword_lower in content_match:
                    score = content_match.count(keyword_lower)
                elif p.link_url and keyword_lower in p.link_url.lower():
                    score = 1
                else:
                    continue
            results['posts'].append({'post': p, 'score': score})
        results['posts'].sort(key=lambda x: x['score'], reverse=True)
    
    if search_type in ['all', 'file']:
        # 搜索所有共享文件（所有层级文件夹和不在文件夹中的文件）
        uploads = Upload.objects.filter(is_shared=True).select_related('user__profile').prefetch_related('questions')
        if school:
            uploads = uploads.filter(user__profile__school=school)
        if subject:
            uploads = uploads.filter(subject=subject)
        
        folder_uploads_map = {}
        
        # 先收集文件，同时记录每个文件所在的顶层文件夹
        file_top_folder_map = {}  # upload_id -> top_folder_path
        
        for u in uploads:
            score = 1
            if keyword_lower:
                fname_lower = u.file_name.lower() if u.file_name else ''
                desc_lower = u.description.lower() if u.description else ''
                if keyword_lower in fname_lower:
                    score = fname_lower.count(keyword_lower) * 2
                elif keyword_lower in desc_lower:
                    score = desc_lower.count(keyword_lower)
                else:
                    continue
            
            # 使用数据库中存储的学科
            detected_subject = u.subject if u.subject else None
            all_tags_in_upload = []
            
            for q in u.questions.all():
                if q.tags:
                    tags_str = q.tags
                    if ',' in tags_str:
                        for t in tags_str.split(','):
                            t = t.strip()
                            if t:
                                all_tags.add(t)
                                all_tags_in_upload.append(t)
                    else:
                        for t in tags_str.split('，'):
                            t = t.strip()
                            if t:
                                all_tags.add(t)
                                all_tags_in_upload.append(t)
            
            if detected_subject:
                all_subjects.add(detected_subject)
            
            if score > 0:
                results['uploads'].append({'upload': u, 'score': score, 'subject': detected_subject, 'tags_count': len(all_tags_in_upload)})
                # 收集文件夹信息（只按顶层文件夹分组）
                if u.folder_path:
                    # 获取顶层文件夹（路径的第一部分）
                    top_folder = u.folder_path.split('/')[0]
                    if top_folder not in folder_uploads_map:
                        folder_uploads_map[top_folder] = []
                    folder_uploads_map[top_folder].append(u)
        results['uploads'].sort(key=lambda x: x['score'], reverse=True)
        
        # 从匹配的文件中提取文件夹信息（只显示顶层文件夹）
        for folder_path, folder_uploads in folder_uploads_map.items():
            first_upload = folder_uploads[0]
            results['folders'].append({
                'folder_path': folder_path,
                'folder_name': folder_path,
                'user': first_upload.user,
                'profile': getattr(first_upload.user, 'profile', None),
                'description': first_upload.description,
                'file_count': len(folder_uploads),
                'score': 1
            })
        results['folders'].sort(key=lambda x: x['score'], reverse=True)
    
    if search_type in ['all', 'question']:
        questions = QuestionBank.objects.filter(upload__processing_status='completed', upload__is_shared=True).select_related('upload__user__profile').prefetch_related('favorited_by')
        if school:
            questions = questions.filter(upload__user__profile__school=school)
        if subject:
            questions = questions.filter(upload__subject=subject)
        # 将选中的标签转换为集合以便快速查找
        selected_tags_set = set(selected_tags)
        
        for q in questions:
            score = 1
            tags_list = []
            if q.tags:
                if ',' in q.tags:
                    tags_list = [t.strip() for t in q.tags.split(',') if t.strip()]
                else:
                    tags_list = [t.strip() for t in q.tags.split('，') if t.strip()]
            
            # 计算匹配的标签数量
            matched_tags_count = 0
            if selected_tags_set:
                for tag in tags_list:
                    if tag in selected_tags_set:
                        matched_tags_count += 1
                # 如果有选中的标签但没有匹配，跳过这个题目
                if matched_tags_count == 0:
                    continue
            
            if keyword_lower:
                content_lower = q.content.lower()
                answer_lower = q.answer.lower() if q.answer else ''
                if keyword_lower in content_lower:
                    score = content_lower.count(keyword_lower) * 2
                elif keyword_lower in answer_lower:
                    score = answer_lower.count(keyword_lower)
                else:
                    continue
            
            # 标签匹配数量作为评分的重要部分（每个匹配的标签加10分）
            score += matched_tags_count * 10
            
            is_favorited = False
            if request.user.is_authenticated:
                is_favorited = request.user in q.favorited_by.all()
            
            results['questions'].append({'question': q, 'score': score, 'tags_list': tags_list, 'is_favorited': is_favorited, 'matched_tags': matched_tags_count})
            for tag in tags_list:
                all_tags.add(tag)
        
        # 按评分排序（标签匹配越多，评分越高）
        results['questions'].sort(key=lambda x: x['score'], reverse=True)
    
    if search_type in ['all', 'api']:
        api_instances = ApiInstance.objects.filter(is_active=True).select_related('user__profile').order_by('-created_at')
        if school:
            api_instances = api_instances.filter(user__profile__school=school)
        for inst in api_instances:
            score = 1
            if keyword_lower:
                name_lower = inst.name.lower()
                username_lower = inst.user.username.lower()
                if keyword_lower in name_lower:
                    score = name_lower.count(keyword_lower) * 2
                elif keyword_lower in username_lower:
                    score = username_lower.count(keyword_lower)
                else:
                    continue
            results['api'].append({
                'instance': inst,
                'user': inst.user,
                'profile': getattr(inst.user, 'profile', None),
                'score': score,
            })
        results['api'].sort(key=lambda x: x['score'], reverse=True)
    
    if search_type in ['all', 'user']:
        profiles = Profile.objects.all().select_related('user')
        if school:
            profiles = profiles.filter(school=school)
        for prof in profiles:
            if keyword_lower:
                if keyword_lower in prof.user.username.lower():
                    results['users'].append({'profile': prof, 'score': 1})
            else:
                results['users'].append({'profile': prof, 'score': 1})
    
    schools = Profile.objects.exclude(school='').values_list('school', flat=True).distinct().order_by('school')
    
    grouped_tags = {
        '章节/知识点': [],
        '难度': [],
        '模块': [],
        '其他': []
    }
    
    for tag in all_tags:
        tag_stripped = tag.strip()
        matched = False
        
        if tag_stripped in tag_groups['难度']:
            grouped_tags['难度'].append(tag)
            matched = True
        elif tag_stripped in tag_groups['模块']:
            grouped_tags['模块'].append(tag)
            matched = True
        elif tag_stripped in tag_groups['章节']:
            grouped_tags['章节/知识点'].append(tag)
            matched = True
        elif tag_stripped not in all_subjects_list:
            grouped_tags['章节/知识点'].append(tag)
    
    return render(request, 'search.html', {
        'keyword': keyword,
        'search_type': search_type,
        'school': school,
        'subject': subject,
        'selected_tags': selected_tags,
        'results': results,
        'all_tags': sorted(list(all_tags)),
        'grouped_tags': grouped_tags,
        'schools': schools,
        'all_subjects': all_subjects_list,
    })

def favorite_question(request):
    if request.method == 'POST':
        question_id = request.POST.get('question_id')
        try:
            question = QuestionBank.objects.get(id=question_id)
            if request.user in question.favorited_by.all():
                question.favorited_by.remove(request.user)
                action = 'removed'
            else:
                question.favorited_by.add(request.user)
                action = 'added'
            return JsonResponse({'success': True, 'action': action})
        except QuestionBank.DoesNotExist:
            return JsonResponse({'success': False, 'error': '题目不存在'})
    return JsonResponse({'success': False, 'error': '无效请求'})

def about(request):
    return render(request, 'about.html')

@login_required
def follow_user(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        try:
            user_to_follow = User.objects.get(id=user_id)
            if user_to_follow != request.user:
                Follow.objects.get_or_create(follower=request.user, following=user_to_follow)
                return JsonResponse({'success': True, 'message': '关注成功'})
            else:
                return JsonResponse({'success': False, 'message': '不能关注自己'})
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': '用户不存在'})
    return JsonResponse({'success': False, 'message': '请求方法错误'})

@login_required
def unfollow_user(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        try:
            user_to_unfollow = User.objects.get(id=user_id)
            follow_relation = Follow.objects.filter(follower=request.user, following=user_to_unfollow)
            if follow_relation.exists():
                follow_relation.delete()
                return JsonResponse({'success': True, 'message': '取消关注成功'})
            else:
                return JsonResponse({'success': False, 'message': '未关注该用户'})
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': '用户不存在'})
    return JsonResponse({'success': False, 'message': '请求方法错误'})

def extract_questions(request):
    if request.method == 'POST':
        try:
            upload_id = request.POST.get('upload_id', '').strip()
            if not upload_id:
                return JsonResponse({'success': False, 'message': '缺少文件ID'})
            
            from .utils import decrypt_id
            upload_id = decrypt_id(upload_id)
            if upload_id is None:
                return JsonResponse({'success': False, 'message': '无效的文件ID'})
            
            upload = Upload.objects.get(id=upload_id)
            if upload.user != request.user:
                return JsonResponse({'success': False, 'message': '无权操作此文件'})
            if upload.processing_status not in ('pending', 'error'):
                return JsonResponse({'success': False, 'message': '该文件已在处理或已完成'})
            
            import threading
            thread = threading.Thread(target=process_upload_in_background, args=(upload_id, request.user.id), daemon=True)
            thread.start()
            return JsonResponse({'success': True, 'message': '开始处理'})
        except Upload.DoesNotExist:
            return JsonResponse({'success': False, 'message': '文件不存在'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'启动失败: {str(e)}'})
    return JsonResponse({'success': False, 'message': '请求方法错误'})


import re as _re_helper

def strip_question_number(text):
    """剥离 AI 提取的题号前缀（如 '1. '、'1、'、'10. '），仅保留纯题目内容"""
    if not text:
        return text
    # 剥离行首的数字题号：1. 1、 10. 等
    text = _re_helper.sub(r'^\s*\d+[\.、\s]\s*', '', text)
    return text.strip()


def renumber_questions(upload_id):
    """根据 id 顺序重新分配 question_number"""
    from app1.models import QuestionBank
    qs = QuestionBank.objects.filter(upload_id=upload_id).order_by('id')
    for i, q in enumerate(qs, 1):
        if q.question_number != i:
            QuestionBank.objects.filter(id=q.id).update(question_number=i)


@login_required
def get_upload_progress(request):
    """获取文件处理进度"""
    if request.method == 'GET':
        try:
            upload_id = request.GET.get('upload_id', '').strip()
            if not upload_id:
                return JsonResponse({'success': False, 'message': '缺少文件ID'})
            
            from .utils import decrypt_id
            upload_id = decrypt_id(upload_id)
            if upload_id is None:
                return JsonResponse({'success': False, 'message': '无效的文件ID'})
            
            upload = Upload.objects.get(id=upload_id)
            if upload.user != request.user:
                return JsonResponse({'success': False, 'message': '无权访问'})
            
            # 计算进度百分比
            total = upload.total_questions or 1
            processed = upload.processed_questions or 0
            progress = min(int((processed / total) * 100), 99) if upload.processing_status == 'ai_processing' else 0
            
            return JsonResponse({
                'success': True,
                'status': upload.processing_status,
                'progress': progress,
                'total': upload.total_questions,
                'processed': upload.processed_questions,
                'error': upload.processing_error or ''
            })
        except Upload.DoesNotExist:
            return JsonResponse({'success': False, 'message': '文件不存在'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '请求方法错误'})


@login_required
def upload_question_image(request):
    """上传题目编辑器中的图片，返回图片 URL"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    file = request.FILES.get('image')
    if not file:
        return JsonResponse({'success': False, 'message': '请选择图片'})
    # 验证文件类型
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'):
        return JsonResponse({'success': False, 'message': '不支持的图片格式，支持 jpg/png/gif/webp/bmp'})
    from django.conf import settings
    from PIL import Image as PilImage
    import io
    import uuid
    # 生成唯一文件名（统一转成 .jpg）
    filename = f'qimg_{uuid.uuid4().hex}.jpg'
    # 确保目录存在
    img_dir = os.path.join(settings.MEDIA_ROOT, 'question_images')
    os.makedirs(img_dir, exist_ok=True)
    filepath = os.path.join(img_dir, filename)
    # 用 Pillow 打开并缩放到固定宽度 400px（高度等比缩放）
    image = PilImage.open(file)
    # 转为 RGB（处理 RGBA/透明图）
    if image.mode in ('RGBA', 'LA', 'P'):
        bg = PilImage.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        bg.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = bg
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    # 缩放
    MAX_WIDTH = 200
    w, h = image.size
    if w > MAX_WIDTH:
        ratio = MAX_WIDTH / w
        new_h = int(h * ratio)
        image = image.resize((MAX_WIDTH, new_h), PilImage.LANCZOS)
    # 保存为 JPEG（质量 85）
    image.save(filepath, 'JPEG', quality=85, optimize=True)
    # 返回可访问的 URL
    url = f'{settings.MEDIA_URL}question_images/{filename}'
    return JsonResponse({'success': True, 'url': url})


@login_required
def edit_question(request):
    if request.method == 'POST':
        try:
            question_id = request.POST.get('question_id')
            content = request.POST.get('content', '').strip()
            answer = request.POST.get('answer', '').strip()
            tags = request.POST.get('tags', '').strip()
            question_type = request.POST.get('question_type', '').strip()
            
            if not question_id:
                return JsonResponse({'success': False, 'message': '缺少题目ID'})
            
            question = QuestionBank.objects.get(id=question_id)
            
            # 检查权限：用户必须是上传者本人
            if question.upload.user != request.user:
                return JsonResponse({'success': False, 'message': '无权编辑此题目'})
            
            # 更新内容
            if content:
                question.content = content
            
            # 更新答案
            if answer is not None:
                question.answer = answer
            
            # 更新标签：tags是完整标签列表（含题型），question_type单独存储
            if tags is not None:
                # 解析标签（逗号或中文逗号分隔）
                all_list = [t.strip() for t in tags.replace('，', ',').split(',') if t.strip()]
                # 题型标签单独存储
                if question_type:
                    question.question_type = question_type
                    # 去重：从标签列表中移除重复的题型标签
                    filtered = [t for t in all_list if t != question_type]
                    # 标签格式：知识点1，知识点2，题型
                    all_tags = '，'.join(filtered + [question_type]) if filtered else question_type
                else:
                    all_tags = '，'.join(all_list) if all_list else ''
                question.tags = all_tags
            
            question.save()
            
            return JsonResponse({'success': True, 'message': '保存成功'})
        
        except QuestionBank.DoesNotExist:
            return JsonResponse({'success': False, 'message': '题目不存在'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'保存失败: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': '请求方法错误'})

@login_required
def open_question_bank(request, upload_id):
    try:
        upload_id = decrypt_id(upload_id)
        if upload_id is None:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': '无效的文件ID'})
            return render(request, 'question_bank.html', {'upload': None, 'questions': [], 'error': '无效的文件ID'})
        upload = Upload.objects.get(id=upload_id)
        
        # 检查权限：用户是上传者本人，或者题库已共享
        if upload.user != request.user and not upload.is_shared:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': '无权访问此题库'})
            return render(request, 'question_bank.html', {'upload': None, 'questions': [], 'error': '无权访问此题库'})
        
        questions = QuestionBank.objects.filter(upload=upload).order_by('id')
        
        # AJAX请求返回JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if questions.count() > 0:
                # 已有题目，自动修复状态为completed
                if upload.processing_status != 'completed':
                    upload.processing_status = 'completed'
                    upload.save(update_fields=['processing_status'])
                pass
            elif upload.processing_status in ('pending', 'extracting', 'ai_processing'):
                return JsonResponse({'success': True, 'upload_status': 'processing', 'questions': []})
            elif upload.processing_status == 'error':
                return JsonResponse({'success': True, 'upload_status': 'error', 'questions': [], 'error_msg': upload.processing_error or '处理失败'})
            else:
                return JsonResponse({'success': True, 'upload_status': 'empty', 'questions': []})
            
            favorited_question_ids = set(QuestionBank.objects.filter(favorited_by=request.user, upload=upload).values_list('id', flat=True))
            questions_data = []
            for q in questions:
                questions_data.append({
                    'id': q.id,
                    'content': q.content,
                    'answer': q.answer,
                    'is_favorited': q.id in favorited_question_ids,
                    'tags': q.tags,
                    'question_type': q.question_type,
                    'question_number': q.question_number,
                })
            is_owner = upload.user == request.user
            return JsonResponse({'success': True, 'upload_status': 'completed', 'questions': questions_data, 'favorited_question_ids': list(favorited_question_ids), 'is_owner': is_owner})
        
        # 直接访问：分页加载，每页20道
        from django.core.paginator import Paginator
        paginator = Paginator(questions, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        favorited_question_ids = set(QuestionBank.objects.filter(favorited_by=request.user, upload=upload).values_list('id', flat=True))
        return render(request, 'question_bank.html', {
            'upload': upload,
            'page_obj': page_obj,
            'questions': page_obj.object_list,
            'favorited_question_ids': favorited_question_ids,
        })
    except Upload.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': '文件不存在'})
        return render(request, 'question_bank.html', {'upload': None, 'questions': []})
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': str(e)})
        return render(request, 'question_bank.html', {'upload': None, 'questions': [], 'error': str(e)})

def _wrap_math_expressions(text):
    """
    将文本中的数学表达式包装为 LaTeX 格式
    处理模式：x^2, x_n, f(x), sqrt(x), 积分符号等
    """
    import re
    
    # 处理上下标模式：x^2, a_n, x^{2}, a_{n}
    text = re.sub(r'([a-zA-Z])\^\{(\d+)\}', r'$\1^{\2}$', text)
    text = re.sub(r'([a-zA-Z])\^(\d+)', r'$\1^\2$', text)
    text = re.sub(r'([a-zA-Z])_(\d+)', r'$\1_\2$', text)
    text = re.sub(r'([a-zA-Z])_\{(\d+)\}', r'$\1_{\2}$', text)
    
    # 处理分数模式
    text = re.sub(r'(\b\d+)\s*/\s*(\d+\b)', r'$\1/\2$', text)
    
    # 处理函数：f(x), sin(x), cos(x) 等
    text = re.sub(r'\b([a-zA-Z]+)\(([^)]+)\)', r'$\1(\2)$', text)
    
    # 处理根号
    text = re.sub(r'sqrt\(([^)]+)\)', r'$\\sqrt{\1}$', text)
    
    # 处理绝对值
    text = re.sub(r'\|([^|]+)\|', r'$|\1|$', text)
    
    # 处理希腊字母
    greek_map = {
        'alpha': '\\alpha', 'beta': '\\beta', 'gamma': '\\gamma', 'delta': '\\delta',
        'epsilon': '\\epsilon', 'theta': '\\theta', 'lambda': '\\lambda', 'mu': '\\mu',
        'pi': '\\pi', 'sigma': '\\sigma', 'phi': '\\phi', 'psi': '\\psi', 'omega': '\\omega',
        'Alpha': '\\Alpha', 'Beta': '\\Beta', 'Gamma': '\\Gamma', 'Delta': '\\Delta',
        'Theta': '\\Theta', 'Lambda': '\\Lambda', 'Pi': '\\Pi', 'Sigma': '\\Sigma',
        'Phi': '\\Phi', 'Psi': '\\Psi', 'Omega': '\\Omega'
    }
    for greek, latex in greek_map.items():
        text = text.replace(greek, '$' + latex + '$')
    
    # 处理向量符号
    text = re.sub(r'vec\s+([a-zA-Z])', r'$\\vec{\1}$', text)
    text = re.sub(r'vec\{([a-zA-Z])\}', r'$\\vec{\1}$', text)
    
    # 处理积分、求和等符号
    text = text.replace('∫', '$\\int$')
    text = text.replace('∬', '$\\iint$')
    text = text.replace('∭', '$\\iiint$')
    text = text.replace('∑', '$\\sum$')
    text = text.replace('∞', '$\\infty$')
    text = text.replace('∂', '$\\partial$')
    text = text.replace('≥', '$\\geq$')
    text = text.replace('≤', '$\\leq$')
    text = text.replace('≠', '≠')
    text = text.replace('∈', '$\\in$')
    text = text.replace('⊂', '$\\subset$')
    text = text.replace('⊃', '$\\supset$')
    text = text.replace('∪', '$\\cup$')
    text = text.replace('∩', '$\\cap$')
    text = text.replace('∅', '$\\emptyset$')
    text = re.sub(r'(\d+)°', r'$\1^\\circ$', text)
    text = text.replace('π', '$\\pi$')
    
    return text


def extract_text_from_word(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.docx':
        # 先预处理DOCX：将OMML公式转换为LaTeX文本
        from app1.docx_math.pre_process import pre_process_docx_file
        import tempfile, os as os_mod
        processed_path = None
        try:
            processed_path = pre_process_docx_file(file_path)
            doc = Document(processed_path)
        except Exception as e:
            print(f"公式预处理失败，使用原始文件: {e}")
            doc = Document(file_path)
        
        text = []
        for para in doc.paragraphs:
            if para.text.strip():
                text.append(para.text.strip())
        
        # 清理临时文件
        if processed_path and os_mod.path.exists(processed_path):
            try:
                os_mod.remove(processed_path)
            except:
                pass
        
        raw = '\n'.join(text)
        # 后处理：将数学表达式包装为LaTeX
        return _wrap_math_expressions(raw)
    elif ext == '.pdf':
        # 先用 pdf2docx 将 PDF 转为 DOCX（可保留公式结构），再走 OMML→LaTeX 管道
        from app1.docx_math.pre_process import pre_process_docx_file
        import tempfile, os as os_mod
        docx_path = None
        processed_path = None
        
        # 尝试 PyMuPDF（最佳CID字体支持）
        try:
            import fitz
            doc = fitz.open(file_path)
            text = []
            for page in doc:
                page_text = page.get_text()
                if page_text:
                    text.append(page_text)
            doc.close()
            raw = '\n'.join(text)
            if raw.strip():
                return _wrap_math_expressions(raw)
        except Exception as e_fitz:
            print(f"PyMuPDF提取失败({e_fitz})，尝试其他方法")
        
        # 尝试 pdfplumber（更好的文本提取）
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                text = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text.append(page_text)
                raw = '\n'.join(text)
                
                if raw.strip():
                    # 后处理：将数学表达式包装为LaTeX
                    return _wrap_math_expressions(raw)
        except Exception as e_plumber:
            print(f"pdfplumber提取失败({e_plumber})，尝试其他方法")
        
        # 尝试 pdf2docx
        try:
            from pdf2docx import Converter
            tmp_fd, docx_path = tempfile.mkstemp(suffix='.docx')
            os.close(tmp_fd)
            cv = Converter(file_path)
            cv.convert(docx_path, start=0, end=None)
            cv.close()
            
            # 尝试预处理
            try:
                processed_path = pre_process_docx_file(docx_path)
                doc = Document(processed_path)
            except Exception as e2:
                print(f"公式预处理失败，使用pdf2docx原始输出: {e2}")
                doc = Document(docx_path)
            
            text = []
            for para in doc.paragraphs:
                if para.text.strip():
                    text.append(para.text.strip())
            raw = '\n'.join(text)
            
            if raw.strip():
                return _wrap_math_expressions(raw)
        except Exception as e_pdf:
            print(f"pdf2docx转换失败({e_pdf})，继续尝试")
        finally:
            # 清理临时文件
            for p in [docx_path, processed_path]:
                if p and os_mod.path.exists(p):
                    try: os_mod.remove(p)
                    except: pass
        
        # 回退：使用 PyPDF2
        try:
            text = []
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text.append(page_text)
            raw = '\n'.join(text)
            # 在句号、问号、右括号后添加换行，帮助AI识别题目边界
            raw = raw.replace('。', '。\n')
            raw = raw.replace('？', '？\n')
            raw = raw.replace(')', ')\n')
            lines = [line.strip() for line in raw.split('\n') if line.strip()]
            return '\n'.join(lines)
        except Exception as e:
            print(f"读取PDF失败: {e}")
            return ""
    elif ext == '.md':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw = f.read()
            raw = raw.replace('。', '。\n')
            raw = raw.replace('？', '？\n')
            lines = [line.strip() for line in raw.split('\n') if line.strip()]
            return '\n'.join(lines)
        except Exception as e:
            print(f"读取MD失败: {e}")
            return ""
    return ""

def process_with_deepseek(text_content, start_num=1, existing_tags=None, model_name='qwen3.5-27b', model_config=None):
    tags_hint = ""
    if existing_tags:
        tags_str = "、".join(existing_tags[:100])
        tags_hint = f"\n已有标签参考：{tags_str}\n请优先从以上标签中选择，如果没有合适的再创建新标签。新标签应保持通用、简洁（2-6个字），不要过于详细（如不要出现具体的人名、地名、年代数字等细节）。"
    
    # 使用字符串拼接避免 LaTeX 中的 {} 被解析为 Python 变量
    prompt_part1 = """请整理以下题目文字，按照不同题型输出：

【单选题/多选题格式】：
题号.题目内容(   )
A.选项内容
B.选项内容
C.选项内容
D.选项内容
答案：X（选择题输出字母如A/B/C/D；多选题输出如ABC）
标签：知识点1，知识点2
题型：单选题/多选题

【判断题格式】：
题号.题目内容(   )
答案：√/×
标签：知识点1，知识点2
题型：判断题

【填空题格式】：
题号.题目内容
答案：答案内容（如有多个空，用分号分隔）
标签：知识点1，知识点2
题型：填空题

【解答题格式】：
题号.题目内容
答案：解答内容
标签：知识点1，知识点2
题型：解答题

要求：
1. 根据题目类型选择对应的格式输出
2. 判断题识别：题目末尾有( )或（），要求判断对错，答案输出√或×
3. 填空题识别：题目中有____、__或下划线表示填空位置，答案填写空白处应填内容
4. 选择题识别：有(A)(B)(C)(D)等选项的题目
5. 解答题识别：需要详细解答的问答题
6. **题目内容中不得包含答案**。先查看题目原文中是否包含答案（如括号内有字母、√、×、具体数值等），如果有则将其提取到"答案:"行中，同时将题目内容中的答案去掉。
   - 例如原文是"对称的点为( D )"，题目内容应写为"对称的点为(   )"，答案行写"答案：D"
   - 例如原文是"则 abc = 30"，题目内容应写为"则 abc ="，答案行写"答案：30"
7. **如果题目原文中没有答案**，则由你思考后给出正确答案
8. **必须保持原始题号不变**。例如原题是"4."则输出时也要用"4."，不能改为"1."。原题有几题就输出几题。
9. **标签格式：标签中必须包含知识点和题型**，知识点和题型用"，"隔开，例如：
    - 判断题：标签：向量运算，判断题
    - 单选题：标签：空间解析几何，单选题
    - 填空题：标签：二重积分，填空题
    - 解答题：标签：向量运算，解答题
10. 每道题1~2个标签即可
11. **每道题之间必须用一个空行隔开**，每道题内容、答案、标签、题型信息都结束后，必须换一行再加下一道题
12. **必须保持原始题号不变**：例如原题是"4."则输出也要用"4."，不能重编为"1."。
13. **对不完整的题目请直接舍弃**：如果题目内容末尾明显截断（如只有半个句子、末尾仅剩单个汉字）、选项不完整（如选项只有"A."、"B."没有选项文字）、或无法辨认出有效题目内容，**请不要输出，直接跳过**。宁可少一题，也不输出残缺题。
"""
    
    prompt_part2 = """
13. **数学公式必须使用LaTeX格式输出，所有数学内容都必须用$...$包裹**：
    - 行内公式用 $公式内容$ 包裹，例如：$a+b=c$
    - **题目中所有英文字母（变量如a,b,x,y,D,z等）必须放在$...$内**，如 $a$, $b$, $x$, $y$, $D$
    - **题目中所有数字（在数学上下文中）必须放在$...$内**，如 $1$, $2$, $0$
    - **所有数学运算符（+、-、=、≤、≥、≠、⊥等）必须放在$...$内**
    - **题目中的（）和{ }也必须放在$...$内**
    - **如果题目涉及向量（有|a+b|、⊥、a×b等），变量必须使用 \\vec 表示**，如 $\\vec{a}$, $\\vec{b}$
    - 例题：原题"设 a \\neq 0, b \\neq 0, 且 a \\perp b, 则 |a+b| = |a-b|"（其中a,b是向量）应输出为：设 $\\vec{a} \\neq 0$, $\\vec{b} \\neq 0$, 且 $\\vec{a} \\perp \\vec{b}$, 则 $|\\vec{a}+\\vec{b}| = |\\vec{a}-\\vec{b}|$。( )
    - 例题：原题"设D: x + y ≤ 1" 应输出为：设 $D$: $x + y \\leq 1$
    - 例题：原题"∫∫_D (x+y)dσ = 1" 应输出为：$\\iint_D (x+y) \\mathrm{d}\\sigma = 1$
    - 数学符号用LaTeX命令：极限用 \\lim，积分用 \\int，二重积分用 \\iint，偏导用 \\partial，向量用 \\vec
    - 希腊字母：\\alpha, \\beta, \\gamma, \\delta, \\theta, \\lambda, \\pi, \\sigma, \\phi, \\psi, \\omega
    - 特殊符号：\\infty, \\cdot, \\times, \\div, \\pm, \\leq, \\geq, \\neq, \\equiv, \\approx, \\sim
    - 分数用 \\frac{a}{b}，例如：\\frac{x+y}{2}
    - 下标用 _{n}，上标用 ^{2}，例如：x_{i}, x^{2}
    - 三角符号：\\sin, \\cos, \\tan, \\cot
    - 对数指数：\\ln, \\log, \\exp
"""
    
    prompt_part3 = """

题目内容：
"""
    
    prompt = prompt_part1 + prompt_part2 + tags_hint + prompt_part3 + text_content

    print(f"[DEBUG] 发送AI请求, model={model_name}, prompt长度={len(prompt)}")
    
    if model_config:
        # 使用用户自定义的模型配置
        import requests as _requests
        import json as _json
        
        headers = {
            'Content-Type': 'application/json',
        }
        
        if model_config.api_format == 'openai':
            # OpenAI Chat Completions 格式
            headers['Authorization'] = f'Bearer {model_config.api_key}'
            payload = {
                'model': model_config.model_id,
                'messages': [
                    {"role": "system", "content": "你是一个专业的题目整理助手，请严格按照要求格式输出。"},
                    {"role": "user", "content": prompt}
                ],
                'temperature': 0.1,
                'max_tokens': 32000,
            }
        elif model_config.api_format == 'anthropic':
            # Anthropic Messages 格式
            headers['x-api-key'] = model_config.api_key
            headers['anthropic-version'] = '2023-06-01'
            payload = {
                'model': model_config.model_id,
                'max_tokens': 32000,
                'messages': [
                    {"role": "user", "content": prompt}
                ],
            }
        else:
            raise ValueError(f"不支持的API格式: {model_config.api_format}")
        
        try:
            # 根据 API 格式自动拼接完整路径
            if model_config.api_format == 'openai':
                base = model_config.request_url.rstrip('/')
                if not base.endswith('/v1/chat/completions'):
                    url = base + '/v1/chat/completions'
                else:
                    url = base
            elif model_config.api_format == 'anthropic':
                base = model_config.request_url.rstrip('/')
                if not base.endswith('/v1/messages'):
                    url = base + '/v1/messages'
                else:
                    url = base
            else:
                url = model_config.request_url
            
            resp = _requests.post(url, headers=headers, json=payload, timeout=300)
            resp.raise_for_status()
            result = resp.json()
            
            if model_config.api_format == 'openai':
                content = result['choices'][0]['message'].get('content', '')
                # 只从 content 获取内容，不读取 reasoning_content（避免输出推理内容）
            elif model_config.api_format == 'anthropic':
                content = result['content'][0]['text']
            else:
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            # 剥离思考过程
            content = _strip_reasoning(content)
            
            print(f"[DEBUG] AI返回内容长度={len(content) if content else 0}")
            return content or ""
        except Exception as e:
            print(f"[DEBUG] 自定义AI调用异常: {type(e).__name__}: {e}")
            # 如果自定义配置失败，尝试使用内置配置
            raise
    else:
        raise ValueError("未配置 AI 模型。请在个人中心 → 模型配置中添加并启用一个 AI 模型。")


def _sanitize_error(msg):
    """过滤错误信息中可能泄露的 API 密钥"""
    import re
    msg = re.sub(r'(sk-)[A-Za-z0-9_\-]{6,}', r'\1******', msg)
    msg = re.sub(r'(Bearer\s+)[A-Za-z0-9_\-\.]{6,}', r'\1******', msg)
    return msg


def _strip_reasoning(content):
    """剥离 AI 返回内容中的思考/推理过程（DeepSeek-R1, QwQ 等模型常见）"""
    import re as _re
    if not content:
        return content
    # 清理代码块标记
    content = content.replace('```latex', '').replace('```tex', '').replace('```', '')
    
    # 找到第一个 \begin{problem} 或 \newtheorem{problem}，删除之前的所有内容（思考过程）
    for marker in ['\\begin{problem}', '\\newtheorem{problem}']:
        idx = content.find(marker)
        if idx >= 0:
            content = content[idx:]
            break
    
    # 找到最后一个 \end{solution}，删除之后的所有内容（杂音）
    idx = content.rfind('\\end{solution}')
    if idx >= 0:
        content = content[:idx + len('\\end{solution}')]
    
    return content.strip()


def _strip_answer_reasoning(answer):
    """剥离 AI 在答案末尾添加的推理/对比文字"""
    import re as _re
    if not answer:
        return answer
    # 常见推理标记：问号后跟中文思考，或"但原"、"然而"、"原解答"等
    # 标记列表
    markers = [
        r'\?\s*但\s*原',           # "?但原"、"？但原"
        r'\?\s*然而',              # "?然而"
        r'\?\s*原解答',            # "?原解答"
        r'\?\s*实际',              # "?实际"
        r'\?\s*需重新',            # "?需重新"
        r'\?\s*检查',              # "?检查"
        r'\。\s*但\s*原',          # "。但原"
        r'\。\s*然而',             # "。然而"
        r'\。\s*原解答',           # "。原解答"
        r'\。\s*此处以原',         # "。此处以原"
        r'两种解法结果冲突',       # 直接匹配
        r'原解答过程较为复杂',     # 直接匹配
        r'详细计算略',             # 直接匹配
        r'具体过程略',             # 直接匹配 
        r'故修正题目为',           # AI 擅自改题
        r'可能题目有误',           # 怀疑题目
    ]
    for marker in markers:
        idx = _re.search(marker, answer)
        if idx:
            answer = answer[:idx.start()]
    # 如果以 ? 或 ?" 结尾但前面有数学公式，截断
    answer = answer.strip().rstrip('?？')
    return answer.strip()


def process_deepseek_chunked(text_content, existing_tags=None, model_name='qwen3.5-27b', upload_id=None, model_config=None):
    # 检测换行符类型
    if '\r\n' in text_content:
        raw_lines = text_content.replace('\r\n', '\n').split('\n')
    elif '\r' in text_content:
        raw_lines = text_content.split('\r')
    else:
        raw_lines = text_content.split('\n')
    
    lines = [l.strip() for l in raw_lines if l.strip()]
    
    # 按题目边界分组：以数字开头的行是新题开始
    question_blocks = []
    current_block = []
    
    for line in lines:
        # 检测是否以数字开头（如 "1xxx", "2xxx"）
        if line and line[0].isdigit():
            # 过滤掉孤立的纯数字（如页码 "4"、"5"单独成行），它们不是题目
            is_page_num = line.strip().isdigit() and len(line.strip()) <= 2
            if is_page_num:
                # 如果是孤立数字，跳过它（不另起新块）
                continue
            if current_block:
                question_blocks.append('\n'.join(current_block))
            current_block = [line]
        else:
            current_block.append(line)
    
    if current_block:
        question_blocks.append('\n'.join(current_block))
    
    # 按每15题合并为一个AI请求（降低分块大小避免AI输出超限）
    CHUNK_SIZE = 15
    chunks = []
    for i in range(0, len(question_blocks), CHUNK_SIZE):
        chunks.append('\n\n'.join(question_blocks[i:i+CHUNK_SIZE]))
    
    all_questions = []
    for idx, chunk in enumerate(chunks):
        start_num = len(all_questions) + 1
        try:
            ai_output = process_with_deepseek(chunk, start_num, existing_tags, model_name, model_config)
            questions = parse_ai_questions(ai_output)
            all_questions.extend(questions)
        except Exception as e:
            error_msg = f"第{idx+1}块处理失败: {_sanitize_error(str(e))}"
            print(error_msg)
            if upload_id:
                try:
                    from django.db import close_old_connections
                    close_old_connections()
                    up = Upload.objects.get(id=upload_id)
                    existing = up.processing_error or ''
                    up.processing_error = (existing + '; ' + error_msg)[:500]
                    up.save(update_fields=['processing_error'])
                except:
                    pass
            continue
    
    # 如果部分块失败，在 processing_error 中追加警告
    if all_questions and upload_id:
        try:
            from django.db import close_old_connections
            close_old_connections()
            up = Upload.objects.get(id=upload_id)
            existing = up.processing_error or ''
            if existing:
                up.processing_error = (existing + f' (共{len(all_questions)}道题成功)')[:500]
                up.save(update_fields=['processing_error'])
        except:
            pass
    
    return all_questions

def _replace_latex_with_image(text):
    """
    保持 LaTeX 公式为文本格式，用 $ 包裹，让前端 KaTeX 渲染
    如果文本已含 $ 则直接返回，否则检测并包裹 LaTeX 表达式
    """
    if not text or '$' in text:
        return text
    return _wrap_latex_content(text)


def _wrap_latex_content(text):
    """
    将文本中的 LaTeX 代码包装为 KaTeX 可识别的格式。
    智能分段：只包裹数学表达式，保留中文文本在$...$之外。
    支持：\\command{...}, \\command_{...}, \\command^{...} 以及嵌套大括号。
    """
    import re
    
    if not text or '$' in text:
        return text
    
    # LaTeX 命令列表（用于快速检测）
    latex_commands = [
        r'\frac', r'\lim', r'\int', r'\iint', r'\iiint', r'\oint', r'\sum', r'\prod',
        r'\sqrt', r'\partial', r'\nabla', r'\infty', r'\cdot', r'\times', r'\div',
        r'\pm', r'\mp', r'\leq', r'\geq', r'\neq', r'\equiv', r'\approx', r'\sim',
        r'\propto', r'\in', r'\subset', r'\supset', r'\cup', r'\cap', r'\emptyset',
        r'\forall', r'\exists', r'\neg', r'\implies', r'\iff', r'\therefore', r'\because',
        r'\underline', r'\overline', r'\hat', r'\tilde', r'\vec', r'\dot', r'\ddot',
        r'\prime', r'\left', r'\right', r'\begin', r'\end', r'\Prj', r'\proj',
        r'\mid', r'\Vert', r'\mathrm', r'\mathbf', r'\mathcal', r'\mathbb',
        r'\displaystyle', r'\alpha', r'\beta', r'\gamma', r'\delta', r'\theta',
        r'\lambda', r'\pi', r'\sigma', r'\phi', r'\psi', r'\omega', r'\epsilon',
        r'\zeta', r'\eta', r'\kappa', r'\mu', r'\nu', r'\xi', r'\rho', r'\tau',
        r'\upsilon', r'\chi', r'\Gamma', r'\Delta', r'\Theta', r'\Lambda', r'\Xi',
        r'\Pi', r'\Sigma', r'\Upsilon', r'\Phi', r'\Psi', r'\Omega',
        r'\sin', r'\cos', r'\tan', r'\cot', r'\sec', r'\csc', r'\ln', r'\log', r'\exp',
        r'\rightarrow', r'\leftarrow', r'\Rightarrow', r'\Leftarrow',
        r'\longrightarrow', r'\longleftarrow', r'\perp', r'\parallel',
        r'\star', r'\ast', r'\oplus', r'\otimes', r'\odot', r'\text',
    ]
    
    has_latex = any(cmd in text for cmd in latex_commands)
    has_subscript = '_{' in text or '^{' in text
    
    if not has_latex and not has_subscript:
        return text
    
    # 辅助函数：从位置pos开始，读取一个完整的 {...} 组（处理嵌套）
    def read_brace_group(s, pos):
        """从 s[pos] 开始（s[pos]必须是 '{'），读取完整的大括号组，返回结束位置"""
        if pos >= len(s) or s[pos] != '{':
            return pos
        count = 1
        j = pos + 1
        while j < len(s) and count > 0:
            if s[j] == '{':
                count += 1
            elif s[j] == '}':
                count -= 1
            j += 1
        return j  # 返回 } 之后的位置
    
    # 预处理：将非标准命令替换为KaTeX兼容的命令
    text = text.replace(r'\Prj', r'\operatorname{Prj}')
    
    result = []
    i = 0
    n = len(text)
    
    while i < n:
        if text[i] == '\\' and i + 1 < n and text[i+1].isalpha():
            # ---- 找到 LaTeX 命令 ----
            start = i
            i += 1
            # 读取命令名称
            while i < n and text[i].isalpha():
                i += 1
            # 读取后续的 _{...}、^{...}、{...} 等参数
            while i < n:
                if text[i] == '{':
                    i = read_brace_group(text, i)
                elif text[i] in '^_' and i + 1 < n and text[i+1] == '{':
                    # 读取 ^{...} 或 _{...}
                    i = read_brace_group(text, i + 1)
                elif text[i] in '^_' and i + 1 < n and text[i+1].isalpha():
                    # 简单的 ^ 或 _ 后跟字母（如 x^2）
                    i += 2
                elif text[i] == '(' and i > start:  # 命令后的 () 参数（如 \sin(x)）
                    count = 1
                    j = i + 1
                    while j < n and count > 0:
                        if text[j] == '(':
                            count += 1
                        elif text[j] == ')':
                            count -= 1
                        j += 1
                    i = j
                else:
                    break
            expr = text[start:i]
            result.append('$' + expr + '$')
        elif text[i] in '^_' and i + 1 < n and text[i+1] == '{':
            # 独立的 ^{...} 或 _{...}
            start = i
            i = read_brace_group(text, i + 1)
            result.append('$' + text[start:i] + '$')
        else:
            result.append(text[i])
            i += 1
    
    return ''.join(result)


def parse_ai_questions(ai_output):
    import re as _re
    
    # 预处理1：将 AI 常用的 \(...\) 替换为 $...$
    ai_output = _re.sub(r'\\\(', '$', ai_output)
    ai_output = _re.sub(r'\\\)', '$', ai_output)
    
    # 预处理2：确保所有题号单独成行
    # 对2位及以上数字（10, 11...），即使前面没有换行也插入换行
    ai_output = _re.sub(r'(?<!\d)(\d{2,})([\.、])(?!\d)', r'\n\1\2', ai_output)
    
    safe = ai_output[:2000].encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    print(f"=== AI 输出 (预处理后) ===")
    print(safe)
    if len(ai_output) > 2000:
        print("...（截断）")
    print(f"=== 结束 ===")
    
    questions = []
    
    # 按 \n数字. 或 \n数字、 拆分为独立题块
    blocks = _re.split(r'\n(?=\d+[\.、])', ai_output.strip())
    # 去掉第一块如果它不是以数字开头
    if blocks and not _re.match(r'^\d+[\.、]', blocks[0].strip()):
        blocks = blocks[1:]
    
    print(f"拆分为 {len(blocks)} 个题块")
    for bi, b in enumerate(blocks):
        print(f"  块{bi+1}({len(b)}字符): {b[:80]}...")
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        lines_in_block = block.split('\n')
        content_lines = []
        answer = ''
        tags = ''
        qtype = '单选题'
        
        for line in lines_in_block:
            line = line.strip()
            if not line:
                continue
            if line.startswith('答案：') or line.startswith('答案:'):
                answer = line.replace('答案：', '').replace('答案:', '').strip()
            elif line.startswith('标签：') or line.startswith('标签:'):
                tags = line.replace('标签：', '').replace('标签:', '').strip()
            elif line.startswith('题型：') or line.startswith('题型:'):
                qtype = line.replace('题型：', '').replace('题型:', '').strip()
            else:
                content_lines.append(line)
        
        content = '\n'.join(content_lines)
        if not content:
            continue
        
        # 过滤掉含有乱码的题目（cid字体编码）
        if '(cid:' in content.lower() or '(cid:' in answer.lower():
            print(f"  跳过含乱码的题目: {content[:60]}")
            continue
        
        # 检测截断的题目：内容末尾明显不完整
        last_line = content_lines[-1] if content_lines else ''
        last_char = last_line.rstrip()[-1] if last_line.rstrip() else ''
        # 如果答案为空，最后一行很短（≤3字）且末尾不是正常标点，判定为截断
        if not answer and last_line and len(last_line.strip()) <= 3:
            if last_char not in ('。', '？', '！', ')', '）', '"', '"', "'", "'", '》', '」', '】', '?', '!', '.'):
                print(f"  跳过截断题目(短行无标点): {content[:60]}")
                continue
        # 如果答案为空，且最后一行只有1个汉字（PDF分页截断）
        if not answer and last_line and len(last_line.strip()) == 1:
            lc = last_char
            if '\u4e00' <= lc <= '\u9fff' or '\u3400' <= lc <= '\u4dbf':
                print(f"  跳过截断题目(单个汉字结尾): {content[:60]}")
                continue
        
        # 推断题型
        if qtype == '单选题':
            if answer in ['√', '×', '对', '错', '正确', '错误']:
                qtype = '判断题'
            elif any(kw in content for kw in ['证明', '求', '计算', '解答']):
                qtype = '解答题'
            elif '____' in content or '___' in content or '______' in content:
                qtype = '填空题'
        
        questions.append({
            'content': content,
            'answer': answer,
            'tags': tags,
            'question_type': qtype
        })
    
    print(f"解析出 {len(questions)} 道题目")
    return questions

def contact(request):
    return render(request, 'contact.html')


@login_required
def submit_feedback(request):
    """用户提交建议，发送通知给 admin"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    content = request.POST.get('content', '').strip()
    image = request.FILES.get('image')
    if not content and not image:
        return JsonResponse({'success': False, 'message': '请输入建议内容或上传截图'})
    from .models import Notification
    from django.contrib.auth.models import User
    import os, uuid
    from django.conf import settings
    # 处理图片
    image_url = ''
    if image:
        ext = os.path.splitext(image.name)[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'):
            return JsonResponse({'success': False, 'message': '不支持的图片格式'})
        # 缩放图片
        from PIL import Image as PilImage
        filename = f'feedback_{uuid.uuid4().hex}.jpg'
        img_dir = os.path.join(settings.MEDIA_ROOT, 'feedback_images')
        os.makedirs(img_dir, exist_ok=True)
        filepath = os.path.join(img_dir, filename)
        pil_img = PilImage.open(image)
        if pil_img.mode in ('RGBA', 'LA', 'P'):
            bg = PilImage.new('RGB', pil_img.size, (255, 255, 255))
            if pil_img.mode == 'P':
                pil_img = pil_img.convert('RGBA')
            bg.paste(pil_img, mask=pil_img.split()[-1] if pil_img.mode == 'RGBA' else None)
            pil_img = bg
        elif pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')
        MAX_WIDTH = 400
        w, h = pil_img.size
        if w > MAX_WIDTH:
            ratio = MAX_WIDTH / w
            pil_img = pil_img.resize((MAX_WIDTH, int(h * ratio)), PilImage.LANCZOS)
        pil_img.save(filepath, 'JPEG', quality=85, optimize=True)
        image_url = f'{settings.MEDIA_URL}feedback_images/{filename}'
    # 组装通知内容
    from django.utils.html import escape
    safe_content = escape(content) if content else '(无文字内容)'
    notif_content = f'用户 {request.user.username}（ID: {request.user.id}）提交了建议：\n{safe_content}'
    if image_url:
        notif_content += f'\n\n截图：{request.build_absolute_uri(image_url)}'
    # 发送通知给所有超级管理员，如果没有超级管理员则发给 id=1 的用户
    admins = User.objects.filter(is_superuser=True)
    if not admins.exists():
        admins = User.objects.filter(id=1)
    for admin in admins:
        Notification.objects.create(
            user=admin,
            sender=request.user,
            title=f'📩 用户反馈 - {request.user.username}',
            content=notif_content,
        )
    return JsonResponse({'success': True, 'message': '感谢您的建议！已提交给管理员。'})


@login_required
def delete_notification(request):
    """删除通知"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    notification_id = data.get('notification_id')
    if not notification_id:
        return JsonResponse({'success': False, 'message': '缺少通知ID'})
    try:
        from django.db.models import Q
        # 尝试解密（如果是加密ID）
        nid = decrypt_id(str(notification_id)) if isinstance(notification_id, str) and len(str(notification_id)) > 10 else None
        if nid is None:
            nid = int(notification_id)
        notif = Notification.objects.get(
            Q(id=nid) & (Q(user=request.user) | Q(sender=request.user))
        )
        notif.delete()
        return JsonResponse({'success': True})
    except (Notification.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'success': False, 'message': '通知不存在或无权限删除'})


@login_required
def reply_notification(request):
    """回复通知，发送通知给原发送者"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    notification_id = data.get('notification_id')
    reply_content = data.get('content', '').strip()
    if not reply_content:
        return JsonResponse({'success': False, 'message': '回复内容不能为空'})
    try:
        original = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'message': '通知不存在'})
    # 确定回复目标：sender 存在且不是自己
    reply_target = None
    if original.sender and original.sender != request.user:
        reply_target = original.sender
    if not reply_target:
        # 无发送者或发送者是自己时发给管理员
        from django.contrib.auth.models import User
        targets = list(User.objects.filter(is_superuser=True).exclude(id=request.user.id))
        if not targets:
            targets = list(User.objects.filter(id=1))
        if not targets:
            return JsonResponse({'success': False, 'message': '无法回复：找不到接收方'})
        for target in targets:
            Notification.objects.create(
                user=target,
                sender=request.user,
                title=f'📩 回复：{original.title}',
                content=f'{request.user.username} 回复了您的通知：\n{reply_content}',
            )
        return JsonResponse({'success': True, 'message': '回复已发送'})
    # 发送回复通知给原发送者
    Notification.objects.create(
        user=reply_target,
        sender=request.user,
        title=f'📩 回复：{original.title}',
        content=f'{request.user.username} 回复了您的通知：\n{reply_content}',
    )
    return JsonResponse({'success': True, 'message': '回复已发送'})


@login_required
def notification_detail(request, notification_id):
    """通知详情页"""
    try:
        nid = decrypt_id(notification_id)
        if nid is None:
            raise Notification.DoesNotExist
        # 允许接收者或发送者查看
        from django.db.models import Q
        notif = Notification.objects.get(
            Q(id=nid) & (Q(user=request.user) | Q(sender=request.user))
        )
        is_sent = (notif.sender == request.user)
    except Notification.DoesNotExist:
        return render(request, 'notification_detail.html', {'error': '通知不存在'})
    
    # 标记为已读（仅当是接收者时）
    if not notif.is_read and not is_sent:
        notif.is_read = True
        notif.save()
    
    sender_info = None
    reply_target = None
    if not is_sent:
        # 常规通知：回复给发送者
        if notif.sender and notif.sender != request.user:
            reply_target = notif.sender
            sender_info = {
                'username': notif.sender.username,
                'id': notif.sender.id,
            }
    if not reply_target and not is_sent:
        from django.contrib.auth.models import User
        admin = User.objects.filter(is_superuser=True).exclude(id=request.user.id).first()
        if not admin:
            admin = User.objects.filter(id=1).first()
        if admin:
            reply_target = admin
            sender_info = {
                'username': admin.username,
                'id': admin.id,
            }
    
    if request.method == 'POST':
        reply_content = request.POST.get('reply_content', '').strip()
        reply_image = request.FILES.get('reply_image')
        if reply_content or reply_image:
            import os, uuid
            from django.conf import settings
            from PIL import Image as PilImage
            # 处理图片
            image_url = ''
            if reply_image:
                filename = f'reply_{uuid.uuid4().hex}.jpg'
                img_dir = os.path.join(settings.MEDIA_ROOT, 'feedback_images')
                os.makedirs(img_dir, exist_ok=True)
                filepath = os.path.join(img_dir, filename)
                pil_img = PilImage.open(reply_image)
                if pil_img.mode in ('RGBA', 'LA', 'P'):
                    bg = PilImage.new('RGB', pil_img.size, (255, 255, 255))
                    if pil_img.mode == 'P':
                        pil_img = pil_img.convert('RGBA')
                    bg.paste(pil_img, mask=pil_img.split()[-1] if pil_img.mode == 'RGBA' else None)
                    pil_img = bg
                elif pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')
                MAX_WIDTH = 400
                w, h = pil_img.size
                if w > MAX_WIDTH:
                    ratio = MAX_WIDTH / w
                    pil_img = pil_img.resize((MAX_WIDTH, int(h * ratio)), PilImage.LANCZOS)
                pil_img.save(filepath, 'JPEG', quality=85, optimize=True)
                image_url = f'{settings.MEDIA_URL}feedback_images/{filename}'
            # 组装回复内容
            notif_content = f'{request.user.username} 回复了您的通知：\n{reply_content}' if reply_content else f'{request.user.username} 回复了您的通知'
            if image_url:
                notif_content += f'\n\n{request.build_absolute_uri(image_url)}'
            # 确定接收方：用 reply_target（已排除自身的情况）
            if not reply_target:
                from django.contrib.auth.models import User
                targets = list(User.objects.filter(is_superuser=True).exclude(id=request.user.id))
                if not targets:
                    targets = list(User.objects.filter(id=1))
                if not targets:
                    targets = []
            else:
                targets = [reply_target]
            for target in targets:
                Notification.objects.create(
                    user=target,
                    sender=request.user,
                    title=f'📩 回复：{notif.title}',
                    content=notif_content,
                )
            return redirect('notification_detail', notification_id=notification_id)
    
    # 将内容中的图片URL转为img标签
    import re
    content_html = notif.content.replace('\n', '<br>')
    content_html = re.sub(
        r'(https?://[^\s<]+(\.jpg|\.jpeg|\.png|\.gif|\.webp)[^\s<]*)',
        r'<br><img src="\1" style="max-width:100%;max-height:300px;" class="img-thumbnail mt-1">',
        content_html, flags=re.IGNORECASE
    )
    
    return render(request, 'notification_detail.html', {
        'notification': notif,
        'content_html': content_html,
        'sender_info': sender_info,
        'notification_id': notification_id,
        'is_sent': is_sent,
    })


@login_required
def delete_notification_page(request, notification_id):
    """从详情页删除通知"""
    if request.method == 'POST':
        try:
            from django.db.models import Q
            nid = decrypt_id(notification_id)
            if nid is None:
                raise Notification.DoesNotExist
            notif = Notification.objects.get(
                Q(id=nid) & (Q(user=request.user) | Q(sender=request.user))
            )
            notif.delete()
        except Notification.DoesNotExist:
            pass
    return redirect('my')


@login_required
def admin_send_notification(request):
    """管理员发送通知给用户"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': '无权限'})
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    user_ids = data.get('user_ids', [])
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    if not user_ids or not title or not content:
        return JsonResponse({'success': False, 'message': '请选择接收用户并填写标题和内容'})
    from .models import Notification
    from django.contrib.auth.models import User
    targets = User.objects.filter(id__in=user_ids)
    count = 0
    for target in targets:
        Notification.objects.create(
            user=target,
            sender=request.user,
            title=title,
            content=content,
        )
        count += 1
    return JsonResponse({'success': True, 'message': f'已发送给 {count} 个用户'})


@login_required
def revoke_notification(request):
    """撤回已发出的通知（删除自己和对方的记录）"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    notification_id = data.get('notification_id')
    if not notification_id:
        return JsonResponse({'success': False, 'message': '参数错误'})
    from .models import Notification
    try:
        nid = decrypt_id(notification_id)
        if nid is None:
            return JsonResponse({'success': False, 'message': '通知不存在'})
        notif = Notification.objects.get(id=nid, sender=request.user)
        recipient_user = notif.user
        title = notif.title
        content = notif.content
        # 删除发送者的记录（即本条）
        notif.delete()
        # 也删除接收方的同一条通知（匹配 sender + user + title + content）
        Notification.objects.filter(
            user=recipient_user,
            sender=request.user,
            title=title,
            content=content,
        ).delete()
        return JsonResponse({'success': True, 'message': '已撤回'})
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'message': '通知不存在或无权限'})


def price(request):
    return render(request, 'price.html')

def user_profile(request, user_id):
    """用户详情页面"""
    try:
        user_id = decrypt_id(user_id)
        if user_id is None:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': '无效的用户ID'})
            return render(request, 'user_profile.html', {'error': '无效的用户ID'})
        target_user = User.objects.get(id=user_id)
        profile = getattr(target_user, 'profile', None)
        
        # 获取关注和粉丝数
        following_count = Follow.objects.filter(follower=target_user).count()
        follower_count = Follow.objects.filter(following=target_user).count()
        
        # 是否已关注（仅登录用户）
        is_following = False
        if request.user.is_authenticated:
            is_following = Follow.objects.filter(follower=request.user, following=target_user).exists()
        
        # 共享的题库文件
        shared_uploads = Upload.objects.filter(user=target_user, processing_status='completed', is_shared=True).order_by('-uploaded_at')
        
        # 获取共享的文件夹
        from django.db.models import Q
        all_shared_uploads = Upload.objects.filter(user=target_user, is_shared=True)
        folder_paths = all_shared_uploads.exclude(folder_path='').values_list('folder_path', flat=True).distinct()
        shared_folders = []
        seen_top_folders = set()
        for fp in folder_paths:
            top_folder = fp.split('/')[0]
            if top_folder not in seen_top_folders:
                seen_top_folders.add(top_folder)
                folder_uploads = all_shared_uploads.filter(folder_path=top_folder)
                subfolder_uploads = all_shared_uploads.filter(folder_path__startswith=top_folder + '/')
                total_count = folder_uploads.count() + subfolder_uploads.count()
                if folder_uploads.exists():
                    first = folder_uploads.first()
                    shared_folders.append({
                        'folder_path': top_folder,
                        'folder_name': top_folder,
                        'description': first.description,
                        'file_count': total_count,
                        'uploaded_at': first.uploaded_at,
                    })
        
        # 用户的帖子
        from .models import Post
        user_posts = Post.objects.filter(user=target_user).order_by('-created_at')
        
        # 计算年龄
        age = None
        if profile and profile.birthday:
            from datetime import date
            today = date.today()
            age = today.year - profile.birthday.year
            if (today.month, today.day) < (profile.birthday.month, profile.birthday.day):
                age -= 1
        
        # 如果是 AJAX 请求，返回片段模板
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.template.loader import render_to_string
            from django.middleware.csrf import get_token
            
            avatar_url = profile.get_avatar_url() if profile else '/static/pictures/头像/男生头像1.jpg'
            school = profile.school if profile and profile.school else ''
            
            html = render_to_string('user_profile_partial.html', {
                'target_user': target_user,
                'avatar_url': avatar_url,
                'school': school,
                'following_count': following_count,
                'follower_count': follower_count,
                'is_following': is_following,
                'shared_uploads': shared_uploads,
                'shared_folders': shared_folders,
                'total_shared_count': shared_uploads.count() + len(shared_folders),
                'age': age,
                'user': request.user,
                'csrf_token_value': get_token(request),
            })
            return JsonResponse({'success': True, 'html': html})
        
        return render(request, 'user_profile.html', {
            'target_user': target_user,
            'profile': profile,
            'following_count': following_count,
            'follower_count': follower_count,
            'is_following': is_following,
            'shared_uploads': shared_uploads,
            'shared_folders': shared_folders,
            'total_shared_count': shared_uploads.count() + len(shared_folders),
            'user_posts': user_posts,
            'age': age,
        })
    except User.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': '用户不存在'})
        return render(request, 'user_profile.html', {'error': '用户不存在'})

@login_required
def toggle_follow(request):
    """关注/取消关注"""
    if request.method == 'POST':
        try:
            target_user_id = request.POST.get('target_user_id')
            target_user_id = decrypt_id(target_user_id)
            if target_user_id is None:
                return JsonResponse({'success': False, 'message': '无效的用户ID'})
            target_user = User.objects.get(id=target_user_id)
            
            # 检查是否已关注
            follow, created = Follow.objects.get_or_create(
                follower=request.user, 
                following=target_user
            )
            
            if not created:
                # 已关注，取消关注
                follow.delete()
                is_following = False
            else:
                is_following = True
            
            return JsonResponse({
                'success': True, 
                'is_following': is_following,
                'following_count': Follow.objects.filter(follower=request.user).count(),
                'follower_count': Follow.objects.filter(following=request.user).count()
            })
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': '用户不存在'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def my(request):
    viewed_user = None
    target_user_id = request.GET.get('user_id')
    if target_user_id:
        try:
            decrypted_id = decrypt_id(target_user_id)
            if decrypted_id is not None:
                viewed_user = User.objects.get(id=decrypted_id)
        except User.DoesNotExist:
            viewed_user = None
    
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    default_avatars = os.listdir(os.path.join(settings.BASE_DIR, 'static', 'pictures', '头像'))
    default_avatars = [f for f in default_avatars if f.endswith(('.jpg', '.png', '.jpeg'))]
    following_count = Follow.objects.filter(follower=request.user).count()
    follower_count = Follow.objects.filter(following=request.user).count()
    following_list = Follow.objects.filter(follower=request.user).select_related('following__profile')
    followers_list = Follow.objects.filter(following=request.user).select_related('follower__profile')
    following_ids = set(Follow.objects.filter(follower=request.user).values_list('following_id', flat=True))
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:50]
    # 为通知添加 sender_username
    notification_list = []
    for n in notifications:
        notification_list.append({
            'id': n.id,
            'title': n.title,
            'content': n.content,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
            'sender_username': n.sender.username if n.sender else None,
            'has_sender': n.sender is not None,
            'encrypted_id': encrypt_id(n.id),
        })
    import json
    notifications_json = json.dumps(notification_list, ensure_ascii=False)
    
    # 我发出的通知
    sent_notifications = Notification.objects.filter(sender=request.user).order_by('-created_at')[:50]
    sent_notification_list = []
    for n in sent_notifications:
        sent_notification_list.append({
            'id': n.id,
            'title': n.title,
            'content': n.content,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
            'recipient_username': n.user.username,
            'encrypted_id': encrypt_id(n.id),
        })
    sent_notifications_json = json.dumps(sent_notification_list, ensure_ascii=False)
    
    uploads = Upload.objects.filter(user=request.user).order_by('-uploaded_at')
    favorite_uploads = Upload.objects.filter(favorited_by=request.user).order_by('-uploaded_at')
    favorite_questions = QuestionBank.objects.filter(favorited_by=request.user).select_related('upload').order_by('-id')
    favorite_posts = Post.objects.filter(favorited_by=request.user).select_related('user__profile').order_by('-created_at')
    favorite_upload_ids = set(Upload.objects.filter(favorited_by=request.user).values_list('id', flat=True))
    
    # 获取收藏的文件夹（所有文件都被收藏的文件夹）
    favorite_folder_groups = []
    # 获取所有已共享的文件夹路径（包括其他用户的）
    all_folders = Upload.objects.filter(is_shared=True).exclude(folder_path='').values_list('folder_path', flat=True).distinct()
    for folder_path in all_folders:
        # 只处理顶层文件夹
        if '/' not in folder_path:
            # 获取该文件夹下的所有文件
            folder_uploads = Upload.objects.filter(is_shared=True, folder_path=folder_path)
            # 检查是否所有文件都被收藏
            all_favorited = all(u.id in favorite_upload_ids for u in folder_uploads)
            if all_favorited:
                # 获取显示名称和所有者
                display_name = folder_path.split('/')[-1] if '/' in folder_path else folder_path
                owner_user = folder_uploads.first().user
                favorite_folder_groups.append({
                    'folder': folder_path,
                    'files': folder_uploads,
                    'display_name': display_name,
                    'owner_id': owner_user.id,
                    'owner_id_encrypted': encrypt_id(owner_user.id)
                })
    # 预设学科列表
    default_subjects = ['程序设计(C)', '程序设计(C++)', '程序设计(Java)', '程序设计(Python)', '思想道德与法治', '心理健康与职业发展', '高等数学', '大学物理', '离散数学', '通用英语', '中国近代史纲要', '数学文化']
    
    # 获取用户已使用的学科
    user_subjects = list(Upload.objects.exclude(subject='').values_list('subject', flat=True).distinct())
    
    # 合并并去重，保持顺序（预设学科在前，用户自定义学科在后）
    all_subjects = []
    seen = set()
    
    # 添加预设学科
    for subj in default_subjects:
        if subj not in seen:
            all_subjects.append(subj)
            seen.add(subj)
    
    # 添加用户自定义学科（排除已在预设列表中的）
    for subj in user_subjects:
        if subj not in seen:
            all_subjects.append(subj)
            seen.add(subj)
    for q in favorite_questions:
        q.content = re.sub(r'^\d+[.、]?\s*', '', q.content)
        q.tags_list = [t.strip() for t in q.tags.split('，') if t.strip()]
    # 计算年龄
    age = None
    if profile.birthday:
        from datetime import date
        today = date.today()
        age = today.year - profile.birthday.year
        if (today.month, today.day) < (profile.birthday.month, profile.birthday.day):
            age -= 1
    # 按文件夹分组上传文件
    grouped_uploads = {}
    for u in uploads:
        fp = u.folder_path or ''
        if fp not in grouped_uploads:
            grouped_uploads[fp] = []
        grouped_uploads[fp].append(u)
    # 根目录文件始终在最前面
    root_uploads = grouped_uploads.pop('', [])
    # 转为有序列表，模板中可直接遍历，只显示顶层文件夹
    folder_groups = []
    for fp in grouped_uploads:
        # 只显示顶层文件夹（没有"/"的文件夹路径）
        if '/' not in fp:
            folder_groups.append({
                'folder': fp,
                'files': grouped_uploads[fp],
                'display_name': fp
            })
    # 获取所有用户列表（用于管理员发送通知）
    all_users = User.objects.all().order_by('username')
    all_users_list = [{'id': u.id, 'username': u.username} for u in all_users]
    
    return render(request, 'my.html', {
        'profile': profile,
        'viewed_user': viewed_user,
        'default_avatars': default_avatars,
        'following_count': following_count,
        'follower_count': follower_count,
        'following_list': following_list,
        'followers_list': followers_list,
        'following_ids': following_ids,
        'notifications': notification_list,
        'notifications_json': notifications_json,
        'sent_notifications': sent_notification_list,
        'sent_notifications_json': sent_notifications_json,
        'uploads': uploads,
        'root_uploads': root_uploads,
        'folder_groups': folder_groups,
        'favorite_uploads': favorite_uploads,
        'favorite_questions': favorite_questions,
        'favorite_posts': favorite_posts,
        'favorite_upload_ids': favorite_upload_ids,
        'favorite_folder_groups': favorite_folder_groups,
        'age': age,
        'all_subjects': all_subjects,
        'all_users': all_users,
    })

@login_required
def mark_notifications_read(request):
    """标记通知为已读。若不传 notification_id 则标记全部"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body) if request.body else {}
            notification_id = data.get('notification_id')
            if notification_id:
                Notification.objects.filter(id=notification_id, user=request.user, is_read=False).update(is_read=True)
            else:
                Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def update_nickname(request):
    if request.method == 'POST':
        new_nickname = request.POST.get('nickname', '').strip()
        if not new_nickname:
            messages.error(request, '昵称不能为空')
        elif User.objects.filter(username=new_nickname).exclude(id=request.user.id).exists():
            messages.error(request, '该昵称已被使用')
        else:
            request.user.username = new_nickname
            request.user.save()
            messages.success(request, '昵称修改成功')
        return redirect(add_user_id_to_url(reverse('my'), request.user))
    return None


@login_required
def change_password(request):
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not re.match(PASSWORD_REGEX, new_password):
            messages.error(request, '密码格式错误：8-16位，包含大小写字母+数字')
        elif new_password != confirm_password:
            messages.error(request, '两次输入的新密码不一致')
        else:
            request.user.set_password(new_password)
            request.user.save()
            login(request, request.user)
            messages.success(request, '密码修改成功')
        return redirect(add_user_id_to_url(reverse('my'), request.user))

@login_required
def upload_avatar(request):
    if request.method == 'POST' and request.FILES.get('avatar'):
        try:
            profile, created = Profile.objects.get_or_create(user=request.user)
            profile.avatar = request.FILES['avatar']
            profile.default_avatar = ''
            profile.save()
            return JsonResponse({'success': True, 'message': '头像上传成功'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def select_default_avatar(request):
    if request.method == 'POST':
        avatar_name = request.POST.get('avatar_name', '')
        avatar_path = os.path.join('static', 'pictures', '头像', avatar_name)
        if os.path.exists(os.path.join(settings.BASE_DIR, avatar_path)):
            try:
                profile, created = Profile.objects.get_or_create(user=request.user)
                if profile.avatar:
                    if os.path.exists(profile.avatar.path):
                        os.remove(profile.avatar.path)
                    profile.avatar = None
                profile.default_avatar = os.path.join('pictures', '头像', avatar_name)
                profile.save()
                return JsonResponse({'success': True, 'message': '头像设置成功'})
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)})
        return JsonResponse({'success': False, 'message': '头像不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def update_school(request):
    if request.method == 'POST':
        school = request.POST.get('school', '').strip()
        profile, created = Profile.objects.get_or_create(user=request.user)
        profile.school = school
        profile.save()
        messages.success(request, '学校信息已更新')
    return redirect(add_user_id_to_url(reverse('my'), request.user))

@login_required
def cancel_account(request):
    if request.method == 'POST':
        user = request.user
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        confirm_text = request.POST.get('confirm_text', '').strip()

        if not user.check_password(password1):
            messages.error(request, '密码错误')
        elif password1 != password2:
            messages.error(request, '两次输入的密码不一致')
        elif confirm_text != '我已知悉删除账户的所有影响，所有风险自行承担。':
            messages.error(request, '确认声明不匹配')
        else:
            user_id = user.id
            try:
                with transaction.atomic():
                    uploads = Upload.objects.filter(user_id=user_id)
                    for upload in uploads:
                        if upload.file and upload.file.path:
                            file_path = upload.file.path
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        for qb in upload.questions.all():
                            if qb.image and qb.image.path:
                                img_path = qb.image.path
                                if os.path.exists(img_path):
                                    os.remove(img_path)
                    uploads.delete()

                    posts = Post.objects.filter(user_id=user_id)
                    for post in posts:
                        if post.file and post.file.path:
                            file_path = post.file.path
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        if post.image and post.image.path:
                            img_path = post.image.path
                            if os.path.exists(img_path):
                                os.remove(img_path)
                    posts.delete()

                    Comment.objects.filter(Q(user_id=user_id) | Q(upload__user_id=user_id) | Q(post__user_id=user_id)).delete()
                    CommentInteraction.objects.filter(user_id=user_id).delete()
                    Notification.objects.filter(user_id=user_id).delete()
                    UploadLike.objects.filter(user_id=user_id).delete()
                    PostLike.objects.filter(user_id=user_id).delete()
                    Follow.objects.filter(follower_id=user_id).delete()
                    Follow.objects.filter(following_id=user_id).delete()
                    Profile.objects.filter(user_id=user_id).delete()

                    User.objects.filter(id=user_id).delete()

                logout(request)
                messages.success(request, '账号已注销')
                return redirect('/')
            except Exception as e:
                messages.error(request, f'删除失败：{str(e)}')
        return redirect(add_user_id_to_url(reverse('my'), request.user))
    return redirect(add_user_id_to_url(reverse('my'), request.user))

def user_login(request):
    message = ""
    next_url = request.GET.get('next', '/home/')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        next_url = request.POST.get('next', '/home/')

        if not username:
            message = "请输入昵称"
        elif not password:
            message = "请输入密码"
        else:
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                messages.success(request, '登录成功，欢迎访问学测工坊！')
                return redirect(add_user_id_to_url(next_url, request.user))
            else:
                message = "昵称或密码错误"

    return render(request, 'index.html', {'message': message, 'next_url': next_url})

def user_register(request):
    message = ""
    next_url = request.GET.get('next', '/home/')
    username = ""

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        next_url = request.POST.get('next', '/home/')

        if not username:
            message = "请输入昵称"
        elif not password:
            message = "请输入密码"
        elif not re.match(PASSWORD_REGEX, password):
            message = "密码格式错误：8-16位，包含大小写字母+数字"
        elif not confirm_password:
            message = "请输入确认密码"
        elif password != confirm_password:
            message = "两次输入的密码不一致"
        elif User.objects.filter(username=username).exists():
            message = "该昵称已被使用，请选择其他昵称"
        else:
            user = User.objects.create_user(username=username, password=password)
            login(request, user)
            default_avatars = [f for f in os.listdir(os.path.join(settings.BASE_DIR, 'static', 'pictures', '头像')) if f.endswith(('.jpg', '.png', '.jpeg'))]
            random_avatar = random.choice(default_avatars) if default_avatars else ''
            Profile.objects.create(user=user, default_avatar=os.path.join('pictures', '头像', random_avatar))
            messages.success(request, '注册成功，欢迎访问学测工坊！')
            return redirect(add_user_id_to_url(next_url, request.user))

    return render(request, 'index.html', {'message': message, 'next_url': next_url, 'register_username': username, 'active_tab': 'register'})

def logout_view(request):
    logout(request)
    return redirect('/')

import json

def search_universities(request):
    query = request.GET.get('q', '')
    universities = []
    json_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'universities.json')
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            universities = data.get('universities', [])
    if query:
        universities = [u for u in universities if query.lower() in u.get('name', '').lower()]
    # 返回包含id和text的格式，供Select2使用
    results = [{'id': u['name'], 'text': u['name']} for u in universities[:50]]
    return JsonResponse(results, safe=False)

@login_required
def upload_file(request):
    if request.method == 'POST' and request.FILES.get('file'):
        try:
            import ntpath
            uploaded_file = request.FILES['file']
            raw_name = request.POST.get('file_name', '').strip() or uploaded_file.name
            # 解析文件夹路径和文件名
            folder_dir = ''
            base_name = raw_name
            # 支持正斜杠和反斜杠路径分隔
            normalized = raw_name.replace('\\', '/')
            if '/' in normalized:
                folder_dir, base_name = normalized.rsplit('/', 1)
            upload = Upload()
            upload.user = request.user
            upload.file_name = base_name
            upload.description = request.POST.get('description', '').strip()
            upload.subject = request.POST.get('subject', '').strip()
            upload.folder_path = folder_dir
            upload.processing_status = 'pending'
            # 如果有文件夹路径，保存文件到对应的子目录中
            if folder_dir:
                save_path = 'uploads/' + folder_dir + '/' + base_name
                upload.file.save(save_path, uploaded_file)
            else:
                upload.file = uploaded_file
            upload.save()
            return JsonResponse({'success': True, 'message': '文件上传成功', 'upload_id': upload.id})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def process_upload(request, upload_id):
    if request.method == 'POST':
        try:
            upload_id = decrypt_id(upload_id)
            if upload_id is None:
                return JsonResponse({'success': False, 'message': '无效的文件ID'})
            upload = Upload.objects.get(id=upload_id, user=request.user)
            if upload.processing_status not in ('pending', 'error'):
                return JsonResponse({'success': False, 'message': '该文件已在处理或已完成'})
            
            # 重新提取时，删除该文件之前提取的旧题目
            from app1.models import QuestionBank
            old_count = QuestionBank.objects.filter(upload=upload).delete()[0]
            if old_count:
                print(f"重新提取: 删除了{old_count}道旧题目")
            
            thread = threading.Thread(target=process_upload_in_background, args=(upload_id,), daemon=True)
            thread.start()
            return JsonResponse({'success': True, 'message': '开始处理'})
        except Upload.DoesNotExist:
            return JsonResponse({'success': False, 'message': '文件不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

def parse_latex_questions(latex_text):
    """
    解析 AI 返回的 LaTeX 格式文本，提取 \begin{problem}...\end{problem} 和
    \begin{solution}...\end{solution} 块，返回题目列表。
    """
    import re as _re
    
    problems = []
    
    # 提取 \begin{problem}...\end{problem} 块
    pat = _re.compile(r'\\begin\{problem\}(.*?)\\end\{problem\}', _re.DOTALL)
    for pm in pat.finditer(latex_text):
        body = pm.group(1).strip()
        # 提取可选参数 [知识点：...] 和 [题型]
        tags = ''
        q_type = '解答题'
        
        # [知识点：xxx]
        m = _re.search(r'\[知识点：([^\]]*)\]', body)
        if m:
            tags = m.group(1).strip()
            body = body.replace(m.group(0), '')
        
        # [填空题] / [单选题] / [解答题] ...
        m = _re.search(r'\[([^\]]*?[题])\]', body)
        if m:
            tn = m.group(1)
            if '单选' in tn:
                q_type = '单选题'
            elif '多选' in tn:
                q_type = '多选题'
            elif '填空' in tn:
                q_type = '填空题'
            elif '判断' in tn:
                q_type = '判断题'
            elif '解答' in tn or '计算' in tn or '证明' in tn or '论述' in tn:
                q_type = '解答题'
            else:
                q_type = '其他'
            body = body.replace(m.group(0), '')
        
        body = body.strip()
        if body:
            problems.append({
                'content': body,
                'tags': tags,
                'question_type': q_type,
                'answer': '',
            })
    
    # 提取 \begin{solution}...\end{solution} 块，按顺序匹配题目
    sol_pat = _re.compile(r'\\begin\{solution\}(.*?)\\end\{solution\}', _re.DOTALL)
    solutions = [s.group(1).strip() for s in sol_pat.finditer(latex_text)]
    
    for i, ans in enumerate(solutions):
        if i < len(problems):
            # 保持 \[ \] 为 $$（clean_latex_text 会处理转换）
            problems[i]['answer'] = ans.strip()
    
    # 剥离答案中的推理/对比文字
    for p in problems:
        if p['answer']:
            p['answer'] = _strip_answer_reasoning(p['answer'])
        # 也清理 content 中的推理/对比文字（AI 有时会在题目内容中混入）
        if p['content']:
            # 先清理，避免 AI 在题目后加"故修正题目为"等
            p['content'] = _strip_answer_reasoning(p['content'])
    
    # 对 content 和 answer 应用 clean_latex_text 清理
    # 将 \[ \] → $$，包裹裸 LaTeX，清理 \tag 等
    for p in problems:
        p['content'] = clean_latex_text(p['content'])
        if p['answer']:
            p['answer'] = clean_latex_text(p['answer'])
    
    return problems


def extract_pdf_via_ai(text_content, model_config):
    """
    将 PDF 提取出的文本发送到 AI，以 LaTeX 格式输出题目+答案。
    返回 AI 返回的原始 LaTeX 文本。
    """
    import requests as _requests
    import json as _json
    import re as _re
    
    # 清理文本，避免超长
    max_chars = 40000
    if len(text_content) > max_chars:
        text_content = text_content[:max_chars] + '\n\n...（内容过长，已截断）'
    
    # 构建 prompt（用户指定的格式）
    prompt = """给你这些文件，将其综合成一套题目+答案，要求所有转成latex格式，输出要求：无需输出题号，按照下列格式输出：

\\newtheorem{problem}{题目}
\\newtheorem{solution}{解}
\\begin{problem}[知识点：极限，等价无穷小，Taylor展开][填空题]
求 $\\displaystyle \\lim_{n \\to \\infty} n \\cdot \\left[ \\mathrm{e} - \\left(1 + \\frac{1}{n}\\right)^n \\right]$.
\\end{problem}
\\begin{solution}
\\[
\\lim_{n \\to \\infty} n \\cdot \\left[ \\mathrm{e} - \\left(1 + \\frac{1}{n}\\right)^n \\right] = \\frac{\\mathrm{e}}{2}.
\\]
\\end{solution}

各个题目（及答案）之间空行，并且如果文件中没有答案，那么你在对应题目自己给出答案，解答题给出详细解析（不许有略）。（如果原文件中有答案）你需要自己判断答案是否正确，如果正确则直接使用，如果错误则给出你自己100%确定的正确答案。其他无关文字（比如学校、大写题号、评分标准如"·····分"等）不输出，直接输出latex文本，无需转码成数学公式！

重要：只输出 \\begin{{problem}}...\\end{{problem}} 和 \\begin{{solution}}...\\end{{solution}} 格式的 LaTeX 文本。不要输出任何思考过程、分析、对比、说明、疑问或无关文字！即使你在判断答案对错，也绝对不要输出你的推理过程，直接输出最终的 problem/solution 即可！

文件内容：
""" + text_content
    
    headers = {'Content-Type': 'application/json'}
    
    if model_config.api_format == 'openai':
        headers['Authorization'] = f'Bearer {model_config.api_key}'
        payload = {
            'model': model_config.model_id,
            'messages': [
                {"role": "system", "content": "你是一个专业的数学LaTeX转换助手，请严格按照要求的格式输出。不要输出任何思考过程，直接输出LaTeX代码。"},
                {"role": "user", "content": prompt}
            ],
            'temperature': 0.1,
            'max_tokens': 32000,
        }
    elif model_config.api_format == 'anthropic':
        headers['x-api-key'] = model_config.api_key
        headers['anthropic-version'] = '2023-06-01'
        payload = {
            'model': model_config.model_id,
            'max_tokens': 32000,
            'messages': [{"role": "user", "content": prompt}],
        }
    else:
        raise ValueError(f"不支持的API格式: {model_config.api_format}")
    
    # 拼接 URL
    if model_config.api_format == 'openai':
        base = model_config.request_url.rstrip('/')
        if not base.endswith('/v1/chat/completions'):
            url = base + '/v1/chat/completions'
        else:
            url = base
    elif model_config.api_format == 'anthropic':
        base = model_config.request_url.rstrip('/')
        if not base.endswith('/v1/messages'):
            url = base + '/v1/messages'
        else:
            url = base
    else:
        url = model_config.request_url
    
    resp = _requests.post(url, headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    result = resp.json()
    
    if model_config.api_format == 'openai':
        content = result['choices'][0]['message'].get('content', '')
    elif model_config.api_format == 'anthropic':
        content = result['content'][0]['text']
    else:
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
    
    # 剥离思考过程
    content = _strip_reasoning(content)
    
    return content or ""


def process_upload_in_background(upload_id, user_id=None):
    try:
        from django.db import close_old_connections
        close_old_connections()
        upload = Upload.objects.get(id=upload_id)
        
        # 使用触发提取的用户（而非上传者）的模型配置和API key
        from django.contrib.auth import get_user_model
        User = get_user_model()
        effective_user = User.objects.get(id=user_id) if user_id else upload.user
        file_path = upload.file.path
        
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ('.doc', '.docx', '.pdf', '.md'):
            upload.processing_status = 'completed'
            upload.save(update_fields=['processing_status'])
            return
        
        upload.processing_status = 'extracting'
        upload.save(update_fields=['processing_status'])
        
        text_content = extract_text_from_word(file_path)
        close_old_connections()
        if not text_content.strip():
            upload = Upload.objects.get(id=upload_id)
            upload.processing_status = 'completed'
            upload.save(update_fields=['processing_status'])
            return
        
        # 检查用户是否有启用的模型配置
        enabled_config = UserModelConfig.objects.filter(user=effective_user, is_enabled=True).first()
        if not enabled_config:
            upload = Upload.objects.get(id=upload_id)
            upload.processing_status = 'error'
            upload.processing_error = '请先在个人中心-模型配置中添加并启用一个AI模型'
            upload.save(update_fields=['processing_status', 'processing_error'])
            return
        
        upload.processing_status = 'ai_processing'
        upload.save(update_fields=['processing_status'])
        
        # 收集已有标签供AI参考
        existing_tags_list = list(QuestionBank.objects.filter(upload__user=effective_user).exclude(tags='').values_list('tags', flat=True))
        all_tags = set()
        for t in existing_tags_list:
            for tag in t.split('，'):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)
        
        # PDF 文件使用专用的 LaTeX 输出提示词
        if ext == '.pdf':
            upload.processing_status = 'ai_processing'
            upload.save(update_fields=['processing_status'])
            
            latex_raw = extract_pdf_via_ai(text_content, enabled_config)
            close_old_connections()
            
            if not latex_raw.strip():
                upload = Upload.objects.get(id=upload_id)
                upload.processing_status = 'error'
                upload.processing_error = 'AI返回内容为空，请检查文件内容或模型配置'
                upload.save(update_fields=['processing_status', 'processing_error'])
                return
            
            questions = parse_latex_questions(latex_raw)
        else:
            questions = process_deepseek_chunked(text_content, existing_tags=list(all_tags), model_name=enabled_config.model_id, upload_id=upload_id, model_config=enabled_config)
        close_old_connections()
        
        # 如果AI未提取到任何题目，记录错误
        if not questions:
            upload = Upload.objects.get(id=upload_id)
            upload.processing_status = 'error'
            upload.processing_error = upload.processing_error or 'AI未能提取到任何题目，请检查文件内容是否包含有效题目，或检查模型配置是否正确'
            upload.save(update_fields=['processing_status', 'processing_error'])
            return
        
        # 最终防线：检查每道题的content中是否还嵌着后续题目
        # （对 PDF 的 LaTeX 输出跳过，因为 AI 已按要求不输出题号）
        import re as _re
        if ext != '.pdf':
            expanded_questions = []
            for q in questions:
                content = q.get('content', '')
                safe_content = _re.sub(r'(?<!\d)(\d{2,})([\.、])(?!\d)', r'\n\1\2', content)
                q_blocks = _re.split(r'\n(?=\d+[\.、])', safe_content)
                if len(q_blocks) > 1:
                    for j, block in enumerate(q_blocks):
                        block = block.strip()
                        if not block:
                            continue
                        if j == 0:
                            q['content'] = block
                            expanded_questions.append(q)
                        else:
                            new_ans = q.get('answer', '')
                            expanded_questions.append({
                                'content': block,
                                'answer': new_ans if j == len(q_blocks) - 1 else '',
                                'tags': q.get('tags', ''),
                                'question_type': q.get('question_type', '单选题')
                            })
                else:
                    expanded_questions.append(q)
            questions = expanded_questions
        
        upload = Upload.objects.get(id=upload_id)
        upload.total_questions = len(questions)
        upload.save(update_fields=['total_questions'])
        
        for i, q in enumerate(questions):
            q_type = q.get('question_type', '单选题')
            if q_type not in dict(QuestionBank.QUESTION_TYPES):
                q_type = '单选题'
            
            content = q.get('content', '')
            answer = q.get('answer', '')
            tags = q.get('tags', '')
            
            content = content.replace('\r', '')
            answer = answer.replace('\r', '')
            
            import re as _re2
            
            # 后处理0：过滤掉AI提取到的章节标题
            content = _re2.sub(r'(?:^|\n)\s*[一二三四五六七八九十]+[、．]\s*(?:选择|填空|判断|计算|解答|单项选择|多项选择|不定项选择|名词解释|简答|论述|证明|应用)[题]?\s*(?:\n|$)', '\n', content)
            content = _re2.sub(r'\n\s*[一二三四五六七八九十]+[、．]\s*\S*[题]\s*', '\n', content)
            content = content.strip()
            
            # PDF AI 的 LaTeX 输出不需要 \neq 后处理和 $$ 移除（已经是合法 LaTeX）
            if ext != '.pdf':
                def _fix_neq(m):
                    before, after = m.group(1), m.group(2)
                    return ('$' + before.strip() + '$' if before.strip() else '') + ' ≠ ' + ('$' + after.strip() + '$' if after.strip() else '')
                content = _re2.sub(r'\$([^$]*?)\\neq([^$]*?)\$', _fix_neq, content)
                answer = _re2.sub(r'\$([^$]*?)\\neq([^$]*?)\$', _fix_neq, answer)
                content = content.replace('$$', '')
                answer = answer.replace('$$', '')
                content = _re2.sub(r'\$\s*\$', '', content)
                answer = _re2.sub(r'\$\s*\$', '', answer)
                
                # 处理填空下划线：\_\_\_\_ → \underline{\qquad}
                content = content.replace('\\_\\_\\_\\_', r'\underline{\qquad}')
                content = content.replace('\\_\\_\\_', r'\underline{\qquad}')
                content = content.replace('\\_\\_', r'\underline{\qquad}')
                answer = answer.replace('\\_\\_\\_\\_', r'\underline{\qquad}')
                answer = answer.replace('\\_\\_\\_', r'\underline{\qquad}')
                answer = answer.replace('\\_\\_', r'\underline{\qquad}')
                
                # 处理AI输出的 \Pr\nolimits → \operatorname{Prj}
                content = _re2.sub(r'\\Pr\\nolimits', r'\\operatorname{Prj}', content)
                answer = _re2.sub(r'\\Pr\\nolimits', r'\\operatorname{Prj}', answer)
                content = _re2.sub(r'\\Prj(?=[^a-zA-Z])', r'\\operatorname{Prj}', content)
                answer = _re2.sub(r'\\Prj(?=[^a-zA-Z])', r'\\operatorname{Prj}', answer)
                content = _re2.sub(r'\\proj(?=[^a-zA-Z])', r'\\operatorname{proj}', content)
                answer = _re2.sub(r'\\proj(?=[^a-zA-Z])', r'\\operatorname{proj}', answer)
                
                # 后处理2：如果答案字母出现在括号中，移除
                if answer in ['A', 'B', 'C', 'D', '√', '×', '对', '错']:
                    content = _re2.sub(r'\(\s*' + _re2.escape(answer) + r'\s*\)', '(   )', content)
            
            # 后处理3：确保标签中包含题目类型
            type_tag = f'，{q_type}'
            if tags:
                if q_type not in tags.split('，'):
                    tags = tags + type_tag
            else:
                tags = type_tag.lstrip('，')
            
            # 剥离 AI 生成的题号
            content = strip_question_number(content)
            
            QuestionBank.objects.create(
                upload=upload,
                question_number=i + 1,
                content=content,
                answer=answer,
                tags=tags,
                question_type=q_type
            )
            upload.processed_questions = i + 1
            upload.save(update_fields=['processed_questions'])
        
        upload.processing_status = 'completed'
        upload.save(update_fields=['processing_status'])
    except Exception as e:
        try:
            from django.db import close_old_connections
            close_old_connections()
            upload = Upload.objects.get(id=upload_id)
            upload.processing_status = 'error'
            upload.processing_error = _sanitize_error(str(e))[:500]
            upload.save(update_fields=['processing_status', 'processing_error'])
        except:
            pass

@login_required
def upload_status(request, upload_id):
    try:
        upload_id = decrypt_id(upload_id)
        if upload_id is None:
            return JsonResponse({'success': False, 'message': '无效的文件ID'})
        upload = Upload.objects.get(id=upload_id, user=request.user)
        return JsonResponse({
            'success': True,
            'status': upload.processing_status,
            'total': upload.total_questions,
            'processed': upload.processed_questions,
            'error': upload.processing_error
        })
    except Upload.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文件不存在'})

@login_required
def delete_upload(request, upload_id):
    if request.method == 'POST':
        try:
            upload_id = decrypt_id(upload_id)
            if upload_id is None:
                return JsonResponse({'success': False, 'message': '无效的文件ID'})
            upload = Upload.objects.get(id=upload_id, user=request.user)
            # 删除文件
            if upload.file and upload.file.path:
                if os.path.exists(upload.file.path):
                    os.remove(upload.file.path)
            upload.delete()
            return JsonResponse({'success': True, 'message': '文件删除成功'})
        except Upload.DoesNotExist:
            return JsonResponse({'success': False, 'message': '文件不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def toggle_share(request, upload_id):
    if request.method == 'POST':
        try:
            upload_id = decrypt_id(upload_id)
            if upload_id is None:
                return JsonResponse({'success': False, 'message': '无效的文件ID'})
            upload = Upload.objects.get(id=upload_id, user=request.user)
            upload.is_shared = not upload.is_shared
            upload.save()
            return JsonResponse({'success': True, 'is_shared': upload.is_shared})
        except Upload.DoesNotExist:
            return JsonResponse({'success': False, 'message': '文件不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def edit_upload(request):
    if request.method == 'POST':
        try:
            upload_id = request.POST.get('upload_id')
            upload_id = decrypt_id(upload_id)
            if upload_id is None:
                return JsonResponse({'success': False, 'message': '无效的文件ID'})
            file_name = request.POST.get('file_name', '').strip()
            description = request.POST.get('description', '').strip()
            subject = request.POST.get('subject', '').strip()
            
            upload = Upload.objects.get(id=upload_id, user=request.user)
            upload.file_name = file_name
            upload.description = description
            upload.subject = subject
            upload.save()
            
            return JsonResponse({'success': True, 'message': '修改成功'})
        except Upload.DoesNotExist:
            return JsonResponse({'success': False, 'message': '文件不存在'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

def download_upload(request, upload_id):
    """下载文件（记录非上传者的下载次数）"""
    try:
        upload_id = decrypt_id(upload_id)
        if upload_id is None:
            return JsonResponse({'success': False, 'message': '无效的文件ID'})
        upload = Upload.objects.get(id=upload_id)
        from django.http import FileResponse
        file_path = upload.file.path
        if os.path.exists(file_path):
            is_owner = request.user.is_authenticated and request.user == upload.user
            if not is_owner:
                upload.download_count += 1
                upload.save(update_fields=['download_count'])
            response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=upload.file_name or os.path.basename(file_path))
            return response
        return JsonResponse({'success': False, 'message': '文件不存在'})
    except Upload.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文件不存在'})

@login_required
def get_favorite_items(request):
    uploads = Upload.objects.filter(favorited_by=request.user).order_by('-uploaded_at')
    questions = QuestionBank.objects.filter(favorited_by=request.user).select_related('upload').order_by('-id')
    
    uploads_data = [{
        'id': u.id,
        'name': u.file_name or u.file.name.replace('uploads/', ''),
        'description': u.description or '无描述',
        'subject': u.subject or '',
        'uploaded_at': u.uploaded_at.strftime('%Y-%m-%d %H:%M'),
        'file_url': u.file.url,
        'upload_user_id': u.user_id,
        'download_count': u.download_count,
    } for u in uploads]
    
    questions_data = [{
        'id': q.id,
        'content': re.sub(r'^\d+[.、]?\s*', '', q.content),
        'answer': q.answer,
        'tags': q.tags,
        'question_type': q.question_type
    } for q in questions]
    
    # 收集所有可用标签
    all_tags_set = set()
    for q in QuestionBank.objects.filter(upload__user=request.user).exclude(tags='').values_list('tags', flat=True):
        for tag in q.split('，'):
            tag = tag.strip()
            if tag:
                all_tags_set.add(tag)
    
    return JsonResponse({
        'success': True,
        'uploads': uploads_data,
        'questions': questions_data,
        'all_tags': sorted(all_tags_set),
        'question_types': ['全部', '单选题', '多选题', '填空题', '解答题', '判断题', '其他']
    })

@login_required
def search_favorite_questions(request):
    question_type = request.GET.get('question_type', '全部')
    search_mode = request.GET.get('search_mode', '全部')
    keyword = request.GET.get('keyword', '').strip()
    
    questions = QuestionBank.objects.filter(favorited_by=request.user).select_related('upload').order_by('-id')
    
    if question_type and question_type != '全部':
        questions = questions.filter(question_type=question_type)
    
    if keyword:
        if search_mode == '知识点':
            questions = questions.filter(tags__icontains=keyword)
        elif search_mode == '题目内容':
            questions = questions.filter(content__icontains=keyword)
        else:
            questions = questions.filter(content__icontains=keyword) | questions.filter(tags__icontains=keyword)
    
    questions_data = [{
        'id': q.id,
        'content': re.sub(r'^\d+[.、]?\s*', '', q.content),
        'answer': q.answer,
        'tags': q.tags,
        'question_type': q.question_type
    } for q in questions]
    
    return JsonResponse({'success': True, 'questions': questions_data})

@login_required
def toggle_file_favorite(request):
    if request.method == 'POST':
        try:
            upload_id = request.POST.get('upload_id')
            upload_id = decrypt_id(upload_id)
            if upload_id is None:
                return JsonResponse({'success': False, 'message': '无效的文件ID'})
            upload = Upload.objects.get(id=upload_id)
            if request.user in upload.favorited_by.all():
                upload.favorited_by.remove(request.user)
                is_fav = False
            else:
                upload.favorited_by.add(request.user)
                is_fav = True
            return JsonResponse({'success': True, 'is_favorited': is_fav, 'favorite_count': upload.favorited_by.count()})
        except Upload.DoesNotExist:
            return JsonResponse({'success': False, 'message': '文件不存在'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def toggle_favorite(request):
    if request.method == 'POST':
        try:
            question_id = request.POST.get('question_id')
            question = QuestionBank.objects.get(id=question_id)
            if request.user in question.favorited_by.all():
                question.favorited_by.remove(request.user)
                is_fav = False
            else:
                question.favorited_by.add(request.user)
                is_fav = True
            return JsonResponse({'success': True, 'is_favorited': is_fav})
        except QuestionBank.DoesNotExist:
            return JsonResponse({'success': False, 'message': '题目不存在'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def save_profile(request):
    if request.method == 'POST':
        try:
            # 更新用户名
            first_name = request.POST.get('firstName', '').strip()
            if first_name and first_name != request.user.username:
                if User.objects.filter(username=first_name).exclude(id=request.user.id).exists():
                    return JsonResponse({'success': False, 'message': '该昵称已被使用'})
                request.user.username = first_name
                request.user.save()
            
            # 更新学校
            school = request.POST.get('school', '').strip()
            profile, created = Profile.objects.get_or_create(user=request.user)
            profile.school = school
            # 更新AI模型
            ai_model = request.POST.get('ai_model', '').strip()
            if ai_model in dict(Profile.AI_MODEL_CHOICES):
                profile.ai_model = ai_model
            # 更新生日
            birthday = request.POST.get('birthday', '').strip()
            if birthday:
                from datetime import datetime
                profile.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()
            else:
                profile.birthday = None
            profile.save()
            
            return JsonResponse({'success': True, 'message': '保存成功'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})
    
def upload_like(request):
    if request.method == 'POST':
        upload_id = request.POST.get('upload_id')
        upload_id = decrypt_id(upload_id)
        if upload_id is None:
            return JsonResponse({'success': False, 'message': '无效的文件ID'})
        try:
            upload = Upload.objects.get(id=upload_id)
            like, created = UploadLike.objects.get_or_create(upload=upload, user=request.user)
            if not created:
                like.delete()
                return JsonResponse({'success': True, 'liked': False, 'count': UploadLike.objects.filter(upload=upload).count()})
            return JsonResponse({'success': True, 'liked': True, 'count': UploadLike.objects.filter(upload=upload).count()})
        except Upload.DoesNotExist:
            return JsonResponse({'success': False, 'message': '文件不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

def comment_page(request, upload_id):
    try:
        upload_id = decrypt_id(upload_id)
        if upload_id is None:
            return render(request, 'comment_page.html', {'upload': None})
        upload = Upload.objects.get(id=upload_id, is_shared=True)
        questions = QuestionBank.objects.filter(upload=upload).order_by('question_number')
        # 如果该上传属于某个文件夹，加载文件夹内所有文件用于文件列表展示
        folder_files = []
        if upload.folder_path:
            folder_filter = {
                'user': upload.user,
                'folder_path': upload.folder_path,
            }
            # 非上传者只能看已共享的
            if request.user != upload.user:
                folder_filter['is_shared'] = True
            folder_files = Upload.objects.filter(**folder_filter).order_by('uploaded_at')
        like_count = UploadLike.objects.filter(upload=upload).count()
        favorite_count = upload.favorited_by.count()
        is_favorited = request.user.is_authenticated and request.user in upload.favorited_by.all()
        favorited_question_ids = set()
        if request.user.is_authenticated:
            favorited_question_ids = set(QuestionBank.objects.filter(favorited_by=request.user, upload=upload).values_list('id', flat=True))
        comments = Comment.objects.filter(upload=upload, parent__isnull=True).order_by('-created_at')
        comments = sorted(comments, key=lambda c: c.score(), reverse=True)
        total_comments = Comment.objects.filter(upload=upload).count()
        
        user_comment_interactions = {}
        can_delete_comments = set()
        if request.user.is_authenticated:
            for ci in CommentInteraction.objects.filter(comment__upload=upload, user=request.user):
                user_comment_interactions[ci.comment_id] = ci.is_like
            # 可以删除的评论：自己发的或管理员
            if request.user.is_superuser:
                can_delete_comments = set(Comment.objects.filter(upload=upload).values_list('id', flat=True))
            else:
                can_delete_comments = set(Comment.objects.filter(upload=upload, user=request.user).values_list('id', flat=True))
        
        return render(request, 'comment_page.html', {
            'upload': upload,
            'folder_files': folder_files,
            'questions': questions,
            'comments': comments,
            'total_comments': total_comments,
            'like_count': like_count,
            'is_liked': request.user.is_authenticated and UploadLike.objects.filter(upload=upload, user=request.user).exists(),
            'favorite_count': favorite_count,
            'is_favorited': is_favorited,
            'favorited_question_ids': favorited_question_ids,
            'user_comment_interactions': user_comment_interactions,
            'can_delete_comments': can_delete_comments,
        })
    except Upload.DoesNotExist:
        return render(request, 'comment_page.html', {'upload': None})

@login_required
def add_comment(request):
    if request.method == 'POST':
        upload_id = request.POST.get('upload_id')
        post_id = request.POST.get('post_id')
        api_instance_id = request.POST.get('api_instance_id')
        content = request.POST.get('content', '').strip()
        parent_id = request.POST.get('parent_id')
        image = request.FILES.get('image')
        link_url = request.POST.get('link_url', '').strip()
        if not content:
            return JsonResponse({'success': False, 'message': '评论内容不能为空'})
        try:
            parent = None
            if parent_id:
                parent = Comment.objects.get(id=parent_id)
                parent.replies_count += 1
                parent.save()
            if upload_id:
                upload_id = decrypt_id(upload_id)
                if upload_id is None:
                    return JsonResponse({'success': False, 'message': '无效的文件ID'})
                upload = Upload.objects.get(id=upload_id)
                comment = Comment.objects.create(
                    upload=upload, user=request.user, parent=parent,
                    content=content, image=image, link_url=link_url
                )
            elif post_id:
                post_id = decrypt_id(post_id)
                if post_id is None:
                    return JsonResponse({'success': False, 'message': '无效的帖子ID'})
                post = Post.objects.get(id=post_id)
                comment = Comment.objects.create(
                    post=post, user=request.user, parent=parent,
                    content=content, image=image, link_url=link_url
                )
                post.comments_count = Comment.objects.filter(post=post).count()
                post.save()
            elif api_instance_id:
                api_inst = get_object_or_404(ApiInstance, id=api_instance_id)
                comment = Comment.objects.create(
                    api_instance=api_inst, user=request.user, parent=parent,
                    content=content, image=image, link_url=link_url
                )
            else:
                return JsonResponse({'success': False, 'message': '参数错误'})
            return JsonResponse({
                'success': True,
                'comment': {
                    'id': comment.id,
                    'username': comment.user.username,
                    'avatar_url': comment.user.profile.get_avatar_url() if hasattr(comment.user, 'profile') else '',
                    'content': comment.content,
                    'image_url': comment.image.url if comment.image else '',
                    'link_url': comment.link_url,
                    'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
                    'likes_count': comment.likes_count,
                    'dislikes_count': comment.dislikes_count,
                    'replies_count': comment.replies_count,
                    'parent_id': comment.parent_id,
                    'parent_username': parent.user.username if parent else None,
                    'can_delete': True,
                }
            })
        except (Upload.DoesNotExist, Post.DoesNotExist, Comment.DoesNotExist):
            return JsonResponse({'success': False, 'message': '参数错误'})
    return JsonResponse({'success': False, 'message': '无效请求'})

def get_post_comments(request, post_id):
    parent_id = request.GET.get('parent_id')
    try:
        post_id = decrypt_id(post_id)
        if post_id is None:
            return JsonResponse({'success': False, 'message': '无效的帖子ID'})
        post = Post.objects.get(id=post_id)
        if parent_id:
            comments = Comment.objects.filter(post=post, parent_id=parent_id).order_by('created_at')
        else:
            comments = Comment.objects.filter(post=post, parent__isnull=True)
            comments = sorted(comments, key=lambda c: c.score(), reverse=True)
        
        user_interactions = {}
        if request.user.is_authenticated:
            for ci in CommentInteraction.objects.filter(comment__in=comments, user=request.user):
                user_interactions[ci.comment_id] = ci.is_like
        
        comments_data = []
        for c in comments:
            replies = Comment.objects.filter(parent=c).order_by('created_at')
            replies_data = []
            for r in replies:
                can_del = request.user.is_authenticated and (request.user.is_superuser or r.user == request.user)
                parent_username = r.parent.user.username if r.parent else None
                replies_data.append({
                    'id': r.id,
                    'user_id': r.user.id,
                    'encrypted_user_id': encrypt_id(r.user.id),
                    'username': r.user.username,
                    'avatar_url': r.user.profile.get_avatar_url() if hasattr(r.user, 'profile') else '',
                    'content': r.content,
                    'image_url': r.image.url if r.image else '',
                    'link_url': r.link_url,
                    'created_at': r.created_at.strftime('%Y-%m-%d %H:%M'),
                    'likes_count': r.likes_count,
                    'dislikes_count': r.dislikes_count,
                    'replies_count': r.replies_count,
                    'parent_id': r.parent_id,
                    'parent_username': parent_username,
                    'is_liked': user_interactions.get(r.id),
                    'can_delete': can_del,
                })
            
            can_del = request.user.is_authenticated and (request.user.is_superuser or c.user == request.user)
            comments_data.append({
                'id': c.id,
                'user_id': c.user.id,
                'encrypted_user_id': encrypt_id(c.user.id),
                'username': c.user.username,
                'avatar_url': c.user.profile.get_avatar_url() if hasattr(c.user, 'profile') else '',
                'content': c.content,
                'image_url': c.image.url if c.image else '',
                'link_url': c.link_url,
                'created_at': c.created_at.strftime('%Y-%m-%d %H:%M'),
                'likes_count': c.likes_count,
                'dislikes_count': c.dislikes_count,
                'replies_count': c.replies_count,
                'parent_id': c.parent_id,
                'is_liked': user_interactions.get(c.id),
                'can_delete': can_del,
                'replies': replies_data,
            })
        
        return JsonResponse({'success': True, 'comments': comments_data})
    except Post.DoesNotExist:
        return JsonResponse({'success': False, 'message': '帖子不存在'})

def get_comments(request, upload_id):
    parent_id = request.GET.get('parent_id')
    try:
        upload_id = decrypt_id(upload_id)
        if upload_id is None:
            return JsonResponse({'success': False, 'message': '无效的文件ID'})
        upload = Upload.objects.get(id=upload_id)
        if parent_id:
            comments = Comment.objects.filter(upload=upload, parent_id=parent_id).order_by('created_at')
        else:
            comments = Comment.objects.filter(upload=upload, parent__isnull=True)
            comments = sorted(comments, key=lambda c: c.score(), reverse=True)
        
        user_interactions = {}
        if request.user.is_authenticated:
            for ci in CommentInteraction.objects.filter(comment__in=comments, user=request.user):
                user_interactions[ci.comment_id] = ci.is_like
        
        comments_data = []
        for c in comments:
            replies = Comment.objects.filter(parent=c).order_by('created_at')
            replies_data = []
            for r in replies:
                can_del = request.user.is_authenticated and (request.user.is_superuser or r.user == request.user)
                parent_username = r.parent.user.username if r.parent else None
                replies_data.append({
                    'id': r.id,
                    'user_id': r.user.id,
                    'encrypted_user_id': encrypt_id(r.user.id),
                    'username': r.user.username,
                    'avatar_url': r.user.profile.get_avatar_url() if hasattr(r.user, 'profile') else '',
                    'content': r.content,
                    'image_url': r.image.url if r.image else '',
                    'link_url': r.link_url,
                    'created_at': r.created_at.strftime('%Y-%m-%d %H:%M'),
                    'likes_count': r.likes_count,
                    'dislikes_count': r.dislikes_count,
                    'replies_count': r.replies_count,
                    'parent_id': r.parent_id,
                    'parent_username': parent_username,
                    'is_liked': user_interactions.get(r.id),
                    'can_delete': can_del,
                })
            
            can_del = request.user.is_authenticated and (request.user.is_superuser or c.user == request.user)
            comments_data.append({
                'id': c.id,
                'user_id': c.user.id,
                'encrypted_user_id': encrypt_id(c.user.id),
                'username': c.user.username,
                'avatar_url': c.user.profile.get_avatar_url() if hasattr(c.user, 'profile') else '',
                'content': c.content,
                'image_url': c.image.url if c.image else '',
                'link_url': c.link_url,
                'created_at': c.created_at.strftime('%Y-%m-%d %H:%M'),
                'likes_count': c.likes_count,
                'dislikes_count': c.dislikes_count,
                'replies_count': c.replies_count,
                'parent_id': c.parent_id,
                'is_liked': user_interactions.get(c.id),
                'can_delete': can_del,
                'replies': replies_data,
            })
        
        return JsonResponse({'success': True, 'comments': comments_data})
    except Upload.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文件不存在'})

@login_required
def comment_interact(request):
    if request.method == 'POST':
        comment_id = request.POST.get('comment_id')
        action = request.POST.get('action')
        if action not in ('like', 'dislike'):
            return JsonResponse({'success': False, 'message': '无效操作'})
        try:
            comment = Comment.objects.get(id=comment_id)
            existing = CommentInteraction.objects.filter(comment=comment, user=request.user).first()
            is_like = (action == 'like')
            if existing:
                if existing.is_like == is_like:
                    existing.delete()
                    if is_like:
                        comment.likes_count -= 1
                    else:
                        comment.dislikes_count -= 1
                    comment.save()
                    return JsonResponse({
                        'success': True,
                        'action': 'none',
                        'likes_count': comment.likes_count,
                        'dislikes_count': comment.dislikes_count,
                    })
                else:
                    if existing.is_like:
                        comment.likes_count -= 1
                        comment.dislikes_count += 1
                    else:
                        comment.dislikes_count -= 1
                        comment.likes_count += 1
                    existing.is_like = is_like
                    existing.save()
                    comment.save()
                    return JsonResponse({
                        'success': True,
                        'action': action,
                        'likes_count': comment.likes_count,
                        'dislikes_count': comment.dislikes_count,
                    })
            else:
                CommentInteraction.objects.create(comment=comment, user=request.user, is_like=is_like)
                if is_like:
                    comment.likes_count += 1
                else:
                    comment.dislikes_count += 1
                comment.save()
                return JsonResponse({
                    'success': True,
                    'action': action,
                    'likes_count': comment.likes_count,
                    'dislikes_count': comment.dislikes_count,
                })
        except Comment.DoesNotExist:
            return JsonResponse({'success': False, 'message': '评论不存在'})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def delete_comment(request):
    if request.method == 'POST':
        import json
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            comment_id = data.get('comment_id')
        else:
            comment_id = request.POST.get('comment_id')
        try:
            comment = Comment.objects.get(id=comment_id)
            # 只有评论者或管理员才能删除
            if not (request.user.is_superuser or comment.user == request.user):
                return JsonResponse({'success': False, 'message': '无权删除该评论'})
            
            # 如果是回复，减少父评论的回复数
            if comment.parent:
                comment.parent.replies_count = max(0, comment.parent.replies_count - 1)
                comment.parent.save()
            
            comment.delete()
            return JsonResponse({'success': True, 'message': '删除成功'})
        except Comment.DoesNotExist:
            return JsonResponse({'success': False, 'message': '评论不存在'})

@login_required
def rename_folder(request):
    """重命名文件夹（包括子文件夹）"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            old_name = str(data.get('old_name', '')).strip()
            new_name = str(data.get('new_name', '')).strip()
            
            if not old_name or not new_name:
                return JsonResponse({'success': False, 'message': '文件夹名称不能为空'})
            
            # 更新该文件夹及所有子文件夹下文件的folder_path
            from django.db.models import Q
            all_uploads = Upload.objects.filter(
                Q(user=request.user) & (Q(folder_path=old_name) | Q(folder_path__startswith=old_name + '/'))
            )
            all_uploads_list = list(all_uploads)
            if not all_uploads_list:
                return JsonResponse({'success': False, 'message': '文件夹不存在'})
            
            # 检查新名称是否已存在
            if Upload.objects.filter(user=request.user, folder_path=new_name).exists():
                return JsonResponse({'success': False, 'message': '文件夹名称已存在'})
            
            # 更新文件系统中的文件夹名称
            old_folder_path = os.path.join(settings.MEDIA_ROOT, 'uploads', old_name)
            new_folder_path = os.path.join(settings.MEDIA_ROOT, 'uploads', new_name)
            if os.path.exists(old_folder_path):
                os.rename(old_folder_path, new_folder_path)
            
            # 更新数据库记录
            for upload in all_uploads_list:
                if upload.folder_path == old_name:
                    upload.folder_path = new_name
                elif upload.folder_path.startswith(old_name + '/'):
                    upload.folder_path = new_name + '/' + upload.folder_path[len(old_name)+1:]
                upload.save()
            
            return JsonResponse({'success': True, 'message': '文件夹重命名成功'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def download_folder(request):
    """下载文件夹（打包成zip，包括子文件夹中的文件）"""
    if request.method == 'POST':
        try:
            import zipfile
            from io import BytesIO
            
            data = json.loads(request.body)
            folder_name = str(data.get('folder_name', '')).strip()
            
            if not folder_name:
                return JsonResponse({'success': False, 'message': '文件夹名称不能为空'})
            
            from django.db.models import Q
            # 获取该文件夹及所有子文件夹下的所有文件
            all_uploads = Upload.objects.filter(
                (Q(user=request.user) | (Q(is_shared=True))) & (Q(folder_path=folder_name) | Q(folder_path__startswith=folder_name + '/'))
            )
            if not all_uploads:
                return JsonResponse({'success': False, 'message': '文件夹不存在'})
            
            # 创建zip文件
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for upload in all_uploads:
                    if upload.file and upload.file.path:
                        file_path = upload.file.path
                        if os.path.exists(file_path):
                            # 保留子文件夹结构
                            if upload.folder_path and upload.folder_path != folder_name:
                                # 子文件夹中的文件：folder_name/子文件夹/文件名
                                relative_path = upload.folder_path.replace(folder_name + '/', '', 1) + '/' + os.path.basename(file_path)
                            else:
                                # 直接在该文件夹下的文件
                                relative_path = os.path.basename(file_path)
                            zip_file.write(file_path, relative_path)
            
            zip_buffer.seek(0)
            
            from django.http import HttpResponse
            response = HttpResponse(zip_buffer, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{folder_name}.zip"'
            return response
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def delete_folder(request):
    """删除文件夹及其所有内容（包括子文件夹）"""
    if request.method == 'POST':
        try:
            # 支持JSON和表单数据
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                folder_name = str(data.get('folder_name', '')).strip()
            else:
                folder_name = request.POST.get('folder_name', '').strip()
            
            if not folder_name:
                return JsonResponse({'success': False, 'message': '文件夹名称不能为空'})
            
            from django.db.models import Q
            # 获取该文件夹及所有子文件夹下的所有文件
            all_uploads = Upload.objects.filter(
                Q(folder_path=folder_name) | Q(folder_path__startswith=folder_name + '/')
            )
            if not all_uploads:
                return JsonResponse({'success': False, 'message': '文件夹不存在'})
            
            # 删除文件系统中的文件
            for upload in all_uploads:
                if upload.file and upload.file.path:
                    file_path = upload.file.path
                    if os.path.exists(file_path):
                        os.remove(file_path)
            
            # 删除数据库记录
            all_uploads.delete()
            
            # 删除空文件夹
            folder_path = os.path.join(settings.MEDIA_ROOT, 'uploads', folder_name)
            if os.path.exists(folder_path):
                try:
                    os.rmdir(folder_path)
                except OSError:
                    pass  # 文件夹不为空，可能有其他文件
            
            return JsonResponse({'success': True, 'message': '文件夹删除成功'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def toggle_folder_share(request):
    """切换文件夹共享状态（共享/取消共享文件夹下所有文件及子文件夹中的文件）"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            folder_name = str(data.get('folder_name', '')).strip()
            
            if not folder_name:
                return JsonResponse({'success': False, 'message': '文件夹名称不能为空'})
            
            # 获取该文件夹及所有子文件夹下的所有文件（不限共享状态）
            from django.db.models import Q
            all_uploads = Upload.objects.filter(
                Q(folder_path=folder_name) | Q(folder_path__startswith=folder_name + '/')
            )
            if not all_uploads.exists():
                return JsonResponse({'success': False, 'message': '文件夹不存在'})
            
            # 检查当前共享状态：如果所有文件都已共享，则取消共享；否则共享所有文件
            all_shared = all(u.is_shared for u in all_uploads)
            new_shared_status = not all_shared
            
            # 更新所有文件（包括子文件夹中的文件）的共享状态
            all_uploads.update(is_shared=new_shared_status)
            
            return JsonResponse({'success': True, 'is_shared': new_shared_status})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def toggle_folder_favorite(request):
    """切换文件夹收藏状态（收藏/取消收藏文件夹下所有文件及子文件夹中的文件）"""
    if request.method == 'POST':
        try:
            # 支持JSON和表单数据
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                folder_name = str(data.get('folder_name', '')).strip()
            else:
                folder_name = request.POST.get('folder_name', '').strip()
            
            if not folder_name:
                return JsonResponse({'success': False, 'message': '文件夹名称不能为空'})
            
            # 获取该文件夹及所有子文件夹下的所有文件（不限共享状态）
            from django.db.models import Q
            all_uploads = Upload.objects.filter(
                Q(folder_path=folder_name) | Q(folder_path__startswith=folder_name + '/')
            )
            all_uploads_list = list(all_uploads)
            if not all_uploads_list:
                return JsonResponse({'success': False, 'message': '文件夹不存在'})
            
            # 检查当前收藏状态（以第一个文件为准）
            first_upload = all_uploads_list[0]
            is_current_favorited = request.user in first_upload.favorited_by.all()
            new_favorite_status = not is_current_favorited
            
            # 更新所有文件（包括子文件夹中的文件）的收藏状态
            if new_favorite_status:
                for upload in all_uploads_list:
                    upload.favorited_by.add(request.user)
            else:
                for upload in all_uploads_list:
                    upload.favorited_by.remove(request.user)
            
            # 计算收藏数：收藏了文件夹下所有文件的用户数
            fav_count = 0
            user_id_sets = [set(u.favorited_by.values_list('id', flat=True)) for u in all_uploads_list]
            if user_id_sets:
                common_user_ids = set.intersection(*user_id_sets)
                fav_count = len(common_user_ids)
            
            return JsonResponse({'success': True, 'is_favorited': new_favorite_status, 'favorite_count': fav_count})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': '无效请求'})

@login_required
def browse_folder(request, folder_path=None):
    """浏览文件夹内容，支持嵌套文件夹"""
    # 获取当前路径
    current_path = folder_path or ''
    
    # 获取用户ID参数（用于查看其他用户的共享文件夹）
    owner_id = request.GET.get('owner_id', '')
    if owner_id:
        from django.contrib.auth.models import User
        owner_id_decrypted = decrypt_id(owner_id)
        if owner_id_decrypted:
            owner = User.objects.get(id=owner_id_decrypted)
            # 查看其他用户时，只显示已共享的文件
            is_owner = (owner == request.user)
        else:
            owner = request.user
            is_owner = True
    else:
        owner = request.user
        is_owner = True
    
    # 获取当前文件夹下的所有文件
    base_filter = {'user': owner}
    if not is_owner:
        base_filter['is_shared'] = True
    
    if current_path:
        uploads = Upload.objects.filter(**base_filter, folder_path=current_path)
    else:
        base_filter['folder_path'] = ''
        uploads = Upload.objects.filter(**base_filter)
    
    # 获取当前文件夹下的子文件夹
    if current_path:
        all_folder_paths = Upload.objects.filter(
            user=owner,
            folder_path__startswith=current_path + '/',
            **({} if is_owner else {'is_shared': True})
        ).values_list('folder_path', flat=True).distinct()
        
        subfolders = set()
        for fp in all_folder_paths:
            if fp.startswith(current_path + '/'):
                remaining = fp[len(current_path) + 1:]
                if '/' in remaining:
                    subfolder = remaining.split('/')[0]
                    subfolders.add(current_path + '/' + subfolder)
                else:
                    subfolders.add(fp)
    else:
        all_folder_paths = Upload.objects.filter(
            user=owner,
            folder_path__isnull=False
        ).exclude(
            folder_path=''
        ).values_list('folder_path', flat=True).distinct()
        
        subfolders = set()
        for fp in all_folder_paths:
            top = fp.split('/')[0]
            subfolders.add(top)
    
    # 创建文件夹项列表
    folder_items = []
    for folder in subfolders:
        folder_filter = {'user': owner, 'folder_path': folder}
        if not is_owner:
            folder_filter['is_shared'] = True
        folder_uploads = Upload.objects.filter(**folder_filter)
        if folder_uploads.exists():
            first_upload = folder_uploads.first()
            folder_items.append({
                'type': 'folder',
                'folder': folder,
                'display_name': folder.split('/')[-1] if folder else '',
                'file_count': folder_uploads.count(),
                'is_shared': first_upload.is_shared,
                'user_id': owner.id,
            })
    
    # 创建文件项列表
    file_items = []
    for upload in uploads:
        file_items.append({
            'type': 'file',
            'upload': upload,
            'display_name': upload.file_name or upload.file.name.split('/')[-1],
        })
    
    # 混合文件夹和文件，按名称排序（文件夹优先）
    all_items = []
    for item in folder_items:
        all_items.append({
            'type': 'folder',
            'name': item['display_name'].lower(),
            'data': item
        })
    for item in file_items:
        all_items.append({
            'type': 'file',
            'name': item['display_name'].lower(),
            'data': item
        })
    
    # 排序：文件夹优先，然后按名称排序
    all_items.sort(key=lambda x: (0 if x['type'] == 'folder' else 1, x['name']))
    
    # 获取面包屑路径
    breadcrumbs = []
    if current_path:
        parts = current_path.split('/')
        current_breadcrumb = ''
        for i, part in enumerate(parts):
            if i == 0:
                current_breadcrumb = part
            else:
                current_breadcrumb += '/' + part
            breadcrumbs.append({
                'name': part,
                'path': current_breadcrumb
            })
    
    # 获取收藏的文件ID（仅当用户已登录）
    favorite_upload_ids = []
    if request.user.is_authenticated and is_owner:
        favorite_upload_ids = list(request.user.favorite_uploads.values_list('id', flat=True))
    
    # 构建owner_id的加密形式供模板使用
    owner_id_encrypted = encrypt_id(owner.id) if owner.id != request.user.id else ''
    
    # 获取所有学科列表（与个人中心同步）
    default_subjects = ['程序设计(C)', '程序设计(C++)', '程序设计(Java)', '程序设计(Python)', '思想道德与法治', '心理健康与职业发展', '高等数学', '大学物理', '离散数学', '通用英语', '中国近代史纲要', '数学文化']
    user_subjects = list(Upload.objects.exclude(subject='').values_list('subject', flat=True).distinct())
    all_subjects = []
    seen = set()
    for subj in default_subjects:
        if subj not in seen:
            all_subjects.append(subj)
            seen.add(subj)
    for subj in user_subjects:
        if subj not in seen:
            all_subjects.append(subj)
            seen.add(subj)
    
    return render(request, 'browse_folder.html', {
        'all_items': all_items,
        'current_path': current_path,
        'breadcrumbs': breadcrumbs,
        'favorite_upload_ids': favorite_upload_ids,
        'is_owner': is_owner,
        'owner_id': owner_id,
        'owner_id_encrypted': owner_id_encrypted,
        'all_subjects': all_subjects,
    })


def get_model_configs(request):
    configs = UserModelConfig.objects.filter(user=request.user).order_by('-id')
    data = []
    for c in configs:
        data.append({
            'id': c.id,
            'api_format': c.api_format,
            'request_url': c.request_url,
            'model_id': c.model_id,
            'api_key_mask': 'sk-······',
            'is_enabled': c.is_enabled,
        })
    return JsonResponse({'success': True, 'configs': data})


def save_model_config(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})

    api_format = request.POST.get('api_format', '').strip()
    request_url = request.POST.get('request_url', '').strip()
    model_id = request.POST.get('model_id', '').strip()
    api_key = request.POST.get('api_key', '').strip()
    is_enabled = request.POST.get('is_enabled') == '1'

    if not all([api_format, request_url, model_id, api_key]):
        return JsonResponse({'success': False, 'message': '所有字段均为必填'})

    if is_enabled:
        UserModelConfig.objects.filter(user=request.user, is_enabled=True).update(is_enabled=False)
    config = UserModelConfig.objects.create(
        user=request.user,
        api_format=api_format,
        request_url=request_url,
        model_id=model_id,
        api_key=api_key,
        is_enabled=is_enabled,
    )

    return JsonResponse({'success': True, 'message': '保存成功'})


def delete_model_config(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    try:
        config_id = request.POST.get('id', '').strip()
        UserModelConfig.objects.get(id=config_id, user=request.user).delete()
        return JsonResponse({'success': True, 'message': '删除成功'})
    except UserModelConfig.DoesNotExist:
        return JsonResponse({'success': False, 'message': '配置不存在'})


def toggle_model_config(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    try:
        config_id = request.POST.get('id', '').strip()
        config = UserModelConfig.objects.get(id=config_id, user=request.user)
        if config.is_enabled:
            config.is_enabled = False
        else:
            UserModelConfig.objects.filter(user=request.user, is_enabled=True).update(is_enabled=False)
            config.is_enabled = True
        config.save()
        return JsonResponse({'success': True, 'message': '操作成功'})
    except UserModelConfig.DoesNotExist:
        return JsonResponse({'success': False, 'message': '配置不存在'})


@login_required
def model_config_page(request):
    return render(request, 'model_config.html')


@login_required
def model_config_add(request):
    return render(request, 'model_config_form.html', {'title': '添加模型配置'})


# ========== 题单 & 自测功能 ==========

@login_required
def my_question_lists(request):
    """我的题单页面"""
    from django.db.models import Count
    lists = QuestionList.objects.filter(user=request.user).annotate(
        question_count=Count('items')
    ).order_by('-updated_at')
    response = render(request, 'my_question_lists.html', {
        'question_lists': lists,
    })
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@login_required
def create_question_list(request):
    """AJAX 创建题单"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    if not title:
        return JsonResponse({'success': False, 'message': '题单名称不能为空'})
    ql = QuestionList.objects.create(user=request.user, title=title, description=description)
    return JsonResponse({'success': True, 'question_list': {'id': ql.id, 'title': ql.title}})


@login_required
def get_question_lists(request):
    """AJAX 获取用户的题单列表"""
    lists = QuestionList.objects.filter(user=request.user).order_by('-updated_at')
    data = [{'id': ql.id, 'title': ql.title, 'count': ql.items.count()} for ql in lists]
    return JsonResponse({'success': True, 'lists': data})


@login_required
def add_to_question_list(request):
    """AJAX 将题目加入题单"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    list_id = data.get('list_id')
    question_ids = data.get('question_ids', [])
    if not list_id or not question_ids:
        return JsonResponse({'success': False, 'message': '参数错误'})
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
    except QuestionList.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题单不存在'})
    added = 0
    for qid in question_ids:
        try:
            q = QuestionBank.objects.get(id=qid)
            _, created = QuestionListItem.objects.get_or_create(question_list=ql, question=q)
            if created:
                added += 1
        except QuestionBank.DoesNotExist:
            continue
    return JsonResponse({'success': True, 'added': added})


@login_required
def question_ai_chat(request, question_id):
    """AI 解析对话页面"""
    from app1.models import QuestionBank, UserModelConfig, QuestionAIChat
    try:
        q = QuestionBank.objects.get(id=question_id)
    except QuestionBank.DoesNotExist:
        return redirect('my')
    # 检查是否有启用的模型配置
    config = UserModelConfig.objects.filter(user=request.user, is_enabled=True).first()
    has_config = config is not None
    # 获取历史对话记录
    chat_history = QuestionAIChat.objects.filter(user=request.user, question=q).order_by('created_at')
    # 记录来源页面，供返回按钮使用
    referer = request.META.get('HTTP_REFERER', '')
    return render(request, 'question_ai_chat.html', {
        'q': q,
        'has_config': has_config,
        'chat_history': chat_history,
        'referer': referer,
    })


def _is_inside_math(text, pos):
    """检查位置 pos 是否已在数学定界符（$$ $ \( \[）内"""
    if not text or pos <= 0:
        return False
    inside = False
    i = 0
    while i < pos:
        if text[i] == '$':
            # $$（双美元）统一切换一次
            if i + 1 < len(text) and text[i+1] == '$':
                inside = not inside
                i += 2
                continue
            inside = not inside
            i += 1
        elif text[i] == '\\' and i + 1 < pos:
            if text[i+1] == '(' or text[i+1] == '[':
                inside = True
                i += 2
                continue
            elif text[i+1] == ')' or text[i+1] == ']':
                inside = False
                i += 2
                continue
            i += 1
        else:
            i += 1
    return inside


def _wrap_standalone_latex(text):
    """将游离的 LaTeX \begin{...} 环境用 $$ 包裹，将 \boxed{...} 用 $ 包裹"""
    import re
    if not text:
        return text
    # 修正 array 等表格环境中缺少的 \\ 换行符
    def fix_array_lines(m):
        block = m.group(0)
        inner = m.group(1)
        lines = inner.split('\n')
        fixed = []
        for line in lines:
            stripped = line.strip()
            if (stripped == '' or '\\\\' in line or
                stripped.startswith('\\begin') or stripped.startswith('\\end') or
                stripped.startswith('\\hline') or stripped.endswith('\\hline')):
                fixed.append(line)
            else:
                fixed.append(line.rstrip() + ' \\\\')
        # m.start()/end() are absolute positions — convert to relative
        rel_start = m.start(1) - m.start(0)
        rel_end = m.end(1) - m.start(0)
        return block[:rel_start] + '\n'.join(fixed) + block[rel_end:]
    text = re.sub(r'\\begin\{array\}\{[^}]*\}(.*?)\\end\{array\}', fix_array_lines, text, flags=re.DOTALL)
    # 将 [ ... ] 显示公式转为 $$ ... $$（多行和单行）
    text = re.sub(r'^\[\s*\n([\s\S]*?)\n\s*\]$', r'$$\n\1\n$$', text, flags=re.MULTILINE)
    text = re.sub(r'^\[\s*([^\n]+?)\s*\]$', r'$$\1$$', text, flags=re.MULTILINE)
    # 包裹 \begin{...}...\end{...}（检查是否已在数学定界符内）
    def replace_begin(m):
        full = m.group(0)
        if _is_inside_math(text, m.start()):
            return full
        return '$$\n' + full + '\n$$'
    text = re.sub(r'\\begin\{[^}]*\}.*?\\end\{[^}]*\}', replace_begin, text, flags=re.DOTALL)
    # 包裹 \boxed{...}（支持嵌套大括号，检查是否已在数学定界符内）
    result = []
    i = 0
    while i < len(text):
        idx = text.find('\\boxed{', i)
        if idx == -1:
            result.append(text[i:])
            break
        result.append(text[i:idx])
        depth = 1
        j = idx + 7
        while j < len(text) and depth > 0:
            if text[j] == '{': depth += 1
            elif text[j] == '}': depth -= 1
            j += 1
        if _is_inside_math(text, idx):
            result.append(text[idx:j])
        else:
            result.append('$' + text[idx:j] + '$')
        i = j
    text = ''.join(result)
    return text


@login_required
def question_ai_ask(request):
    """AJAX: 向 AI 发送消息进行解析/对话"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json, requests as _requests
    data = json.loads(request.body)
    question_id = data.get('question_id')
    user_message = data.get('message', '').strip()
    if not question_id:
        return JsonResponse({'success': False, 'message': '缺少参数'})
    from app1.models import QuestionBank, UserModelConfig, QuestionAIChat
    try:
        q = QuestionBank.objects.get(id=question_id)
    except QuestionBank.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题目不存在'})
    # 获取用户启用的模型配置
    config = UserModelConfig.objects.filter(user=request.user, is_enabled=True).first()
    if not config:
        return JsonResponse({'success': False, 'message': '请先在 设置→模型配置 中添加并启用一个 AI 模型'})

    # 保存用户消息（如果有）
    if user_message:
        QuestionAIChat.objects.create(user=request.user, question=q, role='user', content=_wrap_standalone_latex(user_message))

    # 构建 system prompt
    if not user_message:
        system_prompt = '你是一个专业的数学解题分析助手。请用中文对下面的题目进行详细解析，包括：1）解题思路分析；2）关键步骤推导；3）最终答案确认。要求使用 LaTeX 数学公式（$$ 或 $ 包裹）进行表达，解析要详细透彻。'
        user_prompt = f'题目：\n{q.content}\n\n答案：\n{q.answer}\n\n请给出详细的解析过程。'
    else:
        system_prompt = '你是一个专业的数学解题分析助手，正在与用户讨论一道数学题。请使用 LaTeX 公式表达数学内容，用中文回答。'
        context_parts = [f'题目：{q.content}']
        if q.answer:
            context_parts.append(f'答案：{q.answer}')
        history = QuestionAIChat.objects.filter(user=request.user, question=q).order_by('created_at')
        history_lines = []
        for msg in history:
            role_name = '用户' if msg.role == 'user' else 'AI'
            history_lines.append(f'{role_name}：{msg.content}')
        if history_lines:
            context_parts.append('对话历史：\n' + '\n'.join(history_lines))
        user_prompt = '\n\n'.join(context_parts)

    headers = {'Content-Type': 'application/json'}
    if config.api_format == 'openai':
        headers['Authorization'] = f'Bearer {config.api_key}'
        payload = {
            'model': config.model_id,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'temperature': 0.3,
            'max_tokens': 8192,
        }
    elif config.api_format == 'anthropic':
        headers['x-api-key'] = config.api_key
        headers['anthropic-version'] = '2023-06-01'
        payload = {
            'model': config.model_id,
            'max_tokens': 8192,
            'messages': [{'role': 'user', 'content': user_prompt}],
        }
    else:
        return JsonResponse({'success': False, 'message': f'不支持的API格式: {config.api_format}'})

    base = config.request_url.rstrip('/')
    if config.api_format == 'openai':
        url = base + '/v1/chat/completions' if not base.endswith('/v1/chat/completions') else base
    elif config.api_format == 'anthropic':
        url = base + '/v1/messages' if not base.endswith('/v1/messages') else base
    else:
        url = base

    try:
        resp = _requests.post(url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        result = resp.json()
        if config.api_format == 'openai':
            content = result['choices'][0]['message'].get('content', '')
        elif config.api_format == 'anthropic':
            content = result['content'][0]['text']
        else:
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        # 预处理游离的 LaTeX
        content = _wrap_standalone_latex(content)
        # 保存 AI 回复
        ai_msg = QuestionAIChat.objects.create(user=request.user, question=q, role='ai', content=content)
        return JsonResponse({'success': True, 'raw_content': content, 'msg_id': ai_msg.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'AI 请求失败: {_sanitize_error(str(e))}'})


@login_required
def ai_chat_delete_message(request):
    """AJAX: 删除单条对话记录"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    msg_id = data.get('msg_id')
    if not msg_id:
        return JsonResponse({'success': False, 'message': '缺少参数'})
    from app1.models import QuestionAIChat
    try:
        msg = QuestionAIChat.objects.get(id=msg_id, user=request.user)
        msg.delete()
        return JsonResponse({'success': True})
    except QuestionAIChat.DoesNotExist:
        return JsonResponse({'success': False, 'message': '消息不存在'})


@login_required
def remove_from_question_list(request):
    """AJAX 从题单移除题目"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    list_id = data.get('list_id')
    question_id = data.get('question_id')
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
        QuestionListItem.objects.filter(question_list=ql, question_id=question_id).delete()
        return JsonResponse({'success': True})
    except QuestionList.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题单不存在'})


@login_required
def edit_question_list(request):
    """AJAX 编辑题单"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    list_id = data.get('list_id')
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    if not title:
        return JsonResponse({'success': False, 'message': '题单名称不能为空'})
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
        ql.title = title
        ql.description = description
        ql.save()
        return JsonResponse({'success': True})
    except QuestionList.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题单不存在'})


@login_required
def delete_question_list(request):
    """AJAX 删除题单"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    list_id = data.get('list_id')
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
        ql.delete()
        return JsonResponse({'success': True})
    except QuestionList.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题单不存在'})


@login_required
def preview_question_list(request, list_id):
    """预览题单"""
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
    except QuestionList.DoesNotExist:
        return redirect('my_question_lists')
    items = ql.items.select_related('question').order_by('id')
    questions = [item.question for item in items]
    resp = render(request, 'preview_question_list.html', {
        'question_list': ql,
        'questions': questions,
    })
    resp['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp['Pragma'] = 'no-cache'
    resp['Expires'] = '0'
    return resp


@login_required
def start_self_test(request, list_id):
    """开始自测"""
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
    except QuestionList.DoesNotExist:
        return redirect('my_question_lists')
    items = list(ql.items.select_related('question').order_by('id'))
    if not items:
        return redirect('my_question_lists')
    questions = [item.question for item in items]
    return render(request, 'self_test.html', {
        'question_list': ql,
        'questions': questions,
    })


@login_required
def submit_self_test(request):
    """提交自测结果"""
    if request.method != 'POST':
        return redirect('my_question_lists')
    import json
    data = json.loads(request.body)
    list_id = data.get('list_id')
    answers = data.get('answers', [])
    total_time = data.get('total_time', 0)
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
    except QuestionList.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题单不存在'})
    result = TestResult.objects.create(
        user=request.user,
        question_list=ql,
        total_questions=len(answers),
        total_time=total_time,
    )
    correct = 0
    wrong = 0
    half = 0
    for idx, ans in enumerate(answers):
        qid = ans.get('question_id')
        status = ans.get('status', 'wrong')
        user_answer = ans.get('user_answer', '')
        time_spent = ans.get('time_spent', 0)
        try:
            q = QuestionBank.objects.get(id=qid)
        except QuestionBank.DoesNotExist:
            continue
        # 选择题：自动评测
        if q.question_type in ('单选题', '多选题'):
            # 去除答案中的空格和分隔符后比较
            clean_user = user_answer.strip().replace(' ', '').replace('，', ',').replace('、', ',')
            clean_answer = q.answer.strip().replace(' ', '').replace('，', ',').replace('、', ',')
            status = 'correct' if clean_user == clean_answer else 'wrong'
        TestResultItem.objects.create(
            test_result=result,
            question=q,
            sort_order=idx,
            status=status,
            user_answer=user_answer,
            time_spent=time_spent,
        )
        if status == 'correct':
            correct += 1
        elif status == 'half':
            half += 1
        else:
            wrong += 1
    result.correct_count = correct
    result.wrong_count = wrong
    result.half_count = half
    result.save()
    return JsonResponse({'success': True, 'result_id': result.id})


@login_required
def test_result(request, result_id):
    """查看自测结果"""
    try:
        result = TestResult.objects.get(id=result_id, user=request.user)
    except TestResult.DoesNotExist:
        return redirect('my_question_lists')
    items = result.items.select_related('question').order_by('sort_order')
    question_data = []
    for item in items:
        q = item.question
        from app1.utils import encrypt_id
        upload_id_enc = encrypt_id(q.upload_id) if q.upload_id else ''
        question_data.append({
            'id': q.id,
            'sort_order': item.sort_order,
            'content': q.content,
            'answer': q.answer,
            'question_type': q.question_type,
            'status': item.status,
            'user_answer': item.user_answer,
            'time_spent': item.time_spent,
            'upload_id_encrypted': upload_id_enc,
        })
    return render(request, 'test_result.html', {
        'result': result,
        'question_data': question_data,
    })


@login_required
def test_reports(request):
    """检测报告页面"""
    results = TestResult.objects.filter(user=request.user).select_related('question_list').order_by('-completed_at')
    return render(request, 'test_reports.html', {
        'results': results,
    })


@login_required
def wrong_questions(request):
    """错题查看页面"""
    wrong_item_ids = TestResultItem.objects.filter(
        test_result__user=request.user,
        status='wrong'
    ).values_list('question_id', flat=True).distinct()
    questions = QuestionBank.objects.filter(id__in=wrong_item_ids).select_related('upload')
    
    # 获取所有涉及的学科和题库
    upload_ids = questions.values_list('upload_id', flat=True).distinct()
    subjects_info = {}
    uploads_info = {}
    for u_id in upload_ids:
        if not u_id:
            continue
        upload_obj = Upload.objects.filter(id=u_id).first()
        if not upload_obj:
            continue
        subj = upload_obj.subject or '未分类'
        from app1.utils import encrypt_id
        enc_id = encrypt_id(u_id)
        wrong_count = questions.filter(upload_id=u_id).count()
        # 按学科分组
        if subj not in subjects_info:
            subjects_info[subj] = {'count': 0, 'upload_ids': []}
        subjects_info[subj]['count'] += wrong_count
        subjects_info[subj]['upload_ids'].append(u_id)
        # 题库信息
        uploads_info[u_id] = {
            'encrypted_id': enc_id,
            'name': upload_obj.file_name,
            'subject': subj,
            'wrong_count': wrong_count,
        }
    
    subjects_list = [{'name': k, 'count': v['count']} for k, v in subjects_info.items()]
    subjects_list.sort(key=lambda x: -x['count'])
    
    uploads_list = [{'id': k, **v} for k, v in uploads_info.items()]
    
    # 筛选：先学科，后题库
    filter_subject = request.GET.get('subject', '')
    filter_upload_enc = request.GET.get('upload_id', '')
    
    if filter_subject:
        subject_uids = subjects_info.get(filter_subject, {}).get('upload_ids', [])
        if subject_uids:
            questions = questions.filter(upload_id__in=subject_uids)
    
    if filter_upload_enc:
        from app1.utils import decrypt_id
        decrypted = decrypt_id(filter_upload_enc)
        if decrypted:
            questions = questions.filter(upload_id=decrypted)
    
    # 为每道题添加加密的 upload_id
    question_list = []
    for q in questions:
        from app1.utils import encrypt_id
        question_list.append({
            'id': q.id,
            'content': q.content,
            'answer': q.answer,
            'question_type': q.question_type,
            'tags': q.tags,
            'upload_id_encrypted': encrypt_id(q.upload_id) if q.upload_id else '',
        })
    
    return render(request, 'wrong_questions.html', {
        'questions': question_list,
        'subjects': subjects_list,
        'uploads': uploads_list,
        'current_subject': filter_subject or '',
        'current_upload_id': filter_upload_enc or '',
    })


@login_required
def delete_test_result(request):
    """AJAX 删除检测报告"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    result_id = data.get('result_id')
    try:
        from app1.models import TestResult
        result = TestResult.objects.get(id=result_id, user=request.user)
        result.delete()
        return JsonResponse({'success': True})
    except TestResult.DoesNotExist:
        return JsonResponse({'success': False, 'message': '记录不存在'})


@login_required
def delete_wrong_question(request):
    """AJAX 从错题中移除（删除该题所有错误记录）"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    question_id = data.get('question_id')
    from app1.models import TestResultItem
    deleted, _ = TestResultItem.objects.filter(
        test_result__user=request.user,
        question_id=question_id,
        status='wrong'
    ).delete()
    if deleted:
        return JsonResponse({'success': True, 'message': f'已移除{deleted}条记录'})
    return JsonResponse({'success': False, 'message': '未找到该错题记录'})


@login_required
def delete_question(request):
    """AJAX 删除题库中的题目"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    question_id = data.get('question_id')
    from app1.models import QuestionBank
    try:
        q = QuestionBank.objects.get(id=question_id, upload__user=request.user)
        upload_id = q.upload_id
        q.delete()
        renumber_questions(upload_id)
        # 如果文件没有题目了，重置状态
        remaining = QuestionBank.objects.filter(upload_id=upload_id).count()
        if remaining == 0:
            Upload.objects.filter(id=upload_id).update(processing_status='pending')
        return JsonResponse({'success': True})
    except QuestionBank.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题目不存在或无权限删除'})


@login_required
def add_question(request):
    """AJAX 新增题目到题库"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    upload_id = data.get('upload_id')
    content = data.get('content', '').strip()
    if not content:
        return JsonResponse({'success': False, 'message': '题目内容不能为空'})
    from app1.models import Upload, QuestionBank
    try:
        upload = Upload.objects.get(id=upload_id, user=request.user)
    except Upload.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文件不存在'})
    q = QuestionBank.objects.create(
        upload=upload,
        question_number=QuestionBank.objects.filter(upload=upload).count() + 1,
        content=content,
        answer=data.get('answer', '').strip(),
        question_type=data.get('question_type', '单选题'),
        tags=data.get('tags', '').strip(),
    )
    # 更新文件总题数并自动标记为已完成
    upload.total_questions = QuestionBank.objects.filter(upload=upload).count()
    if upload.processing_status != 'completed':
        upload.processing_status = 'completed'
        upload.save(update_fields=['total_questions', 'processing_status'])
    else:
        upload.save(update_fields=['total_questions'])
    # 判断是否被当前用户收藏
    is_fav = q.favorited_by.filter(id=request.user.id).exists()
    from app1.utils import encrypt_id
    return JsonResponse({
        'success': True,
        'question': {
            'id': q.id,
            'content': q.content,
            'answer': q.answer,
            'question_type': q.question_type,
            'tags': q.tags,
            'question_number': q.question_number,
            'is_favorited': is_fav,
            'upload_id_encrypted': encrypt_id(upload.id),
        }
    })


@login_required
def batch_delete_uploads(request):
    """批量删除上传文件"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    upload_ids = data.get('upload_ids', [])
    if not upload_ids:
        return JsonResponse({'success': False, 'message': '请选择题库'})
    deleted = 0
    from app1.models import Upload
    import os
    for uid in upload_ids:
        try:
            upload = Upload.objects.get(id=uid, user=request.user)
            if upload.file and upload.file.path:
                if os.path.exists(upload.file.path):
                    os.remove(upload.file.path)
            upload.delete()
            deleted += 1
        except Upload.DoesNotExist:
            continue
    return JsonResponse({'success': True, 'deleted': deleted})


@login_required
def batch_add_uploads_to_list(request):
    """将多个上传文件的所有题目加入题单"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    upload_ids = data.get('upload_ids', [])
    list_id = data.get('list_id')
    if not upload_ids or not list_id:
        return JsonResponse({'success': False, 'message': '参数错误'})
    from app1.models import QuestionList, QuestionBank, QuestionListItem
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
    except QuestionList.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题单不存在'})
    added = 0
    for uid in upload_ids:
        questions = QuestionBank.objects.filter(upload_id=uid)
        for q in questions:
            _, created = QuestionListItem.objects.get_or_create(question_list=ql, question=q)
            if created:
                added += 1
    return JsonResponse({'success': True, 'added': added})


@login_required
def batch_delete_questions(request):
    """批量删除题目"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    question_ids = data.get('question_ids', [])
    if not question_ids:
        return JsonResponse({'success': False, 'message': '请选择题目的编号'})
    from app1.models import QuestionBank, Upload
    # 收集受影响的 upload_ids
    affected_uploads = set()
    for qid in question_ids:
        try:
            q = QuestionBank.objects.get(id=qid, upload__user=request.user)
            affected_uploads.add(q.upload_id)
            q.delete()
        except QuestionBank.DoesNotExist:
            continue
    # 重编号并更新状态
    for uid in affected_uploads:
        renumber_questions(uid)
        remaining = QuestionBank.objects.filter(upload_id=uid).count()
        if remaining == 0:
            Upload.objects.filter(id=uid).update(processing_status='pending')
        else:
            Upload.objects.filter(id=uid).update(
                total_questions=remaining,
                processing_status='completed'
            )
    return JsonResponse({'success': True, 'deleted': len(question_ids)})


@login_required
def batch_add_questions_to_list(request):
    """将多道题目加入题单"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    question_ids = data.get('question_ids', [])
    list_id = data.get('list_id')
    if not question_ids or not list_id:
        return JsonResponse({'success': False, 'message': '参数错误'})
    from app1.models import QuestionList, QuestionBank, QuestionListItem
    try:
        ql = QuestionList.objects.get(id=list_id, user=request.user)
    except QuestionList.DoesNotExist:
        return JsonResponse({'success': False, 'message': '题单不存在'})
    added = 0
    for qid in question_ids:
        try:
            q = QuestionBank.objects.get(id=qid)
            _, created = QuestionListItem.objects.get_or_create(question_list=ql, question=q)
            if created:
                added += 1
        except QuestionBank.DoesNotExist:
            continue
    return JsonResponse({'success': True, 'added': added})


@login_required
def upload_auxiliary_file(request):
    """上传附属文件并解析其中的题目，添加到当前题库"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    
    upload_id = request.POST.get('upload_id')
    file = request.FILES.get('file')
    
    if not upload_id or not file:
        return JsonResponse({'success': False, 'message': '缺少参数'})
    
    try:
        upload = Upload.objects.get(id=upload_id, user=request.user)
    except Upload.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文件不存在或无权操作'})
    
    # 读取文件内容（确保只读一次）
    raw_bytes = file.read()
    try:
        raw_text = raw_bytes.decode('utf-8', errors='ignore')
    except Exception:
        raw_text = raw_bytes.decode('gbk', errors='ignore')
    # 统一清理回车符 \r，避免破坏 KaTeX 的 $$ 显示数学
    raw_text = raw_text.replace('\r', '')
    
    # 根据文件扩展名选择解析方式
    ext = os.path.splitext(file.name)[1].lower()
    questions_data = []
    
    if ext == '.tex':
        questions_data = parse_tex_file(raw_text)
    elif ext == '.py':
        questions_data = parse_python_doc(raw_text)
    elif ext == '.json':
        import json as json_module
        try:
            data_list = json_module.loads(raw_text)
            if isinstance(data_list, list):
                for item in data_list:
                    if isinstance(item, dict) and 'content' in item:
                        questions_data.append({
                            'content': item.get('content', '').strip(),
                            'answer': item.get('answer', '').strip(),
                            'question_type': item.get('question_type', '单选题'),
                            'tags': item.get('tags', '').strip(),
                        })
        except Exception:
            pass
    else:
        # .txt, .md 等纯文本：启发式解析
        questions_data = parse_text_file(raw_text)
    
    if not questions_data:
        return JsonResponse({'success': False, 'message': '未能从文件中解析出任何题目，请检查文件格式'})
    
    # 将解析出的题目添加到题库
    from app1.models import QuestionBank
    from app1.utils import encrypt_id
    count = 0
    for qd in questions_data:
        if not qd.get('content', '').strip():
            continue
        next_num = QuestionBank.objects.filter(upload=upload).count() + 1
        QuestionBank.objects.create(
            upload=upload,
            question_number=next_num,
            content=qd['content'].strip(),
            answer=qd.get('answer', '').strip(),
            question_type=qd.get('question_type', '解答题'),
            tags=qd.get('tags', '').strip(),
        )
        count += 1
    
    # 更新总题数
    upload.total_questions = QuestionBank.objects.filter(upload=upload).count()
    upload.save(update_fields=['total_questions'])
    
    return JsonResponse({'success': True, 'count': count})


@login_required
def auxiliary_direct_text(request):
    """直接输入 LaTeX 文本，解析并添加到当前题库（无需 AI）"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    text = data.get('text', '').strip()
    upload_id = data.get('upload_id', '')
    
    if not text:
        return JsonResponse({'success': False, 'message': '请输入题目内容'})
    if not upload_id:
        return JsonResponse({'success': False, 'message': '缺少 upload_id'})
    
    try:
        upload = Upload.objects.get(id=upload_id, user=request.user)
    except Upload.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文件不存在或无权操作'})
    
    # 解析 LaTeX 文本
    questions_data = parse_tex_file(text)
    
    if not questions_data:
        return JsonResponse({'success': False, 'message': '未能解析出任何题目，请检查 LaTeX 格式'})
    
    # 将解析出的题目添加到题库
    from app1.models import QuestionBank
    count = 0
    for qd in questions_data:
        if not qd.get('content', '').strip():
            continue
        next_num = QuestionBank.objects.filter(upload=upload).count() + 1
        QuestionBank.objects.create(
            upload=upload,
            question_number=next_num,
            content=qd['content'].strip(),
            answer=qd.get('answer', '').strip(),
            question_type=qd.get('question_type', '解答题'),
            tags=qd.get('tags', '').strip(),
        )
        count += 1
    
    # 更新总题数
    upload.total_questions = QuestionBank.objects.filter(upload=upload).count()
    upload.save(update_fields=['total_questions'])
    
    return JsonResponse({'success': True, 'count': count})


def parse_tex_file(text):
    """解析 LaTeX 文件中的 problem/solution 环境"""
    import re as _re
    questions = []
    
    # 匹配 \begin{problem}...\end{problem} 及其所有可选参数
    # 可选参数形如 [知识点：极限] 或 [填空题] 或 [知识点：极限][填空题]
    pattern = _re.compile(
        r'\\begin\{problem\}((?:\s*\[[^\]]*\])*)\s*(.*?)\\end\{problem\}',
        _re.DOTALL
    )
    
    # 匹配 \begin{solution}...\end{solution}
    sol_pattern = _re.compile(
        r'\\begin\{solution\}(.*?)\\end\{solution\}',
        _re.DOTALL
    )
    
    all_solutions = sol_pattern.findall(text)
    sol_index = 0
    
    for match in pattern.finditer(text):
        optional_args_str = match.group(1)  # 所有可选参数，如 "[知识点：极限][填空题]"
        body = match.group(2).strip()
        if not body:
            continue
        
        # 提取所有可选参数中的文本
        optional_args = _re.findall(r'\[([^\]]*)\]', optional_args_str)
        
        # 从 optional_args 中识别题型
        q_type = '解答题'
        for arg in optional_args:
            if '单选' in arg:
                q_type = '单选题'
            elif '多选' in arg:
                q_type = '多选题'
            elif '填空' in arg:
                q_type = '填空题'
            elif '判断' in arg:
                q_type = '判断题'
        
        # 从内容中移除题型标签 [填空题]、[解答题] 等
        content_text = body
        content_text = _re.sub(r'^\s*\[(?:填空题|解答题|单选题|多选题|判断题|知识点：.*?)\]\s*', '', content_text)
        
        # 获取对应的 answer（按顺序匹配 solution）
        answer_text = ''
        if sol_index < len(all_solutions):
            answer_text = all_solutions[sol_index].strip()
            sol_index += 1
        
        # 清理 LaTeX 命令但保留内容
        content_text = clean_latex_text(content_text)
        if answer_text:
            answer_text = clean_latex_text(answer_text)
        
        questions.append({
            'content': content_text.strip(),
            'answer': answer_text.strip(),
            'question_type': q_type,
            'tags': '',
        })
    
    return questions


def clean_latex_text(text):
    """清理 LaTeX 源文本，保留所有 KaTeX 可渲染的数学命令"""
    import re as _re
    # 移除回车符 \r，避免破坏 KaTeX 的 $$ 显示数学
    text = text.replace('\r', '')
    # 移除 \label{...} 和 \ref{...}（交叉引用）
    text = _re.sub(r'\\label\{[^}]*\}', '', text)
    text = _re.sub(r'\\ref\{[^}]*\}', '', text)
    # 移除 \newtheorem{...}{...} 定义
    text = _re.sub(r'\\newtheorem\{[^}]*\}\{[^}]*\}', '', text)
    # 将 \hbox to 20pt{} 替换为 KaTeX 可渲染的填空横线
    text = _re.sub(r'\\hbox\s+to\s+\d+pt\{[^}]*\}', r'\\underline{\\qquad}', text)
    # 将 \hspace{2em} 等替换为空格（不在数学模式内时不可渲染）
    text = _re.sub(r'\\hspace\{[^}]*\}', r'\\qquad', text)
    # 移除 \begin{enumerate} / \item / \end{enumerate}（KaTeX 不支持）
    text = _re.sub(r'\\begin\{enumerate\}', '', text)
    text = _re.sub(r'\\end\{enumerate\}', '', text)
    text = _re.sub(r'\\item\s*', '\n', text)
    # 将 \par(?!tial) 替换为换行（避免截断 \partial）
    text = _re.sub(r'\\par(?!tial)\s*', '\n', text)
    # 将 \\\\ 替换为换行（但保护 \\begin{cases}...\\end{cases} 环境内的 \\\\）
    def _protect_cases_repl(m):
        return m.group(0).replace('\\\\', '%%%CASES_BR%%%')
    text = _re.sub(r'\\begin\{cases\}(.*?)\\end\{cases\}', _protect_cases_repl, text, flags=_re.DOTALL)
    text = _re.sub(r'\\\\', '\n', text)
    text = text.replace('%%%CASES_BR%%%', '\\\\')
    # 保留 textbf/textit/underline 等文本命令的内容，去掉命令
    text = _re.sub(r'\\textbf\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\textit\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\underline\{([^}]*)\}', r'\1', text)
    # 保留 mathbf/mathit/mathrm 的内容但保持命令形式（KaTeX 可渲染）
    # 不做替换，保留原始 LaTeX 命令
    # 将 \( \) 转换为 $ $，将 \[ \] 转换为 $$ $$
    text = _re.sub(r'\\\(', '$', text)
    text = _re.sub(r'\\\)', '$', text)
    text = _re.sub(r'\\\[', '$$', text)
    text = _re.sub(r'\\\]', '$$', text)
    # 只移除空的 $$（保留有效的 $$...$$ 显示数学分隔符）
    text = _re.sub(r'\$\$\s*\$\$', '', text)
    text = _re.sub(r'\$\s*\$', '', text)
    # 将数学模式外孤立的 LaTeX 命令包裹上 $...$
    text = _wrap_orphaned_latex(text)
    # 修复 $...\tag{...}$ → $$...\tag{...}$$（\tag 只能在 display 模式使用）
    text = _re.sub(r'\$([^$]*?\\tag\{[^}]*\}[^$]*?)\$', r'$$\1$$', text)
    # 清理残留的 $$$ → $$
    text = text.replace('$$$', '$$')
    # 移除 $ 前后的多余空格（KaTeX 不支持 $ f(x)$ 这种格式）
    text = _re.sub(r'(?<!\$)\$ +(?=\S)', '$', text)
    text = _re.sub(r'(?<=\S) +\$(?!\$)', '$', text)
    # 移除多余的空白行
    text = _re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# KaTeX 可渲染的常用 LaTeX 数学命令列表
_LATEX_MATH_CMDS = [
    'frac', 'int', 'iint', 'iiint', 'iiiint', 'sum', 'prod', 'lim', 'infty', 'partial',
    'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'arcsin', 'arccos', 'arctan',
    'sinh', 'cosh', 'tanh', 'coth',
    'ln', 'lg', 'log', 'exp', 'to', 'cdot', 'times', 'div', 'pm', 'mp',
    'leq', 'geq', 'neq', 'equiv', 'approx', 'sim', 'propto',
    'sqrt', 'displaystyle', 'text', 'mathrm', 'mathbf', 'mathit', 'tag',
    'rightarrow', 'leftarrow', 'Rightarrow', 'Leftarrow',
    'left', 'right', 'big', 'Big', 'bigg', 'Bigg', 'bigl', 'bigr', 'Bigl', 'Bigr',
    'ge', 'le', 'ne', 'll', 'gg', 'subset', 'supset', 'subseteq', 'supseteq',
    'cup', 'cap', 'in', 'notin', 'emptyset', 'varnothing',
    'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'varepsilon',
    'zeta', 'eta', 'theta', 'vartheta', 'iota', 'kappa', 'lambda',
    'mu', 'nu', 'xi', 'pi', 'varpi', 'rho', 'varrho',
    'sigma', 'varsigma', 'tau', 'upsilon', 'phi', 'varphi',
    'chi', 'psi', 'omega',
    'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma',
    'Phi', 'Psi', 'Omega', 'nabla', 'triangle', 'forall', 'exists', 'neg',
    'mathbb', 'mathcal', 'mathfrak', 'mathscr',
    'quad', 'qquad', 'colon', 'vert', 'Vert', 'mid',
    'Pr', 'operatorname', 'min', 'max', 'sup', 'inf',
    'cdots', 'ddots', 'vdots',
    'binom', 'choose', 'pmod', 'bmod',
    'prime', 'bullet', 'circ',
    'langle', 'rangle', 'lceil', 'rceil', 'lfloor', 'rfloor',
    'widetilde', 'widehat', 'bar', 'hat', 'check', 'tilde', 'dot', 'ddot',
    'degree', 'Box', 'triangleleft', 'triangleright',
]

# \begin{...} / \end{...} 环境名列表
_LATEX_ENVS = [
    'cases', 'align', 'align*', 'equation', 'equation*',
    'gather', 'gather*', 'split', 'multline', 'multline*',
    'matrix', 'pmatrix', 'bmatrix', 'vmatrix', 'Vmatrix',
    'array', 'tabular', 'table',
]


def _wrap_orphaned_latex(text):
    """将数学模式外孤立的 LaTeX 命令包裹在 $...$ 中"""
    import re as _re
    
    # 1. 找出所有数学模式范围 $...$ 和 $$...$$
    math_ranges = []
    i = 0
    while i < len(text):
        if text[i] != '$':
            i += 1
            continue
        if i > 0 and text[i-1] == '\\':
            i += 1
            continue
        if i + 1 < len(text) and text[i+1] == '$':
            end = text.find('$$', i + 2)
            if end != -1:
                math_ranges.append((i, end + 2))
                i = end + 2
                continue
            i += 2
            continue
        j = i + 1
        while j < len(text):
            if text[j] == '$' and (j == 0 or text[j-1] != '\\'):
                math_ranges.append((i, j + 1))
                i = j + 1
                break
            j += 1
        else:
            i += 1
    
    def _in_math(pos):
        return any(s <= pos < e for s, e in math_ranges)
    
    # 2. 先处理 \begin{env}...\end{env} 环境块
    env_ranges = []  # [(start, end)]
    env_pat = _re.compile(r'\\(begin|end)\{([^}]*)\}')
    
    # 找到所有 \begin 和 \end
    env_starts = {}  # env_name -> [(pos, ...)]
    env_ends = {}
    for m in env_pat.finditer(text):
        kw, env_name = m.group(1), m.group(2)
        pos = m.start()
        if _in_math(pos):
            continue
        if kw == 'begin':
            env_starts.setdefault(env_name, []).append(pos)
        else:
            env_ends.setdefault(env_name, []).append(pos)
    
    # 匹配 \begin{name}...\end{name} 对
    for env_name in set(list(env_starts.keys()) + list(env_ends.keys())):
        starts = sorted(env_starts.get(env_name, []), reverse=True)
        ends = sorted(env_ends.get(env_name, []))
        for s in starts:
            for e in ends:
                if e > s and not any(rs <= s < re or rs < e <= re for rs, re in env_ranges):
                    env_ranges.append((s, e + 6 + len(env_name)))  # \end{name}
                    ends.remove(e)
                    break
    
    # 移除已经被环境块覆盖的区域（用函数检查）
    def _in_env(pos):
        return any(s <= pos < e for s, e in env_ranges)
    
    # 3. 处理单个 LaTeX 命令
    _CMD_PAT = _re.compile(r'\\(?:' + '|'.join(_LATEX_MATH_CMDS) + r')(?![a-zA-Z])')
    expr_ranges = list(env_ranges)  # 先加入环境块
    
    for m in _CMD_PAT.finditer(text):
        pos = m.start()
        if _in_math(pos):
            continue
        if _in_env(pos):
            continue
        
        # 消耗命令后的参数
        k = m.end()
        while k < len(text):
            ch = text[k]
            if ch in ' \t':
                k += 1
                continue
            if ch == '[':
                brk = text.find(']', k+1)
                if brk != -1:
                    k = brk + 1
                    continue
                break
            if ch in ('_', '^'):
                if k + 1 < len(text) and text[k+1] == '{':
                    bk = k+2; depth = 1
                    while bk < len(text) and depth > 0:
                        if text[bk] == '{': depth += 1
                        elif text[bk] == '}': depth -= 1
                        bk += 1
                    if depth == 0:
                        k = bk; continue
                elif k + 1 < len(text):
                    k += 2; continue
                break
            if ch == '{':
                depth = 1; bk = k + 1
                while bk < len(text) and depth > 0:
                    if text[bk] == '{': depth += 1
                    elif text[bk] == '}': depth -= 1
                    bk += 1
                if depth == 0:
                    k = bk
                    continue
                break
            # 遇到中文、换行、$ 时停止
            if '\u4e00' <= ch <= '\u9fff':
                break
            if ch == '\n':
                break
            if ch == '$':
                break
            if ch == '\\':
                if k + 1 < len(text) and text[k+1].isalpha():
                    break
                k += 2
                continue
            if ch in '，。、；：！？':
                break
            if ch == '&':
                k += 1
                continue
            if ch in '.,;:!?)':
                k += 1
                if k >= len(text) or text[k] in ' \n\t\u4e00-\u9fff':
                    break
                continue
            k += 1
        
        if k <= pos + 1:
            continue
        
        # 合并
        merged = False
        for idx, (rs, re_) in enumerate(expr_ranges):
            if abs(pos - re_) <= 2 or abs(k - rs) <= 2 or (pos >= rs and k <= re_):
                expr_ranges[idx] = (min(rs, pos), max(re_, k))
                merged = True
                break
        if not merged:
            expr_ranges.append((pos, k))
    
    # 3b. 扫描"裸写数学"：不含 LaTeX 命令但含 ^, _ 下标, = 的表达式
    # 模式：在非数学区域中寻找 ^, _下标, 行首 +/-
    _NAKED_MATH_PAT = _re.compile(r'(?<!\^)\^|(?<=[a-zA-Z0-9])_(?=[a-zA-Z0-9\{])|(?<=\n)[+\-]\s*\(|^[+\-]\s*\(')
    for m in _NAKED_MATH_PAT.finditer(text):
        pos = m.start()
        if _in_math(pos) or _in_env(pos):
            continue
        # 向前扩展到行首或中文或 $
        s = pos
        while s > 0:
            ch = text[s-1]
            if ch == '\n':
                # 如果前一个字符是换行，且再前一个是 $，则在 $ 后停止
                if s > 1 and text[s-2] == '$':
                    break
                break
            if ch == '$':
                break
            if '\u4e00' <= ch <= '\u9fff':
                break
            s -= 1
        # 向后扩展到行尾或中文或 $
        e = pos + len(m.group())
        while e < len(text):
            ch = text[e]
            if ch in '\n$':
                break
            if '\u4e00' <= ch <= '\u9fff':
                break
            e += 1
        if e > s and not (s > 0 and text[s-1] == '$') and not (e < len(text) and text[e] == '$'):
            # 合并到已有的 expr_ranges
            merged = False
            for idx, (rs, re_) in enumerate(expr_ranges):
                if abs(s - re_) <= 5 or abs(e - rs) <= 5 or (s >= rs and e <= re_):
                    expr_ranges[idx] = (min(rs, s), max(re_, e))
                    merged = True
                    break
            if not merged:
                expr_ranges.append((s, e))
    
    if not expr_ranges:
        return text
    
    # 4. 合并相邻区域
    expr_ranges.sort()
    merged = [expr_ranges[0]]
    for s, e in expr_ranges[1:]:
        if s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    
    # 5. 应用包裹
    result = list(text)
    for s, e in reversed(merged):
        if s > 0 and result[s-1] == '$':
            continue
        if e < len(result) and result[e] == '$':
            continue
        snippet = ''.join(result[s:e]).strip().rstrip('.,;:，。；：\n ')
        if not snippet or snippet.startswith('$'):
            continue
        if any(result[i] == '$' for i in range(s, e)):
            continue
        # 含 \tag 或多行用 $$，否则用 $
        if '\n' in snippet or '\\tag' in snippet:
            result.insert(e, '$$')
            result.insert(s, '$$')
        else:
            result.insert(e, '$')
            result.insert(s, '$')
    
    return ''.join(result)


def parse_text_file(text):
    """解析纯文本文件中的题目"""
    import re as _re
    # 清理回车符
    text = text.replace('\r', '')
    questions = []
    lines = text.split('\n')
    
    current_content = []
    current_answer = []
    in_answer = False
    in_question = False
    
    for line in lines:
        stripped = line.strip()
        
        # 检测答案标记
        if _re.match(r'^(答案|答|Answer|answer)[：:\s]', stripped):
            in_answer = True
            if current_content:
                pass  # keep previous content
            current_answer.append(_re.sub(r'^(答案|答|Answer|answer)[：:\s]', '', stripped))
            continue
        
        # 检测题目编号（如 1. 2、 等）
        if _re.match(r'^\s*\d+[\.、\s]\s*', stripped) and len(stripped) > 3:
            # 保存上一条目
            if current_content:
                questions.append({
                    'content': '\n'.join(current_content).strip(),
                    'answer': '\n'.join(current_answer).strip(),
                    'question_type': '解答题',
                    'tags': '',
                })
                current_answer = []
            current_content = [_re.sub(r'^\s*\d+[\.、\s]\s*', '', stripped)]
            in_answer = False
            in_question = True
        elif in_answer:
            current_answer.append(stripped)
        elif in_question:
            if stripped:
                current_content.append(stripped)
    
    # 最后一条
    if current_content:
        questions.append({
            'content': '\n'.join(current_content).strip(),
            'answer': '\n'.join(current_answer).strip(),
            'question_type': '解答题',
            'tags': '',
        })
    
    return questions


def parse_python_doc(text):
    """解析 Python 文件中的题目文档字符串"""
    import re as _re
    questions = []
    
    # 匹配三引号字符串中可能包含的题目定义
    doc_matches = _re.findall(r'"""([^"]*)"""', text)
    if not doc_matches:
        doc_matches = _re.findall(r"'''([^']*)'''", text)
    
    for doc in doc_matches:
        qs = parse_text_file(doc)
        questions.extend(qs)
    
    if not questions:
        # 尝试从注释中提取
        comments = _re.findall(r'#\s*(.*)', text)
        comment_text = '\n'.join(comments)
        questions = parse_text_file(comment_text)
    
    return questions


# ==================== 接口文档 - API 实例管理 ====================

@login_required
def api_management(request):
    """接口文档页面"""
    instances = ApiInstance.objects.filter(user=request.user).order_by('-created_at')
    import os
    for inst in instances:
        inst.filename_only = os.path.basename(inst.json_filename)
    return render(request, 'api_management.html', {'instances': instances})


@login_required
def script_explanation(request):
    """案例解释独立页面"""
    import os
    md_path = os.path.join(settings.BASE_DIR, 'static', 'docs', 'script_api_explanation.md')
    script_explanation_html = ''
    if os.path.exists(md_path):
        import markdown
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        script_explanation_html = markdown.markdown(
            md_content,
            extensions=['fenced_code', 'tables']
        )
    return render(request, 'script_explanation.html', {
        'script_explanation_html': script_explanation_html,
    })


@login_required
def view_api_json_file(request, instance_id):
    """查看 API 实例关联的 JSON 文件内容"""
    import json
    from django.http import JsonResponse
    from django.conf import settings
    instance = get_object_or_404(ApiInstance, id=instance_id, user=request.user)
    full_path = os.path.join(settings.BASE_DIR, instance.json_filename)
    if not os.path.exists(full_path):
        return JsonResponse({'error': '文件不存在'}, status=404)
    with open(full_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return JsonResponse(data, json_dumps_params={'ensure_ascii': False, 'indent': 2})


@login_required
def api_instance_detail(request, instance_id):
    """API 实例详情页"""
    instance = get_object_or_404(ApiInstance, id=instance_id, user=request.user)
    import os
    filename_only = os.path.basename(instance.json_filename)
    comments = Comment.objects.filter(api_instance=instance, parent=None).order_by('-created_at')
    files = instance.files.all().order_by('-uploaded_at')
    return render(request, 'api_instance_detail.html', {
        'instance': instance,
        'filename_only': filename_only,
        'comments': comments,
        'files': files,
    })


@login_required
def upload_api_script(request):
    """上传文件到 API 实例 — 支持单个文件、文件夹(多文件)、压缩包(自动解压)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    instance_id = request.POST.get('instance_id')
    if not instance_id:
        return JsonResponse({'success': False, 'message': '缺少实例ID'})
    try:
        instance = ApiInstance.objects.get(id=instance_id, user=request.user)
    except ApiInstance.DoesNotExist:
        return JsonResponse({'success': False, 'message': '实例不存在'})

    import zipfile, tarfile, tempfile, shutil, os
    from django.conf import settings

    uploaded_files = request.FILES.getlist('script_file')
    if not uploaded_files:
        return JsonResponse({'success': False, 'message': '请选择要上传的文件'})

    saved_count = 0

    for uploaded_file in uploaded_files:
        name_lower = uploaded_file.name.lower()

        # 处理压缩包：自动解压
        if name_lower.endswith('.zip') or name_lower.endswith('.tar') or name_lower.endswith('.tar.gz') or name_lower.endswith('.tgz'):
            ext_path = f'api_extracted/{instance.id}/{uploaded_file.name}/'
            extract_dir = os.path.join(settings.MEDIA_ROOT, ext_path)
            os.makedirs(extract_dir, exist_ok=True)

            try:
                if name_lower.endswith('.zip'):
                    with zipfile.ZipFile(uploaded_file, 'r') as zf:
                        zf.extractall(extract_dir)
                elif name_lower.endswith('.tar.gz') or name_lower.endswith('.tgz'):
                    with tarfile.open(fileobj=uploaded_file, mode='r:gz') as tf:
                        tf.extractall(extract_dir)
                elif name_lower.endswith('.tar'):
                    with tarfile.open(fileobj=uploaded_file, mode='r') as tf:
                        tf.extractall(extract_dir)
            except Exception as e:
                return JsonResponse({'success': False, 'message': f'解压失败: {str(e)}'})

            # 遍历解压后的文件，逐个存入数据库
            for root, dirs, files in os.walk(extract_dir):
                for fname in files:
                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, extract_dir)
                    # 跳过隐藏文件
                    if fname.startswith('.'):
                        continue
                    with open(full_path, 'rb') as f:
                        file_content = f.read()
                    # 用 Django 的 File 对象保存
                    from django.core.files.base import ContentFile
                    aim_file = ApiInstanceFile(api_instance=instance, original_name=fname, file_path=rel_path)
                    aim_file.file.save(f'{instance.id}/{rel_path}', ContentFile(file_content), save=True)
                    saved_count += 1

            # 清理临时解压目录
            shutil.rmtree(extract_dir, ignore_errors=True)
        else:
            # 普通文件直接保存
            aim_file = ApiInstanceFile(api_instance=instance, original_name=uploaded_file.name, file_path='')
            aim_file.file.save(f'{instance.id}/{uploaded_file.name}', uploaded_file, save=True)
            saved_count += 1

    return JsonResponse({'success': True, 'message': f'上传成功，共 {saved_count} 个文件', 'count': saved_count})


@login_required
def delete_api_script(request):
    """删除 API 实例的脚本文件"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json as json_mod
    data = json_mod.loads(request.body)
    instance_id = data.get('instance_id')
    try:
        instance = ApiInstance.objects.get(id=instance_id, user=request.user)
    except ApiInstance.DoesNotExist:
        return JsonResponse({'success': False, 'message': '实例不存在'})
    if instance.script_file:
        instance.script_file.delete(save=False)
        instance.script_file = None
        instance.save()
    return JsonResponse({'success': True, 'message': '已删除'})


@login_required
def delete_api_file(request):
    """删除 API 实例的单个文件"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json as json_mod
    data = json_mod.loads(request.body)
    file_id = data.get('file_id')
    try:
        f = ApiInstanceFile.objects.get(id=file_id, api_instance__user=request.user)
        f.file.delete(save=False)
        f.delete()
        return JsonResponse({'success': True, 'message': '已删除'})
    except ApiInstanceFile.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文件不存在'})


@login_required
def create_api_instance(request):
    """创建新的 API 实例，自动分配 API Key 和 JSON 文件"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    import secrets
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': '请输入实例名称'})
    
    # 生成唯一 API Key
    api_key = 'qbank_' + secrets.token_hex(16)
    # 确保唯一
    while ApiInstance.objects.filter(api_key=api_key).exists():
        api_key = 'qbank_' + secrets.token_hex(16)
    
    # 生成 JSON 文件名
    from django.utils import timezone
    timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
    safe_name = re.sub(r'[^\w\u4e00-\u9fff]+', '_', name)[:30]
    filename = f'api_instances/{request.user.id}_{safe_name}_{timestamp}.json'
    
    # 创建实例
    instance = ApiInstance.objects.create(
        user=request.user,
        name=name,
        api_key=api_key,
        json_filename=filename,
    )
    
    # 创建 JSON 文件（初始空数据）
    from django.conf import settings
    full_path = os.path.join(settings.BASE_DIR, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    initial_data = {
        "questions": [],
        "wrong_questions": [],
        "last_updated": None,
        "instance_name": name,
        "instance_id": instance.id,
    }
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(initial_data, f, ensure_ascii=False, indent=2)
    
    return JsonResponse({'success': True, 'message': '创建成功'})


@login_required
def delete_api_instance(request):
    """删除 API 实例及其关联的 JSON 文件"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '请求方法错误'})
    import json
    data = json.loads(request.body)
    instance_id = data.get('instance_id')
    if not instance_id:
        return JsonResponse({'success': False, 'message': '缺少实例ID'})
    try:
        instance = ApiInstance.objects.get(id=instance_id, user=request.user)
    except ApiInstance.DoesNotExist:
        return JsonResponse({'success': False, 'message': '实例不存在'})
    
    # 删除 JSON 文件
    from django.conf import settings
    full_path = os.path.join(settings.BASE_DIR, instance.json_filename)
    if os.path.exists(full_path):
        os.remove(full_path)
    
    instance.delete()
    return JsonResponse({'success': True, 'message': '已删除'})


@csrf_exempt
def question_bank_api(request):
    """
    通用题库 API
    GET /api/question_bank/?api_key=xxx → 返回该实例的题库 JSON
    POST /api/question_bank/ (Header: X-API-Key) → 保存题库 JSON
    """
    if request.method == 'GET':
        api_key = request.GET.get('api_key', '')
        if not api_key:
            return JsonResponse({'success': False, 'message': '缺少 api_key 参数'})
        
        try:
            instance = ApiInstance.objects.get(api_key=api_key, is_active=True)
        except ApiInstance.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'API密钥无效或已停用'})
        
        from django.conf import settings
        full_path = os.path.join(settings.BASE_DIR, instance.json_filename)
        if os.path.exists(full_path):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return JsonResponse({'success': True, 'data': data})
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)})
        else:
            # 文件不存在则重建
            initial_data = {
                "questions": [],
                "wrong_questions": [],
                "last_updated": None,
                "instance_name": instance.name,
                "instance_id": instance.id,
            }
            return JsonResponse({'success': True, 'data': initial_data})

    elif request.method == 'POST':
        api_key = request.headers.get('X-API-Key', '')
        if not api_key:
            return JsonResponse({'success': False, 'message': '缺少 X-API-Key 请求头'})
        
        try:
            instance = ApiInstance.objects.get(api_key=api_key, is_active=True)
        except ApiInstance.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'API密钥无效或已停用'})
        
        try:
            data = json.loads(request.body)
            from django.conf import settings
            full_path = os.path.join(settings.BASE_DIR, instance.json_filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return JsonResponse({'success': True, 'message': '保存成功'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': '无效请求'})

