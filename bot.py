import logging
import os
import random
import json
import discord
from discord.ext import commands
from discord.utils import get
from dotenv import load_dotenv


DOWNLOAD_DIR = "/home/ubuntu/assassin_discord/DOWNLOAD_DIR"

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PASSWORD = os.getenv("PASSWORD")
PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID", "0"))
GENERAL_CHANNEL_ID = int(os.getenv("GENERAL_CHANNEL_ID", "0"))


logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w"),
        logging.StreamHandler(),
    ],
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def load_people() -> list:
    """Load player data from people.json, or return empty list if not found."""
    try:
        with open("people.json", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_people(data: list) -> None:
    """Save player data to people.json."""
    with open("people.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)



intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)



@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")



@bot.command()
async def join(ctx, *, full_name: str):
    """Register a new player."""
    people = load_people()
    if people[0]["target"]:
        await ctx.author.send("game has started no more registrations")
        return

    if any(p["username"] == str(ctx.author) for p in people):
        await ctx.author.send("You are already registered!")
        await ctx.message.delete()
        return


    people.append({
        "fullname": full_name,
        "target": None,
        "status": "alive",
        "username": str(ctx.author),
        "path": None,
    })
    save_people(people)
    logging.info("Added new player: %s", full_name)

    await ctx.message.delete()
    await ctx.author.send(
        f"You are registered!\nHere are the rules...\nYour fullname: {full_name}"
    )


@bot.command(hidden=True)
async def super_duper_secret_command(ctx, *, password: str):

    await ctx.message.delete()

    if password != PASSWORD:
        await ctx.author.send("Invalid password.")
        return

    people = load_people()
    content = "```json\n" + json.dumps(people, indent=2, ensure_ascii=False) + "\n```"
    await ctx.author.send(content)


@bot.command(hidden=True)
async def start(ctx, *, password: str):

    await ctx.message.delete()

    if password != PASSWORD:
        await ctx.author.send("Invalid password.")
        return

    people = load_people()
    random.shuffle(people)


    for i in range(len(people)):
        people[i]["target"] = people[(i + 1) % len(people)]["username"]

    save_people(people)
    logging.info("Game started: %s", people)


@bot.command()
async def kill(ctx):
    """Submit a kill attempt with an image."""
    people = load_people()

    if not ctx.message.attachments:
        await ctx.author.send("No image attached.")
        return

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for att in ctx.message.attachments:
        if att.content_type and att.content_type.startswith("image/") or att.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp")
        ):
            path = os.path.join(DOWNLOAD_DIR, att.filename)

            try:
                await att.save(path)
            except Exception as e:
                logging.exception("Failed to save attachment: %s", e)
                await ctx.author.send("Couldn’t save your image. Try again.")
                return

            await ctx.author.send("Submission received. Processing...")

            if PRIVATE_CHANNEL_ID:
                try:
                    channel = bot.get_channel(PRIVATE_CHANNEL_ID) or await bot.fetch_channel(PRIVATE_CHANNEL_ID)

                    # Save submission path to player
                    for person in people:
                        if person["username"] == str(ctx.author):
                            person["path"] = path
                            target = person["target"]
                            save_people(people)
                            break

                    await channel.send(
                        content=f"Kill submission from {ctx.author} targeting {target}",
                        file=discord.File(path)
                    )
                except Exception as e:
                    logging.exception("Failed to forward kill submission: %s", e)
                    await ctx.author.send("Couldn’t forward image. Notify an admin.")
            else:
                await ctx.author.send("No review channel configured.")

    await ctx.message.delete()






@bot.command(hidden=True)
async def confirm_kill(ctx, *, value: str):
    try:
        password, username = value.split(maxsplit=1)
    except ValueError:
        await ctx.author.send("Format: `!confirm_kill <password> <username>`")
        return

    if password != PASSWORD:
        await ctx.author.send("Invalid password.")
        return

    people = load_people()
    dead_player = None
    killer = None

    # Find dead player
    for person in people:
        if person["username"] == username:
            dead_player = person
            person["status"] = "dead"
            break

    if not dead_player:
        await ctx.author.send("That player doesn’t exist.")
        return

    # Find the killer (person who had the dead player as target)
    for person in people:
        if person["target"] == username and person["status"] == "alive":
            killer = person
            # Give the killer the dead player's target
            killer["target"] = dead_player["target"]
            break
    
    # If no killer found, the dead player might have been eliminated by admin
    if not killer:
        logging.info("Player %s eliminated (no killer found)", dead_player['fullname'])
    else:
        logging.info("Player %s eliminated by %s, new target: %s", 
                    dead_player['fullname'], killer['fullname'], killer['target'])

    save_people(people)
    start = True

    if GENERAL_CHANNEL_ID:
        try:
            channel = bot.get_channel(GENERAL_CHANNEL_ID) or await bot.fetch_channel(GENERAL_CHANNEL_ID)
            
            # Get the kill image if available
            kill_image = None
            if dead_player.get("path") and os.path.exists(dead_player["path"]):
                try:
                    kill_image = discord.File(dead_player["path"])
                except Exception as e:
                    logging.warning("Could not load kill image: %s", e)
            
            await channel.send(
                content=f"**{dead_player['fullname']}** has been pegged! @{dead_player['username']}",
                file=kill_image
            )
            
            # Clean up the image file
            if dead_player.get("path") and os.path.exists(dead_player["path"]):
                try:
                    os.remove(dead_player["path"])
                    dead_player["path"] = None
                    save_people(people)
                except Exception as e:
                    logging.warning("Could not remove kill image: %s", e)
                    
        except Exception as e:
            logging.error("Failed to announce kill in general channel: %s", e)
            await ctx.author.send("Kill confirmed but couldn't announce it publicly.")
    else:
        await ctx.author.send("No general channel configured.")


# @bot.command(hidden=True)
# async def close(ctx, *, password: str):
#     """Shutdown the bot."""
#     if password != PASSWORD:
#         await ctx.author.send("Invalid password.")
#         return
    
#     logging.info("Bot shutdown requested by %s", ctx.author)
#     await ctx.author.send("Shutting down...")
#     await bot.close()


def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set in .env")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
