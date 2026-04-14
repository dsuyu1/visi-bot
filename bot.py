"""
VISI Discord Events & Announcements Bot
----------------------------------------
Commands:
  !announce <event_id>   - Post a specific event by its ID
  !announce all          - List all upcoming events (summary)
  !events                - Alias for !announce all
  !schedule              - Show what the bot will auto-announce and when

Auto-posts at 7 days and 1 day before each event's date.
"""

import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TOKEN             = os.environ["DISCORD_TOKEN"]
ANNOUNCE_CHANNEL  = int(os.environ.get("ANNOUNCE_CHANNEL_ID", 0))   # 0 = reply in same channel
EVENTS_FILE       = Path(__file__).parent / "events.json"
CHECK_INTERVAL    = 60 * 60   # run scheduler check every hour (in seconds)

# How many days before an event to auto-announce (can add/remove values)
ADVANCE_DAYS = [7, 1]

# ---------------------------------------------------------------------------
# Skill-level colors for embeds
# ---------------------------------------------------------------------------
LEVEL_COLORS = {
    "beginner":     discord.Color.from_str("#1D9E75"),   # teal
    "intermediate": discord.Color.from_str("#7F77DD"),   # purple
    "advanced":     discord.Color.from_str("#D85A30"),   # coral
    "training":     discord.Color.from_str("#378ADD"),   # blue
}

# ---------------------------------------------------------------------------
# Load events
# ---------------------------------------------------------------------------
def load_events() -> list[dict]:
    with open(EVENTS_FILE, "r") as f:
        return json.load(f)

def get_event_by_id(event_id: str) -> dict | None:
    for event in load_events():
        if event["id"].lower() == event_id.lower():
            return event
    return None

def upcoming_events() -> list[dict]:
    """Return events whose date is today or in the future, sorted."""
    today = datetime.now(timezone.utc).date()
    events = [
        e for e in load_events()
        if datetime.fromisoformat(e["date"]).date() >= today
    ]
    return sorted(events, key=lambda e: e["date"])

# ---------------------------------------------------------------------------
# Embed builder
# ---------------------------------------------------------------------------
def build_embed(event: dict, headline: str | None = None) -> discord.Embed:
    level  = event.get("level", "training").lower()
    color  = LEVEL_COLORS.get(level, discord.Color.blurple())
    date   = datetime.fromisoformat(event["date"]).strftime("%B %-d, %Y")

    title = f"{'📣 ' if headline else ''}{event['name']}"
    embed = discord.Embed(title=title, color=color)

    if headline:
        embed.description = f"*{headline}*"

    embed.add_field(
        name="📅  Date",
        value=date,
        inline=True
    )
    embed.add_field(
        name="🎯  Skill level",
        value=event.get("level", "All levels").capitalize(),
        inline=True
    )
    embed.add_field(
        name="💰  Cost",
        value=event.get("cost", "Free"),
        inline=True
    )
    embed.add_field(
        name="👥  Who should participate",
        value=event["who"],
        inline=False
    )
    embed.add_field(
        name="📋  How to participate",
        value=event["how"],
        inline=False
    )
    embed.add_field(
        name="🏆  What you'll get out of it",
        value=event["deliverables"],
        inline=False
    )
    if event.get("link"):
        embed.add_field(
            name="🔗  Link",
            value=event["link"],
            inline=False
        )
    if event.get("team_size"):
        embed.set_footer(text=f"Team size: {event['team_size']}  •  VISI – Vaquero Information Security Initiative")
    else:
        embed.set_footer(text="VISI – Vaquero Information Security Initiative")

    return embed

