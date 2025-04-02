import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, date
import json
import os
import pytz
import asyncio

intents = discord.Intents.default()
intents.presences = True
intents.members = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

bot.remove_command("help")

VN_TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

# Channel IDs
NOTIFICATION_CHANNEL_ID = 1356329940089442545
REPORT_CHANNEL_ID = 1356616756017369189
PLAYTIME_UPDATE_CHANNEL_ID = 1356616109473660971
VINEWOOD_CHANNEL_ID = 1356615723413278881
DUTY_CHANNEL_ID = 1356615522850046154

# Admin IDs
ADMIN_USER_IDS = ["896570526607237121"]

# Authorized vehicles
AUTHORIZED_VEHICLES = [
    "Porsche 911 Turbo S SASD",
    "2014 BMW R1200RT LAW ENFORCEMENT",
    "2018 Dodge Charger LEO Edition"
]

# File paths
ACTIVITY_FILE = "activity.json"
USER_MAPPING_FILE = "user_mapping.json"
PLAYTIME_FILE = "playtime.json"
ONLINE_TIMES_FILE = "online_times.json"
VINEWOOD_ACTIVITY_FILE = "vinewood_activity.json"

def load_json_file(file_path, default_value):
    """Safely load a JSON file, return default_value if it fails."""
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error loading {file_path}: Invalid JSON. Initializing with default value.")
            return default_value
    return default_value

async def save_json_file(file_path, data):
    """Safely save data to a JSON file."""
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving {file_path}: {e}")

def load_activity_data():
    return load_json_file(ACTIVITY_FILE, {})

async def save_activity_data(data):
    await save_json_file(ACTIVITY_FILE, data)

def load_user_mapping():
    data = load_json_file(USER_MAPPING_FILE, {})
    filtered_data = {user_id: user_info for user_id, user_info in data.items()
                     if isinstance(user_info, dict) and "guild_id" in user_info}
    if data != filtered_data:
        asyncio.create_task(save_json_file(USER_MAPPING_FILE, filtered_data))
    return filtered_data

async def save_user_mapping(data):
    await save_json_file(USER_MAPPING_FILE, data)

def load_playtime_data():
    return load_json_file(PLAYTIME_FILE, {})

