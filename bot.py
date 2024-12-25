import os
import sqlite3
import time
from datetime import datetime
from threading import Thread
from PIL import Image, ImageDraw, ImageTk
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from dotenv import load_dotenv

# Initialize Telegram bot
load_dotenv()

# Constants for Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Bot Token for your Telegram bot

# Database to store user data (GitHub username, GitHub token, chat_id)
DATABASE_PATH = os.path.join(os.getcwd(), "user_data.db")
IMAGE_PATH = os.path.join(os.getcwd(), "Images")

# Ensure necessary directories exist
os.makedirs(IMAGE_PATH, exist_ok=True)

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Database initialization
def init_database():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            github_username TEXT,
            github_token TEXT,
            chat_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

# Store user information in the database
def store_user_data(user_id, github_username, github_token, chat_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, github_username, github_token, chat_id)
        VALUES (?, ?, ?, ?)
    """, (user_id, github_username, github_token, chat_id))
    conn.commit()
    conn.close()

# Fetch user data from the database
def get_user_data(user_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT github_username, github_token, chat_id FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    return user_data

# Command to start the bot
async def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    await update.message.reply_text(
        f"Hello {user.first_name}! I can help you track your GitHub contributions. Please send your GitHub username to begin."
    )

# Handle GitHub username
async def set_github_username(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = user.id

    # Store the GitHub username temporarily
    context.user_data['github_username'] = update.message.text.strip()

    await update.message.reply_text("Thanks! Now please send your GitHub personal access token.")

# Handle GitHub token
async def set_github_token(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = user.id

    # Retrieve the GitHub username
    github_username = context.user_data.get('github_username')

    if not github_username:
        await update.message.reply_text("Please set your GitHub username first using the /setgithub command.")
        return

    # Store the GitHub token temporarily
    context.user_data['github_token'] = update.message.text.strip()

    await update.message.reply_text("Thanks! Your GitHub credentials are set. Now please send your Telegram chat ID.")

# Handle Telegram chat ID
async def set_chat_id(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = user.id
    chat_id = update.message.chat_id

    # Retrieve GitHub username and token from stored user data
    github_username = context.user_data.get('github_username')
    github_token = context.user_data.get('github_token')

    if not github_username or not github_token:
        await update.message.reply_text("Please set your GitHub username and token first using /setgithub and /setgithub_token commands.")
        return

    # Store all data in the database
    store_user_data(user_id, github_username, github_token, chat_id)

    # Confirmation message
    await update.message.reply_text(f"Your information is saved! You can now start tracking your GitHub contributions.")

# Check if the user has committed today on GitHub
def check_today_contribution(github_username, github_token):
    url = f"https://api.github.com/users/{github_username}/events/public"
    headers = {"Authorization": f"token {github_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        today_date = datetime.now().strftime('%Y-%m-%d')
        events = response.json()
        commit_count = sum(1 for event in events if event['type'] == 'PushEvent' and event['created_at'][:10] == today_date)
        return commit_count > 0, commit_count
    return False, 0

# Generate the GitHub contribution graph
def create_contribution_graph(activity_data, output_file="contribution_graph.png"):
    if not activity_data:
        print("No activity data available to create the graph.")
        return

    box_size, padding = 20, 5
    cols, rows = 53, 7
    img_width, img_height = cols * (box_size + padding) + padding, rows * (box_size + padding) + padding
    image = Image.new("RGB", (img_width, img_height), "white")
    draw = ImageDraw.Draw(image)

    colors = ["#ebedf0", "#c6e48b", "#7bc96f", "#239a3b", "#196127"]
    daily_contributions = [day for week in activity_data for day in week]

    for i, count in enumerate(daily_contributions):
        week, day = divmod(i, 7)
        x = padding + week * (box_size + padding)
        y = padding + day * (box_size + padding)
        color = colors[min(count, len(colors) - 1)]
        draw.rectangle([x, y, x + box_size, y + box_size], fill=color)

    output_path = os.path.join(IMAGE_PATH, output_file)
    image.save(output_path)
    return output_path

# Command to monitor GitHub contributions and send notifications
async def monitor_contributions(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)

    if user_data:
        github_username, github_token, chat_id = user_data

        # Check if the user has committed today
        contributed, count = check_today_contribution(github_username, github_token)
        if contributed:
            message = f"Yay! 🎉 You committed {count} {'time' if count == 1 else 'times'} today! Keep up the amazing work! 🚀"
            image_path = create_contribution_graph(fetch_commit_activity(github_username, github_token))
            await send_telegram_notification(message, image_path, chat_id)
        else:
            message = "Hey, you haven't committed today yet! Don't let your streak slip! 💪"
            image_path = create_contribution_graph(fetch_commit_activity(github_username, github_token))
            await send_telegram_notification(message, image_path, chat_id)
    else:
        await update.message.reply_text("Please set your GitHub username, token, and chat ID first using /setgithub.")

# Send Telegram notification
async def send_telegram_notification(message, image_path=None, chat_id=None):
    try:
        await application.bot.send_message(chat_id=chat_id, text=message)
        if image_path:
            with open(image_path, 'rb') as img_file:
                await application.bot.send_photo(chat_id=chat_id, photo=img_file)
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")

# Main function to run the bot
def main():
    init_database()

    # Initialize the Application object
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setgithub", set_github_username))
    application.add_handler(CommandHandler("setgithub_token", set_github_token))
    application.add_handler(CommandHandler("setchatid", set_chat_id))
    application.add_handler(CommandHandler("monitor", monitor_contributions))

    # Start polling for messages
    application.run_polling()


if __name__ == "__main__":
    main()