def build_summary_embed(events: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="📅  Upcoming VISI Events & Competitions",
        color=discord.Color.from_str("#7F77DD"),
        description="Here's everything on the calendar. Use `!announce <id>` to get full details on any event."
    )
    for e in events:
        date = datetime.fromisoformat(e["date"]).strftime("%b %-d")
        cost = "Free" if e.get("cost", "Free").lower() == "free" else e["cost"]
        embed.add_field(
            name=f"{date}  —  {e['name']}",
            value=f"`!announce {e['id']}`  •  {e.get('level','').capitalize()}  •  {cost}",
            inline=False
        )
    embed.set_footer(text="VISI – Vaquero Information Security Initiative")
    return embed

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@bot.command(name="announce")
async def cmd_announce(ctx: commands.Context, *, arg: str = ""):
    """!announce <event_id>  or  !announce all"""
    arg = arg.strip().lower()

    if not arg or arg == "all":
        events = upcoming_events()
        if not events:
            await ctx.send("No upcoming events found in the calendar.")
            return
        await _send_to_channel(ctx, embed=build_summary_embed(events))
        return

    event = get_event_by_id(arg)
    if not event:
        await ctx.send(
            f"❌  No event found with ID `{arg}`. "
            f"Try `!announce all` to see valid IDs."
        )
        return

    await _send_to_channel(ctx, embed=build_embed(event))


@bot.command(name="events")
async def cmd_events(ctx: commands.Context):
    """Alias for !announce all"""
    await cmd_announce(ctx, arg="all")


@bot.command(name="schedule")
async def cmd_schedule(ctx: commands.Context):
    """Show what the bot will auto-announce and when."""
    events = upcoming_events()
    today  = datetime.now(timezone.utc).date()

    lines = []
    for e in events:
        edate = datetime.fromisoformat(e["date"]).date()
        for days in ADVANCE_DAYS:
            post_on = edate - timedelta(days=days)
            if post_on >= today:
                label = "tomorrow" if (post_on - today).days == 0 else post_on.strftime("%b %-d")
                lines.append(f"• **{label}** → *{e['name']}* ({days}d notice)")

    if not lines:
        await ctx.send("No scheduled auto-announcements coming up.")
        return

    embed = discord.Embed(
        title="🗓️  Auto-announcement schedule",
        description="\n".join(lines) or "Nothing scheduled.",
        color=discord.Color.from_str("#378ADD")
    )
    embed.set_footer(text="Checks run hourly. Times are UTC.")
    await ctx.send(embed=embed)


@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    embed = discord.Embed(
        title="VISI Bot — Commands",
        color=discord.Color.from_str("#7F77DD")
    )
    embed.add_field(name="!events",               value="List all upcoming events",              inline=False)
    embed.add_field(name="!announce all",          value="Same as !events",                       inline=False)
    embed.add_field(name="!announce <id>",         value="Full details for a specific event",     inline=False)
    embed.add_field(name="!schedule",              value="Show upcoming auto-announcements",       inline=False)
    embed.add_field(name="!help",                  value="This message",                          inline=False)
    await ctx.send(embed=embed)

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
@tasks.loop(seconds=CHECK_INTERVAL)
async def scheduler():
    """Check every hour whether any event needs a 7-day or 1-day announcement."""
    channel = bot.get_channel(ANNOUNCE_CHANNEL)
    if channel is None:
        log.warning("ANNOUNCE_CHANNEL_ID not set or channel not found; skipping scheduler.")
        return

    today  = datetime.now(timezone.utc).date()
    events = load_events()

    for event in events:
        edate = datetime.fromisoformat(event["date"]).date()
        for days in ADVANCE_DAYS:
            if (edate - today).days == days:
                log.info(f"Auto-announcing '{event['name']}' ({days}d notice)")
                headline = (
                    f"Only {days} day{'s' if days > 1 else ''} away!"
                    if days <= 1
                    else f"Coming up in {days} days!"
                )
                await channel.send(embed=build_embed(event, headline=headline))
                break   # only one notice per day per event


@scheduler.before_loop
async def before_scheduler():
    await bot.wait_until_ready()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _send_to_channel(ctx: commands.Context, **kwargs):
    """Send to ANNOUNCE_CHANNEL if set, else reply in the command channel."""
    target = bot.get_channel(ANNOUNCE_CHANNEL) if ANNOUNCE_CHANNEL else ctx.channel
    await target.send(**kwargs)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (id: {bot.user.id})")
    scheduler.start()

bot.run(TOKEN)
