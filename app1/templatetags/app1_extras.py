from django import template
from django.conf import settings

register = template.Library()

@register.filter
def split_tags(tags_str):
    """将标签字符串按中文逗号或英文逗号拆分为列表"""
    if not tags_str:
        return []
    import re
    return [t.strip() for t in re.split(r'[，,]', tags_str) if t.strip()]


@register.filter
def get(dict_obj, key):
    try:
        return dict_obj.get(key)
    except (AttributeError, TypeError):
        try:
            return dict_obj[key]
        except (KeyError, TypeError, IndexError):
            return None

@register.filter
def avatar_url(user):
    profile = getattr(user, 'profile', None)
    if profile:
        if profile.avatar:
            return profile.avatar.url
        elif profile.default_avatar:
            return settings.STATIC_URL + profile.default_avatar.replace('\\', '/')
    return settings.STATIC_URL + 'pictures/头像/男生头像1.jpg'

@register.filter
def in_set(value, arg):
    return value in arg

@register.filter
def encrypt_id(obj_id):
    """模板过滤器：加密ID"""
    from app1.utils import encrypt_id
    return encrypt_id(obj_id)


@register.filter
def extract_options(content):
    """从题目内容中提取选择题选项（A.B.C.D.等开头的行）"""
    if not content:
        return []
    options = []
    lines = content.split('\n')
    for line in lines:
        line_stripped = line.strip()
        if line_stripped and len(line_stripped) >= 2 and line_stripped[1] == '.' and line_stripped[0].isupper():
            options.append(line_stripped)
    return options


@register.filter
def render_content(value):
    """渲染题目内容/答案：转义 HTML，将 Markdown 图片 ![alt](url) 转为 <img> 标签"""
    if not value:
        return ''
    import re
    # 先转义 HTML，但保留 <img> 标签（用户只能通过我们的上传接口添加图片）
    escaped = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    # 将 Markdown 图片语法转回 <img> 标签
    # 注意：markdown 里的 URL 不会包含 HTML 特殊字符
    escaped = re.sub(
        r'!\[([^\]]*)\]\(([^)]+)\)',
        r'<img src="\2" alt="\1" style="max-width:100%;">',
        escaped
    )
    return escaped


@register.filter
def strip_number(content):
    """去除题目内容开头的题号（如 '1. '、'1、'等）"""
    if not content:
        return content
    import re
    lines = content.split('\n')
    if lines and re.match(r'^\d+[.、．\s]', lines[0].strip()):
        lines[0] = re.sub(r'^\d+[.、．\s]+', '', lines[0].strip())
    return '\n'.join(lines)


@register.filter
def render_markdown(value):
    """将 Markdown 文本渲染为 HTML（支持表格、代码块等），然后渲染 LaTeX"""
    if not value:
        return ''
    import markdown
    import re
    # 先保护 LaTeX 公式（$$...$$ 和 $...$），防止 markdown 渲染器破坏它们
    latex_blocks = {}
    def protect_latex(m):
        idx = len(latex_blocks)
        placeholder = f'☺LATEX{idx}☺'
        latex_blocks[placeholder] = m.group(0)
        return placeholder
    # 将 [ ... ] 显示公式转为 $$ ... $$
    # 多行 [\n...\n]
    value = re.sub(r'^\[\s*\n([\s\S]*?)\n\s*\]$', r'$$\n\1\n$$', value, flags=re.MULTILINE)
    # 单行 [ ... ]
    value = re.sub(r'^\[\s*([^\n]+?)\s*\]$', r'$$\1$$', value, flags=re.MULTILINE)
    # 保护 \[...\] 显示公式不被 markdown 破坏（markdown 会去掉反斜杠）
    value = re.sub(r'\\\[([\s\S]*?)\\\]', protect_latex, value)
    # 保护 \(...\) 内联公式不被 markdown 破坏
    value = re.sub(r'\\\(([\s\S]*?)\\\)', protect_latex, value)
    # 保护 display math $$...$$
    protected = re.sub(r'\$\$[\s\S]*?\$\$', protect_latex, value)
    # 保护 inline math $...$（逐个匹配以避免冲突）
    protected = re.sub(r'(?<!\$)\$(?!\$)[^\n$]+\$(?!\$)', protect_latex, protected)
    # 渲染 markdown
    html = markdown.markdown(
        protected,
        extensions=['fenced_code', 'tables', 'codehilite']
    )
    # 恢复 LaTeX 公式
    for placeholder, latex in latex_blocks.items():
        html = html.replace(placeholder, latex)
    return html


@register.filter
def format_duration(total_seconds):
    """将秒数转换为 xhxmxs 格式，如果 x 为 0 则不显示"""
    if not total_seconds:
        return '0s'
    total_seconds = int(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    parts = []
    if h:
        parts.append(f'{h}h')
    if m:
        parts.append(f'{m}m')
    if s or not parts:
        parts.append(f'{s}s')
    return ''.join(parts)
