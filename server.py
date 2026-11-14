#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个人综合健康助手 v1.0 —— 后端服务
纯 Python 标准库实现，无第三方依赖，双击「启动健康助手.bat」即可运行。
启动后会自动打开浏览器访问 http://127.0.0.1:8765
"""

import base64
import hashlib
import json
import os
import re
import secrets
import socket
import uuid
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 让 Windows 控制台能正常打印中文
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------- 路径与常量 ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
PROMPT_FILE = os.path.join(BASE_DIR, "01-人设与系统提示词.md")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
HEALTH_DB = os.path.join(DATA_DIR, "health.db")   # 常规档案 + 对话历史 + 画像
SEX_DB = os.path.join(DATA_DIR, "sexual.db")      # 性健康档案（独立库）
IMAGES_DIR = os.path.join(DATA_DIR, "images")     # 对话里的图片（本地保存）

HOST = "0.0.0.0"   # 监听所有网卡：本机 127.0.0.1 + 局域网 IP + Tailscale 虚拟 IP 都能访问
PORT = 8765

MAX_HISTORY_CHARS = 8000   # 带入上下文的历史消息总字符上限（省 token、控成本）

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model_fast": "deepseek-flash",      # 快速模式：便宜、支持视觉
    "model_deep": "deepseek-v4-pro",     # 深度分析：更强
    "temperature": 1.0,
    "access_password": "",               # 远程访问密码（首次启动自动生成 6 位数字）
}

# 提示词正文的起止标记（对应 01 文件里的复制标记）
PROMPT_START = "▽▽▽ 提示词正文开始"
PROMPT_END = "▽▽▽ 提示词正文结束"

FALLBACK_PROMPT = (
    "你是「知衡」，用户的个人循证健康顾问。你不是医生，不做诊断、不开处方、"
    "不给具体剂量、不替代就医。回答要客观、全面、靠谱，说人话。"
    "急症请立即建议拨打 120。"
)

# ---------------- 用户画像（从对话中自动提炼） ----------------
REFINE_THRESHOLD = 5      # 每累计多少条用户消息触发一次提炼
RECENT_EXPIRE_DAYS = 7    # 近期状态多少天后不再注入上下文

REFINE_PROMPT = (
    "你是「知衡」的后台信息整理器。下面是一段用户与健康助手的对话记录。\n"
    "请从中提炼两类信息，严格只输出 JSON（不要输出任何其他文字、不要 markdown 代码块）：\n"
    '{"长期画像":[{"内容":"...","领域":"..."}],"近期状态":[{"内容":"...","领域":"..."}]}\n\n'
    "规则：\n"
    "1. 长期画像：用户透露的、长期稳定的信息（疾病史、过敏、慢性困扰、固定生活习惯、长期关注方向）；没有就输出空数组 []。\n"
    "2. 近期状态：临时的、可能很快改变的信息（如「这周熬夜」「最近有点累」「这两天感冒」）；没有就输出空数组 []。\n"
    "3. 只提炼对话里明确出现的信息，绝不臆测、绝不推断。\n"
    "4. 「领域」只能从以下选一个：健康背景、生活方式、心理认知、性健康、关注方向、其他。\n"
    "5. 「内容」用一句客观陈述，直接说事实，不要用第二人称、不要带「用户」字样。\n"
)

# ---------------- 安全兜底（在调用模型之前先拦截） ----------------
EMERGENCY_PATTERNS = [
    r"胸痛|心绞痛|胸口.{0,4}(闷|疼|痛|压)",
    r"呼吸困难|喘不上气|喘不过气|气短|憋气",
    r"意识不清|昏迷|晕倒|昏厥|不省人事|叫不醒",
    r"大出血|吐.{0,3}血|咯血|便血.{0,3}(多|大量)",
    r"突发.{0,6}(剧烈|炸裂|要炸).{0,4}头痛",
    r"半边(身体|身子|脸|胳膊|腿).{0,4}(无力|麻木|动不了)|口角歪斜|言语不清|说话.{0,4}不清",
    r"严重过敏|喉头水肿|过敏性休克|全身.{0,4}红疹.{0,4}(呼吸|肿)",
    r"(吃|服|吞)了.{0,6}(很多|过量|一瓶|一把).{0,4}药|药物过量|服药过量",
]

CRISIS_PATTERNS = [
    r"自杀|不想活|想死|结束生命|活着(没|无)意思|轻生",
    r"自残|割腕|割手|跳楼|上吊|安眠药.{0,4}(自杀|寻死)",
]

EMERGENCY_CARD = (
    "⚠️ **紧急提醒**：你描述的情况可能是需要立即就医的急症。\n\n"
    "请**马上拨打 120（急救）**，或让身边人送你去最近的急诊，**不要自行驾车**。\n\n"
    "等待期间：保持冷静；如果患者意识不清，让其**侧卧**、保持呼吸道通畅；"
    "不要给昏迷者喂水喂药。\n\n"
    "——如果你只是想了解相关知识、并不是现在正在发生，请告诉我，我会正常回答你。"
)

CRISIS_CARD = (
    "🆘 如果你此刻有伤害自己的念头或计划，请**立即联系你信任的人**，"
    "或拨打全国心理援助热线 **12356**（24 小时）；情况紧急请拨打 **120** 或前往最近医院急诊。\n\n"
    "你不需要一个人扛，现在找人陪着你是最重要的事。\n\n"
    "——如果你只是想聊聊情绪、并不是现在有危险，请告诉我，我会好好听你说。"
)

SEX_TOPIC_KEYWORDS = [
    "性", "避孕", "安全套", "套", "月经", "例假", "痛经", "白带", "阴道", "阴茎", "睾丸",
    "遗精", "自慰", "手淫", "性欲", "性功能", "勃起", "早泄", "射精", "高潮",
    "HPV", "hiv", "艾滋病", "梅毒", "淋病", "尖锐湿疣", "生殖器", "性传播", "性病",
    "怀孕", "紧急避孕", "暴露后预防", "PEP", "窗口期",
]


# ---------------- 基础工具 ----------------
def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)


def get_db(path):
    """每次新建一个连接，用完关闭，避免多线程冲突。"""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    ensure_data_dir()
    conn = get_db(HEALTH_DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, ts INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS image ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, domain TEXT, "
            "source TEXT, created_at INTEGER, updated_at INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS recent_state ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, domain TEXT, "
            "source TEXT, created_at INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        # 老库迁移：给 messages 加上 images 列（存本轮图片文件名 JSON 数组）
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
        if "images" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN images TEXT DEFAULT '[]'")
        conn.commit()
    finally:
        conn.close()

    conn = get_db(SEX_DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT)"
        )
        conn.commit()
    finally:
        conn.close()


# ---------------- 配置 ----------------
_config_lock = threading.Lock()


def load_config():
    with _config_lock:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(cfg)
                return merged
            except Exception:
                pass
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with _config_lock:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------------- 远程访问鉴权 ----------------
AUTH_COOKIE = "hz_auth"
AUTH_MAX_AGE = 60 * 60 * 24 * 30   # cookie 记住 30 天


def _hash_pw(pw):
    return hashlib.sha256(("hz:" + (pw or "")).encode("utf-8")).hexdigest()


def get_lan_ip():
    """探测本机在局域网中的 IP（用于打印给用户访问）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()


