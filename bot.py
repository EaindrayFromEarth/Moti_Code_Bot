import os
import sqlite3
import requests
from datetime import datetime
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
    print(f"Contribution graph saved at {output_path}")
    return output_path

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
# def check_today_contribution(username, token):
#     url = f"https://api.github.com/users/{username}/events/public"
#     headers = {"Authorization": f"token {token}"}
#     response = requests.get(url, headers=headers)

#     if response.status_code == 200:
#         today_date = datetime.now().strftime('%Y-%m-%d')  # Get today's date in 'YYYY-MM-DD' format
#         events = response.json()
        
#         # Count commits for today only
#         commit_count = sum(1 for event in events if event['type'] == 'PushEvent' and event['created_at'][:10] == today_date)
        
#         return commit_count
#     return 0

# def check_today_contribution(username, token):
#     url = "https://api.github.com/graphql"
#     headers = {"Authorization": f"Bearer {token}"}
    
#     query = """
#     {
#       viewer {
#         contributionsCollection {
#           contributionCalendar {
#             weeks {
#               contributionDays {
#                 contributionCount
#               }
#             }
#           }
#         }
#       }
#     }
#     """
    
#     response = requests.post(url, json={"query": query}, headers=headers)
    
#     if response.status_code == 200:
#         data = response.json()
#         # Extract the weeks' contribution counts
#         weeks = data['data']['viewer']['contributionsCollection']['contributionCalendar']['weeks']
        
#         # Get today's date and determine which day of the week it is (0 = Sunday, 6 = Saturday)
#         today_date = datetime.now()
#         today_day_of_week = today_date.weekday()  # 0 (Monday) to 6 (Sunday)
#         today_date_str = today_date.strftime('%Y-%m-%d')

#         # Loop through the weeks and find the contributions for today
#         commit_count = 0
#         for week in weeks:
#             for day in week['contributionDays']:
#                 # Check if this is the current day (matching today_day_of_week)
#                 if today_day_of_week == week['contributionDays'].index(day):
#                     commit_count += day['contributionCount']

#         # Return total commits for today
#         return commit_count
#     else:
#         print(f"Error fetching contribution data: {response.status_code}")
#         return 0

# def check_today_contribution(username, token):
#     url = "https://api.github.com/graphql"
#     headers = {"Authorization": f"Bearer {token}"}
    
#     query = """
#     {
#       viewer {
#         contributionsCollection {
#           contributionCalendar {
#             weeks {
#               contributionDays {
#                 contributionCount
#                 date
#               }
#             }
#           }
#         }
#       }
#     }
#     """
    
#     response = requests.post(url, json={"query": query}, headers=headers)
    
#     if response.status_code == 200:
#         data = response.json()
#         weeks = data['data']['viewer']['contributionsCollection']['contributionCalendar']['weeks']
        
#         # Get today's date and determine which day of the week it is
#         today_date = datetime.now()
#         today_date_str = today_date.strftime('%Y-%m-%d')  # Get today's date in 'YYYY-MM-DD'
        
#         commit_count = 0
#         for week in weeks:
#             for day in week['contributionDays']:
#                 # If the day's date matches today's date, add the contribution count
#                 if day['date'][:10] == today_date_str:
#                     commit_count += day['contributionCount']
        
#         # Return total commits for today
#         return commit_count
#     else:
#         print(f"Error fetching contribution data: {response.status_code}")
#         return 0


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
        
        # Get today's date in Thailand time
        thailand_timezone = pytz.timezone('Asia/Bangkok')
        today_date = datetime.now(thailand_timezone)  # Get local time in Thailand
        today_date_str = today_date.strftime('%Y-%m-%d')  # Get today's date in 'YYYY-MM-DD'
        
        # Log the date being used
        print(f"Today's date (Thailand time): {today_date_str}")
        
        commit_count = 0
        for week in weeks:
            for day in week['contributionDays']:
                # Log the contribution days and their date for debugging
                print(f"Checking day: {day['date'][:10]} with contribution count: {day['contributionCount']}")
                
                # Adjust the date to match today
                if day['date'][:10] == today_date_str:
                    commit_count += day['contributionCount']

        # Log the total commit count
        print(f"Total commits today: {commit_count}")
        
        return commit_count
    else:
        print(f"Error fetching contribution data: {response.status_code}")
        return 0


# Send Telegram notification
async def send_telegram_notification(chat_id, message, context, image_path=None):
    try:
        # Send text message
        await context.bot.send_message(chat_id=chat_id, text=message)
        
        # Send image if provided
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
    return result  # Returns (github_username, github_token)

# Monitor contributions and send notifications (Now triggered on login and every 3 hours)
async def monitor_contributions(chat_id, context):
    # Get GitHub username and token from the database
    result = get_github_username_and_token_from_db(chat_id)
    if not result:
        print(f"GitHub username or token not found for {chat_id}")
        return

    github_username, github_token = result

    # Proceed with checking contributions only if both username and token are found
    commit_count = check_today_contribution(github_username, github_token)
    if commit_count > 0:
        print(f"User has committed {commit_count} time(s) today.")
        
        # Send the "commit count" message first with positive notifications
        commit_message = f"Yay! You've committed {commit_count} time(s) today. Keep it up!"
        await send_telegram_notification(chat_id, commit_message, context)
        
        # Fetch the positive notification (gentle or medium)
        notification_message = generate_notification("gentle", github_username, "gentle")
        if notification_message:
            await send_telegram_notification(chat_id, notification_message, context)

        # Fetch the real activity data from GitHub
        activity_data = fetch_commit_activity(github_username, github_token)
        if activity_data:
            # Generate contribution graph with the fetched activity data
            graph_path = create_contribution_graph(activity_data)
            
            # Send the graph as a Telegram message
            await send_telegram_notification(chat_id, "Here is your contribution graph:", context, graph_path)

    else:
        # If no commits today, send harsh notifications if it's late evening
        current_hour = datetime.now().hour
        if current_hour >= 18:  # After 6 PM (Late Evening)
            print("Sending harsh notification for inactivity")
            harsh_message = "Final Coding Warning: Inactivity Detected. Get coding now!"
            await send_telegram_notification(chat_id, harsh_message, context)
            
            # Generate harsh notification and send it
            notification_message = generate_notification("harsh", github_username, "harsh")
            if notification_message:
                await send_telegram_notification(chat_id, notification_message, context)

    # Check again every 3 hours
    await asyncio.sleep(3 * 3600)  # Sleep for 3 hours
    await monitor_contributions(chat_id, context)

# Telegram bot command: start
async def start(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Welcome to the GitHub Contribution Bot! Please provide your GitHub username and token to get started.")

# Telegram bot command: set github info
async def github_info(update: Update, context: CallbackContext):
    try:
        # Extract GitHub username and token from the message
        user_input = update.message.text.split()
        if len(user_input) != 3:
            raise ValueError("Please provide both GitHub username and token")

        github_username = user_input[1]
        github_token = user_input[2]
        telegram_username = update.effective_user.username
        chat_id = update.effective_chat.id

        # Store user's info in the database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (id, telegram_username, github_username, github_token) VALUES (?, ?, ?, ?)", (chat_id, telegram_username, github_username, github_token))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"GitHub username and token set for {github_username}!")

        # Start monitoring the user's contributions
        await monitor_contributions(chat_id, context)

    except Exception as e:
        await update.message.reply_text(str(e))

# Main program to initialize everything
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("github", github_info))

    # Initialize database and schedule cleanup
    init_database()

    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
