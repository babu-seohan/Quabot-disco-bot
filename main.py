import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
import datetime
import os
import json
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# =========================
# 🔧 설정
# =========================
TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")   # ← Render에 등록 필수!

WELCOME_CHANNEL_ID = 1496478743873589448
LOG_CHANNEL_ID = 1496478745538855146
TICKET_CATEGORY_ID = 1496840441654677614
VERIFY_ROLE_ID = 1496479066075697234

WARNINGS_FILE = "warnings.json"

# AI 대화 기록
conversations = {}

# =========================
# 🌐 Keep Alive
# =========================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_http():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

def keep_alive():
    t = threading.Thread(target=run_http, daemon=True)
    t.start()

# =========================
# ⚙️ 봇 초기화
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
warnings = {}

# =========================
# 경고 데이터 관리
# =========================
def load_warnings():
    global warnings
    try:
        if os.path.exists(WARNINGS_FILE):
            with open(WARNINGS_FILE, 'r', encoding='utf-8') as f:
                warnings = json.load(f)
    except:
        warnings = {}

def save_warnings():
    try:
        with open(WARNINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(warnings, f, ensure_ascii=False, indent=2)
    except:
        pass

# =========================
# OpenAI AI 응답
# =========================
async def get_ai_response(user_id: str, user_message: str):
    if not OPENAI_API_KEY:
        return "❌ OpenAI API 키가 설정되지 않았습니다."

    if user_id not in conversations:
        conversations[user_id] = []
    
    conversations[user_id].append({"role": "user", "content": user_message})
    if len(conversations[user_id]) > 20:
        conversations[user_id] = conversations[user_id][-20:]

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 친근하고 도움이 되는 한국어 AI 어시스턴트야. 솔직하고 재치있게 답변해."}
            ] + conversations[user_id],
            temperature=0.8,
            max_tokens=1000
        )
        
        reply = response.choices[0].message.content
        conversations[user_id].append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        print(f"AI Error: {e}")
        return "❌ AI 응답 중 오류가 발생했습니다. 다시 시도해주세요."

# =========================
# /ai 명령어
# =========================
@bot.tree.command(name="ai", description="AI와 대화하기")
@app_commands.describe(message="AI에게 물어볼 내용")
async def ai_command(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    response = await get_ai_response(str(interaction.user.id), message)
    await interaction.followup.send(f"**{interaction.user.mention}** → {response}")

# =========================
# 인증 View
# =========================
class VerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="인증하기", style=discord.ButtonStyle.green)
    async def verify(self, interaction: discord.Interaction, button: Button):
        role = interaction.guild.get_role(VERIFY_ROLE_ID)
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ 인증 완료!", ephemeral=True)

# =========================
# 티켓 시스템
# =========================
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="티켓 생성", style=discord.ButtonStyle.blurple)
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not category:
            await interaction.response.send_message("❌ 카테고리를 찾을 수 없습니다.", ephemeral=True)
            return

        channel_name = f"ticket-{interaction.user.name}-{interaction.user.id % 10000}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        ch = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
        embed = discord.Embed(title="🎫 티켓 생성됨", description="문의 내용을 작성해주세요.", color=0x5865F2)
        await ch.send(embed=embed, view=CloseView())
        await interaction.response.send_message(f"✅ {ch.mention}", ephemeral=True)

class CloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="티켓 닫기", style=discord.ButtonStyle.red)
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if interaction.user.guild_permissions.administrator or str(interaction.user.id) in interaction.channel.name:
            await interaction.response.send_message("🔒 5초 후 삭제됩니다...")
            await asyncio.sleep(5)
            await interaction.channel.delete()

# =========================
# 관리자 패널 (간단 버전)
# =========================
class AdminPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="공지 작성", style=discord.ButtonStyle.blurple)
    async def announce(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("관리자 패널 - 공지 기능은 추후 추가 예정", ephemeral=True)

    @discord.ui.button(label="티켓 전체 삭제", style=discord.ButtonStyle.red)
    async def delete_tickets(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 가능", ephemeral=True)
            return
        # (티켓 삭제 로직은 필요시 추가)
        await interaction.response.send_message("티켓 전체 삭제 기능 준비중...", ephemeral=True)

# =========================
# 이벤트 & 명령어
# =========================
@bot.event
async def on_ready():
    load_warnings()
    await bot.tree.sync()
    print(f"{bot.user} 온라인 • AI 기능 활성화됨")

@bot.tree.command(name="관리자패널")
async def admin_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 관리자만 사용 가능", ephemeral=True)
        return
    embed = discord.Embed(title="👑 관리자 패널", color=0x5865F2)
    await interaction.response.send_message(embed=embed, view=AdminPanel())

# =========================
# 실행
# =========================
keep_alive()
bot.run(TOKEN)
