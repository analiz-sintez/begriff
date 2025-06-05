from flask import Blueprint, jsonify, request
from .srs import get_views
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

srs_bp = Blueprint("srs_bp", __name__)


@srs_bp.route("/", methods=["GET"])
def get_root():
    logger.info("GET request to root endpoint.")
    return jsonify({"message": "Hello World"}), 200


@srs_bp.route("/views", methods=["GET"])
def get_views():
    logger.info("GET request to /views endpoint without params.")
    return jsonify([view.to_dict() for view in get_views()])