async def save_playtime_data(data, notify_changes=False):
    old_data = load_playtime_data()
    await save_json_file(PLAYTIME_FILE, data)
    if notify_changes and old_data != data:
        channel = bot.get_channel(PLAYTIME_UPDATE_CHANNEL_ID)
        if channel:
            changes = []
            for user_id, user_data in data.items():
                guild_id = user_mapping.get(user_id, {}).get("guild_id")
                if not guild_id:
                    continue
                guild = bot.get_guild(int(guild_id))
                if not guild:
                    continue
                member = guild.get_member(int(user_id))
                if not member:
                    continue
                display_name = member.display_name
                old_user_data = old_data.get(user_id, {})
                for date_str, minutes in user_data.get("daily_online", {}).items():
                    old_minutes = old_user_data.get("daily_online", {}).get(date_str, 0)
                    if minutes != old_minutes:
                        hours_new = int(minutes // 60)
                        mins_new = int(minutes % 60)
                        hours_old = int(old_minutes // 60)
                        mins_old = int(old_minutes % 60)
                        changes.append(f"- {display_name} ({date_str}): {hours_new}h {mins_new}m (trước: {hours_old}h {mins_old}m)")
            if changes:
                await channel.send(f"📝 **Cập nhật playtime.json**:\n" + "\n".join(changes))

def load_online_times():
    data = load_json_file(ONLINE_TIMES_FILE, {})
    return {user_id: datetime.fromisoformat(time_str).astimezone(VN_TIMEZONE)
            for user_id, time_str in data.items()}

async def save_online_times(data):
    await save_json_file(ONLINE_TIMES_FILE, {user_id: time.isoformat() for user_id, time in data.items()})

def load_vinewood_activity_data():
    return load_json_file(VINEWOOD_ACTIVITY_FILE, {})

async def save_vinewood_activity_data(data):
    await save_json_file(VINEWOOD_ACTIVITY_FILE, data)

def has_admin_role(member):
    return str(member.id) in ADMIN_USER_IDS

online_start_times = load_online_times()
activity_data = load_activity_data()
user_mapping = load_user_mapping()
playtime_data = load_playtime_data()
vinewood_activity_data = load_vinewood_activity_data()

@bot.event
async def on_ready():
    global online_start_times, user_mapping, vinewood_activity_data, playtime_data
    bot.start_time = datetime.now(VN_TIMEZONE)
    online_start_times = load_online_times()  # Tải lại từ file
    print(f"Bot đã sẵn sàng: {bot.user}")
    for guild in bot.guilds:
        guild_id = str(guild.id)
        for member in guild.members:
            user_id = str(member.id)
            if user_id not in user_mapping:
                user_mapping[user_id] = {"guild_id": guild_id}
    await save_user_mapping(user_mapping)
    check_vinewood_activity.start()
    daily_report.start()
    current_time = datetime.now(VN_TIMEZONE)
    for user_id, start_time in list(online_start_times.items()):
        time_online = (current_time - start_time).total_seconds() / 60
        if time_online > 0:
            if user_id not in playtime_data:
                playtime_data[user_id] = {"daily_online": {}}
            current_date = start_time
            while current_date.date() <= current_time.date():
                date_str = current_date.date().isoformat()
                playtime_data[user_id]["daily_online"].setdefault(date_str, 0)
                end_of_period = min(current_time, datetime.combine(current_date.date() + timedelta(days=1), datetime.min.time(), tzinfo=VN_TIMEZONE) - timedelta(seconds=1))
                start_of_period = max(start_time, datetime.combine(current_date.date(), datetime.min.time(), tzinfo=VN_TIMEZONE))
                time_in_day = (end_of_period - start_of_period).total_seconds() / 60
                playtime_data[user_id]["daily_online"][date_str] += time_in_day
                current_date += timedelta(days=1)
            await save_playtime_data(playtime_data, notify_changes=True)
            channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if channel:
                hours = int(time_online // 60)
                mins = int(time_online % 60)
                await channel.send(f"Bot đã reset, thời gian on-duty của {user_id} từ {start_time.strftime('%H:%M:%S %Y-%m-%d')} được khôi phục: {hours}h {mins}m.")

@tasks.loop(minutes=5)
async def check_vinewood_activity():
    global activity_data, vinewood_activity_data
    current_time = datetime.now(VN_TIMEZONE)
    channel = bot.get_channel(VINEWOOD_CHANNEL_ID)
    if not channel:
        print(f"Không tìm thấy kênh Vinewood với ID {VINEWOOD_CHANNEL_ID}")
        return

    users_to_remove = []
    for user_id in list(user_mapping.keys()):
        if user_id not in user_mapping:
            continue
        user_info = user_mapping[user_id]
        guild_id = user_info.get("guild_id")
        if not guild_id:
            users_to_remove.append(user_id)
            continue
        guild = bot.get_guild(int(guild_id))
        if not guild:
            users_to_remove.append(user_id)
            continue
        member = guild.get_member(int(user_id))
        if not member:
            continue

        if user_id not in online_start_times:
            if activity_data.get(user_id, {}).get("in_vinewood", False):
                activity_data[user_id]["in_vinewood"] = False
                activity_data[user_id]["vinewood_start_time"] = None
                activity_data[user_id]["last_notified"] = current_time.isoformat()
                await save_activity_data(activity_data)
                if user_id in vinewood_activity_data and vinewood_activity_data[user_id]["visits"] and not vinewood_activity_data[user_id]["visits"][-1].get("end_time"):
                    vinewood_activity_data[user_id]["visits"][-1]["end_time"] = current_time.isoformat()
                    await save_vinewood_activity_data(vinewood_activity_data)
            continue

        vinewood_active = False
        vehicle = "CARNOTFOUND"
        for activity in member.activities:
            if isinstance(activity, (discord.Game, discord.Activity)):
                activity_text = f"{activity.name} {activity.state or ''} {activity.details or ''}"
                if "Vinewood Park Dr" in activity_text and "bên trong xe" in activity_text:
                    vinewood_active = True
                    vehicle_part = activity_text.split("bên trong xe")[-1].strip()
                    vehicle = vehicle_part.split(" tại ")[0].split(" vào ")[0].strip() or "CARNOTFOUND"
                    break

        if user_id not in activity_data:
            activity_data[user_id] = {"in_vinewood": False, "vinewood_start_time": None, "last_notified": None}
        if user_id not in vinewood_activity_data:
            vinewood_activity_data[user_id] = {"visits": []}

        last_notified = activity_data[user_id].get("last_notified")
        can_notify = not last_notified or (current_time - datetime.fromisoformat(last_notified)).total_seconds() >= 300

        vehicle_status = " (xe không được phép)" if vinewood_active and vehicle not in AUTHORIZED_VEHICLES else ""

        if vinewood_active and not activity_data[user_id]["in_vinewood"] and can_notify:
            activity_data[user_id]["in_vinewood"] = True
            activity_data[user_id]["vinewood_start_time"] = current_time.isoformat()
            activity_data[user_id]["last_notified"] = current_time.isoformat()
            await save_activity_data(activity_data)
            await channel.send(
                f"{member.display_name} đã vào khu vực Vinewood Park Dr lúc {current_time.strftime('%H:%M:%S %Y-%m-%d')} "
                f"bên trong xe {vehicle}{vehicle_status} (đang on-duty)."
            )
            vinewood_activity_data[user_id]["visits"].append({
                "start_time": current_time.isoformat(),
                "vehicle": vehicle,
                "end_time": None,
                "unauthorized": vehicle not in AUTHORIZED_VEHICLES
            })
            await save_vinewood_activity_data(vinewood_activity_data)

        elif not vinewood_active and activity_data[user_id]["in_vinewood"] and can_notify:
            start_time_str = activity_data[user_id]["vinewood_start_time"]
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str).astimezone(VN_TIMEZONE)
                time_spent_seconds = (current_time - start_time).total_seconds()
                hours = int(time_spent_seconds // 3600)
                minutes = int((time_spent_seconds % 3600) // 60)
                seconds = int(time_spent_seconds % 60)
                await channel.send(
                    f"{member.display_name} đã rời khỏi khu vực Vinewood Park Dr sau {hours}h {minutes}m {seconds}s "
                    f"vào lúc {current_time.strftime('%H:%M:%S %Y-%m-%d')} (đang on-duty)."
                )
                if vinewood_activity_data[user_id]["visits"] and not vinewood_activity_data[user_id]["visits"][-1].get("end_time"):
                    vinewood_activity_data[user_id]["visits"][-1]["end_time"] = current_time.isoformat()
                    await save_vinewood_activity_data(vinewood_activity_data)
            activity_data[user_id]["in_vinewood"] = False
            activity_data[user_id]["vinewood_start_time"] = None
            activity_data[user_id]["last_notified"] = current_time.isoformat()
            await save_activity_data(activity_data)

    if users_to_remove:
        for user_id in users_to_remove:
            if user_id in user_mapping:
                del user_mapping[user_id]
        await save_user_mapping(user_mapping)

@tasks.loop(minutes=1)
async def daily_report():
    current_time = datetime.now(VN_TIMEZONE)
    if current_time.hour != 23 or current_time.minute != 59:
        return

    channel = bot.get_channel(REPORT_CHANNEL_ID)
    if not channel:
        print(f"Không tìm thấy kênh báo cáo với ID {REPORT_CHANNEL_ID}")
        return

    report = f"📊 **Báo cáo on-duty ngày {current_time.strftime('%d/%m/%Y')}**:\n"
    users_reported = 0
    current_date_str = current_time.date().isoformat()

    users_to_remove = []
    for user_id, user_info in user_mapping.items():
        if not isinstance(user_info, dict):
            users_to_remove.append(user_id)
            continue
        guild_id = user_info.get("guild_id")
        if not guild_id or not (guild := bot.get_guild(int(guild_id))) or not (member := guild.get_member(int(user_id))):
            users_to_remove.append(user_id)
            continue
        total_online = playtime_data.get(user_id, {}).get("daily_online", {}).get(current_date_str, 0)
        if total_online > 0:
            hours = int(total_online // 60)
            mins = int(total_online % 60)
            report += f"- {member.display_name}: {hours}h {mins}m\n"
            users_reported += 1

    if users_reported == 0:
        report += "Không có ai on-duty hôm nay.\n"

    report += f"\n📍 **Báo cáo hoạt động tại Vinewood Park Dr ngày {current_time.strftime('%d/%m/%Y')}**:\n"
    vinewood_users_reported = 0
    for user_id, user_info in user_mapping.items():
        if not isinstance(user_info, dict):
            continue
        guild_id = user_info.get("guild_id")
        if not guild_id or not (guild := bot.get_guild(int(guild_id))) or not (member := guild.get_member(int(user_id))):
            continue
        visits = vinewood_activity_data.get(user_id, {}).get("visits", [])
        daily_visits = [v for v in visits if datetime.fromisoformat(v["start_time"]).astimezone(VN_TIMEZONE).date() == current_time.date()]
        if daily_visits:
            report += f"- {member.display_name}:\n"
            for visit in daily_visits:
                start_time = datetime.fromisoformat(visit["start_time"]).astimezone(VN_TIMEZONE)
                end_time = datetime.fromisoformat(visit["end_time"]).astimezone(VN_TIMEZONE) if visit.get("end_time") else current_time
                time_spent_seconds = (end_time - start_time).total_seconds()
                hours = int(time_spent_seconds // 3600)
                minutes = int((time_spent_seconds % 3600) // 60)
                seconds = int(time_spent_seconds % 60)
                vehicle = visit.get("vehicle", "CARNOTFOUND")
                vehicle_status = " (xe không được phép)" if visit.get("unauthorized", False) else ""
                report += f"  - {start_time.strftime('%H:%M:%S')} - {end_time.strftime('%H:%M:%S')}: {vehicle}{vehicle_status}, {hours}h {minutes}m {seconds}s\n"
            vinewood_users_reported += 1

    if vinewood_users_reported == 0:
        report += "Không có ai vào Vinewood Park Dr hôm nay.\n"

    await channel.send(report)
    if users_to_remove:
        for user_id in users_to_remove:
            if user_id in user_mapping:
                del user_mapping[user_id]
        await save_user_mapping(user_mapping)

@bot.event
async def on_presence_update(before, after):
    global activity_data, user_mapping, vinewood_activity_data
    user_id = str(after.id)
    current_time = datetime.now(VN_TIMEZONE)

    game_active = any(
        isinstance(activity, (discord.Game, discord.Activity)) and (
            any(keyword in str(activity.name).lower() for keyword in ["gta5vn.net", "gta5vn", "gta v", "gta 5", "fivem"])
        )
        for activity in after.activities
    )

    if game_active and user_id not in user_mapping and after.guild:
        guild_id = str(after.guild.id)
        user_mapping[user_id] = {"guild_id": guild_id}
        await save_user_mapping(user_mapping)
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            await channel.send(f"Người chơi {after.name} đã được tự động thêm vào danh sách.")

    if user_id not in activity_data:
        activity_data[user_id] = {"in_vinewood": False, "vinewood_start_time": None, "last_notified": None}
    if user_id not in vinewood_activity_data:
        vinewood_activity_data[user_id] = {"visits": []}

    # Chỉ kết thúc on-duty khi người dùng offline
    if after.status == discord.Status.offline and user_id in online_start_times:
        if activity_data[user_id]["in_vinewood"]:
            start_time_str = activity_data[user_id]["vinewood_start_time"]
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str).astimezone(VN_TIMEZONE)
                time_spent_seconds = (current_time - start_time).total_seconds()
                hours = int(time_spent_seconds // 3600)
                minutes = int((time_spent_seconds % 3600) // 60)
                seconds = int(time_spent_seconds % 60)
                channel = bot.get_channel(VINEWOOD_CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"{after.name} đã rời khỏi khu vực Vinewood Park Dr sau {hours}h {minutes}m {seconds}s "
                        f"vào lúc {current_time.strftime('%H:%M:%S %Y-%m-%d')} do offline (đang on-duty)."
                    )
                if vinewood_activity_data[user_id]["visits"] and not vinewood_activity_data[user_id]["visits"][-1].get("end_time"):
                    vinewood_activity_data[user_id]["visits"][-1]["end_time"] = current_time.isoformat()
            activity_data[user_id]["in_vinewood"] = False
            activity_data[user_id]["vinewood_start_time"] = None
            activity_data[user_id]["last_notified"] = current_time.isoformat()
            await save_activity_data(activity_data)
            await save_vinewood_activity_data(vinewood_activity_data)

        start_time = online_start_times.pop(user_id)
        time_online = (current_time - start_time).total_seconds() / 60
        if user_id not in playtime_data:
            playtime_data[user_id] = {"daily_online": {}}
        current_date = start_time
        while current_date.date() <= current_time.date():
            date_str = current_date.date().isoformat()
            playtime_data[user_id]["daily_online"].setdefault(date_str, 0)
            end_of_period = min(current_time, datetime.combine(current_date.date() + timedelta(days=1), datetime.min.time(), tzinfo=VN_TIMEZONE) - timedelta(seconds=1))
            start_of_period = max(start_time, datetime.combine(current_date.date(), datetime.min.time(), tzinfo=VN_TIMEZONE))
            time_in_day = (end_of_period - start_of_period).total_seconds() / 60
            playtime_data[user_id]["daily_online"][date_str] += time_in_day
            current_date += timedelta(days=1)
        await save_playtime_data(playtime_data, notify_changes=True)
        await save_online_times(online_start_times)
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            hours = int(time_online // 60)
            mins = int(time_online % 60)
            await channel.send(f"{after.display_name} đã dừng on-duty lúc {current_time.strftime('%H:%M:%S %Y-%m-%d')}. Thời gian: {hours}h {mins}m (tự động do offline).")

@bot.command()
async def help(ctx):
    if not ctx.guild:
        await ctx.send("Lệnh !help chỉ có thể được sử dụng trong server.")
        return

    is_admin = has_admin_role(ctx.author)
    current_time = datetime.now(VN_TIMEZONE)
    formatted_time = current_time.strftime('%H:%M:%S %d/%m/%Y')
    embed = discord.Embed(
        title="📋 **Hướng Dẫn Sử Dụng Bot**",
        description="Danh sách các lệnh có sẵn trong bot.",
        color=discord.Color.green() if not is_admin else discord.Color.gold()
    )
    embed.add_field(
        name="🔹 **Lệnh Dành Cho Tất Cả Người Dùng**",
        value="`!onduty` - Bắt đầu trạng thái on-duty.\n`!offduty` - Dừng trạng thái on-duty.\n`!help` - Hiển thị menu hướng dẫn này.",
        inline=False
    )
    if is_admin:
        embed.add_field(
            name="🔸 **Lệnh Dành Riêng Cho Admin**",
            value="`!donduty @tag` - Buộc người được tag vào trạng thái on-duty.\n"
                  "`!doffduty @tag` - Buộc người được tag dừng trạng thái on-duty.\n"
                  "`!id [số_id]` - Xem tên người dùng từ ID.\n"
                  "`!checkdays [ngày/tháng] hoặc [ngày/tháng-ngày/tháng]` - Xem thời gian on-duty.\n"
                  "`!checkduty` - Hiển thị danh sách người chơi đang on-duty.\n"
                  "`!checkoff` - Hiển thị danh sách người chơi đang off-duty.\n"
                  "`!checkreg` - Xem danh sách người chơi đã đăng ký.\n"
                  "`!vinewood` - Xem người chơi đang ở Vinewood Park Dr.\n"
                  "`!checkstatus` - Kiểm tra trạng thái bot.\n"
                  "`!playtime [@tag]` - Xem tổng thời gian on-duty.\n"
                  "`!lichsu [@tag]` - Xem lịch sử on-duty 7 ngày gần nhất.\n"
                  "`!clean <số_lượng>` - Xóa số lượng tin nhắn được chỉ định.\n"
                  "`!time add/subtract @tag <time>` - Thêm/trừ thời gian on-duty (ví dụ: 10m, 2h30m)",
            inline=False
    )
    embed.set_footer(text=f"Bot được tạo bởi Thowm2005 | Thời gian hiện tại: {formatted_time}")
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1354932216643190784/1354932353486819430/lapd-code3.gif")
    await ctx.send(embed=embed)

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def onduty(ctx):
    if not ctx.guild:
        await ctx.send("Lệnh !onduty chỉ có thể được sử dụng trong server.")
        return
    user_id = str(ctx.author.id)
    current_time = datetime.now(VN_TIMEZONE)
    if user_id in online_start_times:
        start_time = online_start_times[user_id]
        time_online = (current_time - start_time).total_seconds() / 60
        hours = int(time_online // 60)
        mins = int(time_online % 60)
        await ctx.send(f"Bạn đã on-duty từ {start_time.strftime('%H:%M:%S %Y-%m-%d')}. Thời gian: {hours}h {mins}m.")
        return
    if user_id not in user_mapping:
        guild_id = str(ctx.guild.id)
        user_mapping[user_id] = {"guild_id": guild_id}
        await save_user_mapping(user_mapping)
    online_start_times[user_id] = current_time
    await save_online_times(online_start_times)
    await ctx.send(f"{ctx.author.display_name} đã bắt đầu on-duty lúc {current_time.strftime('%H:%M:%S %Y-%m-%d')}.")

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def offduty(ctx):
    if not ctx.guild:
        await ctx.send("Lệnh !offduty chỉ có thể được sử dụng trong server.")
        return
    user_id = str(ctx.author.id)
    current_time = datetime.now(VN_TIMEZONE)
    if user_id not in online_start_times:
        await ctx.send("Bạn hiện không ở trạng thái on-duty.")
        loaded_times = load_online_times()
        if user_id in loaded_times:
            await ctx.send(f"(Debug) Tuy nhiên, file online_times.json vẫn ghi nhận bạn on-duty từ {loaded_times[user_id].strftime('%H:%M:%S %Y-%m-%d')}. Đang sửa...")
            online_start_times[user_id] = loaded_times[user_id]
        return
    start_time = online_start_times.pop(user_id)
    time_online = (current_time - start_time).total_seconds() / 60
    if user_id not in playtime_data:
        playtime_data[user_id] = {"daily_online": {}}
    current_date = start_time
    while current_date.date() <= current_time.date():
        date_str = current_date.date().isoformat()
        playtime_data[user_id]["daily_online"].setdefault(date_str, 0)
        end_of_period = min(current_time, datetime.combine(current_date.date() + timedelta(days=1), datetime.min.time(), tzinfo=VN_TIMEZONE) - timedelta(seconds=1))
        start_of_period = max(start_time, datetime.combine(current_date.date(), datetime.min.time(), tzinfo=VN_TIMEZONE))
        time_in_day = (end_of_period - start_of_period).total_seconds() / 60
        playtime_data[user_id]["daily_online"][date_str] += time_in_day
        current_date += timedelta(days=1)
    await save_playtime_data(playtime_data, notify_changes=True)
    await save_online_times(online_start_times)
    await ctx.send(f"{ctx.author.display_name} đã dừng on-duty. Thời gian: {int(time_online // 60)}h {int(time_online % 60)}m.")

@bot.command()
async def donduty(ctx, member: discord.Member):
    if not ctx.guild:
        await ctx.send("Lệnh !donduty chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    user_id = str(member.id)
    current_time = datetime.now(VN_TIMEZONE)
    if user_id in online_start_times:
        start_time = online_start_times[user_id]
        time_online = (current_time - start_time).total_seconds() / 60
        hours = int(time_online // 60)
        mins = int(time_online % 60)
        await ctx.send(f"{member.display_name} đã on-duty từ {start_time.strftime('%H:%M:%S %Y-%m-%d')}. Thời gian: {hours}h {mins}m.")
        return
    if user_id not in user_mapping:
        guild_id = str(ctx.guild.id)
        user_mapping[user_id] = {"guild_id": guild_id}
        await save_user_mapping(user_mapping)
    online_start_times[user_id] = current_time
    await save_online_times(online_start_times)
    await ctx.send(f"{member.display_name} đã được admin {ctx.author.display_name} buộc vào trạng thái on-duty lúc {current_time.strftime('%H:%M:%S %Y-%m-%d')}.")

@bot.command()
async def doffduty(ctx, member: discord.Member):
    if not ctx.guild:
        await ctx.send("Lệnh !doffduty chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    user_id = str(member.id)
    current_time = datetime.now(VN_TIMEZONE)
    if user_id not in online_start_times:
        await ctx.send(f"{member.display_name} hiện không ở trạng thái on-duty.")
        return
    start_time = online_start_times.pop(user_id)
    time_online = (current_time - start_time).total_seconds() / 60
    if user_id not in playtime_data:
        playtime_data[user_id] = {"daily_online": {}}
    current_date = start_time
    while current_date.date() <= current_time.date():
        date_str = current_date.date().isoformat()
        playtime_data[user_id]["daily_online"].setdefault(date_str, 0)
        end_of_period = min(current_time, datetime.combine(current_date.date() + timedelta(days=1), datetime.min.time(), tzinfo=VN_TIMEZONE) - timedelta(seconds=1))
        start_of_period = max(start_time, datetime.combine(current_date.date(), datetime.min.time(), tzinfo=VN_TIMEZONE))
        time_in_day = (end_of_period - start_of_period).total_seconds() / 60
        playtime_data[user_id]["daily_online"][date_str] += time_in_day
        current_date += timedelta(days=1)
    await save_playtime_data(playtime_data, notify_changes=True)
    await save_online_times(online_start_times)
    await ctx.send(f"{member.display_name} đã bị admin {ctx.author.display_name} buộc dừng on-duty. Thời gian: {int(time_online // 60)}h {int(time_online % 60)}m.")

@bot.command()
async def id(ctx, user_id: int):
    if not ctx.guild:
        await ctx.send("Lệnh !id chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    member = ctx.guild.get_member(user_id)
    if member:
        await ctx.send(f"ID `{user_id}` thuộc về: **{member.display_name}**")
    else:
        await ctx.send(f"Không tìm thấy người dùng với ID `{user_id}` trong server này.")

@bot.command(name="checkdays")
async def checkdays(ctx, *, date_range: str):
    if not ctx.guild:
        await ctx.send("Lệnh !checkdays chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    current_time = datetime.now(VN_TIMEZONE)
    current_year = current_time.year
    if "-" in date_range:
        try:
            start_date_str, end_date_str = date_range.split("-")
            start_day, start_month = map(int, start_date_str.split("/"))
            end_day, end_month = map(int, end_date_str.split("/"))
            start_date = date(current_year, start_month, start_day)
            end_date = date(current_year, end_month, end_day)
            if start_date > end_date:
                await ctx.send("Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc.")
                return
        except ValueError:
            await ctx.send("Định dạng: !checkdays ngày/tháng hoặc !checkdays ngày/tháng-ngày/tháng (ví dụ: 25/3 hoặc 25/3-30/3).")
            return
        report = f"📊 **Thời gian on-duty từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}**:\n"
        users_reported = 0
        users_to_remove = []
        for user_id, user_info in user_mapping.items():
            if not isinstance(user_info, dict):
                users_to_remove.append(user_id)
                continue
            guild_id = user_info.get("guild_id")
            if not guild_id or not (guild := bot.get_guild(int(guild_id))) or not (member := guild.get_member(int(user_id))):
                users_to_remove.append(user_id)
                continue
            total_online = 0
            daily_summary = ""
            for date_str, minutes in playtime_data.get(user_id, {}).get("daily_online", {}).items():
                date_obj = datetime.fromisoformat(date_str).date()
                if start_date <= date_obj <= end_date:
                    total_online += minutes
                    hours = int(minutes // 60)
                    mins = int(minutes % 60)
                    daily_summary += f"  - {date_obj.strftime('%d/%m/%Y')}: {hours}h {mins}m\n"
            if total_online > 0:
                total_hours = int(total_online // 60)
                total_mins = int(total_online % 60)
                report += f"- {member.display_name}:\n{daily_summary}  Tổng: {total_hours}h {total_mins}m\n"
                users_reported += 1
        if users_reported == 0:
            report += "Không có dữ liệu on-duty trong khoảng thời gian này.\n"
    else:
        try:
            day, month = map(int, date_range.split("/"))
            target_date = date(current_year, month, day)
        except ValueError:
            await ctx.send("Định dạng: !checkdays ngày/tháng (ví dụ: 25/3).")
            return
        target_date_str = target_date.isoformat()
        report = f"📊 **Thời gian on-duty ngày {target_date.strftime('%d/%m/%Y')}**:\n"
        users_reported = 0
        users_to_remove = []
        for user_id, user_info in user_mapping.items():
            if not isinstance(user_info, dict):
                users_to_remove.append(user_id)
                continue
            guild_id = user_info.get("guild_id")
            if not guild_id or not (guild := bot.get_guild(int(guild_id))) or not (member := guild.get_member(int(user_id))):
                users_to_remove.append(user_id)
                continue
            total_online = playtime_data.get(user_id, {}).get("daily_online", {}).get(target_date_str, 0)
            if total_online > 0:
                hours = int(total_online // 60)
                mins = int(total_online % 60)
                report += f"- {member.display_name}: {hours}h {mins}m\n"
                users_reported += 1
        if users_reported == 0:
            report += "Không có dữ liệu on-duty trong ngày này.\n"
    await ctx.send(report)
    if users_to_remove:
        for user_id in users_to_remove:
            if user_id in user_mapping:
                del user_mapping[user_id]
        await save_user_mapping(user_mapping)

@bot.command(name="checkduty")
async def checkduty(ctx):
    if not ctx.guild:
        await ctx.send("Lệnh !checkduty chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    current_time = datetime.now(VN_TIMEZONE)
    report = "📊 **Danh sách người chơi đang on-duty**:\n"
    users_reported = 0
    users_to_remove = []
    for user_id, user_info in user_mapping.items():
        if not isinstance(user_info, dict):
            users_to_remove.append(user_id)
            continue
        guild_id = user_info.get("guild_id")
        if not guild_id or not (guild := bot.get_guild(int(guild_id))) or not (member := guild.get_member(int(user_id))):
            users_to_remove.append(user_id)
            continue
        if user_id in online_start_times:
            start_time = online_start_times[user_id]
            time_online = (current_time - start_time).total_seconds() / 60
            hours = int(time_online // 60)
            mins = int(time_online % 60)
            report += f"- {member.display_name}: {hours}h {mins}m (bắt đầu từ {start_time.strftime('%H:%M:%S %Y-%m-%d')})\n"
            users_reported += 1
    if users_reported == 0:
        report += "Không có ai đang on-duty.\n"
    await ctx.send(report)
    if users_to_remove:
        for user_id in users_to_remove:
            if user_id in user_mapping:
                del user_mapping[user_id]
        await save_user_mapping(user_mapping)

@bot.command(name="checkoff")
async def checkoff(ctx):
    if not ctx.guild:
        await ctx.send("Lệnh !checkoff chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    report = "📊 **Danh sách người chơi đang off-duty**:\n"
    users_reported = 0
    users_to_remove = []
    for user_id, user_info in user_mapping.items():
        if not isinstance(user_info, dict):
            users_to_remove.append(user_id)
            continue
        guild_id = user_info.get("guild_id")
        if not guild_id or not (guild := bot.get_guild(int(guild_id))) or not (member := guild.get_member(int(user_id))):
            users_to_remove.append(user_id)
            continue
        if user_id not in online_start_times:
            report += f"- {member.display_name}\n"
            users_reported += 1
    if users_reported == 0:
        report += "Không có ai đang off-duty.\n"
    await ctx.send(report)
    if users_to_remove:
        for user_id in users_to_remove:
            if user_id in user_mapping:
                del user_mapping[user_id]
        await save_user_mapping(user_mapping)

@bot.command(name="checkreg")
async def checkreg(ctx):
    if not ctx.guild:
        await ctx.send("Lệnh !checkreg chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    report = "📋 **Danh sách người chơi đã đăng ký**:\n"
    users_reported = 0
    for user_id, user_info in user_mapping.items():
        guild_id = user_info.get("guild_id")
        if guild_id and (guild := bot.get_guild(int(guild_id))) and (member := guild.get_member(int(user_id))):
            report += f"- {member.display_name} (ID: {user_id})\n"
            users_reported += 1
    if users_reported == 0:
        report += "Không có người chơi nào được đăng ký.\n"
    await ctx.send(report)

@bot.command()
async def vinewood(ctx):
    if not ctx.guild:
        await ctx.send("Lệnh !vinewood chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    report = "📍 **Danh sách người chơi đang ở Vinewood Park Dr**:\n"
    users_reported = 0
    current_time = datetime.now(VN_TIMEZONE)
    for user_id, user_info in user_mapping.items():
        guild_id = user_info.get("guild_id")
        if guild_id and (guild := bot.get_guild(int(guild_id))) and (member := guild.get_member(int(user_id))):
            if activity_data.get(user_id, {}).get("in_vinewood", False):
                start_time = datetime.fromisoformat(activity_data[user_id]["vinewood_start_time"]).astimezone(VN_TIMEZONE)
                time_spent = (current_time - start_time).total_seconds() / 60
                hours = int(time_spent // 60)
                mins = int(time_spent % 60)
                report += f"- {member.display_name}: {hours}h {mins}m\n"
                users_reported += 1
    if users_reported == 0:
        report += "Không có ai đang ở Vinewood Park Dr.\n"
    await ctx.send(report)

@bot.command()
async def checkstatus(ctx):
    if not ctx.guild:
        await ctx.send("Lệnh !checkstatus chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    current_time = datetime.now(VN_TIMEZONE)
    uptime = (current_time - bot.start_time) if hasattr(bot, 'start_time') else timedelta(seconds=0)
    embed = discord.Embed(
        title="🤖 **Trạng thái Bot**",
        color=discord.Color.blue()
    )
    embed.add_field(name="Thời gian hoạt động", value=f"{int(uptime.total_seconds() // 3600)}h {int((uptime.total_seconds() % 3600) // 60)}m", inline=False)
    embed.add_field(name="Số server", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Số người dùng", value=str(sum(guild.member_count for guild in bot.guilds)), inline=True)
    embed.set_footer(text=f"Thời gian hiện tại: {current_time.strftime('%H:%M:%S %Y-%m-%d')}")
    await ctx.send(embed=embed)

@bot.command()
async def playtime(ctx, member: discord.Member = None):
    if not ctx.guild:
        await ctx.send("Lệnh !playtime chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    target = member or ctx.author
    user_id = str(target.id)
    if user_id not in playtime_data or "daily_online" not in playtime_data[user_id]:
        await ctx.send(f"{target.display_name} chưa có dữ liệu on-duty.")
        return
    total_minutes = sum(playtime_data[user_id]["daily_online"].values())
    total_hours = int(total_minutes // 60)
    total_mins = int(total_minutes % 60)
    report = f"⏱ **Tổng thời gian on-duty của {target.display_name}**:\n- Tổng cộng: {total_hours}h {total_mins}m\n"
    await ctx.send(report)

@bot.command()
async def lichsu(ctx, member: discord.Member = None):
    if not ctx.guild:
        await ctx.send("Lệnh !lichsu chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    target = member or ctx.author
    user_id = str(target.id)
    if user_id not in playtime_data or "daily_online" not in playtime_data[user_id]:
        await ctx.send(f"{target.display_name} chưa có dữ liệu on-duty.")
        return
    report = f"📜 **Lịch sử on-duty của {target.display_name} (7 ngày gần nhất)**:\n"
    current_time = datetime.now(VN_TIMEZONE)
    seven_days_ago = current_time - timedelta(days=7)
    total_minutes = 0
    for date_str, minutes in playtime_data[user_id]["daily_online"].items():
        date_obj = datetime.fromisoformat(date_str).date()
        if date_obj >= seven_days_ago.date():
            hours = int(minutes // 60)
            mins = int(minutes % 60)
            report += f"- {date_obj.strftime('%d/%m/%Y')}: {hours}h {mins}m\n"
            total_minutes += minutes
    total_hours = int(total_minutes // 60)
    total_mins = int(total_minutes % 60)
    report += f"**Tổng cộng**: {total_hours}h {total_mins}m\n"
    await ctx.send(report)

@bot.command()
async def clean(ctx, amount: int):
    if not ctx.guild:
        await ctx.send("Lệnh !clean chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    if amount < 1:
        await ctx.send("Số lượng tin nhắn cần xóa phải lớn hơn 0.")
        return
    if amount > 100:
        await ctx.send("Bạn chỉ có thể xóa tối đa 100 tin nhắn một lần.")
        return
    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Đã xóa {len(deleted) - 1} tin nhắn.", delete_after=5)
    except discord.Forbidden:
        await ctx.send("Bot không có quyền xóa tin nhắn.")
    except discord.HTTPException as e:
        await ctx.send(f"Lỗi khi xóa tin nhắn: {e}")

@bot.command()
async def time(ctx, action: str, member: discord.Member, time_str: str):
    if not ctx.guild:
        await ctx.send("Lệnh !time chỉ có thể được sử dụng trong server.")
        return
    if not has_admin_role(ctx.author):
        await ctx.send(f"{ctx.author.mention}, chỉ admin mới có thể sử dụng lệnh này!")
        return
    if action.lower() not in ["add", "subtract"]:
        await ctx.send("Hành động phải là 'add' hoặc 'subtract'. Ví dụ: !time add @user 10m")
        return
    try:
        total_minutes = 0
        if 'h' in time_str.lower():
            hours = int(time_str.lower().split('h')[0])
            total_minutes += hours * 60
            if 'm' in time_str.lower():
                minutes = int(time_str.lower().split('h')[1].split('m')[0])
                total_minutes += minutes
        elif 'm' in time_str.lower():
            minutes = int(time_str.lower().split('m')[0])
            total_minutes += minutes
        else:
            await ctx.send("Vui lòng cung cấp thời gian hợp lệ (ví dụ: 10m, 2h, 2h30m)")
            return
    except ValueError:
        await ctx.send("Định dạng thời gian không hợp lệ. Ví dụ: !time add @user 10m hoặc !time subtract @user 2h30m")
        return
    if total_minutes <= 0:
        await ctx.send("Thời gian phải lớn hơn 0.")
        return
    user_id = str(member.id)
    current_time = datetime.now(VN_TIMEZONE)
    current_date_str = current_time.date().isoformat()
    if user_id not in playtime_data:
        playtime_data[user_id] = {"daily_online": {}}
    playtime_data[user_id]["daily_online"].setdefault(current_date_str, 0)
    if action.lower() == "add":
        playtime_data[user_id]["daily_online"][current_date_str] += total_minutes
        action_str = "thêm"
    else:
        playtime_data[user_id]["daily_online"][current_date_str] = max(0, playtime_data[user_id]["daily_online"][current_date_str] - total_minutes)
        action_str = "trừ"
    await save_playtime_data(playtime_data, notify_changes=True)
    hours = int(total_minutes // 60)
    mins = int(total_minutes % 60)
    time_display = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
    await ctx.send(f"Đã {action_str} {time_display} vào thời gian on-duty của {member.display_name} trong file playtime.json cho ngày {current_date_str}.")

bot.run("Token")
