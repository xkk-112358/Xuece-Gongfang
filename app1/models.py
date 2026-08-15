from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    AI_MODEL_CHOICES = [
        ('qwen3.5-27b', 'Qwen 3.5-27B'),
        ('deepseek-v4-flash', 'DeepSeek Chat'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='上传头像')
    default_avatar = models.CharField(max_length=100, blank=True, verbose_name='默认头像')
    school = models.CharField(max_length=100, blank=True, verbose_name='学校')
    birthday = models.DateField(blank=True, null=True, verbose_name='生日')
    ai_model = models.CharField(max_length=50, choices=AI_MODEL_CHOICES, default='qwen3.5-27b', verbose_name='AI模型')

    def __str__(self):
        return f'{self.user.username}的资料'

    def get_avatar_url(self):
        if self.avatar:
            return self.avatar.url
        elif self.default_avatar:
            return '/static/' + self.default_avatar
        return '/static/pictures/头像/男生头像1.jpg'

class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following_set')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='follower_set')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('follower', 'following')

    def __str__(self):
        return f'{self.follower.username} 关注了 {self.following.username}'

class Upload(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploads')
    file = models.FileField(upload_to='uploads/', verbose_name='上传文件')
    file_name = models.CharField(max_length=255, blank=True, verbose_name='文件名')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')
    description = models.CharField(max_length=500, blank=True, verbose_name='描述')
    is_shared = models.BooleanField(default=False, verbose_name='是否共享')
    processing_status = models.CharField(max_length=20, default='pending', verbose_name='处理状态')
    total_questions = models.IntegerField(default=0, verbose_name='总题目数')
    processed_questions = models.IntegerField(default=0, verbose_name='已处理题目数')
    processing_error = models.TextField(blank=True, verbose_name='处理错误信息')
    is_favorited = models.BooleanField(default=False, verbose_name='是否收藏')
    favorited_by = models.ManyToManyField(User, blank=True, related_name='favorite_uploads')
    subject = models.CharField(max_length=100, blank=True, verbose_name='学科')
    download_count = models.IntegerField(default=0, verbose_name='下载次数')
    folder_path = models.CharField(max_length=500, blank=True, default='', verbose_name='上传时的文件夹路径')

    def __str__(self):
        return f'{self.user.username} - {self.file_name or self.file.name}'

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications', verbose_name='发送者')
    title = models.CharField(max_length=200, verbose_name='标题')
    content = models.TextField(verbose_name='内容')
    is_read = models.BooleanField(default=False, verbose_name='已读')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    def __str__(self):
        return f'{self.user.username} - {self.title}'

class QuestionBank(models.Model):
    QUESTION_TYPES = [
        ('单选题', '单选题'),
        ('多选题', '多选题'),
        ('填空题', '填空题'),
        ('解答题', '解答题'),
        ('判断题', '判断题'),
        ('其他', '其他'),
    ]
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name='questions')
    question_number = models.IntegerField(default=0, verbose_name='题号')
    content = models.TextField(verbose_name='题目内容')
    answer = models.TextField(verbose_name='答案', blank=True)
    image = models.ImageField(upload_to='question_images/', blank=True, null=True, verbose_name='题目图片')
    is_favorited = models.BooleanField(default=False, verbose_name='是否收藏')
    favorited_by = models.ManyToManyField(User, blank=True, related_name='favorite_questions')
    tags = models.TextField(blank=True, verbose_name='知识点标签（逗号分隔）')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='单选题', verbose_name='题目类型')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.upload.file_name} - 题目'

class UploadLike(models.Model):
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='upload_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('upload', 'user')

class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    content = models.TextField(verbose_name='帖子内容')
    image = models.ImageField(upload_to='post_images/', blank=True, null=True, verbose_name='帖子图片')
    link_url = models.URLField(blank=True, verbose_name='帖子链接')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='发布时间')
    likes_count = models.IntegerField(default=0, verbose_name='点赞数')
    comments_count = models.IntegerField(default=0, verbose_name='评论数')
    favorited_by = models.ManyToManyField(User, blank=True, related_name='favorite_posts', verbose_name='收藏用户')

    def __str__(self):
        return f'{self.user.username} 的帖子 ({self.created_at.strftime("%Y-%m-%d %H:%M")})'

class PostLike(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'user')