def ensure_access_password():
    """确保已设置访问密码，返回当前密码；首次自动生成 6 位数字。"""
    cfg = load_config()
    pw = (cfg.get("access_password") or "").strip()
    if not pw:
        pw = "".join(str(secrets.randbelow(10)) for _ in range(6))
        cfg["access_password"] = pw
        save_config(cfg)
    return pw


LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>知衡 · 访问验证</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: linear-gradient(160deg, #0f766e 0%, #134e4a 100%);
    min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px;
  }
  .card {
    background: #fff; border-radius: 16px; padding: 32px 24px; width: 100%; max-width: 340px;
    box-shadow: 0 12px 40px rgba(0,0,0,.25); text-align: center;
  }
  h1 { font-size: 22px; color: #0f766e; margin-bottom: 6px; }
  .sub { font-size: 13px; color: #64748b; margin-bottom: 20px; line-height: 1.6; }
  input {
    width: 100%; font-size: 20px; text-align: center; letter-spacing: 4px;
    padding: 12px; border: 1px solid #cbd5e1; border-radius: 10px; outline: none;
  }
  input:focus { border-color: #0f766e; }
  button {
    width: 100%; margin-top: 14px; padding: 12px; font-size: 16px; color: #fff;
    background: #0f766e; border: none; border-radius: 10px; cursor: pointer;
  }
  button:active { background: #0b5d57; }
  #err { color: #dc2626; font-size: 13px; margin-top: 12px; min-height: 18px; }
</style>
</head>
<body>
  <div class="card">
    <h1>知衡</h1>
    <div class="sub">输入访问密码进入<br>（电脑启动窗口里有显示）</div>
    <input type="password" id="pw" inputmode="numeric" placeholder="6 位数字密码" autocomplete="current-password">
    <button id="go">进入</button>
    <div id="err"></div>
  </div>
<script>
var go = document.getElementById('go');
var pw = document.getElementById('pw');
var err = document.getElementById('err');
function submit(){
  var v = pw.value.trim();
  err.textContent = '';
  if(!v){ err.textContent = '请输入密码'; return; }
  go.disabled = true;
  fetch('/api/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({password: v})
  }).then(function(r){ return r.json().then(function(d){ return {status:r.status, d:d}; }); })
    .then(function(o){
      if(o.d && o.d.ok){ location.reload(); }
      else { err.textContent = (o.d && o.d.error) || '密码错误'; go.disabled = false; }
    })
    .catch(function(){ err.textContent = '网络错误，请重试'; go.disabled = false; });
}
go.onclick = submit;
pw.addEventListener('keydown', function(e){ if(e.key === 'Enter') submit(); });
pw.focus();
</script>
</body>
</html>"""


# ---------------- 提示词 ----------------
def load_prompt():
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return FALLBACK_PROMPT
    i = text.find(PROMPT_START)
    if i == -1:
        return text.strip() or FALLBACK_PROMPT
    # 正文从开始标记那一行的下一行开始
    nl = text.find("\n", i)
    start = nl + 1 if nl != -1 else len(text)
    j = text.find(PROMPT_END, start)
    if j == -1:
        end = len(text)
    else:
        # 回到结束标记所在行的行首，避免把行首的"## "混进正文
        prev = text.rfind("\n", start, j)
        end = prev + 1 if prev != -1 else j
    body = text[start:end].strip()
    return body or FALLBACK_PROMPT


# ---------------- 档案 ----------------
def get_profile(db_path):
    conn = get_db(db_path)
    try:
        row = conn.execute("SELECT data FROM profile WHERE id=1").fetchone()
        if row and row["data"]:
            try:
                return json.loads(row["data"])
            except Exception:
                return {}
        return {}
    finally:
        conn.close()


def set_profile(db_path, data):
    conn = get_db(db_path)
    try:
        conn.execute(
            "INSERT INTO profile(id, data) VALUES(1, ?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (json.dumps(data, ensure_ascii=False),),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------- 对话历史 ----------------
def append_message(role, content, images=None):
    conn = get_db(HEALTH_DB)
    try:
        conn.execute(
            "INSERT INTO messages(role, content, images, ts) VALUES(?,?,?,?)",
            (role, content, json.dumps(images or [], ensure_ascii=False), int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def get_messages():
    conn = get_db(HEALTH_DB)
    try:
        rows = conn.execute(
            "SELECT role, content, images FROM messages ORDER BY id DESC LIMIT 200"
        ).fetchall()
    finally:
        conn.close()
    rows = list(reversed(rows))  # 旧 -> 新
    out, total = [], 0
    for r in rows:
        if total + len(r["content"]) > MAX_HISTORY_CHARS:
            break
        try:
            imgs = json.loads(r["images"] or "[]")
        except Exception:
            imgs = []
        out.append({"role": r["role"], "content": r["content"], "images": imgs})
        total += len(r["content"])
    return out


def clear_messages():
    conn = get_db(HEALTH_DB)
    try:
        conn.execute("DELETE FROM messages")
        conn.commit()
    finally:
        conn.close()


# ---------------- 元信息（提炼计数器 / 开关） ----------------
def get_meta(key, default="0"):
    conn = get_db(HEALTH_DB)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_meta(key, value):
    conn = get_db(HEALTH_DB)
    try:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------- 长期画像 ----------------
def get_image_items():
    conn = get_db(HEALTH_DB)
    try:
        rows = conn.execute(
            "SELECT id, content, domain, source, created_at, updated_at "
            "FROM image ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_image_item(content, domain, source):
    conn = get_db(HEALTH_DB)
    try:
        now = int(time.time())
        cur = conn.execute(
            "INSERT INTO image(content, domain, source, created_at, updated_at) "
            "VALUES(?,?,?,?,?)",
            (content, domain, source, now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_image_item(item_id, content, domain):
    conn = get_db(HEALTH_DB)
    try:
        conn.execute(
            "UPDATE image SET content=?, domain=?, updated_at=? WHERE id=?",
            (content, domain, int(time.time()), item_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_image_item(item_id):
    conn = get_db(HEALTH_DB)
    try:
        conn.execute("DELETE FROM image WHERE id=?", (item_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------- 近期状态 ----------------
def get_recent_items():
    conn = get_db(HEALTH_DB)
    try:
        rows = conn.execute(
            "SELECT id, content, domain, source, created_at FROM recent_state ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_recent_item(content, domain, source):
    conn = get_db(HEALTH_DB)
    try:
        conn.execute(
            "INSERT INTO recent_state(content, domain, source, created_at) VALUES(?,?,?,?)",
            (content, domain, source, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def delete_recent_item(item_id):
    conn = get_db(HEALTH_DB)
    try:
        conn.execute("DELETE FROM recent_state WHERE id=?", (item_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------- 安全检测 ----------------
def safety_check(text):
    for pat in CRISIS_PATTERNS:
        if re.search(pat, text):
            return CRISIS_CARD
    for pat in EMERGENCY_PATTERNS:
        if re.search(pat, text):
            return EMERGENCY_CARD
    return None


def is_sexual_topic(text):
    low = text.lower()
    return any(k.lower() in low for k in SEX_TOPIC_KEYWORDS)


# ---------------- 构造消息 ----------------
def build_image_context():
    """构造画像上下文文本（长期画像 + 近期状态），无内容返回 ''。"""
    parts = []
    images = get_image_items()
    if images:
        lines = ["- " + r["content"] + "（领域：" + r["domain"] + "）" for r in images]
        parts.append(
            "【从历史对话提炼的长期画像（AI 自动整理，未经逐条确认，"
            "回答时可参考但不必全信）】\n" + "\n".join(lines)
        )
    now = int(time.time())
    cutoff = now - RECENT_EXPIRE_DAYS * 86400
    recents = [r for r in get_recent_items() if int(r["created_at"] or 0) >= cutoff]
    if recents:
        lines = ["- " + r["content"] + "（领域：" + r["domain"] + "）" for r in recents]
        parts.append("【近期状态（最近 7 天内记录，可能已过时）】\n" + "\n".join(lines))
    return "\n\n".join(parts)


def build_messages(user_text, image_data_urls=None):
    system = load_prompt()

    profile = get_profile(HEALTH_DB)
    if profile:
        system += (
            "\n\n【用户健康档案（仅在与问题相关时引用；档案里没有的信息不要假设、不要编）】\n"
            + json.dumps(profile, ensure_ascii=False, indent=1)
        )

    # 性健康档案模块已按用户要求从「我的档案」中移除，不再注入。
    # 如需恢复：取消本行下方三行注释，并恢复前端表单即可（data/sexual.db 仍保留）。
    # sp = get_profile(SEX_DB)
    # if sp:
    #     system += "\n\n【用户性健康档案】\n" + json.dumps(sp, ensure_ascii=False, indent=1)

    image_ctx = build_image_context()
    if image_ctx:
        system += "\n\n" + image_ctx

    msgs = [{"role": "system", "content": system}]
    for m in get_messages():
        c = m.get("content") or ""
        if m.get("images"):
            c = (c + "（此条发言还附带了图片）").strip()
        msgs.append({"role": m["role"], "content": c})

    if image_data_urls:
        blocks = [{"type": "text", "text": user_text or "请看看我发的图片。"}]
        for url in image_data_urls[:4]:
            blocks.append({
                "type": "image_url",
                "image_url": {"url": url, "detail": "auto"},
            })
        msgs.append({"role": "user", "content": blocks})
    else:
        msgs.append({"role": "user", "content": user_text})
    return msgs


def save_images(data_urls):
    """把前端传来的 data:image/...;base64,... 列表解码后存成本地文件，返回文件名列表。"""
    names = []
    for url in (data_urls or [])[:4]:
        if not isinstance(url, str):
            continue
        m = re.match(r"^data:image/(jpeg|png|gif|webp);base64,(.+)$", url, re.I | re.S)
        if not m:
            continue
        ext = {"jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}[m.group(1).lower()]
        try:
            raw = base64.b64decode(m.group(2), validate=False)
        except Exception:
            continue
        if len(raw) > 12 * 1024 * 1024:   # 单图上限 12MB
            continue
        name = uuid.uuid4().hex + "." + ext
        try:
            with open(os.path.join(IMAGES_DIR, name), "wb") as f:
                f.write(raw)
            names.append(name)
        except Exception:
            continue
    return names


# ---------------- 调用 DeepSeek（流式） ----------------
def call_deepseek_stream(msgs, cfg, mode):
    """生成器：逐段产出模型返回的正文增量。"""
    if mode == "deep":
        model = cfg.get("model_deep") or "deepseek-v4-pro"
        thinking = {"type": "enabled"}
    else:
        model = cfg.get("model_fast") or "deepseek-flash"
        thinking = {"type": "disabled"}

    payload = {
        "model": model,
        "messages": msgs,
        "stream": True,
        "thinking": thinking,
    }
    if thinking["type"] == "disabled":
        try:
            payload["temperature"] = float(cfg.get("temperature", 1.0))
        except Exception:
            payload["temperature"] = 1.0

    base_url = (cfg.get("base_url") or "https://api.deepseek.com").rstrip("/")
    url = base_url + "/chat/completions"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (cfg.get("api_key") or ""),
            "Accept": "text/event-stream",
        },
    )

    resp = urllib.request.urlopen(req, timeout=180)
    try:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content
            except Exception:
                continue
    finally:
        try:
            resp.close()
        except Exception:
            pass


# ---------------- 画像提炼 ----------------
_refine_lock = threading.Lock()


def parse_refine_json(content):
    """从模型输出里提取 JSON（容忍 markdown 代码块包裹）。"""
    text = (content or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
    except Exception:
        return {"long": [], "recent": []}

    def _clean(items):
        out = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            c = (it.get("内容") or "").strip()
            if not c:
                continue
            d = (it.get("领域") or "其他").strip()
            out.append({"content": c, "domain": d})
        return out

    return {"long": _clean(data.get("长期画像")), "recent": _clean(data.get("近期状态"))}


def call_refine(messages, cfg):
    """非流式调用 flash 提炼画像，返回 parse_refine_json 结果。"""
    model = cfg.get("model_fast") or "deepseek-flash"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": REFINE_PROMPT},
            {"role": "user", "content": "对话记录：\n" + json.dumps(messages, ensure_ascii=False, indent=1)},
        ],
        "stream": False,
        "thinking": {"type": "disabled"},
        "temperature": 0.2,
    }
    base_url = (cfg.get("base_url") or "https://api.deepseek.com").rstrip("/")
    url = base_url + "/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (cfg.get("api_key") or ""),
        },
    )
    resp = urllib.request.urlopen(req, timeout=180)
    try:
        body = resp.read().decode("utf-8", errors="replace")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    obj = json.loads(body)
    content = ""
    try:
        content = obj["choices"][0]["message"]["content"]
    except Exception:
        pass
    return parse_refine_json(content)


def do_refine(force=False):
    """执行一次提炼。force=True 时忽略计数。返回结果 dict。"""
    with _refine_lock:
        cfg = load_config()
        if not cfg.get("api_key"):
            return {"ok": False, "error": "no_key"}
        n = int(get_meta("refine_counter", "0") or 0)
        if not force and n < REFINE_THRESHOLD:
            return {"ok": True, "skipped": True, "counter": n}
        set_meta("refine_counter", 0)
        msgs = get_messages()
        if not msgs:
            return {"ok": True, "skipped": True, "counter": 0}
        try:
            result = call_refine(msgs, cfg)
        except Exception as e:
            set_meta("refine_counter", n)  # 失败恢复计数，避免丢失
            return {"ok": False, "error": str(e)}
        source = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        existing = {r["content"] for r in get_image_items()}
        added_long = 0
        for it in result.get("long", []):
            c = it["content"]
            if c not in existing:
                add_image_item(c, it["domain"], source)
                existing.add(c)
                added_long += 1
        added_recent = 0
        for it in result.get("recent", []):
            add_recent_item(it["content"], it["domain"], source)
            added_recent += 1
        return {"ok": True, "added_long": added_long, "added_recent": added_recent}


def maybe_refine_async():
    """后台线程入口：达到阈值才提炼，静默失败。"""
    try:
        do_refine(force=False)
    except Exception:
        pass


def note_user_message():
    """记录一条用户消息：递增提炼计数，达到阈值后异步触发提炼。"""
    n = int(get_meta("refine_counter", "0") or 0) + 1
    set_meta("refine_counter", n)
    if n >= REFINE_THRESHOLD:
        threading.Thread(target=maybe_refine_async, daemon=True).start()


# ---------------- HTTP 处理 ----------------
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "HealthAssistant/1.0"

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("[%s] %s\n" % (self.address_string(), fmt % args))

    # ---- 鉴权 ----
    def _is_local(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    def _auth_token(self):
        cookie_header = self.headers.get("Cookie") or ""
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(AUTH_COOKIE + "="):
                return part[len(AUTH_COOKIE) + 1:]
        return ""

    def _authorized(self):
        if self._is_local():
            return True
        pw = (load_config().get("access_password") or "").strip()
        if not pw:
            return False
        return self._auth_token() == _hash_pw(pw)

    def _send_login_page(self):
        body = LOGIN_PAGE_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _handle_login(self, body):
        pw_input = (body.get("password") or "").strip()
        pw = (load_config().get("access_password") or "").strip()
        if pw and pw_input == pw:
            token = _hash_pw(pw)
            payload = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header(
                "Set-Cookie",
                f"{AUTH_COOKIE}={token}; Path=/; Max-Age={AUTH_MAX_AGE}; HttpOnly; SameSite=Lax",
            )
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self._send_json({"ok": False, "error": "密码错误"}, 401)

    # ---- 通用响应 ----
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        if not os.path.isfile(path):
            self.send_error(404)
            return
        ext = os.path.splitext(path)[1].lower()
        ctype = MIME.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def _sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _sse_send(self, obj):
        line = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
        try:
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            raise

    # ---- GET ----
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._authorized():
            self._send_login_page()
            return
        if path in ("/", "/index.html"):
            self._send_file(os.path.join(STATIC_DIR, "index.html"))
        elif path.startswith("/static/"):
            name = os.path.basename(path)
            self._send_file(os.path.join(STATIC_DIR, name))
        elif path == "/api/config":
            cfg = load_config()
            self._send_json({
                "api_key_set": bool(cfg.get("api_key")),
                "api_key_tail": (cfg.get("api_key") or "")[-4:],
                "base_url": cfg.get("base_url"),
                "model_fast": cfg.get("model_fast"),
                "model_deep": cfg.get("model_deep"),
                "temperature": cfg.get("temperature"),
                "access_password_set": bool(cfg.get("access_password")),
            })
        elif path == "/api/profile":
            self._send_json({"profile": get_profile(HEALTH_DB)})
        elif path == "/api/sexual":
            self._send_json({"profile": get_profile(SEX_DB)})
        elif path == "/api/messages":
            self._send_json({"messages": get_messages()})
        elif path.startswith("/api/images/"):
            name = os.path.basename(path[len("/api/images/"):])
            if not name or name.startswith("."):
                self.send_error(404)
                return
            self._send_file(os.path.join(IMAGES_DIR, name))
        elif path == "/api/image":
            self._send_json({
                "images": get_image_items(),
                "recent": get_recent_items(),
                "auto_refine": get_meta("auto_refine", "1") != "0",
                "counter": int(get_meta("refine_counter", "0") or 0),
                "threshold": REFINE_THRESHOLD,
            })
        else:
            self.send_error(404)

    # ---- POST ----
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self._read_json()

        if path == "/api/login":
            self._handle_login(body)
            return

        if not self._authorized():
            self._send_json({"ok": False, "error": "未登录"}, 401)
            return

        if path == "/api/config":
            cfg = load_config()
            if body.get("api_key"):
                cfg["api_key"] = body["api_key"].strip()
            elif body.get("clear_api_key"):
                cfg["api_key"] = ""
            for k in ("base_url", "model_fast", "model_deep"):
                if body.get(k):
                    cfg[k] = body[k].strip()
            if body.get("temperature") is not None:
                try:
                    cfg["temperature"] = float(body["temperature"])
                except Exception:
                    pass
            if body.get("access_password"):
                cfg["access_password"] = body["access_password"].strip()
            save_config(cfg)
            self._send_json({"ok": True})
            return

        if path == "/api/profile":
            set_profile(HEALTH_DB, body.get("profile") or {})
            self._send_json({"ok": True})
            return

        if path == "/api/sexual":
            set_profile(SEX_DB, body.get("profile") or {})
            self._send_json({"ok": True})
            return

        if path == "/api/clear":
            clear_messages()
            self._send_json({"ok": True})
            return

        if path == "/api/image":
            action = body.get("action") or "add"
            if action == "add":
                content = (body.get("content") or "").strip()
                domain = (body.get("domain") or "其他").strip()
                if not content:
                    self._send_json({"ok": False, "error": "内容为空"}, 400)
                    return
                new_id = add_image_item(content, domain, "手动添加")
                self._send_json({"ok": True, "id": new_id})
                return
            if action == "update":
                item_id = body.get("id")
                content = (body.get("content") or "").strip()
                domain = (body.get("domain") or "其他").strip()
                if not item_id or not content:
                    self._send_json({"ok": False, "error": "参数缺失"}, 400)
                    return
                update_image_item(item_id, content, domain)
                self._send_json({"ok": True})
                return
            if action == "delete":
                item_id = body.get("id")
                if not item_id:
                    self._send_json({"ok": False, "error": "缺少 id"}, 400)
                    return
                delete_image_item(item_id)
                self._send_json({"ok": True})
                return
            self._send_json({"ok": False, "error": "未知 action"}, 400)
            return

        if path == "/api/recent":
            action = body.get("action") or "delete"
            if action == "delete":
                item_id = body.get("id")
                if not item_id:
                    self._send_json({"ok": False, "error": "缺少 id"}, 400)
                    return
                delete_recent_item(item_id)
                self._send_json({"ok": True})
                return
            self._send_json({"ok": False, "error": "未知 action"}, 400)
            return

        if path == "/api/refine":
            result = do_refine(force=True)
            self._send_json(result)
            return

        if path == "/api/refine_config":
            auto = body.get("auto_refine")
            if auto is not None:
                set_meta("auto_refine", "1" if auto else "0")
            self._send_json({"ok": True, "auto_refine": get_meta("auto_refine", "1") != "0"})
            return

        if path == "/api/chat":
            self._handle_chat(body)
            return

        self.send_error(404)

    # ---- 对话（SSE 流式） ----
    def _handle_chat(self, body):
        text = (body.get("message") or "").strip()
        images = body.get("images") or []
        if not isinstance(images, list):
            images = []
        mode = body.get("mode") or "fast"
        if mode not in ("fast", "deep"):
            mode = "fast"
        if images and mode == "deep":
            mode = "fast"   # deepseek-v4-pro 不支持图片，带图片时自动改用 flash

        if not text and not images:
            self._send_json({"ok": False, "error": "消息为空"}, 400)
            return

        # 1) 前置安全兜底：命中急症 / 心理危机，直接返回固定卡片，不调用模型
        card = safety_check(text)
        if card:
            saved = save_images(images)
            append_message("user", text, saved)
            append_message("assistant", card)
            note_user_message()
            self._sse_headers()
            self._sse_send({"role": "assistant", "delta": card, "safety": True})
            self._sse_send({"done": True})
            return

        cfg = load_config()
        if not cfg.get("api_key"):
            msg = "还没有配置 API Key。请先点击右上角「设置」，填入你的 DeepSeek API Key 再对话。"
            self._sse_headers()
            self._sse_send({"role": "assistant", "delta": msg, "error": "no_key"})
            self._sse_send({"done": True})
            return

        msgs = build_messages(text, images)
        saved = save_images(images)
        append_message("user", text, saved)
        note_user_message()

        self._sse_headers()
        full = []
        try:
            for delta in call_deepseek_stream(msgs, cfg, mode):
                full.append(delta)
                self._sse_send({"role": "assistant", "delta": delta})
            answer = "".join(full).strip()
            if answer:
                append_message("assistant", answer)
            self._sse_send({"done": True})
        except urllib.error.HTTPError as e:
            err = self._explain_http_error(e)
            self._sse_send({"error": "api", "delta": err})
            self._sse_send({"done": True})
        except Exception as e:
            self._sse_send({"error": "network", "delta": "连接模型服务失败：" + str(e)})
            self._sse_send({"done": True})

    def _explain_http_error(self, e):
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = ""
        if e.code == 401:
            return "API Key 无效或没有余额，请到「设置」里检查。"
        if e.code == 402:
            return "账户余额不足，请到 DeepSeek 平台充值。"
        if e.code == 429:
            return "请求太频繁或被限流，请稍等一会儿再试。"
        return f"模型服务返回错误（HTTP {e.code}）。{detail}"


# ---------------- 入口 ----------------
def main():
    ensure_data_dir()
    init_db()
    pw = ensure_access_password()
    lan_ip = get_lan_ip()

    try:
        httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        print(f"启动失败：端口 {PORT} 可能被占用，或已有实例在运行。\n{e}")
        input("按回车退出...")
        sys.exit(1)

    local_url = f"http://127.0.0.1:{PORT}"
    lan_url = f"http://{lan_ip}:{PORT}"
    print("=" * 58)
    print("  知衡 · 个人综合健康助手 v1.1")
    print(f"  本机访问：{local_url}")
    print(f"  局域网访问：{lan_url}   (手机连同一 WiFi)")
    print(f"  手机随时访问：http://<你的 Tailscale IP>:{PORT}")
    print(f"      (电脑上运行命令  tailscale ip -4  可查看该 IP)")
    print(f"  远程访问密码：{pw}")
    print("  关闭本窗口即可退出程序。")
    print("=" * 58)

    threading.Timer(1.0, lambda: webbrowser.open(local_url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
