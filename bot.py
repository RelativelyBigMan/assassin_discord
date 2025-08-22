import logging
import os
import random
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import discord
from discord.ext import commands
from discord.utils import get
from dotenv import load_dotenv


DOWNLOAD_DIR = "./data/download"
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PASSWORD = os.getenv("PASSWORD")
PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID", "0"))
GENERAL_CHANNEL_ID = int(os.getenv("GENERAL_CHANNEL_ID", "0"))


logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler(filename="./data/discord.log", encoding="utf-8", mode="w"),
        logging.StreamHandler(),
    ],
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def load_people() -> list:
    """Load player data from people.json, or return empty list if not found."""
    try:
        with open("./data/people.json", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError):
        with open("./data/people.json", "w") as f:
            json.dump([], f)
            return []

def save_people(data: list) -> None:
    """Save player data to people.json."""
    with open("./data/people.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)



intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
load_people()


@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user.name}")



@bot.command()
async def join(ctx, *, full_name: str):
    """Register a new player."""
    people = load_people()

    if len(people) > 0 and people[0]["target"]:
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
        "user_id": ctx.author.id
    })
    save_people(people)
    logging.info("Added new player: %s", full_name)

    await ctx.message.delete()
    await ctx.author.send(
        """You are registered!\nHere are the rules:
        1.	Each participant is assigned a target. 
        2.	Each participant becomes a target. 
        3.	Each participant is given a murder weapon peg with their own callsign. They must use only this peg to murder their victim. 
        4.	A valid kill is made by pegging (using a clothes peg or clothes pin… you CPP non-compliant monsters…) your victim without them realising it, then taking a sneaky picture and sending it to us by DM. 
        5.	Once a killing has been verified, the participant will be notified via the bot in the discord chat. Their target will now become their killer’s new target. 
        6.	Finesse and subterfuge are “of the essence”. Any participant photographed with their own murder peg will automatically leave the game… and go straight to jail without stopping by the start and without getting the €2000. Their peg will have to be returned to the organisers. 
        7.	Killing is only allowed during day time (between the 7am f* church bells and 22h), and restricted to common zones (i.e. the station, the forest around it and adjacent buildings and the restaurant during breakfast, lunch and dinner times). Murder by clothes peg is strictly prohibited in the dormitories, showers and buildings in the designated silent zone.
        8.	The total number of participants in the Killer game is unknown… trust nobody."""
    )


@bot.command(hidden=True)
async def super_duper_secret_command(ctx, *, password: str):


    if password != PASSWORD:
        await ctx.author.send("Invalid password.")
        return

    people = load_people()
    content = "```json\n" + json.dumps(people, indent=2, ensure_ascii=False) + "\n```"
    await ctx.author.send(content)



@bot.command(hidden=True)
async def delete_user(ctx, *, input_val: str):
    try:
        password, user = input_val.split(maxsplit=1)
    except ValueError:
        await ctx.author.send("Format: `!delete_user <password> <username>`")
        return

    if password != PASSWORD:
        await ctx.author.send("Invalid password.")
        return

    people = load_people()
    people = [p for p in people if p["username"] != str(user)]
    save_people(people)
    logging.info("Deleted player: %s", str(user))


@bot.command(hidden=True)
async def start(ctx, *, password: str):


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
    if not any(p["username"] == str(ctx.author) and p["status"] == "alive" for p in people):
        await ctx.author.send("You are not registered or already dead.")
        await ctx.message.delete()
        return
    
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
                content=f"**{dead_player['fullname']}** has been pegged! <@{dead_player['user_id']}>,            (ignore this <@689205836936904706>, <@1170410289682972804>)"
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

class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_status_server():
    server = HTTPServer(("0.0.0.0", 8080), StatusHandler)
    server.serve_forever()

def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set in .env")
    threading.Thread(target=run_status_server, daemon=True).start()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
