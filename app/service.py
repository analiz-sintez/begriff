from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
import logging
from .models import db, Report, User, Task, Project

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_report(description, hours_spent, user_id, task_id=None, project_id=None, 
                  comment=None, result=None, difficulty=None, remaining_estimate=None):
    """
    Create a new report and add it to the database.
    Perform sanity checks before saving.
    """
    logger.info("Attempting to create a report.")
    
    # Check if user exists
    user = User.query.get(user_id)
    task = Task.query.get(task_id) if task_id else None
    project = Project.query.get(project_id) if project_id else None

    if not user:
        logger.error("User not found: user_id=%s", user_id)
        raise ValueError("User not found")

    # Assume hours_spent must be a positive number
    if hours_spent <= 0:
        logger.error("Invalid hours spent: %s", hours_spent)
        raise ValueError("Hours spent must be positive")

    # Create report instance
    report = Report(
        description=description,
        hours_spent=hours_spent,
        user_id=user_id,
        task_id=task_id,
        comment=comment,
        result=result,
        difficulty=difficulty,
        remaining_estimate=remaining_estimate
    )

    # Add and commit to the database
    try:
        db.session.add(report)
        db.session.commit()
        logger.info("Report created successfully: report_id=%s", report.id)
        return report
    except IntegrityError as e:
        db.session.rollback()
        logger.error("Integrity error occurred while creating a report: %s", e)
        raise ValueError("Integrity error occurred while creating a report.")

def get_reports(user_id=None, task_id=None, project_id=None, created_dttm_start=None, created_dttm_end=None):
    """
    Retrieve reports, optionally filtered by user_id, task_id, project_id, and date range.
    """
    logger.info("Retrieving reports with filters: user_id=%s, task_id=%s, project_id=%s", user_id, task_id, project_id)
    
    query = Report.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    if task_id:
        query = query.filter_by(task_id=task_id)
    if project_id:
        query = query.filter(Project.tasks.any(Task.id == task_id))
    if created_dttm_start:
        query = query.filter(Report.created_dttm >= created_dttm_start)
    if created_dttm_end:
        query = query.filter(Report.created_dttm <= created_dttm_end)

    reports = query.all()
    logger.info("Retrieved %d reports", len(reports))
    return reports
