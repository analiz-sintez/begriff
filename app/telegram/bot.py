from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from ..service import create_report
from ..models import db, User, Project, Task

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Welcome to the Co-op Reporting Bot!')

def parse_report(message: str):
    """Parse a report message in the format "[[<Project>/]<Task>/]<Work description>: <hours spent> [(<comment>)]"."""
    try:
        # Extract potential components
        main_part, hours_comment = message.split(':')
        if '(' in hours_comment and ')' in hours_comment:
            hours_part, comment = hours_comment.split('(')
            comment = comment.rstrip(')')
        else:
            hours_part = hours_comment
            comment = None

        parts = main_part.split('/')
        work_description = parts[-1].strip()
        task_name = parts[-2].strip() if len(parts) > 1 else None
        project_name = parts[-3].strip() if len(parts) > 2 else None
        hours_spent = float(hours_part.strip())

        return work_description, hours_spent, project_name, task_name, comment
    except ValueError:
        raise ValueError("Unable to parse the message. Ensure it's in the correct format.")

async def handle_message(update: Update, context: CallbackContext):
    """Handle incoming messages and parse them into reports."""
    user_nickname = update.message.from_user.username
    message = update.message.text

    try:
        work_description, hours_spent, project_name, task_name, comment = parse_report(message)
        user = User.query.filter_by(login=user_nickname).first()

        if not user:
            # Create new user if not existing
            user = User(login=user_nickname)
            db.session.add(user)
            db.session.commit()

        # TODO: fetch projects and tasks from some database, maybe github repos and issues?
        project = Project.query.filter_by(name=project_name).first() if project_name else None
        task = Task.query.filter_by(name=task_name).first() if task_name else None

        report = create_report(
            description=work_description,
            hours_spent=hours_spent,
            user_id=user.id,
            project_id=project.id if project else None,
            task_id=task.id if task else None,
            comment=comment
        )
        
        await update.message.reply_text(f'Report created: {report.description} for {report.hours_spent} hours.')

    except ValueError as e:
        await update.message.reply_text(str(e))

def create_bot(token):
    """Start the Telegram bot."""
    application = Application.builder().token(token).build()
    application.bot.initialize()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application
