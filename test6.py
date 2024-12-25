from meta_ai_api import MetaAI
import requests
from datetime import datetime
from threading import Thread
from PIL import Image, ImageDraw, ImageTk
import tkinter as tk
import time
import os
import sqlite3
import sys

# Constants
GITHUB_USERNAME = ""  # Replace with your GitHub username
GITHUB_TOKEN = "your_github_token_here"  # Replace with your GitHub personal access token
BOT_TOKEN = ""  # Replace with your bot token
CHAT_ID = ""  # Replace with your chat ID

IMAGE_PATH = os.path.join(os.getcwd(), "Images")
DATABASE_PATH = os.path.join(os.getcwd(), "notifications.db")

# Ensure necessary directories exist
os.makedirs(IMAGE_PATH, exist_ok=True)

# Database initialization
def init_database():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
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


def generate_notification(category):
    """
    Generates a notification message using the Meta AI API.

    Args:
        category: The category of the notification (e.g., "gentle", "bit_harsh").

    Returns:
        The generated notification message.
    """
    try:
        ai = MetaAI()
        prompt = f"Generate a {category} notification for a GitHub user to encourage them to code. No more than 10 words. using {GITHUB_USERNAME} for username.'"
        response = ai.prompt(message=prompt)
        notification_message = response['message']
        print(f"Generated notification message for category '{category}': {notification_message}")
        return notification_message
    except Exception as e:
        print(f"Error generating notification message for category '{category}': {e}")
        return None

# def generate_notification(category):
#     """
#     Generates a notification message using the Meta AI API.

#     Args:
#         category: The category of the notification (e.g., "gentle", "bit_harsh").

#     Returns:
#         The generated notification message.
#     """
#     try:
#         ai = MetaAI()
#         prompt = (
#             f"Generate a {category} notification for a GitHub user to encourage them to code. "
#             "Keep it concise and under 10 words using"
#             f"e.g., {GITHUB_USERNAME} for the username."
#         )
#         response = ai.prompt(message=prompt)
#         notification_message = response['message']
#         print(f"Generated notification message for category '{category}': {notification_message}")
#         return notification_message
#     except Exception as e:
#         print(f"Error generating notification message for category '{category}': {e}")
#         return None


# Fetch notification by category
def get_notification(category):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, message FROM notifications WHERE category = ? ORDER BY RANDOM() LIMIT 1", (category,))
    row = cursor.fetchone()
    conn.close()
    return row

# Update notification rating
def update_notification_rating(notification_id, increment):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET rating = rating + ? WHERE id = ?", (increment, notification_id))
    conn.commit()
    conn.close()

# Cleanup notifications every 3 days
def cleanup_notifications():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM notifications
        WHERE id IN (
            SELECT id FROM notifications ORDER BY rating ASC LIMIT (SELECT COUNT(*) * 15 / 100 FROM notifications)
        )
    """)
    conn.commit()
    conn.close()

# Schedule notification cleanup every 3 days
def schedule_cleanup(interval_days=3):
    def cleanup_task():
        while True:
            print("Performing cleanup of old notifications...")
            cleanup_notifications()
            time.sleep(interval_days * 86400)  # Wait for the interval (in seconds)

    Thread(target=cleanup_task, daemon=True).start()

# Check today's contribution from GitHub
def check_today_contribution(username, token):
    url = f"https://api.github.com/users/{username}/events/public"
    headers = {"Authorization": f"token {token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        today_date = datetime.now().strftime('%Y-%m-%d')
        events = response.json()
        commit_count = sum(1 for event in events if event['type'] == 'PushEvent' and event['created_at'][:10] == today_date)
        return commit_count > 0, commit_count
    return False, 0

# Fetch commit activity for the contribution graph
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

# Send Telegram notification
def send_telegram_notification(message, image_path=None):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": message})
        if image_path:
            with open(image_path, 'rb') as img_file:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    data={"chat_id": CHAT_ID},
                    files={"photo": img_file}
                )
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")

# Monitor contributions and send notifications
def monitor_contributions(username):
    categories = ["gentle", "bit_harsh", "harshest"]
    streak = 0

    for category in categories:
        contributed, count = check_today_contribution(username, GITHUB_TOKEN)
        if contributed:
            print(f"User has committed {count} time(s) today.")
            message = get_notification("gentle")[1].format(count)
            send_telegram_notification(message)
            return True

        notification = get_notification(category)
        if notification:
            message_id, message = notification
            message = message.format(streak)
            send_telegram_notification(message)
            time.sleep(60)  # Retry in 1 minute
    return False

def schedule_reminders(username, token, interval=3600):
    """
    Schedule periodic reminders to check contributions.
    """
    def check_and_remind():
        while True:
            print("Checking today's contributions...")
            contributed_today, commit_count = check_today_contribution(username, token)
            if contributed_today:
                message = f"Yay! 🎉 You committed {commit_count} {'time' if commit_count == 1 else 'times'} today! Keep up the amazing work! 🚀"
                image_path = create_contribution_graph(fetch_commit_activity(username, token))
                send_telegram_notification(message, image_path)
            else:
                message = "Hey, you haven't committed today yet! Don't let your streak slip! 💪 Let's get some code done! 👨‍💻👩‍💻"
                image_path = create_contribution_graph(fetch_commit_activity(username, token))
                send_telegram_notification(message, image_path)
            time.sleep(interval)

    thread = Thread(target=check_and_remind, daemon=True)
    thread.start()

def display_widget(image_path, username, token):
    """
    Display the contribution graph as a widget and start the reminder system.
    """
    schedule_reminders(username, token, interval=3600)

    # Create the GUI
    root = tk.Tk()
    root.title("GitHub Contribution Graph")

    # Load the image
    try:
        img = Image.open(image_path)
        img_tk = ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"Error loading image: {e}")
        return

    # Create a label to display the image
    label = tk.Label(root, image=img_tk)
    label.pack()

    # Keep the widget on top
    root.attributes('-topmost', True)

    root.mainloop()

def populate_notifications():
    categories = ["gentle", "bit_harsh", "harshest"]
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    for category in categories:
        for _ in range(2):  # Generate 2 messages for each category
            message = generate_notification(category)
            cursor.execute("INSERT INTO notifications (category, message) VALUES (?, ?)", (category, message))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_database()
    populate_notifications()  # Populate notifications with AI-generated messages
    schedule_cleanup()  # Schedule cleanup of old notifications
    activity_data = fetch_commit_activity(GITHUB_USERNAME, GITHUB_TOKEN)  # Fetch initial commit activity
    graph_path = create_contribution_graph(activity_data)  # Create the contribution graph
    Thread(target=monitor_contributions, args=(GITHUB_USERNAME,), daemon=True).start()  # Start monitoring contributions
    display_widget(graph_path, GITHUB_USERNAME, GITHUB_TOKEN)  # Display the contribution graph in a GUI
