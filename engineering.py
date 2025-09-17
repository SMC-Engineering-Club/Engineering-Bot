import discord, asyncio, json, os, time, pytz
from discord.ext import tasks, commands
import urllib.parse
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("DISCORD_TOKEN") #hidden token for security
GUILD_ID = #input guild id

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) #defining the base directory
REMINDERS_PATH = os.path.join(BASE_DIR, "engr", "reminders.json") #defining the path to the reminders.json file.
os.makedirs(os.path.dirname(REMINDERS_PATH), exist_ok=True) #make the directory if its not.
print(f"[reminders] using file: {REMINDERS_PATH}") #printing to log which path to reminders.json

LEAD_DAYS = 0.00694 # create event 6 days prior
DURATION_HOURS = 0.1667 #event lasts this long in hours (this is global, i may change it to be dynamic based on reminders file.

#intents allows it to use slash commands
intents = discord.Intents.default()
intents.message_content = True

#defines a command prefix of !
bot = commands.Bot(command_prefix="!", intents=intents)

#when the bot becomes online, it automatically prints that the bot is online into the log and begins the scheduler.
@bot.event
async def on_ready():
  print(f"Bot is online as {bot.user}")
  if not scheduler.is_running():
    scheduler.start()

#simple command to get the id of the owner of the guild. sometimes discord does not show the crown on the person.
@bot.command()
async def o(ctx):
  owner = ctx.guild.owner_id
  await ctx.send(f"{owner}")

#using !l it puts your LaTeX at the back of the https://latex.codecog.com/png.image? url, as well as some latex commands to enhance the image.
@bot.command(help="Render LaTeX. Usage: !l <latex_code>")
async def l(ctx, *, latex_code):
  encoded = urllib.parse.quote(latex_code)
  full_latex = r"\dpi{300}\bg{white}\fg{black}" + encoded
  url = f"https://latex.codecogs.com/png.image?{full_latex}"
  await ctx.send(url)

#main event scheduler:

#loads the reminders file.
def load_reminders():
  if not os.path.exists(REMINDERS_PATH):
    return []
  with open(REMINDERS_PATH, "r", encoding="utf-8") as f:
    return json.load(f)

#this saves data to the reminders file, specifically the "created" part to true once its been created.
def save_reminders(items):
  try:
    with open(REMINDERS_PATH, "w", encoding="utf-8") as f:
      json.dump(items, f, ensure_ascii=False, indent=2)
      print(f"[reminders] saved: {REMINDERS_PATH}")
  except Exception as e:
      print(f"[reminders] save FAILED: {e}")

reminders = load_reminders()


#this is the scheduler loop. every 30 seconds, it checks for all "events" in the reminders json file where the "created" is flase, and the unix time stamp is within the next 6 days. if so, it tries to create an event.
@tasks.loop(seconds=30.0)
async def scheduler():
  now = int(time.time())
  guild = bot.get_guild(GUILD_ID)
  if guild is None:
    try:
      guild = await bot.fetch_guild(GUILD_ID)
    except Exception:
      return

  changed = False
  for r in reminders:
    if r.get("created"):
      continue

    ts = int(r["ts"]) #unix seconds - event start
    create_at = ts - LEAD_DAYS * 24 * 3600

    if now < create_at:
      continue #not time yet

    start_dt = datetime.fromtimestamp(ts, tz=timezone.utc)

    if start_dt <= datetime.now(timezone.utc):
      r["created"] = True
      changed = True
      print(f"[scheduler] Skipped '{r.get('title')}' - start already passed.")
      save_reminders(reminders)
      continue

    end_dt = start_dt + timedelta(hours=DURATION_HOURS)

    #where it tries to make the scheduled event.
    try:
      await guild.create_scheduled_event(
        name=r.get("title", "Reminder"),
        start_time=start_dt,
        end_time=end_dt,
        description=r.get("desc", ""),
        privacy_level=discord.PrivacyLevel.guild_only,
        entity_type=discord.EntityType.external,
        location=r.get("location", "Error! Notify a board member!")
      )
      r["created"] = True
      changed = True
      print(f"[scheduler] Created event '{r.get('title')}' "
        f"(starts {start_dt.isoformat()}, ends {end_dt.isoformat()})")
      save_reminders(reminders)
    except discord.Forbidden: #failsafe for missing permissions
      print("[scheduler] Missing persmissions (need Manage Events).")
    except discord.HTTPException as e: #failsafe for any other rrors.
      print(f"[scheduler] Failed to create event: {e}")

  if changed:
    save_reminders(reminders) #save that to reminders.

#letting you know the scheduler is started.
@scheduler.before_loop
async def before_scheduler():
  await bot.wait_until_ready()
  print("[scheduler] started")

#allowed role ids to run the "admin" commands such as obtaining the scheduler status and the getting the reminders json. it's a list, separated by commas.
ALLOWED_ROLE_IDS = {}

#checks for if the person who ran the command, as a role that's in the list ALLOWED_ROLE_IDS
def has_allowed_role(member: discord.Member) -> bool:
  return any(role.id in ALLOWED_ROLE_IDS for role in member.roles)

# check scheduler status command. just lets you know if its running if so, it sends that its running and how long till next "attempt"
@bot.command(name="scheduler_status")
async def scheduler_status(ctx):
  if not has_allowed_role(ctx.author): #failsafe if no correct perms.
    await ctx.message.delete(delay=5)
    return await ctx.send("Not authorized.", delete_after=5) 

  running = scheduler.is_running()
  msg = f"Scheduler running: **{running}**"

  if running:
    next_when = getattr(scheduler, "next_iteration", None)
    if next_when:
	    now_utc = datetime.now(timezone.utc)
	    seconds_left = int((next_when - now_utc).total_seconds())
	    msg += f"\nNext tick: **{seconds_left} seconds**"
  await ctx.send(msg)

# send reminders.json to the server if you need it.
@bot.command(name="send_reminders")
async def send_reminders(ctx):
  if not has_allowed_role(ctx.author): #failsafe for improper role permissions
    await ctx.message.delete(delay=5)
    return await ctx.send("Not authorized.", delete_after=5)
  if not os.path.exists(REMINDERS_PATH): #failsafe for missing file
    return await ctx.send("reminders.json not found")
  try:
    await ctx.send(file=discord.File(REMINDERS_PATH))
  except Exception as e: #any other errors.
    await ctx.send(f"Couldn't send reminders.json: `{e}`")

bot.run(TOKEN) #running the bot.
