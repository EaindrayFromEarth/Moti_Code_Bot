import os
import sqlite3
import requests
from datetime import datetime, timedelta
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from dotenv import load_dotenv
from meta_ai_api import MetaAI
from PIL import Image, ImageDraw
import pytz

# Load environment variables
load_dotenv()

# Constants
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Your Telegram Bot Token
DATABASE_PATH = os.path.join(os.getcwd(), "notifications.db")
IMAGE_PATH = os.path.join(os.getcwd(), "Images")

# Ensure necessary directories exist
os.makedirs(IMAGE_PATH, exist_ok=True)

# Database initialization
def init_database():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_username TEXT NOT NULL,
            github_username TEXT NOT NULL,
            github_token TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            rating INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# Fetch commit activity from GitHub
def fetch_commit_activity(username, token):
    url = f"https://api.github.com/graphql"
    headers = {"Authorization": f"Bearer {token}"}
    query = """{
      viewer {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                contributionCount
              }
            }
          }
        }
      }
    }"""
    response = requests.post(url, json={"query": query}, headers=headers)
    if response.status_code == 200:
        data = response.json()
        weeks = data['data']['viewer']['contributionsCollection']['contributionCalendar']['weeks']
        activity = [[day['contributionCount'] for day in week['contributionDays']] for week in weeks]
        return activity
    return []

# Create a contribution graph image
def create_contribution_graph(activity_data, github_username, output_file=None):
    if not activity_data or all(sum(week) == 0 for week in activity_data):
        print("No activity data available. Creating an empty contribution graph.")
        return create_empty_contribution_graph(github_username)

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

    now = datetime.now(pytz.timezone('Asia/Bangkok'))  # Time in Thailand timezone
    output_filename = f"{github_username}'s {now.strftime('%Y-%m-%d %H')} contribution graph.png"
    output_path = os.path.join(IMAGE_PATH, output_filename)
    
    image.save(output_path)
    print(f"Contribution graph saved at {output_path}")
    
    delete_time = now + timedelta(hours=12)
    asyncio.create_task(delete_file_after_time(output_path, delete_time))

    return output_path

# Create an empty contribution graph
def create_empty_contribution_graph(github_username):
    box_size, padding = 20, 5
    cols, rows = 53, 7
    img_width, img_height = cols * (box_size + padding) + padding, rows * (box_size + padding) + padding
    image = Image.new("RGB", (img_width, img_height), "white")
    draw = ImageDraw.Draw(image)

    colors = ["#ebedf0"]  # Light color for no activity
    daily_contributions = [0] * (cols * rows)  # No contributions

    for i, count in enumerate(daily_contributions):
        week, day = divmod(i, 7)
        x = padding + week * (box_size + padding)
        y = padding + day * (box_size + padding)
        color = colors[min(count, len(colors) - 1)]
        draw.rectangle([x, y, x + box_size, y + box_size], fill=color)

    now = datetime.now(pytz.timezone('Asia/Bangkok'))
    output_filename = f"{github_username}'s {now.strftime('%Y-%m-%d %H')} empty contribution graph.png"
    output_path = os.path.join(IMAGE_PATH, output_filename)
    
    image.save(output_path)
    print(f"Empty contribution graph saved at {output_path}")
    
    delete_time = now + timedelta(hours=12)
    asyncio.create_task(delete_file_after_time(output_path, delete_time))

    return output_path

# Delete file after a specified time
async def delete_file_after_time(file_path, delete_time):
    now = datetime.now(pytz.timezone('Asia/Bangkok'))
    time_diff = (delete_time - now).total_seconds()
    if time_diff > 0:
        await asyncio.sleep(time_diff)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted file: {file_path}")
    else:
        print(f"Delete time has already passed for {file_path}")

# Generate notification using Meta AI API
def generate_notification(category, username, harshness):
    try:
        ai = MetaAI()
        
        if harshness == "gentle":
            prompt = f"Generate a gentle notification for a GitHub user named {username} to encourage them to code. Keep the tone friendly and motivational. No more than 10 words."
        elif harshness == "medium":
            prompt = f"Generate a moderate notification for a GitHub user named {username} to encourage them to code. Keep the tone more direct but friendly. No more than 10 words."
        else:
            prompt = f"Generate a harsh notification for a GitHub user named {username} to encourage them to code. Be assertive and urgent. No more than 10 words."
        
        response = ai.prompt(message=prompt)
        notification_message = response['message']
        print(f"Generated notification message for category '{category}': {notification_message}")
        return notification_message
    except Exception as e:
        print(f"Error generating notification message for category '{category}': {e}")
        return None

