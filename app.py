import logging
import string
import random
from sqlalchemy.orm import Session
from telegram import Update, ForceReply, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler, CallbackContext
import uuid

from config import BOT_TOKEN, ADMIN_ID
from models import SessionLocal, User, Admin, Command, Settings

# Conversation states
(
    ADD_COMMAND,
    ADD_DESCRIPTION,
    ADD_RESPONSE,
    ADD_IS_ADMIN,
    ADD_IMAGE,
    ADD_INLINE_LINKS,
    EDIT_COMMAND,
    EDIT_CHOICE,
    EDIT_DESCRIPTION,
    EDIT_RESPONSE,
    EDIT_IS_ADMIN,
    DELETE_COMMAND,
    DELETE_CONFIRMATION,
    ADD_ADMIN,
    DELETE_ADMIN_CONFIRMATION
) = range(15)

# Database session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper function to generate referral ID
def generate_referral_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=5))

# Define command handlers
# Define command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    user = update.effective_user
    db: Session = next(get_db())
    new_user = db.query(User).filter(User.telegram_id == user.id).first()
    if not new_user:
        new_user = User(telegram_id=user.id, referral_id=generate_referral_id())
        if context.args:
            ref_id = context.args[0]
            referrer = db.query(User).filter(User.referral_id == ref_id).first()
            if referrer:
                new_user.referrer_id = referrer.id
                referrer.earnings += Settings.referral_earning
                db.commit()
        db.add(new_user)
        db.commit()
        welcome_message = f"Hi {user.mention_html()}! Welcome to the bot."
    else:
        welcome_message = f"Hi {user.mention_html()}! Welcome back."
    
    additional_message = db.query(Command).filter_by(command='start').first()
    if additional_message:
        welcome_message += f"\n\n{additional_message.response}"
    welcome_message += f"\n\nType /help to see available commands."
    markup = ReplyKeyboardMarkup([['🔙 Back_Start']], resize_keyboard=True)
    await update.message.reply_html(
        rf"{welcome_message}", reply_markup=markup, disable_web_page_preview=True
    )



# Define menu command handler
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        ["Option 1"],
        ["Option 2"],
        ["Option 3", "Option 4"],
        ["Option 5", "Option 6"],
        ["Option 7", "Option 8"],
        ["Option 9"],]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Here's the menu:", reply_markup=markup)

# Define handler for forwarding messages from a set channel to all users
async def forward_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    channel_id = update.channel_post.chat.id
    channel_message_id = update.channel_post.message_id
    db: Session = next(get_db())
    users = db.query(User).all()
    for user in users:
        try:
            await context.bot.forward_message(chat_id=user.telegram_id, from_chat_id=channel_id, message_id=channel_message_id)
        except Exception as e:
            print(f"Failed to forward message to user {user.telegram_id}: {e}")

async def command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = next(get_db())
    command_text = update.message.text.lower().replace("/", "")
    command = db.query(Command).filter_by(command=command_text).first()
    if command:
        response_text = command.response
        # Prepare the inline keyboard markup if it exists
        inline_keyboard = []
        if command.inline_links:
            for i in range(0, len(command.inline_links), 2):
                row = [InlineKeyboardButton(link['text'], url=link['url']) for link in command.inline_links[i:i+2]]
                inline_keyboard.append(row)
        inline_reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

        # Prepare the markup buttons if they exist
        markup_buttons = []
        if command.markup_buttons:
            for i in range(0, len(command.markup_buttons), 2):
                row = [KeyboardButton(button) for button in command.markup_buttons[i:i+2]]
                markup_buttons.append(row)
        markup_reply_markup = ReplyKeyboardMarkup(markup_buttons, resize_keyboard=True, one_time_keyboard=True) if markup_buttons else None

        # Send the main response
        if command.image_url:
            await update.message.reply_photo(photo=command.image_url, caption=response_text, reply_markup=inline_reply_markup)
        else:
            await update.message.reply_text(text=response_text, reply_markup=inline_reply_markup, disable_web_page_preview=True)

        # Send the markup buttons as a separate message if they exist
        if markup_reply_markup:
            await update.message.reply_text("Here are your options:", reply_markup=markup_reply_markup)
    else:
        await update.message.reply_text("Command not found.")




