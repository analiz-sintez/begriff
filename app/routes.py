from flask import Blueprint, jsonify, request
from .srs import get_views
import logging

# Set up logging

logger = logging.getLogger(__name__)

srs_bp = Blueprint("srs_bp", __name__)


@srs_bp.route("/", methods=["GET"])
def get_root():
    logger.info("GET request to root endpoint.")
    return jsonify({"message": "Hello World"}), 200
