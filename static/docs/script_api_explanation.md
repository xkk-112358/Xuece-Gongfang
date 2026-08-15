# script.py API 配置与 JSON 文件相关代码解释

## 一、云端题库配置

```python
# ==================== 云端题库配置 ====================
SERVER_URL = "https://your-server.example.com"
QUESTION_BANK_API_URL = f"{SERVER_URL}/api/question_bank/"
QUESTION_BANK_API_KEY = "your-api-key"
```

| 变量 | 说明 |
|------|------|
| `SERVER_URL` | 服务器地址，部署后需改为实际域名或 IP |
| `QUESTION_BANK_API_URL` | 题库 API 接口地址，拼接 `SERVER_URL` 构成 |
| `QUESTION_BANK_API_KEY` | 你在系统中创建 API 实例后获得的密钥 |

用户在系统「接口文档」页面创建 API 实例后，系统会自动分配一个 `QUESTION_BANK_API_KEY`（格式如 `qbank_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`），将生成的 API Key 替换上述配置中的 `QUESTION_BANK_API_KEY` 即可连接自己的题库。

---

## 二、KnowledgeBase 类的核心机制

`KnowledgeBase` 类封装了题库的 **加载 → 查询 → 更新 → 同步** 全流程。

### 2.1 初始化与数据加载 (`load`)

```python
class KnowledgeBase:
    def __init__(self, db_file="question_bank.json"):
        self.db_file = Path(db_file)
        self.questions = self.load()

    def load(self):
        """从云端加载知识库，失败时回退到本地文件"""
        try:
            resp = requests.get(QUESTION_BANK_API_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # ... 解析 data 中的 questions / wrong_questions ...
                return q_data
        except:
            pass  # 回退到本地文件
        # 从本地 JSON 文件读取
        if self.db_file.exists():
            with open(self.db_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        return {"questions": [], "wrong_questions": [], "last_updated": None}
```

- 优先从云端（GET 请求）拉取最新题库数据
- 若云端连接失败，回退到本地 `question_bank.json` 文件
- 返回数据结构：`{ "questions": [...], "wrong_questions": [...], "last_updated": "..." }`

### 2.2 数据持久化与云端同步 (`save`)

```python
def save(self):
    # 1. 先拉取云端最新数据，合并后再上传，避免冲掉别人的数据
    resp = requests.get(QUESTION_BANK_API_URL, timeout=10)
    # 保留云端的完整题库
    self.questions["questions"] = cloud_data["questions"]

    # 2. 更新 last_updated 时间戳
    self.questions["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 3. 保存到本地 JSON 文件
    with open(self.db_file, 'w', encoding='utf-8') as f:
        json.dump(self.questions, f, ensure_ascii=False, indent=2)

    # 4. 同步到云端（POST 请求）
    headers = {"X-API-Key": QUESTION_BANK_API_KEY, "Content-Type": "application/json"}
    requests.post(QUESTION_BANK_API_URL, json=self.questions, headers=headers)
```

保存流程说明：

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | GET 拉取云端数据 | 合并前先获取云端最新数据，避免覆盖他人提交的题目 |
| 2 | 更新时间戳 | 记录本次更新的时间 |
| 3 | 写本地 JSON | 备份到本地 `question_bank.json` 文件 |
| 4 | POST 同步云端 | 通过 API 将数据上传到服务器 |

### 2.3 题目哈希生成 (`generate_hash`)

```python
def generate_hash(self, question_text, options):
    normalized_q = self._normalize_text(question_text)
    sorted_options = sorted([...], key=lambda x: x[1])
    options_str = "||".join([f"{content}" for ...])
    unique_str = f"{normalized_q}||{options_str}"
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:16]
```

- 将题目文本和选项内容归一化（去标点、去空格、统一小写）
- 选项按内容排序后拼接
- 取 MD5 前 16 位作为唯一标识，用于判重和匹配

