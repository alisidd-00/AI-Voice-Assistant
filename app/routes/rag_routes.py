from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from app.services.rag import extract_and_index

rag_bp = Blueprint("rag", __name__, url_prefix="/api/rag")

@rag_bp.route("/index_files", methods=["POST"])
def index_files():
    """
    form-data:
      - assistant_id (int)
      - user_id      (int)
      - files        (one or more: pdf, txt, etc.)
    """
    # 1) Parse and validate IDs
    try:
        assistant_id = int(request.form["assistant_id"])
        user_id      = int(request.form["user_id"])
    except (KeyError, ValueError):
        return jsonify(error="assistant_id & user_id required"), 400

    # 2) Gather uploaded docs
    if "files" not in request.files:
        return jsonify(error="No files uploaded"), 400

    docs: list[str|bytes] = []
    for f in request.files.getlist("files"):
        filename = secure_filename(f.filename or "")
        ext = filename.rsplit(".", 1)[-1].lower()
        raw = f.read()
        if ext == "pdf":
            docs.append(raw)  # bytes → PDF extractor will be invoked
        elif ext in ("txt", "md", "text"):
            docs.append(raw.decode("utf-8", errors="ignore"))
        else:
            # skip unknown types (or add Word, HTML, etc. here)
            continue

    if not docs:
        return jsonify(error="No supported files uploaded"), 400

    # 3) Extract, chunk, embed & index
    result = extract_and_index(assistant_id, user_id, docs)
    return jsonify(result), 200
