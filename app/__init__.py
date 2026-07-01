"""
Flask application factory.

Connects to Postgres, creates the schema if needed, loads the FHIR
JSONL file once at startup, then registers all route blueprints.
"""

import logging
import os
import time

from flask import Flask, jsonify, g, request

from app.db.connection import init_pool, run_schema
from app.db import load as db_load
import app.store as store
from app.routes import patients, analytics, admin, narrative

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)

    init_pool()
    run_schema(os.path.join(os.path.dirname(__file__), "db", "schema.sql"))

    data_file = os.environ.get("FHIR_DATA_FILE", "data/fhir_data.jsonl")
    db_load.load(data_file)

    app.register_blueprint(patients.bp)
    app.register_blueprint(analytics.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(narrative.bp)

    @app.get("/health")
    def health():
        stats = store.ingestion_stats()
        return jsonify({"status": "ok", "patients": stats["patients"]})

    @app.before_request
    def start_timer():
        g.start = time.monotonic()

    @app.after_request
    def log_request(response):
        ms = round((time.monotonic() - g.start) * 1000)
        logger.info(f"{request.method} {request.path} → {response.status_code} ({ms}ms)")
        return response

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found", "detail": str(e.description)}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Unhandled exception")
        return jsonify({"error": "Internal server error"}), 500

    return app
