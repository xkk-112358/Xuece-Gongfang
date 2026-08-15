from pathlib import Path
import os

# ==================== 基础配置 ====================
BASE_DIR = Path(__file__).resolve().parent.parent

# 从环境变量读取SECRET_KEY（不要在代码中硬编码！）
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("请设置环境变量 DJANGO_SECRET_KEY")

# DEBUG模式：从环境变量读取，默认False（fail-secure，开发环境在 .env 中显式设为 True）
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

# 允许访问的域名：从环境变量读取，用逗号分隔
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# ==================== 应用配置 ====================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'app1',
    'compressor',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'project1.middleware.LoginCheckMiddleware',  # 自定义中间件
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project1.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'app1.context_processors.encrypted_user_id',  
                'app1.context_processors.unread_notification_count',
            ],
        },
    },
]

WSGI_APPLICATION = 'project1.wsgi.application'

# ==================== 数据库配置 ====================
import sys
if 'test' in sys.argv:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    # 数据库凭据一律从环境变量读取（.env 或系统环境变量），密码无默认值
    DB_NAME = os.environ.get('DB_NAME', 'xuecegongfang')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
    DB_PORT = os.environ.get('DB_PORT', '3306')
    if not DB_PASSWORD:
        raise ValueError("请设置环境变量 DB_PASSWORD（MySQL 数据库密码）")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
            'OPTIONS': {
                'charset': 'utf8mb4',
            },
        },
    }

# ==================== 密码验证 ====================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ==================== 国际化 ====================
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = False  # 使用本地时间，不使用UTC

# ==================== 静态文件配置 ====================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # 生产环境collectstatic收集到的文件放这里
STATICFILES_DIRS = [BASE_DIR / 'static']  # 开发环境静态文件目录

# django-compressor 配置
COMPRESS_ROOT = BASE_DIR / 'static'
COMPRESS_ENABLED = True

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
]

# ==================== 媒体文件配置 ====================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ==================== 文件上传大小限制 ====================
# 增加文件上传大小限制（50MB）
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50MB

# ==================== 登录/登出配置 ====================
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ==================== Session 配置 ====================
SESSION_COOKIE_SECURE = not DEBUG  # 生产环境自动为True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 1209600  # 两周

# ==================== 自定义加密密钥 ====================
# URL 参数加密密钥（使用Fernet算法，必须是32字节的base64编码）
# 生成方式：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 注意：更换此密钥会导致所有已收藏/已分享的加密URL失效，请谨慎操作
URL_ENCRYPTION_KEY = os.environ.get('URL_ENCRYPTION_KEY')
if not URL_ENCRYPTION_KEY:
    raise ValueError(
        "请设置环境变量 URL_ENCRYPTION_KEY（Fernet 加密密钥），"
        "可用 python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" 生成"
    )

# ==================== 默认主键类型 ====================
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# ==================== 安全配置（根据DEBUG自动调整）====================
if DEBUG:
    # 开发环境：不强制HTTPS
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
else:
    # 生产环境：启用HTTPS安全配置
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000  # 1年
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
