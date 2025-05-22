from flask import Blueprint, jsonify, request
from .service import create_report, get_reports as service_get_reports
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

report_bp = Blueprint('report_bp', __name__)

@report_bp.route('/', methods=['GET'])
def get_root():
    logger.info("GET request to root endpoint.")
    return jsonify({'message': 'Hello World'}), 200

@report_bp.route('/report', methods=['PUT'])
def put_report():
    data = request.get_json()
    logger.info("Received PUT request to create a report with data: %s", data)
    try:
        report = create_report(
            description=data.get('description'),
            hours_spent=data.get('hours_spent'),
            user_id=data.get('user_id'),
            task_id=data.get('task_id'),
            project_id=data.get('project_id'),
            comment=data.get('comment'),
            result=data.get('result'),
            difficulty=data.get('difficulty'),
            remaining_estimate=data.get('remaining_estimate')
        )
        logger.info("Report created successfully with ID: %s", report.id)
        return jsonify({'message': 'Report saved', 'report_id': report.id}), 200
    except ValueError as e:
        logger.error("Error creating report: %s", e)
        return jsonify({'error': str(e)}), 400

@report_bp.route('/report', methods=['GET'])
def get_reports():
    user_id = request.args.get('user_id')
    task_id = request.args.get('task_id')
    project_id = request.args.get('project_id')
    created_dttm_start = request.args.get('created_dttm_start')
    created_dttm_end = request.args.get('created_dttm_end')

    logger.info("GET request to retrieve reports with filters: user_id=%s, task_id=%s, project_id=%s", user_id, task_id, project_id)
    
    reports = service_get_reports(
        user_id=user_id,
        task_id=task_id,
        project_id=project_id,
        created_dttm_start=created_dttm_start,
        created_dttm_end=created_dttm_end
    )

    logger.info("Retrieved %d reports", len(reports))
    return jsonify({'reports': [report.to_dict() for report in reports]}), 200

@report_bp.route('/report/<int:id>', methods=['GET'])
def get_report(id):
    logger.info("GET request for report with ID: %d", id)
    reports = service_get_reports(task_id=id)
    if reports:
        logger.info("Report with ID %d found", id)
        return jsonify({'report': reports[0].to_dict()}), 200
    else:
        logger.error("Report with ID %d not found", id)
        return jsonify({'error': f'Report {id} not found'}), 404
