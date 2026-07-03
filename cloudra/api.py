import os
import json
import aiosqlite
import asyncio
import socket
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 导入你的核心逻辑
from cloudra.main import run_task
from cloudra.config import get_config
from cloudra.conversation_class import Conversation
from cloudra.skill_class import skill_loader

app = FastAPI(
    title="Cloudra API (Mobile-Ready)",
    description="Cloudra AI 化学科研助手 - 增强型局域网服务",
    version="1.6.0"
)

# --- 跨域配置 (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 静态文件挂载 ---
# 允许手机端访问生成的图片、报告等文件
data_dir = get_config().data_dir
app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")

# --- 数据模型 ---
class ChatRequest(BaseModel):
    query: str
    conv_id: Optional[str] = None

class ApprovalDecision(BaseModel):
    decision: str  # 'approved' 或 'denied'

# --- 辅助函数 ---
def get_local_ip():
    """获取本机局域网 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 不需要真的连接，只是为了获取本机出局 IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_db_path():
    return os.path.join(data_dir, 'tasks', 'database.db')

# --- API 路由 ---

@app.get("/")
async def root():
    local_ip = get_local_ip()
    return {
        "status": "online",
        "local_access": f"http://{local_ip}:8000",
        "docs": f"http://{local_ip}:8000/docs",
        "data_root": f"http://{local_ip}:8000/data",
        "device_ip": local_ip
    }

@app.get("/conversations")
async def list_conversations():
    """获取所有历史对话"""
    conv_dir = data_dir / "conversations"
    if not conv_dir.exists():
        return []
    
    conversations = []
    for entry in conv_dir.iterdir():
        if entry.is_dir():
            meta_path = entry / "meta.json"
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    conversations.append(json.load(f))
    
    conversations.sort(key=lambda x: x.get("last_active", ""), reverse=True)
    return conversations

@app.get("/conversations/{conv_id}")
async def get_conversation_history(conv_id: str):
    """获取对话记录，并将本地路径转换为 Web URL"""
    conv = Conversation(conv_id)
    ctx_path = conv.get_context_path("a-0")
    
    if not os.path.exists(ctx_path):
        return []
    
    try:
        with open(ctx_path, "r", encoding="utf-8") as f:
            history = json.load(f)
            
        # 路径重写逻辑：将本地绝对路径转换为 /data/ 相对路径，方便手机访问
        for msg in history:
            content = msg.get('content')
            if isinstance(content, list):
                for part in content:
                    if part.get('type') == 'image_url':
                        local_path = part['image_url'].get('url')
                        if local_path and os.path.isabs(local_path):
                            # 计算相对于 data_dir 的路径
                            try:
                                rel_path = os.path.relpath(local_path, data_dir)
                                part['image_url']['url'] = f"/data/{rel_path}"
                            except ValueError:
                                pass
            elif isinstance(msg.get('image_path'), str):
                try:
                    rel_path = os.path.relpath(msg['image_path'], data_dir)
                    msg['image_path'] = f"/data/{rel_path}"
                except ValueError:
                    pass
                    
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """执行对话任务"""
    try:
        # 注意：run_task 目前是同步的，对于耗时任务，后续建议改为异步或 WebSocket
        result = run_task(req.query, conv_id=req.conv_id, verbose=False)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/approvals")
async def get_pending_approvals():
    """获取待审批请求"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []
    
    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute("SELECT id, session_id, agent_name, details FROM approvals WHERE state = 'pending'")
        rows = await cur.fetchall()
    
    return [{"id": r[0], "session_id": r[1], "agent_name": r[2], "details": r[3]} for r in rows]

@app.post("/approvals/{approval_id}")
async def process_approval(approval_id: int, dec: ApprovalDecision):
    """执行审批操作"""
    db_path = get_db_path()
    state = 'approved' if dec.decision.lower() == 'approved' else 'denied'
    
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("UPDATE approvals SET state = ? WHERE id = ?", (state, approval_id))
        await conn.commit()
    
    return {"status": "success", "id": approval_id, "new_state": state}

@app.get("/skills")
async def get_available_skills():
    """查看可用技能"""
    loader = skill_loader()
    return loader.skill_datas_get()

# --- 启动服务 ---
if __name__ == "__main__":
    import uvicorn
    local_ip = get_local_ip()
    print(f"\n🚀 Cloudra 增强版 API 已启动!")
    print(f"🏠 本地访问: http://127.0.0.1:8000")
    print(f"📱 局域网访问 (手机/平板): http://{local_ip}:8000")
    print(f"📂 静态资源根路径: {data_dir}")
    print(f"📖 交互式文档: http://{local_ip}:8000/docs\n")
    
    # 绑定 0.0.0.0 是局域网发现的关键
    uvicorn.run(app, host="0.0.0.0", port=8000)
