import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

from myserver import server_on

# ตั้งค่าเชื่อม Google Sheet จาก .env
load_dotenv()

SCOPE = ['https://www.googleapis.com/auth/spreadsheets']
service_account_info = {
    "type": "service_account",
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL"),
    "universe_domain": os.getenv("GOOGLE_UNIVERSE_DOMAIN")
}

CREDS = Credentials.from_service_account_info(service_account_info, scopes=SCOPE)
GC = gspread.authorize(CREDS)

# ✅ จากนี้ค่อยเรียกใช้ SHEET_ID และเปิด worksheet
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
sheet = GC.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ สร้าง Modal (ฟอร์มกรอกข้อมูล)
class QuestFormModal(discord.ui.Modal):
    def __init__(self, sheet_name, quest_title):
        super().__init__(title="ฟอร์มส่งเควส")
        self.sheet_name = sheet_name
        self.quest_title = quest_title
        self.player_name = discord.ui.TextInput(label="ชื่อนักโทษในเกม")
        self.add_item(self.player_name)

    async def on_submit(self, interaction: discord.Interaction):
        admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            embed = discord.Embed(
                title="📥 มีคำร้องส่งเควสใหม่",
                description=(
                    f"👤 ชื่อนักโทษ: **{self.player_name.value}**\n"
                    f"🙋‍♂️ ผู้ส่ง: {interaction.user.mention}\n"
                    f"📂 หัวข้อ: **{self.sheet_name}**\n"
                    f"🎯 เควส: {self.quest_title}"
                ),
                color=discord.Color.blue()
            )
            discord_user = interaction.user.mention  # 👈 เก็บชื่อ Discord ผู้ส่งเควส
            view = ApprovalButtons(self.player_name.value, self.sheet_name, self.quest_title, discord_user)
            await admin_channel.send(embed=embed, view=view)

        confirm_embed = discord.Embed(
            title="📋 ส่งคำร้องเรียบร้อย !",
            description=("โปรดรอการตอบกลับทางข้อความส่วนตัวของคุณ หากไม่ได้รับการตอบกลับหรือเพิ่มยศต่างๆ กรุณาติดต่อผู้คุมโดยทันที !"),
            color=discord.Color.blurple()
        )
        confirm_embed.add_field(name="📂 หัวข้อเควส", value=self.sheet_name, inline=False)
        confirm_embed.add_field(name="🎯 รายการเควส", value=self.quest_title, inline=False)

        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)



# 👇 วางต่อจาก QuestFormModal (ก่อน QuestPanelView)

class SheetSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        sheets = [
            "BeginnerQuests",
            "ProcessQuests",
            "LaborQuests_Lv1",
            #"LaborQuests_Lv2",
            #"LaborQuests_Lv3"
        ]
        for i, sheet_name in enumerate(sheets):
            button = SheetButton(sheet_name)
            button.row = i  # ✅ จัดปุ่มแนวตั้ง
            self.add_item(button)


class SheetButton(discord.ui.Button):
    def __init__(self, sheet_name: str):
        # 🔽 กำหนดสีของปุ่มตามชื่อชีท
        if sheet_name == "BeginnerQuests":
            style = discord.ButtonStyle.primary  # น้ำเงิน
        elif sheet_name == "ProcessQuests":
            style = discord.ButtonStyle.danger   # แดง
        else:
            style = discord.ButtonStyle.success  # เขียว (LaborQuests)

        super().__init__(label=sheet_name, style=style, custom_id=f"sheet_{sheet_name}")
        self.sheet_name = sheet_name


    async def callback(self, interaction: discord.Interaction):
        rows = GC.open_by_key(SHEET_ID).worksheet(self.sheet_name).col_values(1)
        if len(rows) < 2:
            await interaction.response.send_message("ไม่มีรายการเควสในชีทนี้", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(QuestDropdown(self.sheet_name, rows[1:]))
        await interaction.response.send_message(f"เลือกรายการเควสจากหัวข้อ {self.sheet_name}", view=view, ephemeral=True)

class QuestDropdown(discord.ui.Select):
    def __init__(self, sheet_name, options_list):
        options = [discord.SelectOption(label=opt[:100]) for opt in options_list[:25]]
        super().__init__(placeholder="เลือกเควสที่ต้องการ", options=options, custom_id=f"dropdown_{sheet_name}")

    async def callback(self, interaction: discord.Interaction):
        selected_quest = self.values[0]
        await interaction.response.send_modal(QuestFormModal(self.custom_id.split("_", 1)[1], selected_quest))


# ✅ ปุ่มที่ใช้แสดง Modal
class QuestPanelView(discord.ui.View):
    @discord.ui.button(label="เริ่มส่งเควส", style=discord.ButtonStyle.primary, custom_id="start_quest")
    async def start_quest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuestFormModal(...))  # ต้องส่ง sheet_name ให้ด้วยหรือสร้าง logic แยกกรณี N/A

