import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

app = FastAPI()

# CORS para o dashboard chamar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuração
API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")
SESSION_NAME = "telegram_session"

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

class SendMessageRequest(BaseModel):
    username: str
    message: str

class AuthCodeRequest(BaseModel):
    code: str
    password: str = None

# Estado da autenticação
auth_state = {"phone_code_hash": None, "awaiting_code": False}

@app.on_event("startup")
async def startup():
    await client.connect()
    if await client.is_user_authorized():
        print("✅ Já autenticado!")
    else:
        print("⚠️ Precisa autenticar. Chame /auth/start")

@app.get("/health")
async def health():
    is_auth = await client.is_user_authorized()
    return {"status": "ok", "authenticated": is_auth}

@app.post("/auth/start")
async def auth_start():
    """Inicia autenticação - envia código SMS"""
    if await client.is_user_authorized():
        return {"status": "already_authenticated"}
    
    result = await client.send_code_request(PHONE)
    auth_state["phone_code_hash"] = result.phone_code_hash
    auth_state["awaiting_code"] = True
    return {"status": "code_sent", "message": f"Código enviado para {PHONE}"}

@app.post("/auth/verify")
async def auth_verify(req: AuthCodeRequest):
    """Verifica o código recebido"""
    if not auth_state["awaiting_code"]:
        raise HTTPException(400, "Chame /auth/start primeiro")
    
    try:
        await client.sign_in(PHONE, req.code, phone_code_hash=auth_state["phone_code_hash"])
        auth_state["awaiting_code"] = False
        return {"status": "authenticated"}
    except SessionPasswordNeededError:
        if req.password:
            await client.sign_in(password=req.password)
            return {"status": "authenticated"}
        return {"status": "need_password", "message": "2FA ativado, envie a senha"}

@app.post("/send")
async def send_message(req: SendMessageRequest):
    """Envia mensagem para um usuário"""
    if not await client.is_user_authorized():
        raise HTTPException(401, "Não autenticado")
    
    try:
        # Tenta encontrar o usuário
        entity = await client.get_entity(req.username)
        result = await client.send_message(entity, req.message)
        return {
            "status": "sent",
            "message_id": result.id,
            "to": req.username
        }
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/forward")
async def forward_message(from_chat: str, message_id: int, to_username: str):
    """Encaminha uma mensagem"""
    if not await client.is_user_authorized():
        raise HTTPException(401, "Não autenticado")
    
    try:
        from_entity = await client.get_entity(from_chat)
        to_entity = await client.get_entity(to_username)
        result = await client.forward_messages(to_entity, message_id, from_entity)
        return {"status": "forwarded", "message_id": result.id}
    except Exception as e:
        raise HTTPException(400, str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