### 2.4 错题添加 (`add_wrong_question`)

```python
def add_wrong_question(self, question_info):
    q_hash = self.generate_hash(question_text, options)
    # 若已存在相同哈希则更新 last_seen，否则新增
    new_question = {
        "hash": q_hash,
        "type": question_info["type"],
        "question_text": question_info["question_text"],
        "options": text_options,
        "correct_answer": question_info["correct_answer"],
        "correct_answer_content": question_info.get("correct_answer_content", ""),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    self.questions["wrong_questions"].append(new_question)
    self.save()
```

- 基于哈希判重，相同题目不会重复添加
- 每条错题记录包含：哈希、类型、题目文本、选项、正确答案、创建/最近看到时间

---

## 三、JSON 文件数据结构

系统自动创建的 JSON 文件（如 `13_大学物理实验_20260610174942.json`）格式如下：

```json
{
  "questions": [
    {
      "hash": "7f420306b99a1994",
      "type": "单选题",
      "question_text": "本实验证明的（）的转动惯量的平行轴定理。",
      "options": {
        "A": "金属细杆",
        "B": "金属细杆和滑块",
        "C": "一个滑块",
        "D": "两个滑块"
      },
      "correct_answer": "C",
      "correct_answer_content": "一个滑块",
      "created_at": "2026-05-24 10:49:10",
      "last_seen": "2026-05-24 10:49:10"
    }
  ],
  "wrong_questions": [
    {
      "hash": "ca5620228dedd88b",
      "type": "单选题",
      "question_text": "...",
      "options": { "A": "...", "B": "..." },
      "correct_answer": "A",
      "correct_answer_content": "...",
      "created_at": "2026-05-24 11:02:48",
      "last_seen": "2026-05-24 11:02:48"
    }
  ],
  "last_updated": "2026-05-24 21:33:21",
  "instance_name": "大学物理实验",
  "instance_id": 3
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `questions` | 完整题库（所有题目） |
| `wrong_questions` | 错题集合 |
| `last_updated` | 最后更新时间 |
| `instance_name` | API 实例名称 |
| `instance_id` | API 实例 ID |

每条题目记录的字段：

| 字段 | 说明 |
|------|------|
| `hash` | 基于题目文本和选项生成的 MD5 哈希，用于唯一标识和判重 |
| `type` | 题目类型：单选题 / 多选题 / 判断题 / 填空题 / 解答题 |
| `question_text` | 题目内容 |
| `options` | 选项字典，如 `{ "A": "内容1", "B": "内容2" }` |
| `correct_answer` | 正确答案的字母（如 "A"）或组合（如 "A、C"） |
| `correct_answer_content` | 正确答案对应的文本内容 |
| `created_at` | 首次收录时间 |
| `last_seen` | 最近一次出现时间 |

---

## 四、API 接口调用方式

### GET 请求 — 获取题库数据

```python
import requests

SERVER_URL = "https://your-server.example.com"
QUESTION_BANK_API_KEY = "你的API_KEY"

resp = requests.get(
    f"{SERVER_URL}/api/question_bank/",
    params={"api_key": QUESTION_BANK_API_KEY}
)
data = resp.json()
print(data)
```

### POST 请求 — 上传/同步题库数据

```python
import requests

SERVER_URL = "https://your-server.example.com"
QUESTION_BANK_API_KEY = "你的API_KEY"

payload = {
    "questions": [],
    "wrong_questions": [],
    "last_updated": "2026-06-10 12:00:00"
}

resp = requests.post(
    f"{SERVER_URL}/api/question_bank/",
    json=payload,
    headers={
        "X-API-Key": QUESTION_BANK_API_KEY,
        "Content-Type": "application/json"
    }
)
print(resp.status_code)
```

> **提示**：GET 请求将 `api_key` 放在 URL 参数中即可；POST 请求需将 API Key 放在 `X-API-Key` 请求头中。