class ApprovalButtons(discord.ui.View):
    def __init__(self, player_name, sheet_name, quest_title, submitted_by):
        super().__init__(timeout=None)
        self.player_name = player_name
        self.sheet_name = sheet_name
        self.quest_title = quest_title
        self.submitted_by = submitted_by

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.success, custom_id="approve_button")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([
            timestamp,
            self.player_name,
            self.sheet_name,
            self.quest_title,
            "อนุมัติ",
         self.submitted_by
        ])

        try:
            spreadsheets = GC.open_by_key(SHEET_ID)
            worksheets = spreadsheets.worksheets()

            role_id = None
            for ws in worksheets:
                if ws.title.startswith("Role_"):
                    data = ws.get_all_values()
                    for row in data[1:]:
                        quest_key = row[0].split("(")[0].strip()
                        if quest_key == self.quest_title.split("(")[0].strip():
                            role_id = int(row[1])
                            break
                if role_id:
                    break

            if role_id:
                guild = interaction.guild
                role = guild.get_role(role_id)

                try:
                    user_id = int(self.submitted_by.strip("<@!>"))  # แปลง mention เป็น user_id
                    member = await guild.fetch_member(user_id)
                except Exception as e:
                    print(f"❗ แปลงหรือดึงผู้เล่นล้มเหลว: {e}")
                    member = None
                if member and role:
                    await member.add_roles(role)
                    print(f"✅ เพิ่ม Role {role.name} ให้ {member.display_name}")
                else:
                    print("❗ ไม่พบสมาชิกหรือ Role")
            else:
                print("❗ ไม่พบ Role ที่ตรงกับชื่อเควส")
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการเพิ่ม Role: {e}")

        await interaction.message.edit(
            content=f"✅ เควสของ {self.player_name} ({self.quest_title}) ได้รับการอนุมัติแล้วโดย {interaction.user.mention}",
            view=None  # ลบปุ่มออก
        )
        # ✅ ส่ง DM ไปยังผู้เล่น
        try:
            user_id = int(self.submitted_by.strip("<@!>"))  # แปลง mention เป็น user_id
            member = await interaction.guild.fetch_member(user_id)

            if member:
                embed_dm = discord.Embed(
                    title="📬 ผลการพิจารณาเควส",
                    description=f"✅ เควสของคุณ `{self.quest_title}` ในหัวข้อ `{self.sheet_name}` ได้รับการอนุมัติแล้ว",
                    color=discord.Color.green()
                )
                await member.send(embed=embed_dm)
        except Exception as e:
            print(f"❗ ไม่สามารถส่ง DM ให้ผู้เล่นได้: {e}")


    # ✅ ส่งข้อความแจ้งไปยังแอดมินหลังอนุมัติ
        admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            await admin_channel.send(
                f"✅ เควสของ **{self.player_name}**: `{self.quest_title}` ได้รับการอนุมัติโดย {interaction.user.mention}"
        )

        

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger, custom_id="reject_button")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([
            timestamp,
            self.player_name,
            self.sheet_name,
            self.quest_title,
            "ไม่อนุมัติ",
            self.submitted_by
        ])

        await interaction.message.edit(
            content=f"❌ เควสของ {self.player_name} ({self.quest_title}) ถูกปฏิเสธโดย {interaction.user.mention}",
            view=None
        )
        # ✅ ส่ง DM ไปยังผู้เล่น
        try:
            user_id = int(self.submitted_by.strip("<@!>"))  # แปลง mention เป็น user_id
            member = await interaction.guild.fetch_member(user_id)
            if member:
                embed_dm = discord.Embed(
                    title="📬 ผลการพิจารณาเควส",
                    description=f"❌ เควสของคุณ `{self.quest_title}` ในหัวข้อ `{self.sheet_name}` ถูกปฏิเสธ",
                    color=discord.Color.red()
                )
                await member.send(embed=embed_dm)
        except Exception as e:
            print(f"❗ ไม่สามารถส่ง DM ให้ผู้เล่นได้: {e}")

    # ✅ แจ้งผลการปฏิเสธเข้าแอดมินแชนแนล
        admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            await admin_channel.send(
                f"❌ เควสของ **{self.player_name}**: `{self.quest_title}` ถูกปฏิเสธโดย {interaction.user.mention}"
        )

        
# ✅ Sync Slash Command
GUILD_ID = 1360583634481975327  # ← ใส่ Server ID ของคุณตรงนี้
CHANNEL_ID = 1374778866903814214  # 👈 แก้เป็น ID ของห้องจริงใน Discord
ADMIN_CHANNEL_ID = 1368302479841693786  # 👈 เปลี่ยนเป็นห้องแอดมินจริง

@bot.event
async def on_ready():
    print(f"ล็อกอินสำเร็จ: {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Slash commands synced to guild: {GUILD_ID} ({len(synced)} คำสั่ง)")

        # ✅ ส่งปุ่มพร้อม embed เมื่อบอทออนไลน์
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            view = SheetSelectView()
            embed = discord.Embed(
                title="ระบบจัดการภารกิจ DEENA",
                description=("เลือกหัวข้อภารกิจที่ต้องการส่งคำร้องด้านล่างนี้\n"
                    "เมื่อทำการส่งคำร้องแล้ว ผู้คุมจะทำการตรวจสอบความถูกต้อง\n"
                    "หลังจากนั้นจะได้รับผลการพิจารณาทางข้อความส่วนตัวของคุณ"
                ),
                color=discord.Color.blurple()
            )
            await channel.send(embed=embed, view=view)
        else:
            print("❗ ไม่พบ Channel ID หรือบอทยังไม่มีสิทธิ์ในห้องนั้น")

    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

server_on()

bot.run(os.getenv('TOKEN'))