class Comment(models.Model):
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    post = models.ForeignKey('Post', on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    api_instance = models.ForeignKey('ApiInstance', on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    content = models.TextField(verbose_name='评论内容')
    image = models.ImageField(upload_to='comment_images/', blank=True, null=True, verbose_name='评论图片')
    link_url = models.URLField(blank=True, verbose_name='评论链接')
    likes_count = models.IntegerField(default=0, verbose_name='点赞数')
    dislikes_count = models.IntegerField(default=0, verbose_name='不喜欢数')
    replies_count = models.IntegerField(default=0, verbose_name='回复数')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    def __str__(self):
        if self.upload:
            target = self.upload.file_name if self.upload.file_name else str(self.upload)
        elif self.api_instance:
            target = f'API实例:{self.api_instance.name}'
        else:
            target = '帖子'
        return f'{self.user.username} 评论 {target}'

    def score(self):
        import math
        from django.utils import timezone
        delta = timezone.now() - self.created_at
        hours = delta.total_seconds() / 3600
        if hours < 0:
            hours = 0
        score = (self.likes_count * 3 + self.replies_count * 5 - self.dislikes_count * 10) * math.exp(-0.0144 * hours)
        return score

class CommentInteraction(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='interactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comment_interactions')
    is_like = models.BooleanField(default=True, verbose_name='喜欢/不喜欢')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'user')

class VerificationCode(models.Model):
    email = models.EmailField(verbose_name='邮箱')
    code = models.CharField(max_length=4, verbose_name='验证码')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    is_used = models.BooleanField(default=False, verbose_name='是否已使用')

    def __str__(self):
        return f'{self.email} - {self.code}'

    def is_expired(self):
        from django.utils import timezone
        import datetime
        return (timezone.now() - self.created_at) > datetime.timedelta(minutes=2)


class UserModelConfig(models.Model):
    API_FORMAT_CHOICES = [
        ('openai', 'OpenAI Chat Completions'),
        ('anthropic', 'Anthropic Messages'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='model_configs')
    api_format = models.CharField(max_length=20, choices=API_FORMAT_CHOICES, verbose_name='API格式')
    request_url = models.URLField(max_length=500, verbose_name='请求地址')
    model_id = models.CharField(max_length=200, verbose_name='模型ID')
    api_key = models.CharField(max_length=500, verbose_name='API密钥')
    is_enabled = models.BooleanField(default=False, verbose_name='是否启用')


class ApiInstance(models.Model):
    """用户API实例 — 每个实例拥有独立API key和JSON题库文件"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_instances')
    name = models.CharField(max_length=100, verbose_name='实例名称')
    api_key = models.CharField(max_length=64, unique=True, verbose_name='API密钥')
    json_filename = models.CharField(max_length=255, verbose_name='JSON文件路径')
    script_file = models.FileField(upload_to='api_scripts/', blank=True, null=True, verbose_name='上传脚本')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    def __str__(self):
        return f'{self.user.username} - {self.name}'


class ApiInstanceFile(models.Model):
    """API 实例关联的上传文件"""
    api_instance = models.ForeignKey(ApiInstance, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='api_files/', verbose_name='文件')
    original_name = models.CharField(max_length=500, verbose_name='原始文件名')
    file_path = models.CharField(max_length=500, blank=True, verbose_name='文件路径(文件夹内)')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')

    def __str__(self):
        return f'{self.api_instance.name} - {self.original_name}'


class QuestionList(models.Model):
    """题单"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='question_lists')
    title = models.CharField(max_length=200, verbose_name='题单名称')
    description = models.TextField(blank=True, verbose_name='题单描述')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    def __str__(self):
        return f'{self.user.username} - {self.title}'


class QuestionListItem(models.Model):
    """题单项（题目与题单的关联）"""
    question_list = models.ForeignKey(QuestionList, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name='list_items')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('question_list', 'question')

    def __str__(self):
        return f'{self.question_list.title} - 题目{self.question.id}'


class TestResult(models.Model):
    """自测结果"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='test_results')
    question_list = models.ForeignKey(QuestionList, on_delete=models.CASCADE, related_name='test_results', null=True, blank=True)
    total_questions = models.IntegerField(default=0, verbose_name='总题数')
    correct_count = models.IntegerField(default=0, verbose_name='正确数')
    wrong_count = models.IntegerField(default=0, verbose_name='错误数')
    half_count = models.IntegerField(default=0, verbose_name='半对数')
    total_time = models.IntegerField(default=0, verbose_name='总耗时（秒）')
    completed_at = models.DateTimeField(auto_now_add=True, verbose_name='完成时间')

    def accuracy(self):
        if self.total_questions == 0:
            return 0
        return round(self.correct_count / self.total_questions * 100, 1)


class TestResultItem(models.Model):
    """自测结果-每道题的详情"""
    test_result = models.ForeignKey(TestResult, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name='test_result_items')
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    status = models.CharField(max_length=20, default='wrong', verbose_name='状态（correct/wrong/half）')
    user_answer = models.TextField(blank=True, verbose_name='用户答案')
    time_spent = models.IntegerField(default=0, verbose_name='耗时（秒）')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户模型配置'
        verbose_name_plural = '用户模型配置'

    def __str__(self):
        return f'{self.user.username} - {self.model_id} ({self.get_api_format_display()})'


class QuestionAIChat(models.Model):
    """AI 解析对话记录"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_chats')
    question = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name='ai_chats')
    role = models.CharField(max_length=10, choices=[('ai', 'AI'), ('user', 'User')], verbose_name='角色')
    content = models.TextField(verbose_name='消息内容')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='发送时间')

    class Meta:
        ordering = ['created_at']
        verbose_name = 'AI 对话记录'
        verbose_name_plural = 'AI 对话记录'

    def __str__(self):
        return f'{self.user.username} - 题目{self.question_id} - {self.role}'
