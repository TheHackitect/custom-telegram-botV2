import logging
import string
import random
from sqlalchemy.orm import Session
from telegram import Update, Bot, ForceReply, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler, CallbackContext, CallbackQueryHandler
import uuid
from sqlalchemy.types import TypeDecorator, TEXT
from config import BOT_TOKEN, ADMIN_ID
from models import SessionLocal, User, Admin, Command, Settings
import pandas as pd
import os
import json
from models import engine

# Conversation states
(
    ADD_COMMAND,
    ADD_DESCRIPTION,
    ADD_RESPONSE,
    ADD_IS_COMMAND,
    ADD_IMAGE,
    ADD_INLINE_LINKS,
    EDIT_COMMAND,
    EDIT_CHOICE,
    EDIT_DESCRIPTION,
    EDIT_RESPONSE,
    EDIT_IS_COMMAND,
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


# Helper function to create the button layout
def create_button_layout(buttons):
    layout = []
    num_buttons = len(buttons)
    if num_buttons % 2 == 0:  # Even number of buttons
        if num_buttons > 0:
            layout.append([buttons[0]])  # First row single button
        for i in range(1, num_buttons - 1, 2):
            layout.append([buttons[i], buttons[i + 1]])  # Middle rows with two buttons each
        if num_buttons > 1:
            layout.append([buttons[-1]])  # Last row single button
    else:  # Odd number of buttons (brick structure)
        i = 0
        while i < num_buttons:
            if i % 5 in (0, 3):  # Rows with 2 buttons
                if i + 1 < num_buttons:
                    layout.append([buttons[i], buttons[i + 1]])
                    i += 2
                else:
                    layout.append([buttons[i]])  # Single button if only one left
                    i += 1
            else:  # Rows with 3 buttons
                if i + 2 < num_buttons:
                    layout.append([buttons[i], buttons[i + 1], buttons[i + 2]])
                    i += 3
                else:
                    layout.append([buttons[i]])  # Single button if only one left
                    i += 1
    return layout

async def check_membership(user_id: int, bot) -> bool:
    # bot = Bot(BOT_TOKEN)
    db: Session = next(get_db())
    settings = db.query(Settings).first()
    
    if settings and settings.strict_join:
        required_chats = settings.chats_to_join
        for chat in required_chats:
            try:
                member = await bot.get_chat_member(chat['id'], user_id)
                if not member.status in ['member', 'administrator', 'creator']:
                    return False
            except:
                return False
    return True


class JSONType(TypeDecorator):
    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is None:
            return '{}'
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return {}
        return json.loads(value)

async def add_chat_group(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    db: Session = next(get_db())

    if user.id in [admin.telegram_id for admin in db.query(Admin).all()]:
        if len(context.args) != 1:
            await update.message.reply_text("Please provide the chat details in the format: /add_chat_group <chat_name>,<chat_id>,<chat_link>")
            return

        try:
            chat_details = context.args[0].split(',')
            if len(chat_details) != 3:
                await update.message.reply_text("Please provide exactly three arguments: <chat_name>,<chat_id>,<chat_link>")
                return

            chat_name, chat_id, chat_link = chat_details
            chat = {'name': chat_name.lower(), 'id': chat_id, 'link': chat_link}

            # Fetch or create Settings object
            settings = db.query(Settings).first()
            if settings is None:
                settings = Settings(chats_to_join=[chat])
                db.add(settings)
            else:
                if settings.chats_to_join is None:
                    settings.chats_to_join = []
                settings.chats_to_join.append(chat)

            db.commit()
            db.refresh(settings)  # Refresh the settings object from the database

            await update.message.reply_text(f"New Chat '{chat_name}' with Link '{chat_link}' added to Group join Protocol.\n\n Users will be requested to join this Chat when required, and the /strict_join is enabled")
        except ValueError:
            await update.message.reply_text("Chat ID must be a number.")
        except Exception as e:
            await update.message.reply_text(f"Failed to add chat: {e}")
        finally:
            db.close()  # Ensure the session is properly closed
    else:
        await update.message.reply_text("You are not authorized to use this command.")


async def remove_chat_group(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    db: Session = next(get_db())
    settings = db.query(Settings).first()
    
    if user.id in [admin.telegram_id for admin in db.query(Admin).all()]:
        if len(context.args) != 1:
            await update.message.reply_text("Please provide the chat name to remove in the format: /remove_chat_group <chat_name>")
            return

        try:
            chat_name = context.args[0].lower()
            if settings and settings.chats_to_join:
                settings.chats_to_join = [chat for chat in settings.chats_to_join if chat['name'] != chat_name]
                db.commit()
                await update.message.reply_text(f"Chat '{chat_name}' removed successfully.")
            else:
                await update.message.reply_text("No chat groups to remove.")
        except Exception as e:
            await update.message.reply_text(f"Failed to remove chat: {e}")
        finally:
            db.close()  # Ensure the session is properly closed
    else:
        await update.message.reply_text("You are not authorized to use this command.")


async def toggle_strict_join(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    db: Session = next(get_db())
    settings = db.query(Settings).first()
    
    if user.id in [admin.telegram_id for admin in db.query(Admin).all()]:
        settings.strict_join = not settings.strict_join
        db.commit()
        status = "enabled" if settings.strict_join else "disabled"
        await update.message.reply_text(f"Strict join {status}.")
    else:
        await update.message.reply_text("You are not authorized to use this command.")

async def check_membership_button(update: Update, context: CallbackContext) -> bool:
    user = update.effective_user
    query = update.callback_query
    db: Session = next(get_db())
    settings = db.query(Settings).first()
    
    if settings and settings.strict_join:
        required_chats = settings.chats_to_join
        all_joined = True
        buttons = []
        
        for chat in required_chats:
            # try:
            member = await context.bot.get_chat_member(chat['id'], user.id)
            status = "✅" if member.status in ['member', 'administrator', 'creator'] else "❌"
            if status == "❌":
                all_joined = False
            # except:
            #     status = "❌"
            #     all_joined = False
            
            buttons.append([InlineKeyboardButton(f"{status} {chat['name']}", url=chat['chat_link'])])
        
        buttons.append([InlineKeyboardButton("Check Again", callback_data="check_membership")])
        keyboard = InlineKeyboardMarkup(buttons)

        if all_joined:
            try:
                await query.delete_message()
            except:
                pass
            return True
        else:
            try:
                await query.edit_message_text("Please join the following chats:", reply_markup=keyboard)
            except Exception as e:
                try:
                    await query.edit_message_text("Please join the following chats.:", reply_markup=keyboard)
                except:
                    await update.message.reply_text("Please join the following chats.:", reply_markup=keyboard)
                    
            return False
    return True  # If strict_join is not enabled or no settings found


async def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_membership":
        await check_membership_button(update, context)

async def restricted_handler(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if await check_membership(user.id, context.bot) == True:
        return True
    else:
        await check_membership_button(update, context)
        return False

async def start(update: Update, context: CallbackContext) -> None:
    if not await restricted_handler(update=update, context=context):
        return
    db: Session = SessionLocal()
    if len(context.args) > 0:
        referral_id = context.args[0]
    else:
        referral_id = None
    referrer = db.query(User).filter_by(referral_id=referral_id).first()
    if referrer:
        referer_id=referrer.id
    else:
        referer_id = None
    

    user = db.query(User).filter_by(telegram_id=update.message.from_user.id).first()
    if not user:
        # Create a new user
        new_user = User(
            telegram_id=update.message.from_user.id,
            username=update.message.from_user.username,
            first_name=update.message.from_user.first_name,
            last_name=update.message.from_user.last_name,
            referral_id=generate_referral_id(),
            referer_id=referer_id
        )
        db.add(new_user)
        db.commit()

    try:
        if referral_id:            
            if referrer:
                # Optionally, update earnings based on settings
                settings = db.query(Settings).first()
                if settings:
                    referrer.earnings += settings.referral_earning
                    referrer.total_earnings += settings.referral_earning  # Optionally update total earnings as well
                    await context.bot.send_message(referrer.telegram_id, f"You have received a referral bonus!")
                    db.commit()
        
        # Fetch and send response for the start command
        command_text = "start"
        command = db.query(Command).filter_by(command=command_text).first()

        if command:
            response_text = f"Hi {update.effective_user.first_name}!\n\n{command.response}"
            inline_reply_markup = None

            # Prepare the inline keyboard markup if it exists
            inline_keyboard = []
            if command.inline_links:
                inline_buttons = [InlineKeyboardButton(link['text'], url=link['url']) for link in command.inline_links]
                inline_keyboard = create_button_layout(inline_buttons)
            inline_reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

            # Prepare the markup buttons if they exist
            markup_buttons = []
            if command.markup_buttons:
                markup_buttons_list = [KeyboardButton(button) for button in command.markup_buttons]
                markup_buttons = create_button_layout(markup_buttons_list)
            markup_reply_markup = ReplyKeyboardMarkup(markup_buttons, resize_keyboard=True) if markup_buttons else None

            # Send the main response
            if command.image_url:
                await update.message.reply_photo(photo=command.image_url, caption=response_text, reply_markup=inline_reply_markup)
            else:
                await update.message.reply_text(text=response_text, reply_markup=inline_reply_markup, disable_web_page_preview=True)
            
            # Send the markup buttons as a separate message if they exist
            if markup_reply_markup:
                await update.message.reply_text("Menu", reply_markup=markup_reply_markup)
        else:
            await update.message.reply_text(f"Welcome {update.effective_user.first_name}!\n\n Use the /help command to see available commands")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()



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

async def forward_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        db: Session = next(get_db())
        settings = db.query(Settings).first()
        
        if settings and settings.broadcast_chat:
            broadcast_chat = settings.broadcast_chat
            chat_id = update.message.chat.id
            chat_username = update.message.chat.username
            chat_link = getattr(update.message.chat, 'invite_link', None)
            
            match = False
            
            if broadcast_chat.isdigit() and int(broadcast_chat) == chat_id:
                match = True
            elif broadcast_chat.startswith('@') and broadcast_chat == f"@{chat_username}":
                match = True
            elif chat_link and broadcast_chat in chat_link:
                match = True
            
            if match:
                users = db.query(User).all()
                for user in users:
                    try:
                        await context.bot.forward_message(chat_id=user.telegram_id, from_chat_id=chat_id, message_id=update.message.message_id)
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
            inline_buttons = [InlineKeyboardButton(link['text'], url=link['url']) for link in command.inline_links]
            inline_keyboard = create_button_layout(inline_buttons)
        inline_reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

        # Prepare the markup buttons if they exist
        markup_buttons = []
        if command.markup_buttons:
            markup_buttons_list = [KeyboardButton(button) for button in command.markup_buttons]
            markup_buttons = create_button_layout(markup_buttons_list)
        markup_reply_markup = ReplyKeyboardMarkup(markup_buttons, resize_keyboard=True) if markup_buttons else None

        # Send the main response
        if command.image_url:
            await update.message.reply_photo(photo=command.image_url, caption=response_text, reply_markup=inline_reply_markup)
        else:
            await update.message.reply_text(text=response_text, reply_markup=inline_reply_markup, disable_web_page_preview=True)

        # Send the markup buttons as a separate message if they exist
        if markup_reply_markup:
            await update.message.reply_text("Menu", reply_markup=markup_reply_markup)
    else:
        await update.message.reply_text(f"❌ Unknown Command!\n\n"

            f"You have send a Message directly into the Bot's chat or"
            f"Menu structure has been modified by Admin.\n\n"

            f"ℹ️ Do not send Messages directly to the Bot or"
            f"reload the Menu by pressing /start")



async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = next(get_db())
    message_text = update.message.text.lower()
    command = db.query(Command).filter_by(command=message_text).first()
    if command:
        response_text = command.response

        # Prepare the inline keyboard markup if it exists
        inline_keyboard = []
        if command.inline_links:
            inline_buttons = [InlineKeyboardButton(link['text'], url=link['url']) for link in command.inline_links]
            inline_keyboard = create_button_layout(inline_buttons)
        inline_reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

        # Prepare the markup buttons if they exist
        markup_buttons = []
        if command.markup_buttons:
            markup_buttons_list = [KeyboardButton(button) for button in command.markup_buttons]
            markup_buttons = create_button_layout(markup_buttons_list)
        markup_reply_markup = ReplyKeyboardMarkup(markup_buttons, resize_keyboard=True) if markup_buttons else None

        # Send the main response
        if command.image_url:
            await update.message.reply_photo(photo=command.image_url, caption=response_text, reply_markup=inline_reply_markup)
        else:
            await update.message.reply_text(text=response_text, reply_markup=inline_reply_markup, disable_web_page_preview=True)

        # Send the markup buttons as a separate message if they exist
        if markup_reply_markup:
            await update.message.reply_text("Menu", reply_markup=markup_reply_markup)
    else:
        await update.message.reply_text(f"❌ Unknown Message!\n\n"

            f"You have send a Message directly into the Bot's chat or"
            f"Menu structure has been modified by Admin.\n\n"

            f"ℹ️ Do not send Messages directly to the Bot or"
            f"reload the Menu by pressing /start")


async def affiliate(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    db: Session = next(get_db())

    # Query the User from the database based on telegram_id
    user_data = db.query(User).filter(User.telegram_id == user.id).first()

    if user_data:
        ref_link = f"https://t.me/{context.bot.username}?start={user_data.referral_id}"
        
        # Count the number of direct referrals
        referrals_count = db.query(User).filter(User.referer_id == user_data.id).count()
        
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
    settings.referral_earning = amount
    db.commit()
    await update.message.reply_text(f"Referral earning set to {amount}")


async def set_broadcast_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /set_broadcast_chat <chat_id_or_username_or_link>")
        return
    
    chat_entity = context.args[0]
    
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings()
        db.add(settings)
    settings.broadcast_chat = chat_entity
    db.commit()
    
    await update.message.reply_text(f"Broadcast chat set to {chat_entity}. Messages from this chat will be forwarded to all users.")


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
    commands = db.query(Command).filter_by(is_command=True).all()
    help_text = "Available commands:\n\n"
    for cmd in commands:
        help_text += f"/{cmd.command}: {cmd.description}\n\n"
    await update.message.reply_text(help_text)


async def deduct_ref_points(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db: Session = next(get_db())
    
    # Check if the user is an admin
    admin = db.query(Admin).filter(Admin.telegram_id == user.id).first()
    if not admin:
        await update.message.reply_text("You do not have permission to use this command.")
        return
    
    # Parse command arguments
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /deduct_ref_points <user id> <points>")
        return
    
    try:
        user_id = int(context.args[0])
        points = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid user ID or points. Please enter a valid number.")
        return
    
    # Fetch the user to deduct points from
    target_user = db.query(User).filter(User.telegram_id == user_id).first()
    if not target_user:
        await update.message.reply_text("User not found.")
        return
    
    # Deduct points ensuring earnings do not go below 0.0
    target_user.earnings = max(target_user.earnings - points, 0.0)
    db.commit()
    
    await update.message.reply_text(f"Successfully deducted {points} points from user {user_id}. New earnings: {target_user.earnings}")

# Conversation handlers for adding a command
async def add_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = update.effective_user.id
    db: Session = next(get_db())
    admin = db.query(Admin).filter_by(telegram_id=admin_id).first()
    if not admin:
        await update.message.reply_text("You are not authorized to perform this action.")
        return ConversationHandler.END
    await update.message.reply_text(f"Enter tbe custom PROMPT for the bot.\n\n"
                                    f"Examples: ' start ' , ' 🏠 Menu ' ...\n\n"
                                    f"Enter the Prompt without ' / ' or ' ! '. \n⚠️ Avoid using existing prompts!:\n\n"
                                    f"Use /cancel to cancel")
    return ADD_COMMAND

async def add_command_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    command = update.message.text
    context.user_data['command'] = command
    await update.message.reply_text("Enter the DESCRIPTION For this prompt.\n\n"
                                    f"Tell Users what this PROMT Does:\n\n"
                                    f"Use /cancel to cancel")
    return ADD_DESCRIPTION

async def add_command_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['description'] = update.message.text
    await update.message.reply_text("Enter the RESPONSE For this prompt.\n\n"
                                    f"This is where you specify what users will seewhen they send in the promt to the bot:\n\n"
                                    f"Use /cancel to cancel")
    return ADD_RESPONSE

async def add_command_is_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['response'] = update.message.text
    keyboard = [
        ["Command", "Text"],
        ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    proposed_prompt = (context.user_data['command'].replace(' ','_')).replace('/','')
    await update.message.reply_text(f"What KIND of PROMT is this?\n\n"
                                    f"Is this a commad: ' / {proposed_prompt} ' OR just text: ' {context.user_data['command']} ' ...\n\n"
                                    f"Use /cancel to cancel", reply_markup=markup)
    return ADD_IS_COMMAND

async def add_command_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_command = update.message.text.lower()
    if is_command == "command":
        context.user_data['is_command'] = 1
        context.user_data['command'] = ((context.user_data['command']).replace(" ","_"))
    elif is_command == "text":
        context.user_data['is_command'] = 0
        context.user_data['command'] = context.user_data['command']
    await update.message.reply_text("Great! Now, you can optionally Upload an IMAGE that will be sent with the prompt response\n\n"
                                    f"If you dont wish to, just type 'skip'\n\n"
                                    f"Use /cancel to cancel")
    return ADD_IMAGE

async def add_command_inline_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # add_image = update.message.text.lower() == 'yes'
    # if add_image:
    #     await update.message.reply_text("Please send the image file:\n\nUse /cancel to cancel")
    #     return ADD_INLINE_LINKS
    # else:
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
      await update.message.reply_text("✅ Image saved successfully. \n\nDo you want to add inline links? (yes/no)\n\nUse /cancel to cancel")
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
    if update.message.text.lower() != 'no':
        buttons = [button.strip() for button in buttons_text.split(',')]  # Split by ',' to create a list of buttons
        context.user_data['markup_buttons'] = buttons
        return await add_command_finish(update, context)

async def add_command_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: Session = next(get_db())
    is_command=context.user_data['is_command'],
    new_command = Command(
        command=(context.user_data['command'].lower() if not context.user_data['is_command'] else context.user_data['command'].lower().replace(' ','_')),
        description=context.user_data['description'],
        response=context.user_data['response'],
        is_command=context.user_data['is_command'],
        image_url=context.user_data.get('image_url'),
        inline_links=context.user_data.get('inline_links'),
        markup_buttons=context.user_data.get('markup_buttons')  # Save markup buttons
    )
    db.add(new_command)
    db.commit()
    if is_command == True:
        await update.message.reply_text(f"✅ Command /{new_command.command} created successfully.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text(f"✅ Text Prompt {new_command.command} created successfully.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Define constants for the new states
ADD_MARKUP_BUTTONS = range(9, 10)

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
    context.user_data['command'] = update.message.text.lower()
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


async def export_database(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db: Session = next(get_db())
    
    # Check if the user is an admin
    admin = db.query(Admin).filter(Admin.telegram_id == user.id).first()
    if not admin:
        await update.message.reply_text("You do not have permission to use this command.")
        return
    
    # Parse command arguments
    if len(context.args) != 1 or context.args[0] not in ['sqlite', 'csv', 'excel']:
        await update.message.reply_text("Usage: /export <sqlite|csv|excel>")
        return
    
    export_format = context.args[0]
    
    try:
        if export_format == 'sqlite':
            # Assuming you are using an SQLite database
            sqlite_file = 'path/to/your/database.sqlite'
            await context.bot.send_document(chat_id=user.id, document=open(sqlite_file, 'rb'))
        else:
            # Export database tables to CSV files
            users_df = pd.read_sql_table('users', engine)
            commands_df = pd.read_sql_table('commands', engine)
            admins_df = pd.read_sql_table('admins', engine)
            settings_df = pd.read_sql_table('settings', engine)

            users_df.to_csv('users.csv', index=False)
            commands_df.to_csv('commands.csv', index=False)
            admins_df.to_csv('admins.csv', index=False)
            settings_df.to_csv('settings.csv', index=False)
            
            if export_format == 'csv':
                for file in ['users.csv', 'commands.csv', 'admins.csv', 'settings.csv']:
                    await context.bot.send_document(chat_id=user.id, document=open(file, 'rb'))
                    os.remove(file)
                    
            elif export_format == 'excel':
                with pd.ExcelWriter('database.xlsx', engine='openpyxl') as writer:
                    users_df.to_excel(writer, sheet_name='Users', index=False)
                    commands_df.to_excel(writer, sheet_name='Commands', index=False)
                    admins_df.to_excel(writer, sheet_name='Admins', index=False)
                    settings_df.to_excel(writer, sheet_name='Settings', index=False)

                await context.bot.send_document(chat_id=user.id, document=open('database.xlsx', 'rb'))
                os.remove('database.xlsx')
                
                # Remove CSV files after creating the Excel file
                for file in ['users.csv', 'commands.csv', 'admins.csv', 'settings.csv']:
                    os.remove(file)
                    
    except Exception as e:
        await update.message.reply_text(f"Failed to export database: {e}")

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db: Session = next(get_db())
    
    # Check if the user is an admin
    admin = db.query(Admin).filter(Admin.telegram_id == user.id).first()
    if not admin:
        await update.message.reply_text("You do not have permission to use this command.")
        return
    with open('admin_help.json','r') as admin_cmds:
        data = json.load(admin_cmds)
    admin_commands = data

    help_text = "👤 Admin Commands:\n\n"
    for cmd in admin_commands:
        help_text += f"{cmd['command']}: {cmd['description']}\nUsage: {cmd['usage']}\n\n"
    
    await update.message.reply_text(help_text)

# Main function to start the bot
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex('🔙 Back_Start'), start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("affiliate", affiliate))
    application.add_handler(CommandHandler("set_ref_earning", set_ref_earning))
    application.add_handler(CommandHandler("set_broadcast_chat", set_broadcast_chat))
    application.add_handler(CommandHandler("set_downline_earning", set_downline_earning))
    application.add_handler(CommandHandler("add_chat_group", add_chat_group))
    application.add_handler(CommandHandler("remove_chat_group", remove_chat_group))
    application.add_handler(CommandHandler("strict_join", toggle_strict_join))
    application.add_handler(CommandHandler('deduct_ref_points', deduct_ref_points))
    application.add_handler(CommandHandler('export', export_database))
    application.add_handler(CommandHandler("admin_help", admin_help))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="check_membership"))
    
    


    # Conversation handlers for adding commands
    add_command_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addcommand", add_command_start)],
        states={
            ADD_COMMAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_description)],
            ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_response)],
            ADD_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_is_command)],
            ADD_IS_COMMAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_image)],
            ADD_IMAGE: [
                MessageHandler(filters.Regex('(?i)^(yes|no)$') & ~filters.COMMAND, add_command_inline_links),
                MessageHandler(filters.PHOTO & ~filters.COMMAND, add_command_save_image)
            ],
            ADD_INLINE_LINKS: [
                MessageHandler(filters.Regex('(?i)^(yes|no)$') & ~filters.COMMAND, add_command_finish_inline_links),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_finish_save_links)
            ],
            ADD_MARKUP_BUTTONS: [
                MessageHandler(filters.Regex('(?i)^(yes|no)$') & ~filters.COMMAND, add_command_markup_buttons),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_command_finish_save_markup_buttons)
            ],
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
    # application.add_handler(edit_command_conv_handler)
    application.add_handler(delete_command_conv_handler)
    application.add_handler(add_admin_conv_handler)
    application.add_handler(delete_admin_conv_handler)

    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(filters.ChatType.GROUP | filters.ChatType.CHANNEL | filters.ChatType.SUPERGROUP | filters.ChatType.PRIVATE, forward_channel_message))
    application.add_handler(MessageHandler(filters.COMMAND, command_handler))
    application.add_handler(MessageHandler(filters.TEXT, text_handler))
    
    

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main()
