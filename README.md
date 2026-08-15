# 学测工坊（Xuece Gongfang）

一个面向师生的在线学习与刷题平台：**题库导入 → AI 智能提取 → 智能刷题/自测 → 自动判分 → 错题本 → AI 答疑**，并支持题库 API 共享、收藏关注、通知等社区功能。

## 主要功能

- **题库上传与 AI 提取**：支持 docx / pdf / md 文件，docx 通过 OMML→LaTeX 本地转换，pdf 通过 AI 解析；用户可配置自己的 OpenAI 兼容或 Anthropic 模型端点（`个人中心 → 模型配置`）
- **智能刷题与自测**：单选/多选自动判分，填空/解答/判断自我评价；计时、暂停、localStorage 断点续答
- **测试报告与错题本**：正确率统计、错题按科目筛选、一键回看原题、AI 逐题解析
- **AI 答疑**：针对单题的多轮对话（KaTeX 公式渲染、markdown 表格/代码块）
- **题库共享（API 实例）**：生成独立密钥的题库 JSON 接口，支持 zip/tar 打包脚本上传发布
- **社区**：文件/文件夹共享、收藏、关注、多级评论、通知、动态帖子
- **公式渲染**：KaTeX 0.16.9 客户端渲染，懒加载

## 技术栈

Django 5.2 / Python 3.10 / MySQL 8 / Bootstrap 5.3（SnowAdmin 主题）/ jQuery / KaTeX / Tailwind v4 / django-compressor / whitenoise

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制模板并填写）
cp .env.example .env

# 3. 初始化数据库
python manage.py migrate

# 4. 启动
python manage.py runserver 0.0.0.0:8000
```

### 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `DJANGO_SECRET_KEY` | ✅ | Django 密钥，`python -c "import secrets; print(secrets.token_urlsafe(50))"` 生成 |
| `URL_ENCRYPTION_KEY` | ✅ | Fernet 密钥（URL 参数加密），`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成；更换会导致已分享链接失效 |
| `DB_PASSWORD` | ✅ | MySQL 密码（`DB_NAME`/`DB_USER`/`DB_HOST`/`DB_PORT` 可选，有默认值） |
| `DJANGO_DEBUG` | | 默认 `False`（生产安全），开发环境设 `True` |
| `DJANGO_ALLOWED_HOSTS` | | 逗号分隔，默认 `localhost,127.0.0.1` |
| `DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` | | 内置命令（如 `python manage.py retag_all`）使用的 AI 密钥 |

### 常用命令

```bash
python manage.py retag_all   # 清空题目标签并用 AI 重新生成（需配置 AI 密钥）
python manage.py collectstatic
```

## 安全说明

- 所有敏感配置（密钥、数据库密码、AI API Key）一律通过环境变量 / `.env` 提供，`.env` 已被 `.gitignore` 排除
- URL 中的 ID 全部经 Fernet 加密，防止枚举越权
- 生产环境请确保 `DJANGO_DEBUG=False` 并通过 HTTPS 部署
- `media/`（用户上传）、`api_instances/`（题库 JSON）、`staticfiles/`（collectstatic 产物）不纳入版本库

## 项目结构

```
project1/            # 项目配置（settings/urls/middleware/wsgi/asgi）
app1/                # 业务代码（models/views/utils/docx_math/management）
templates/           # 前端模板（37 个页面）
static/              # 静态资源（CSS/JS/文档/供应商主题）
```