# Fetch notifications from the database by category
def get_notification(category):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, message FROM notifications WHERE category = ? ORDER BY RANDOM() LIMIT 1", (category,))
    row = cursor.fetchone()
    conn.close()
    return row

# Check today's contribution from GitHub
def check_today_contribution(username, token):
    url = "https://api.github.com/graphql"
    headers = {"Authorization": f"Bearer {token}"}
    
    query = """
    {
      viewer {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
      }
    }
    """
    
    response = requests.post(url, json={"query": query}, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        weeks = data['data']['viewer']['contributionsCollection']['contributionCalendar']['weeks']
        
        thailand_timezone = pytz.timezone('Asia/Bangkok')
        today_date = datetime.now(thailand_timezone)
        today_date_str = today_date.strftime('%Y-%m-%d')
        
        commit_count = 0
        for week in weeks:
            for day in week['contributionDays']:
                if day['date'][:10] == today_date_str:
                    commit_count += day['contributionCount']

        return commit_count
    else:
        print(f"Error fetching contribution data: {response.status_code}")
        return 0

# Send Telegram notification
async def send_telegram_notification(chat_id, message, context, image_path=None):
    try:
        await context.bot.send_message(chat_id=chat_id, text=message)
        
        if image_path:
            with open(image_path, 'rb') as img_file:
                await context.bot.send_photo(chat_id=chat_id, photo=img_file)
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")

# Get GitHub username and token from the database
def get_github_username_and_token_from_db(chat_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT github_username, github_token FROM users WHERE id = ?", (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result

# Monitor contributions and send notifications
async def monitor_contributions(chat_id, context):
    result = get_github_username_and_token_from_db(chat_id)
    if not result:
        print(f"GitHub username or token not found for {chat_id}")
        return

    github_username, github_token = result
    commit_count = check_today_contribution(github_username, github_token)
    
    if commit_count > 0:
        print(f"User has committed {commit_count} time(s) today.")
        
        commit_message = f"Yay! You've committed {commit_count} time(s) today. Keep it up!"
        await send_telegram_notification(chat_id, commit_message, context)
        
        notification_message = generate_notification("gentle", github_username, "gentle")
        if notification_message:
            await send_telegram_notification(chat_id, notification_message, context)

        activity_data = fetch_commit_activity(github_username, github_token)
        if activity_data:
            graph_path = create_contribution_graph(activity_data, github_username)
            await send_telegram_notification(chat_id, "Here is your contribution graph:", context, graph_path)

    else:
        graph_path = create_contribution_graph([], github_username)  # Pass an empty list for no commits
        await send_telegram_notification(chat_id, "You haven't made any contributions today. Here's your empty contribution graph:", context, graph_path)

        print("No commits today. Checking for time to send harsh notification.")
        current_hour = datetime.now().hour
        if current_hour >= 18:
            harsh_message = "Final Coding Warning: Inactivity Detected. Get coding now!"
            await send_telegram_notification(chat_id, harsh_message, context)
            
            notification_message = generate_notification("harsh", github_username, "harsh")
            if notification_message:
                await send_telegram_notification(chat_id, notification_message, context)

    await asyncio.sleep(3 * 3600)  # Sleep for 3 hours before checking again
    await monitor_contributions(chat_id, context)

# Telegram bot command: start
async def start(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Welcome to the GitHub Contribution Bot! Please provide your GitHub username and token to get started.")

# Telegram bot command: set github info
async def github_info(update: Update, context: CallbackContext):
    try:
        user_input = update.message.text.split()
        if len(user_input) != 3:
            raise ValueError("Please provide both GitHub username and token")

        github_username = user_input[1]
        github_token = user_input[2]
        telegram_username = update.effective_user.username
        chat_id = update.effective_chat.id

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (id, telegram_username, github_username, github_token) VALUES (?, ?, ?, ?)", (chat_id, telegram_username, github_username, github_token))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"GitHub username and token set for {github_username}!")
        asyncio.create_task(monitor_contributions(chat_id, context))  # Start monitoring in the background

    except Exception as e:
        await update.message.reply_text(str(e))

# Main program to initialize everything
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("github", github_info))

    init_database()

    application.run_polling()

if __name__ == '__main__':
    main()
