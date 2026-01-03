import asyncio
import json
import time
import base64
import os
import sqlite3
from websockets.legacy.client import connect

# 配置区域：支持多个 Bot 实例
BOT_CONFIGS = [
    {
        "name": "bot1",
        "url": "ws://127.0.0.1:1234",
        "token": "5G5456456"
    },
    # 示例：添加第二个 Bot
    # {
        # "name": "Bot2",
        # "url": "ws://127.0.0.1:2345",
        # "token": "X45645"
    # },
]

DATA_FILE = os.path.join(os.path.dirname(__file__), "fwlog_data.json")
DB_FILE = os.path.join(os.path.dirname(__file__), "fwlog.db")

WATCH_GROUPS = []

def log(*args):
    print("[fwlog-bot]", *args)

# Database handling
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Table: groups (stores state per group)
    c.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            current_log_name TEXT,
            recording INTEGER DEFAULT 0,
            created_at INTEGER,
            updated_at INTEGER
        )
    ''')
    
    # Table: logs (stores log metadata)
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT,
            name TEXT,
            ended INTEGER DEFAULT 0,
            created_at INTEGER,
            updated_at INTEGER,
            UNIQUE(group_id, name)
        )
    ''')
    
    # Table: items (stores log messages)
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id INTEGER,
            nickname TEXT,
            im_userid TEXT,
            time INTEGER,
            message TEXT,
            raw_msg_id TEXT,
            FOREIGN KEY(log_id) REFERENCES logs(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def migrate_json_to_sqlite():
    if not os.path.exists(DATA_FILE):
        return
        
    log("正在从 JSON 迁移数据到 SQLite...")
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        conn = get_db_connection()
        c = conn.cursor()
        
        for group_id, g_data in data.items():
            # Insert group
            c.execute('''
                INSERT OR IGNORE INTO groups (group_id, current_log_name, recording, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                group_id,
                g_data.get("current", ""),
                1 if g_data.get("recording") else 0,
                g_data.get("createdAt", 0),
                g_data.get("updatedAt", 0)
            ))
            
            logs = g_data.get("logs", {})
            for log_name, log_data in logs.items():
                # Insert log
                c.execute('''
                    INSERT OR IGNORE INTO logs (group_id, name, ended, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    group_id,
                    log_name,
                    1 if log_data.get("ended") else 0,
                    log_data.get("createdAt", 0),
                    log_data.get("updatedAt", 0)
                ))
                
                # Get log_id
                c.execute('SELECT id FROM logs WHERE group_id = ? AND name = ?', (group_id, log_name))
                log_row = c.fetchone()
                if log_row:
                    log_id = log_row["id"]
                    items = log_data.get("items", [])
                    for item in items:
                        c.execute('''
                            INSERT INTO items (log_id, nickname, im_userid, time, message, raw_msg_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            log_id,
                            item.get("nickname", ""),
                            item.get("im_userid", ""),
                            item.get("time", 0),
                            item.get("message", ""),
                            item.get("raw_msg_id", "")
                        ))
        
        conn.commit()
        conn.close()
        
        # Rename old JSON file
        os.rename(DATA_FILE, DATA_FILE + ".bak")
        log("迁移完成，旧数据文件已重命名为 fwlog_data.json.bak")
        
    except Exception as e:
        log(f"迁移失败: {e}")

# Initial setup
init_db()
migrate_json_to_sqlite()

def pad2(n):
    return f"{n:02d}"

def format_time(ts):
    d = time.localtime(ts)
    y = d.tm_year
    m = pad2(d.tm_mon)
    day = pad2(d.tm_mday)
    hh = pad2(d.tm_hour)
    mm = pad2(d.tm_min)
    ss = pad2(d.tm_sec)
    return f"{y}/{m}/{day} {hh}:{mm}:{ss}"

def ensure_group_state(group_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM groups WHERE group_id = ?', (group_id,))
    row = c.fetchone()
    
    if not row:
        now = int(time.time() * 1000)
        c.execute('''
            INSERT INTO groups (group_id, current_log_name, recording, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
        ''', (group_id, "", now, now))
        conn.commit()
        c.execute('SELECT * FROM groups WHERE group_id = ?', (group_id,))
        row = c.fetchone()
    
    conn.close()
    return dict(row)

def update_group_state(group_id, **kwargs):
    conn = get_db_connection()
    c = conn.cursor()
    
    updates = []
    values = []
    for k, v in kwargs.items():
        updates.append(f"{k} = ?")
        values.append(v)
    
    values.append(group_id)
    sql = f"UPDATE groups SET {', '.join(updates)} WHERE group_id = ?"
    c.execute(sql, values)
    conn.commit()
    conn.close()

def ensure_log(group_id, name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM logs WHERE group_id = ? AND name = ?', (group_id, name))
    row = c.fetchone()
    
    if not row:
        now = int(time.time() * 1000)
        c.execute('''
            INSERT INTO logs (group_id, name, ended, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
        ''', (group_id, name, now, now))
        conn.commit()
        c.execute('SELECT * FROM logs WHERE group_id = ? AND name = ?', (group_id, name))
        row = c.fetchone()
    
    conn.close()
    return dict(row)

def update_log_meta(log_id, **kwargs):
    conn = get_db_connection()
    c = conn.cursor()
    
    updates = []
    values = []
    for k, v in kwargs.items():
        updates.append(f"{k} = ?")
        values.append(v)
    
    values.append(log_id)
    sql = f"UPDATE logs SET {', '.join(updates)} WHERE id = ?"
    c.execute(sql, values)
    conn.commit()
    conn.close()

def add_log_items(log_id, items):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get count before insert
    c.execute('SELECT COUNT(*) FROM items WHERE log_id = ?', (log_id,))
    old_count = c.fetchone()[0]
    
    for item in items:
        c.execute('''
            INSERT INTO items (log_id, nickname, im_userid, time, message, raw_msg_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            log_id,
            item.get("nickname", ""),
            item.get("im_userid", ""),
            item.get("time", 0),
            item.get("message", ""),
            item.get("raw_msg_id", "")
        ))
    
    # Update log updated_at
    now = int(time.time() * 1000)
    c.execute('UPDATE logs SET updated_at = ? WHERE id = ?', (now, log_id))
    
    conn.commit()
    conn.close()
    
    return old_count, old_count + len(items)

def clear_log_items(log_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM items WHERE log_id = ?', (log_id,))
    conn.commit()
    conn.close()

def get_log_full(group_id, name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM logs WHERE group_id = ? AND name = ?', (group_id, name))
    log_row = c.fetchone()
    
    if not log_row:
        conn.close()
        return None
        
    log_data = dict(log_row)
    c.execute('SELECT * FROM items WHERE log_id = ? ORDER BY id', (log_data["id"],))
    items = [dict(row) for row in c.fetchall()]
    log_data["items"] = items
    
    conn.close()
    return log_data

def get_logs_list(group_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM logs WHERE group_id = ? ORDER BY created_at DESC', (group_id,))
    logs = [dict(row) for row in c.fetchall()]
    
    # Get item counts
    for l in logs:
        c.execute('SELECT COUNT(*) FROM items WHERE log_id = ?', (l["id"],))
        l["item_count"] = c.fetchone()[0]
        
    conn.close()
    return logs

def delete_log(group_id, name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id FROM logs WHERE group_id = ? AND name = ?', (group_id, name))
    row = c.fetchone()
    if row:
        log_id = row["id"]
        c.execute('DELETE FROM items WHERE log_id = ?', (log_id,))
        c.execute('DELETE FROM logs WHERE id = ?', (log_id,))
        conn.commit()
    conn.close()

def extract_forward_ids_from_text(text):
    ids = []
    if not text:
        return ids
    # Standard CQ code
    prefix = "[CQ:forward"
    if prefix in text:
        idx = 0
        while True:
            start = text.find(prefix, idx)
            if start == -1:
                break
            end = text.find("]", start)
            if end == -1:
                break
            segment = text[start:end]
            
            # Try common keys for forward ID
            value = ""
            for key in ["id=", "res_id=", "message_id="]:
                pos = segment.find(key)
                if pos != -1:
                    pos += len(key)
                    j = pos
                    while j < len(segment) and segment[j] not in ",]":
                        j += 1
                    value = segment[pos:j]
                    if value:
                        break
            
            if value:
                ids.append(value)
            idx = end + 1
    return ids

def segments_to_text(message):
    if isinstance(message, str):
        return message
    if not isinstance(message, list):
        return str(message or "")
    parts = []
    for seg in message:
        if not isinstance(seg, dict):
            continue
        t = seg.get("type")
        d = seg.get("data") or {}
        if t == "text":
            parts.append(d.get("text", ""))
        elif t == "image":
            file_val = d.get("file", "")
            url_val = d.get("url") or d.get("file_url") or ""
            if file_val and url_val:
                parts.append(f"[CQ:image,file={file_val},url={url_val}]")
            elif file_val:
                parts.append(f"[CQ:image,file={file_val}]")
            elif url_val:
                parts.append(f"[CQ:image,url={url_val}]")
            else:
                parts.append("[图片]")
        elif t == "at":
            qq_val = d.get("qq", "")
            if qq_val:
                parts.append(f"[CQ:at,qq={qq_val}]")
        elif t == "forward":
            # Direct forward segment
            fid = d.get("id")
            if fid:
                parts.append(f"[CQ:forward,id={fid}]")
        else:
            parts.append(f"[{t}]")
    if not parts:
        return "[空消息]"
    return "".join(parts)

next_echo_id = 1
message_queue = asyncio.Queue()

def gen_echo():
    global next_echo_id
    echo = f"fwlog-{next_echo_id}"
    next_echo_id += 1
    return echo

class BotClient:
    def __init__(self, config):
        self.name = config.get("name", "UnknownBot")
        self.url = config.get("url")
        self.token = config.get("token")
        self.ws_conn = None
        self.pending = {}
        
    async def send_api(self, action, params=None):
        if params is None:
            params = {}
        if self.ws_conn is None or self.ws_conn.closed:
            raise RuntimeError(f"[{self.name}] WebSocket 未连接")
        echo = gen_echo()
        fut = asyncio.get_running_loop().create_future()
        self.pending[echo] = fut
        payload = {"action": action, "params": params, "echo": echo}
        if self.token:
            payload["token"] = self.token
        
        try:
            await self.ws_conn.send(json.dumps(payload, ensure_ascii=False))
            # Wait for response with timeout
            return await asyncio.wait_for(fut, timeout=20.0)
        except asyncio.TimeoutError:
            self.pending.pop(echo, None)
            raise RuntimeError(f"[{self.name}] API请求超时: {action}")
        except Exception as e:
            self.pending.pop(echo, None)
            raise e

    def handle_api_response(self, msg):
        echo = msg.get("echo")
        if not echo:
            return
        fut = self.pending.pop(echo, None)
        if fut is None:
            return
        if not fut.done():
            fut.set_result(msg)

    async def send_group_msg(self, group_id, text):
        try:
            # Use string group_id for better compatibility with NapCat/OneBot
            await self.send_api(
                "send_group_msg",
                {"group_id": str(group_id), "message": text},
            )
        except Exception as e:
            log(f"[{self.name}] 发送群消息失败", e)

    async def send_private_msg(self, user_id, text):
        try:
            await self.send_api(
                "send_private_msg",
                {"user_id": str(user_id), "message": text},
            )
        except Exception as e:
            log(f"[{self.name}] 发送私聊消息失败", e)

    async def send_msg(self, msg_type, target_id, text):
        if msg_type == "group":
            await self.send_group_msg(target_id, text)
        elif msg_type == "private":
            await self.send_private_msg(target_id, text)

    async def run(self):
        while True:
            try:
                log(f"[{self.name}] 尝试连接到 NapCat WS:", self.url)
                async with connect(
                    self.url,
                    extra_headers=(
                        {"Authorization": f"Bearer {self.token}"}
                        if self.token
                        else None
                    ),
                ) as ws:
                    self.ws_conn = ws
                    log(f"[{self.name}] WS 已连接")
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except Exception:
                            continue
                        
                        # If it's an API response (echo), handle immediately
                        if isinstance(data, dict) and "echo" in data:
                            self.handle_api_response(data)
                            continue
                            
                        # Otherwise, queue it with client reference
                        if isinstance(data, dict):
                             if data.get("post_type") == "message" and data.get("message_type") in ["group", "private"]:
                                 message_queue.put_nowait((self, data))
                        
            except Exception as e:
                log(f"[{self.name}] WS 连接出错或关闭", e)
            self.ws_conn = None
            await asyncio.sleep(3)

def generate_log_text(log_obj):
    items = log_obj.get("items", [])
    blocks = []
    for item in items:
        ts = item.get("time", 0)
        dt = format_time(ts)
        name = item.get("nickname", "Unknown")
        uid = item.get("im_userid", "")
        msg = item.get("message", "")
        
        # Header: Name(ID) Time
        header = f"{name}({uid}) {dt}"
        
        # Content: Add leading space to each line
        if msg is None:
            msg = ""
        msg = str(msg)
        content_lines = [f" {line}" for line in msg.splitlines()]
        content_text = "\n".join(content_lines)
        
        # Block: Header + Newline + Content
        blocks.append(f"{header}\n{content_text}")
        
    # Join blocks with an empty line in between
    return "\n\n".join(blocks)

def normalize_fwlog_prefix(text):
    if not text:
        return ""
    # Remove leading whitespace/invisible chars
    t = text.lstrip()
    if not t:
        return ""
    
    # Check for common prefixes
    prefixes = [".", "。", "/", "、"]
    has_prefix = False
    for p in prefixes:
        if t.startswith(p):
            t = t[len(p):].lstrip()
            has_prefix = True
            break
            
    # Check if starts with fwlog (case insensitive)
    if t.lower().startswith("fwlog"):
        # Only allow if prefix was present (User request: strict prefix requirement)
        if has_prefix:
            return ".fwlog" + t[5:]
    
    return text

async def handle_fwlog_command(client, event, text_override=None):
    msg_type = event.get("message_type")
    if msg_type == "group":
        session_id = str(event.get("group_id"))
    elif msg_type == "private":
        session_id = str(event.get("user_id"))
    else:
        return

    sender = event.get("sender") or {}
    user_name = sender.get("card") or sender.get("nickname") or ""
    
    if text_override is not None:
        msg_text = text_override
    else:
        msg_text = segments_to_text(event.get("message")).strip()
    
    # Normalize command
    normalized_text = normalize_fwlog_prefix(msg_text)
    
    if not normalized_text.startswith(".fwlog"):
        return

    body = normalized_text[len(".fwlog") :]
    body = body.replace("\u3000", " ")
    body = body.strip()
    
    if not body:
        sub = "help"
        name_arg = ""
    else:
        parts = body.split()
        sub = parts[0].lower()
        name_arg = parts[1] if len(parts) > 1 else ""

    log(f"[{client.name}] fwlog 子命令解析 ({msg_type}:{session_id}):", msg_text, "=>", sub, name_arg)
    g = ensure_group_state(session_id)

    try:
        if sub == "new":
            name = name_arg
            if not name:
                now = time.localtime()
                name = (
                    "log-"
                    f"{now.tm_year}{pad2(now.tm_mon)}{pad2(now.tm_mday)}-"
                    f"{pad2(now.tm_hour)}{pad2(now.tm_min)}{pad2(now.tm_sec)}"
                )
            
            # Check if log exists, if so clear it (or just use new name)
            # ensure_log creates it if not exists
            log_obj = ensure_log(session_id, name)
            clear_log_items(log_obj["id"])
            
            now_ts = int(time.time() * 1000)
            update_log_meta(log_obj["id"], ended=0, created_at=now_ts, updated_at=now_ts)
            update_group_state(session_id, current_log_name=name, recording=1)

            await client.send_msg(
                msg_type, session_id,
                f"【新建日志】 {user_name} 已新建日志: {name}\n"
                "------------------------------\n"
                "* 记录已开启！请发送【合并转发】消息以提取内容。\n"
                "// 说明：本工具仅将合并转发转化为海豹原始格式，用于补充缺失日志。\n"
                "// 正常跑团请直接使用 .log 指令。",
            )
        elif sub == "on":
            name = name_arg or g["current_log_name"]
            if not name:
                await client.send_msg(
                    msg_type, session_id,
                    "当前没有选中的日志，请先使用 .fwlog new <名称> 创建",
                )
                return
            
            log_obj = get_log_full(session_id, name)
            if not log_obj:
                await client.send_msg(msg_type, session_id, f"指定日志不存在: {name}")
                return
                
            now_ts = int(time.time() * 1000)
            update_log_meta(log_obj["id"], ended=0, updated_at=now_ts)
            update_group_state(session_id, current_log_name=name, recording=1)

            await client.send_msg(
                msg_type, session_id,
                f"【继续记录】 {user_name} 已继续记录合并转发日志: {name}\n"
                "请发送【合并转发】消息以提取内容。",
            )
        elif sub == "off":
            if not g["recording"]:
                await client.send_msg(msg_type, session_id, "当前不在记录状态")
            else:
                update_group_state(session_id, recording=0)
                await client.send_msg(msg_type, session_id, "【暂停记录】 已暂停记录当前合并转发日志")
        elif sub == "end":
            name = name_arg or g["current_log_name"]
            log_obj = get_log_full(session_id, name)
            
            if not log_obj:
                await client.send_msg(msg_type, session_id, "指定日志不存在")
                return
            
            if not log_obj.get("items"):
                await client.send_msg(msg_type, session_id, f"指定日志为空: {name}")
                return
            try:
                full_text = generate_log_text(log_obj)
                # Encode to base64
                b64_content = base64.b64encode(full_text.encode("utf-8")).decode("utf-8")
                file_param = f"base64://{b64_content}"
                
                try:
                    # Try upload_file API first (Standard OneBot for files)
                    if msg_type == "group":
                        await client.upload_group_file(session_id, file_param, f"{name}.txt")
                    else:
                        await client.upload_private_file(session_id, file_param, f"{name}.txt")
                    
                    # Update state only if successful
                    now_ts = int(time.time() * 1000)
                    update_log_meta(log_obj["id"], ended=1, updated_at=now_ts)
                    update_group_state(session_id, recording=0)
                    
                    await client.send_msg(msg_type, session_id, "【发送成功】 日志文件已发送")
                
                except Exception as upload_err:
                    log(f"[{client.name}] upload_file 失败，尝试 CQ 码发送: {upload_err}")
                    # Fallback: Send as file using CQ code
                    file_cq = f"[CQ:file,file={file_param},name={name}.txt]"
                    await client.send_msg(msg_type, session_id, file_cq)
                    
                    now_ts = int(time.time() * 1000)
                    update_log_meta(log_obj["id"], ended=1, updated_at=now_ts)
                    update_group_state(session_id, recording=0)
                    
                    await client.send_msg(msg_type, session_id, "【发送成功】 日志文件已发送 (CQ码模式)")

            except Exception as e:
                await client.send_msg(msg_type, session_id, f"【发送失败】 发送日志文件失败: {e}")
        elif sub == "get":
            name = name_arg or g["current_log_name"]
            log_obj = get_log_full(session_id, name)
            
            if not log_obj:
                await client.send_msg(msg_type, session_id, "指定日志不存在")
                return
            if not log_obj.get("items"):
                await client.send_msg(msg_type, session_id, f"指定日志为空: {name}")
                return
            try:
                full_text = generate_log_text(log_obj)
                # Encode to base64
                b64_content = base64.b64encode(full_text.encode("utf-8")).decode("utf-8")
                file_param = f"base64://{b64_content}"
                
                try:
                    # Try upload_file API first
                    if msg_type == "group":
                        await client.upload_group_file(session_id, file_param, f"{name}.txt")
                    else:
                        await client.upload_private_file(session_id, file_param, f"{name}.txt")
                except Exception as upload_err:
                    log(f"[{client.name}] upload_file 失败，尝试 CQ 码发送: {upload_err}")
                    # Fallback: Send as file using CQ code
                    file_cq = f"[CQ:file,file={file_param},name={name}.txt]"
                    await client.send_msg(msg_type, session_id, file_cq)

            except Exception as e:
                await client.send_msg(msg_type, session_id, f"【发送失败】 发送日志文件失败: {e}")
        elif sub == "list":
            logs = get_logs_list(session_id)
            if not logs:
                await client.send_msg(msg_type, session_id, "当前会话没有任何 fwlog 日志")
                return
            lines = ["【日志列表】 本会话 fwlog 列表:"]
            for l in logs:
                name = l["name"]
                is_current = (g["current_log_name"] == name and g["recording"])
                
                if is_current:
                    status = "* [记录中]"
                elif l["ended"]:
                    status = "  [已结束]"
                else:
                    status = "  [已暂停]"
                
                count = l.get("item_count", 0)
                t = time.localtime((l["created_at"] or 0) / 1000)
                time_str = (
                    f"{t.tm_year}-{pad2(t.tm_mon)}-{pad2(t.tm_mday)} "
                    f"{pad2(t.tm_hour)}:{pad2(t.tm_min)}"
                )
                lines.append(f"- {status} {name} ({count}条, 创建于 {time_str})")
            await client.send_msg(msg_type, session_id, "\n".join(lines))
        elif sub == "clear":
            name = name_arg or g["current_log_name"]
            log_obj = get_log_full(session_id, name)
            if not log_obj:
                await client.send_msg(msg_type, session_id, "指定日志不存在")
                return
                
            delete_log(session_id, name)
            
            if g["current_log_name"] == name:
                update_group_state(session_id, current_log_name="", recording=0)
                
            await client.send_msg(msg_type, session_id, f"【清除成功】 日志 {name} 已清除")
        else:
            help_lines = [
                "【fwlog 聊天记录转海豹日志工具】",
                "// 说明：本工具专用于将【合并转发】消息转换为海豹(SealDice)原生日志格式，以便在日志缺失时进行补充。",
                "// 注意：仅解析合并转发内容，不记录实时消息。",
                "// 正常跑团请使用 .log 指令。",
                "",
                "【指令列表】",
                ".fwlog new [名称]   // 新建并开始记录",
                ".fwlog on [名称]    // 继续记录已有日志",
                ".fwlog off          // 暂停当前日志记录",
                ".fwlog end [名称]   // 结束并发送日志文件",
                ".fwlog get [名称]   // 获取指定日志文件",
                ".fwlog list         // 列出当前会话日志",
                ".fwlog clear [名称] // 清除指定日志",
            ]
            await client.send_msg(msg_type, session_id, "\n".join(help_lines))
    except Exception as e:
        log(f"执行 fwlog {sub} 时出错: {e}")
        # Optionally notify group
        # await client.send_group_msg(group_id, f"执行指令出错: {e}")

async def handle_forward_message(client, event):
    msg_type = event.get("message_type")
    if msg_type == "group":
        session_id = str(event.get("group_id"))
    elif msg_type == "private":
        session_id = str(event.get("user_id"))
    else:
        return

    if WATCH_GROUPS and session_id not in WATCH_GROUPS:
        return
        
    g = ensure_group_state(session_id)
    if not g["recording"] or not g["current_log_name"]:
        return

    text = segments_to_text(event.get("message"))
    forward_ids = extract_forward_ids_from_text(text)
    
    if not forward_ids:
        return
        
    log(f"[{client.name}] 捕获到合并转发ID:", forward_ids, "来自:", session_id)
    
    log_obj = ensure_log(session_id, g["current_log_name"])
    
    for fid in forward_ids:
        try:
            resp = await client.send_api("get_forward_msg", {"id": fid})
            data = resp.get("data")
            if resp.get("status") != "ok" or not data:
                log(f"[{client.name}] 使用 id 获取转发失败，尝试使用 message_id")
                resp = await client.send_api("get_forward_msg", {"message_id": fid})
                data = resp.get("data")
            if resp.get("status") != "ok" or not data:
                log(f"[{client.name}] 获取转发消息内容为空或失败:", fid)
                continue
            
            nodes = []
            if isinstance(data, dict) and "messages" in data:
                nodes = data["messages"]
            elif isinstance(data, list):
                nodes = data
                
            new_items = []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                sender = node.get("sender") or {}
                sender_id = str(sender.get("user_id") or "")
                sender_name = sender.get("nickname") or (
                    f"QQ:{sender_id}" if sender_id else "Unknown"
                )
                ts = node.get("time") or int(time.time())
                content = segments_to_text(node.get("message") or node.get("content") or "")
                
                item = {
                    "nickname": sender_name,
                    "im_userid": sender_id,
                    "time": ts,
                    "message": content,
                    "raw_msg_id": str(node.get("message_id", "")),
                }
                new_items.append(item)
                
            if new_items:
                old_cnt, new_cnt = add_log_items(log_obj["id"], new_items)
                log(f"[{client.name}] 已从转发 {fid} 中提取 {len(new_items)} 条消息 (当前共 {new_cnt} 条)")
                
                # Check 1000 threshold
                if new_cnt // 1000 > old_cnt // 1000:
                    await client.send_msg(
                        msg_type, session_id,
                        f"【系统提醒】 当前日志 {log_obj['name']} 已记录 {new_cnt} 条消息。\n"
                        "如果记录完毕，请记得发送 .fwlog end 结束记录。"
                    )

        except Exception as e:
            log(f"[{client.name}] 获取转发消息异常", fid, e)

async def process_messages():
    """Consume messages from the queue asynchronously"""
    log("消息处理循环已启动")
    while True:
        # Unpack tuple (client, message)
        item = await message_queue.get()
        if not isinstance(item, tuple) or len(item) != 2:
            message_queue.task_done()
            continue
            
        client, msg = item
        try:
            text = segments_to_text(msg.get("message")).strip()
            
            # Handle @ mention
            self_id = str(msg.get("self_id", ""))
            if self_id:
                cq_at = f"[CQ:at,qq={self_id}]"
                if text.startswith(cq_at):
                    text = text[len(cq_at):].strip()

            normalized = normalize_fwlog_prefix(text)
            
            if normalized.startswith(".fwlog"):
                log(f"[{client.name}] 检测到 fwlog 指令:", text)
                await handle_fwlog_command(client, msg, text_override=text)
            else:
                await handle_forward_message(client, msg)
        except Exception as e:
            log(f"处理消息时发生错误: {e}")
        finally:
            message_queue.task_done()

async def main_loop():
    # Create clients
    clients = [BotClient(cfg) for cfg in BOT_CONFIGS]
    
    # Start processor
    processor_task = asyncio.create_task(process_messages())
    
    # Start all clients
    tasks = [client.run() for client in clients]
    await asyncio.gather(*tasks, processor_task)

def main():
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        log("程序已停止")

if __name__ == "__main__":
    main()
