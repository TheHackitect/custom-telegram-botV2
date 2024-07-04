### Telegram Bot README

Introduction
---
This bot provides various functionalities including command handling, referral system, and user management. This guide will help you set up and operate the bot efficiently.

Installation
---
1. Clone the repository: git clone  https://github.com/TheHackitect/custom-telegram-botV2
2. Navigate to the project directory: cd telegram-bot
3. Install the dependencies: pip install -r requirements.txt
4. Set up the configuration files as described in the Configuration section.
5. Run the bot: python bot.py

Configuration
---
Edit the config.py file to include your bot token and admin ID:
BOT_TOKEN = 'YOUR_BOT_TOKEN'
ADMIN_ID = 'YOUR_ADMIN_ID'

Usage
---
Once the bot is running, you can interact with it using the following commands:
- /start - Initialize the bot and handle referral IDs.
- /menu - Display the menu options.
- Additional commands can be added and customized in the commands table in the database.

Commands
---
The bot supports various commands to manage users, admins, and settings. Here are the admin commands:
- /admin_help - Get a list of admin commands for the bot.
- /set_ref_earning - Set the referral earning amount.
- /deduct_ref_points - Deduct referral points from a user.
- /export - Export the database in the specified format (sqlite, csv, excel).
- /addcommand - Start the process to add a new command.
- /deletecommand - Start the process to delete a command.
- /addadmin - Start the process to add a new admin.
- /deleteadmin - Start the process to delete an admin.
- /cancel - Cancel the current operation.

Add Admins
---
To add an admin, use the /addadmin command. This will start the process to grant a user administrative privileges within the bot.

Advanced Setup
---
For advanced configurations and customizations, refer to the documentation in the repository. This includes setting up webhooks, integrating with external APIs, and extending the bot's functionality.

Footer
© 2024 Telegram Bot. All Rights Reserved.
