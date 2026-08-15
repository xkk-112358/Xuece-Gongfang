from django.core.management.base import BaseCommand
from app1.models import Upload, QuestionBank
from django.db import close_old_connections
from openai import OpenAI
import os
import time

# 密钥一律从环境变量读取，禁止硬编码（通过 .env 或系统环境变量配置）
AI_MODEL_CONFIGS = {
    'deepseek-v4-flash': {
        'api_key': os.environ.get('DEEPSEEK_API_KEY', ''),
        'base_url': os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1'),
    },
    'qwen3.5-27b': {
        'api_key': os.environ.get('DASHSCOPE_API_KEY', ''),
        'base_url': os.environ.get('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
    },
}

def get_ai_client(model_name):
    config = AI_MODEL_CONFIGS.get(model_name, AI_MODEL_CONFIGS['qwen3.5-27b'])
    if not config['api_key']:
        raise ValueError(
            f'未配置 {model_name} 的 API 密钥，请设置环境变量 '
            f'{"DEEPSEEK_API_KEY" if model_name == "deepseek-v4-flash" else "DASHSCOPE_API_KEY"}'
        )
    return OpenAI(api_key=config['api_key'], base_url=config['base_url'])

class Command(BaseCommand):
    help = '清空所有题目标签并使用AI重新生成'

    def handle(self, *args, **options):
        # 步骤1：收集所有已有标签供AI参考
        self.stdout.write('收集已有标签...')
        existing_tags_list = list(QuestionBank.objects.exclude(tags='').values_list('tags', flat=True))
        all_existing_tags = set()
        for t in existing_tags_list:
            for tag in t.split('，'):
                tag = tag.strip()
                if tag:
                    all_existing_tags.add(tag)
        self.stdout.write(f'找到 {len(all_existing_tags)} 个已有标签')

        # 步骤2：清空所有标签
        self.stdout.write('正在清空所有已有标签...')
        count = QuestionBank.objects.exclude(tags='').count()
        QuestionBank.objects.all().update(tags='')
        self.stdout.write(f'已清空 {count} 道题目的标签')

        # 步骤3：获取所有已完成的文件，按用户分组
        uploads = Upload.objects.filter(processing_status='completed').order_by('user_id', 'id')
        self.stdout.write(f'找到 {uploads.count()} 个已完成文件，开始重新打标签\n')

        total_questions = 0
        for upload in uploads:
            questions = QuestionBank.objects.filter(upload=upload).order_by('id')
            if not questions.exists():
                continue

            # 收集该用户已有的标签（其他文件的标签）
            user_tags = set()
            user_tag_records = QuestionBank.objects.filter(upload__user=upload.user).exclude(tags='').values_list('tags', flat=True)
            for t in user_tag_records:
                for tag in t.split('，'):
                    tag = tag.strip()
                    if tag:
                        user_tags.add(tag)

            self.stdout.write(f'处理文件 [{upload.id}] {upload.file_name}（{questions.count()} 道题，用户已有标签 {len(user_tags)} 个）...')

            # 分批发送给AI（每批15道题）
            question_list = list(questions)
            batch_size = 15
            for i in range(0, len(question_list), batch_size):
                batch = question_list[i:i+batch_size]
                self._retag_batch(batch, list(user_tags), upload.id)
                total_questions += len(batch)
                self.stdout.write(f'  已完成 {total_questions} 道题...')
                time.sleep(1)  # 避免API限流

            # 更新该文件状态
            upload.processing_status = 'completed'
            upload.save(update_fields=['processing_status'])
            close_old_connections()

        self.stdout.write(self.style.SUCCESS(f'\n全部完成！共处理 {total_questions} 道题目。'))

    def _retag_batch(self, questions, existing_tags, upload_id):
        """对一批题目调用AI重新生成标签"""
        tags_hint = ""
        if existing_tags:
            tags_str = "、".join(existing_tags[:100])
            tags_hint = f"请优先从以下标签中选择（如果没有合适的再创建新标签，新标签应简洁通用，2-6个字）：\n{tags_str}"

        # 构造题目列表输入
        questions_text = ""
        for idx, q in enumerate(questions, 1):
            questions_text += f"题{idx}：{q.content}\n答案：{q.answer}\n原题型：{q.question_type}\n\n"

        prompt = f"""请为以下每道题重新生成知识点标签。

要求：
1. 每道题输出标签，格式为"题号：标签1，标签2，标签3"
2. 每道题1~3个标签，多个标签用中文逗号分隔
3. 标签应概括题目的核心知识点，不要过于详细（不要出现具体人名、地名、年代数字等细节）
4. 标签应通用、简洁（2-6个字）
{tags_hint}

题目列表：
{questions_text}
请按格式输出每道题的标签："""

        try:
            client = get_ai_client('deepseek-v4-flash')
            response = client.chat.completions.create(
                model='deepseek-v4-flash',
                messages=[
                    {"role": "system", "content": "你是一个专业的知识点标签生成助手，请严格按要求格式输出。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=4000,
                timeout=120
            )

            output = response.choices[0].message.content
            self._parse_and_save_tags(output, questions, existing_tags)

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'    AI调用失败: {e}，尝试使用备用模型...'))
            try:
                close_old_connections()
                client = get_ai_client('qwen3.5-27b')
                response = client.chat.completions.create(
                    model='qwen3.5-27b',
                    messages=[
                        {"role": "system", "content": "你是一个专业的知识点标签生成助手，请严格按要求格式输出。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4000,
                    timeout=120
                )
                output = response.choices[0].message.content
                self._parse_and_save_tags(output, questions, existing_tags)
            except Exception as e2:
                self.stdout.write(self.style.ERROR(f'    备用模型也失败: {e2}'))

    def _parse_and_save_tags(self, output, questions, existing_tags):
        """解析AI输出并保存标签"""
        lines = output.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 匹配 "题号：标签" 格式
            if '：' in line:
                parts = line.split('：', 1)
            elif ':' in line:
                parts = line.split(':', 1)
            else:
                continue

            num_part = parts[0].strip()
            tags_str = parts[1].strip()

            # 提取题号
            import re
            num_match = re.search(r'(\d+)', num_part)
            if not num_match:
                continue

            idx = int(num_match.group(1)) - 1
            if idx < 0 or idx >= len(questions):
                continue

            # 清理标签：去除多余分隔符和空格
            cleaned_tags = []
            for tag in tags_str.replace('，', ',').split(','):
                tag = tag.strip().strip('，、,')
                if tag and len(tag) <= 20:
                    cleaned_tags.append(tag)

            if cleaned_tags:
                final_tags = '，'.join(cleaned_tags[:3])
                QuestionBank.objects.filter(id=questions[idx].id).update(tags=final_tags)
                # 将新标签加入已有标签库
                for tag in cleaned_tags:
                    existing_tags.append(tag)