async def affiliate(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    db: Session = next(get_db())

    # Query the User from the database based on telegram_id
    user_data = db.query(User).filter(User.telegram_id == user.id).first()

    if user_data:
        ref_link = f"https://t.me/{context.bot.username}?start={user_data.referral_id}"
        referrals_count = len(user_data.downlines) if user_data.downlines else 0
        affiliate_info = (
            f"👤 Your Affiliate Information\n\n"
            f"👥 Referrals: {referrals_count}\n"
            f"💰 Earnings: {user_data.earnings}\n"
            f"💸 Downline Earnings: {user_data.downline_earnings}\n"
            f"🔗 Referral Link: {ref_link}\n"  # Escape the '.' in ref_link
        )
        await update.message.reply_text(affiliate_info)
    else:
        await update.message.reply_text("You are not registered as a user.")

async def set_ref_earning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /set_ref_earning <amount>")
        return
    amount = float(context.args[0])
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings()
        db.add(settings)
    settings.ref_earning = amount
    db.commit()
    await update.message.reply_text(f"Referral earning set to {amount}")

async def set_downline_earning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /set_downline_earning <amount>")
        return
    amount = float(context.args[0])
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings()
        db.add(settings)
    settings.downline_earning = amount
    db.commit()
    await update.message.reply_text(f"Downline earning set to {amount}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = next(get_db())
    commands = db.query(Command).filter_by(is_admin=False).all()
    help_text = "Available commands:\n"
    for cmd in commands:
        help_text += f"/{cmd.command}: {cmd.description}\n"
    await update.message.reply_text(help_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = next(get_db())
    commands = db.query(Command).filter_by(is_admin=False).all()
    help_text = "Available commands:\n\n"
    for cmd in commands:
        help_text += f"/{cmd.command}: {cmd.description}\n\n"
    await update.message.reply_text(help_text)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    command_text = update.message.text[1:]
    db: Session = next(get_db())
    command = db.query(Command).filter_by(command=command_text).first()

    if command:
        if command.is_admin and user.id != ADMIN_ID:
            await update.message.reply_text("This command is restricted to admins.")
        else:
            await update.message.reply_text(command.response)
    else:
        await update.message.reply_text("Command not found.")

# Conversation handlers for adding a command
async def add_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return ConversationHandler.END
    await update.message.reply_text("Enter the command without '/':\n\nUse /cancel to cancel")
    return ADD_COMMAND

async def add_command_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    command = update.message.text
    context.user_data['command'] = (command.replace(' ','_')).lower()
    await update.message.reply_text("Enter the description:\n\nUse /cancel to cancel")
    return ADD_DESCRIPTION

async def add_command_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['description'] = update.message.text
    await update.message.reply_text("Enter the response:\n\nUse /cancel to cancel")
    return ADD_RESPONSE

async def add_command_is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['response'] = update.message.text
    await update.message.reply_text("Is this an admin command? (yes/no)\n\nUse /cancel to cancel")
    return ADD_IS_ADMIN

async def add_command_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_admin = update.message.text.lower() == 'yes'
    context.user_data['is_admin'] = is_admin
    await update.message.reply_text("Upload an image here, else send 'no' \n\nUse /cancel to cancel")
    return ADD_IMAGE

async def add_command_inline_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_image = update.message.text.lower() == 'yes'
    if add_image:
        await update.message.reply_text("Please send the image file:\n\nUse /cancel to cancel")
        return ADD_INLINE_LINKS
    else:
        context.user_data['image_url'] = None
        await update.message.reply_text("Do you want to add inline links? (yes/no)\n\nUse /cancel to cancel")
        return ADD_INLINE_LINKS

async def add_command_save_image(update: Update, context: CallbackContext) -> int:
  # Check if the message contains a photo
  if update.message.photo:
    # Get the largest available photo (last in the list)
    photo = update.message.photo[-1]
    file_id = photo.file_id
  
    try:
      # Get the file object for the photo using file_id
      photo_obj = await context.bot.get_file(file_id)
  
      # Generate a unique filename for the image
      image_id = str(uuid.uuid4())
      file_path = f'images/{image_id}.jpg'
  
      # Download the photo to the specified file path using download_to_drive method
      await photo_obj.download_to_drive(custom_path=file_path)  
  
      # Store the image path in user_data for later use
      context.user_data['image_url'] = file_path
  
      # Proceed to ask about inline links or finish
      await update.message.reply_text("Image saved successfully. Do you want to add inline links? (yes/no)\n\nUse /cancel to cancel")
      return ADD_INLINE_LINKS
  
    except Exception as e:
      await update.message.reply_text(f"Failed to download the image: {str(e)}")
      return ADD_IMAGE
  
  else:
    await update.message.reply_text("Please send a photo file. Use /cancel to cancel.")
    return ADD_IMAGE


async def add_command_finish_inline_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_inline_links = update.message.text.lower() == 'yes'
    if add_inline_links:
        await update.message.reply_text("Send the links in the format: Text1,URL1;Text2,URL2;...\n\nUse /cancel to cancel")
        return ADD_INLINE_LINKS
    else:
        context.user_data['inline_links'] = []
        await update.message.reply_text("Do you want to add markup buttons? (yes/no)\n\nUse /cancel to cancel")
        return ADD_MARKUP_BUTTONS

async def add_command_finish_save_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    links_text = update.message.text
    links = []
    for link in links_text.split(';'):
        text, url = link.split(',')
        links.append({'text': text.strip(), 'url': url.strip()})
    context.user_data['inline_links'] = links
    await update.message.reply_text("Do you want to add markup buttons? (yes/no)\n\nUse /cancel to cancel")
    return ADD_MARKUP_BUTTONS

async def add_command_markup_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    add_markup_buttons = update.message.text.lower() == 'yes'
    if add_markup_buttons:
        await update.message.reply_text("Send the buttons in the format: Button1,Button2,Button3;...\n\nUse /cancel to cancel")
        return ADD_MARKUP_BUTTONS
    else:
        context.user_data['markup_buttons'] = []
        return await add_command_finish(update, context)

async def add_command_finish_save_markup_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    buttons_text = update.message.text
    buttons = [button.strip() for button in buttons_text.split(',')]  # Split by ',' to create a list of buttons
    context.user_data['markup_buttons'] = buttons
    return await add_command_finish(update, context)

async def add_command_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: Session = next(get_db())
    new_command = Command(
        command=context.user_data['command'],
        description=context.user_data['description'],
        response=context.user_data['response'],
        is_admin=context.user_data['is_admin'],
        image_url=context.user_data.get('image_url'),
        inline_links=context.user_data.get('inline_links'),
        markup_buttons=context.user_data.get('markup_buttons')  # Save markup buttons
    )
    db.add(new_command)
    db.commit()
    await update.message.reply_text(f"Command /{new_command.command} created successfully.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Define constants for the new states
ADD_MARKUP_BUTTONS = range(9, 10)

# Conversation handlers for editing a command
async def edit_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return ConversationHandler.END
    await update.message.reply_text("Enter the command you want to edit:\n\nUse /cancel to cancel")
    return EDIT_COMMAND

async def edit_command_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    command_text = update.message.text
    db: Session = next(get_db())
    command = db.query(Command).filter_by(command=command_text).first()
    if not command:
        await update.message.reply_text("Command not found.")
        return ConversationHandler.END
    context.user_data['command_id'] = command.id
    keyboard = [['Description', 'Response', 'Admin Status']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("What do you want to edit?\n\nUse /cancel to cancel", reply_markup=reply_markup)
    return EDIT_CHOICE

async def edit_command_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['edit_choice'] = 'description'
    await update.message.reply_text("Enter the new description:\n\nUse /cancel to cancel")
    return EDIT_DESCRIPTION

async def edit_command_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['edit_choice'] = 'response'
    await update.message.reply_text("Enter the new response:\n\nUse /cancel to cancel")
    return EDIT_RESPONSE

async def edit_command_is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['edit_choice'] = 'is_admin'
    await update.message.reply_text("Is this an admin command? (yes/no)\n\nUse /cancel to cancel")
    return EDIT_IS_ADMIN

async def edit_command_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: Session = next(get_db())
    command = db.query(Command).filter_by(id=context.user_data['command_id']).first()
    edit_choice = context.user_data['edit_choice']
    if edit_choice == 'description':
        command.description = update.message.text
    elif edit_choice == 'response':
        command.response = update.message.text
    elif edit_choice == 'is_admin':
        command.is_admin = update.message.text.lower() == 'yes'
    db.commit()
    await update.message.reply_text("Command updated successfully.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Conversation handlers for deleting a command
async def delete_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return ConversationHandler.END
    await update.message.reply_text("Enter the command you want to delete:\n\nUse /cancel to cancel")
    return DELETE_COMMAND

async def delete_command_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['command'] = update.message.text
    db: Session = next(get_db())
    command = db.query(Command).filter_by(command=context.user_data['command']).first()
    if not command:
        await update.message.reply_text("Command not found.")
        return ConversationHandler.END
    await update.message.reply_text(f"Are you sure you want to delete the command /{command.command}? (yes/no)\n\nUse /cancel to cancel")
    return DELETE_CONFIRMATION

async def delete_command_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text.lower() == 'yes':
        db: Session = next(get_db())
        command = db.query(Command).filter_by(command=context.user_data['command']).first()
        db.delete(command)
        db.commit()
        await update.message.reply_text("Command deleted successfully.")
    else:
        await update.message.reply_text("Deletion cancelled.")
    return ConversationHandler.END

# Conversation handlers for adding and deleting admins
async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return ConversationHandler.END
    await update.message.reply_text("Enter the Telegram ID of the new admin:\n\nUse /cancel to cancel")
    return ADD_ADMIN

async def add_admin_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_admin_id = int(update.message.text)
    db: Session = next(get_db())
    new_admin = Admin(telegram_id=new_admin_id)
    db.add(new_admin)
    db.commit()
    await update.message.reply_text("New admin added successfully.")
    return ConversationHandler.END

async def delete_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return ConversationHandler.END
    await update.message.reply_text("Enter the Telegram ID of the admin to delete:\n\nUse /cancel to cancel")
    return DELETE_ADMIN_CONFIRMATION

async def delete_admin_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = int(update.message.text)
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if admin:
        db.delete(admin)
        db.commit()
        await update.message.reply_text("Admin deleted successfully.")
    else:
        await update.message.reply_text("Admin not found.")
    return ConversationHandler.END
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text('Action Successfully cancelled')
    return ConversationHandler.END


# Main function to start the bot
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex('🔙 Back_Start'), start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("affiliate", affiliate))
    application.add_handler(CommandHandler("set_ref_earning", set_ref_earning))
    application.add_handler(CommandHandler("set_downline_earning", set_downline_earning))

    # Conversation handlers for adding commands
    add_command_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addcommand", add_command_start)],
        states={
            ADD_COMMAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_description)],
            ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_response)],
            ADD_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_is_admin)],
            ADD_IS_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_image)],
            ADD_IMAGE: [
                MessageHandler(filters.Regex('^(yes|no)$') & ~filters.COMMAND, add_command_inline_links),
                MessageHandler(filters.PHOTO & ~filters.COMMAND, add_command_save_image)
            ],
            ADD_INLINE_LINKS: [
                MessageHandler(filters.Regex('^(yes|no)$') & ~filters.COMMAND, add_command_finish_inline_links),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_finish_save_links)
            ],
            ADD_MARKUP_BUTTONS: [
                MessageHandler(filters.Regex('^(yes|no)$') & ~filters.COMMAND, add_command_markup_buttons),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_finish_save_markup_buttons)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)
        ],
    )


    # Conversation handlers for editing commands
    edit_command_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("editcommand", edit_command_start)],
        states={
            EDIT_COMMAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_command_choice)],
            EDIT_CHOICE: [
                MessageHandler(filters.Regex('^(Description)$'), edit_command_description),
                MessageHandler(filters.Regex('^(Response)$'), edit_command_response),
                MessageHandler(filters.Regex('^(Admin Status)$'), edit_command_is_admin),
            ],
            EDIT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_command_finish)],
            EDIT_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_command_finish)],
            EDIT_IS_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_command_finish)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)
        ],
    )

    # Conversation handlers for deleting commands
    delete_command_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("deletecommand", delete_command_start)],
        states={
            DELETE_COMMAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_command_confirmation)],
            DELETE_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_command_finish)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)
        ],
    )

    # Conversation handlers for managing admins
    add_admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addadmin", add_admin_start)],
        states={
            ADD_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_finish)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)
        ],
    )

    delete_admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("deleteadmin", delete_admin_start)],
        states={
            DELETE_ADMIN_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_admin_finish)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)
        ],
    )

    # Add conversation handlers to the application
    application.add_handler(add_command_conv_handler)
    application.add_handler(edit_command_conv_handler)
    application.add_handler(delete_command_conv_handler)
    application.add_handler(add_admin_conv_handler)
    application.add_handler(delete_admin_conv_handler)

    application.add_handler(CommandHandler("cancel", cancel))
    # Echo handler for non-command messages
    # application.add_handler(MessageHandler(filters.TEXT, echo))

    # Message handler for forwarding channel messages
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, forward_channel_message))

    # Message handler for command responses with optional image/inline links
    application.add_handler(MessageHandler(filters.TEXT & filters.COMMAND, command_handler))
    # application.add_handler(MessageHandler(filters.COMMAND, command_handler))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main()
