import csv
import io
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree
from xml.sax.saxutils import escape
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse as DownloadResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.database import engine, Base
from app.models import Report, UploadedFile, User
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import (
    ChatRequest,
    ChatResponse,
    FileResponse,
    FileUpdate,
    ReportCreate,
    ReportResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

app = FastAPI()

SECRET_KEY = "change-this-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
UPLOAD_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_PREFERRED_MODELS = [
    GEMINI_MODEL,
    "gemini-2.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return plain_password == hashed_password


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


def get_user_file(file_id: int, user: User, db: Session) -> UploadedFile:
    db_file = (
        db.query(UploadedFile)
        .filter(UploadedFile.id == file_id, UploadedFile.owner_id == user.id)
        .first()
    )
    if db_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return db_file


def get_user_report(report_id: int, user: User, db: Session) -> Report:
    db_report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.owner_id == user.id)
        .first()
    )
    if db_report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return db_report


def preview_csv(path: Path, max_rows: int = 25) -> str:
    raw = path.read_bytes()[:200000]
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = []
    for index, row in enumerate(reader):
        if index >= max_rows:
            break
        rows.append(row[:20])
    return "\n".join(", ".join(cell for cell in row) for row in rows)


def preview_xlsx(path: Path, max_rows: int = 25) -> str:
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as workbook:
        shared_strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", namespace):
                text_parts = [node.text or "" for node in item.findall(".//m:t", namespace)]
                shared_strings.append("".join(text_parts))

        sheet_name = next(
            name for name in workbook.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        root = ElementTree.fromstring(workbook.read(sheet_name))
        rows = []
        for row in root.findall(".//m:row", namespace)[:max_rows]:
            values = []
            for cell in row.findall("m:c", namespace)[:20]:
                value_node = cell.find("m:v", namespace)
                value = value_node.text if value_node is not None else ""
                if cell.attrib.get("t") == "s" and value.isdigit():
                    value = shared_strings[int(value)] if int(value) < len(shared_strings) else value
                values.append(value)
            rows.append(", ".join(values))
    return "\n".join(rows)


def get_file_preview(db_file: UploadedFile) -> str:
    path = UPLOAD_DIR / db_file.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file missing")

    extension = Path(db_file.original_filename).suffix.lower()
    try:
        if extension == ".csv":
            return preview_csv(path)
        if extension == ".xlsx":
            return preview_xlsx(path)
    except Exception:
        return "The uploaded file exists, but a preview could not be extracted."

    return "Preview is not available for this Excel format. Use the filename and metadata for context."


def parse_gemini_json(text: str) -> dict:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"answer": text, "charts": []}


def list_gemini_models() -> list[str]:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=f"Gemini model lookup failed: {detail}")
    except urllib.error.URLError as error:
        raise HTTPException(status_code=502, detail=f"Could not reach Gemini API: {error.reason}")

    supported = []
    for model in data.get("models", []):
        methods = model.get("supportedGenerationMethods", [])
        name = model.get("name", "")
        if "generateContent" in methods and name.startswith("models/"):
            supported.append(name.replace("models/", "", 1))
    return supported


def choose_gemini_model() -> str:
    supported = list_gemini_models()
    for model in GEMINI_PREFERRED_MODELS:
        if model in supported:
            return model
    if supported:
        return supported[0]
    raise HTTPException(status_code=502, detail="No Gemini models support generateContent for this API key")


def request_gemini_model(prompt: str, model: str) -> dict:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.25,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 429 or "RESOURCE_EXHAUSTED" in detail:
            status_code = 429
        elif error.code == 503 or "UNAVAILABLE" in detail:
            status_code = 503
        else:
            status_code = 502
        raise HTTPException(status_code=status_code, detail=f"Gemini API error: {detail}")
    except urllib.error.URLError as error:
        raise HTTPException(status_code=502, detail=f"Could not reach Gemini API: {error.reason}")

    candidates = data.get("candidates", [])
    if not candidates:
        raise HTTPException(status_code=502, detail="Gemini returned no response")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts).strip()
    return parse_gemini_json(text)


def call_gemini(prompt: str) -> dict:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured")

    tried = []
    candidate_models = list(GEMINI_PREFERRED_MODELS)
    try:
        for model in list_gemini_models():
            if model not in candidate_models:
                candidate_models.append(model)
    except HTTPException:
        pass

    for model in candidate_models:
        if model in tried:
            continue
        tried.append(model)
        try:
            return request_gemini_model(prompt, model)
        except HTTPException as error:
            if error.status_code in (429, 503):
                continue
            if error.status_code != 502 or "NOT_FOUND" not in str(error.detail):
                raise

    raise HTTPException(
        status_code=503,
        detail=(
            "Gemini is unavailable for the available models due to quota or high demand. "
            f"Tried: {', '.join(tried)}. "
            "Please retry later, use a project with quota, or enable billing for the Google AI project."
        ),
    )


def build_local_analysis(db_file: UploadedFile, preview: str, prompt: str) -> dict:
    rows = [line for line in preview.splitlines() if line.strip()]
    headers = [cell.strip() for cell in rows[0].split(",")] if rows else []
    sample_count = max(len(rows) - 1, 0)
    answer = (
        "Gemini is currently unavailable because the API quota is exhausted or the model is under high demand, "
        "so here is a basic local preview-based insight instead.\n\n"
        f"Selected file: {db_file.original_filename}\n"
        f"Rows visible in preview: {sample_count}\n"
        f"Columns visible in preview: {', '.join(headers) if headers else 'Could not detect headers'}\n\n"
        "Enable billing or wait for quota reset to get full AI-generated analysis."
    )

    chart = None
    wants_chart = any(word in prompt.lower() for word in ["chart", "graph", "plot", "visual", "bar", "line", "pie"])
    if wants_chart and len(rows) > 1:
        labels = []
        values = []
        for row in rows[1:8]:
            cells = [cell.strip() for cell in row.split(",")]
            if len(cells) >= 2:
                try:
                    values.append(float(cells[1]))
                    labels.append(cells[0] or f"Row {len(labels) + 1}")
                except ValueError:
                    continue
        if labels and values:
            chart = {
                "title": "Preview chart",
                "type": "bar",
                "labels": labels,
                "values": values,
            }

    return {"answer": answer, "charts": [chart] if chart else []}


def build_analysis_prompt(db_file: UploadedFile, preview: str, request: ChatRequest) -> str:
    history = "\n".join(
        f"{message.role}: {message.content}"
        for message in request.history[-8:]
    )
    return f"""
You are an AI data analyst inside a web dashboard.
Analyze the selected uploaded file and answer the user's prompt.

Selected file:
- Name: {db_file.original_filename}
- Size: {db_file.size} bytes
- Content type: {db_file.content_type}

File preview, first rows:
{preview}

Recent chat:
{history}

User prompt:
{request.prompt}

Return only valid JSON in this exact shape:
{{
  "answer": "Insightful answer in plain language with concrete observations.",
  "charts": [
    {{
      "title": "Chart title",
      "type": "bar",
      "labels": ["Label A", "Label B"],
      "values": [10, 20]
    }}
  ]
}}

Only include charts when the user asks for a chart, graph, visual, trend, comparison,
or when a chart would clearly help the answer. Supported chart types are bar, line, and pie.
""".strip()


def create_docx_report(path: Path, title: str, messages: list) -> None:
    body_parts = [
        "<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>"
        + escape(title)
        + "</w:t></w:r></w:p>"
    ]
    for message in messages:
        role = escape(message.role.title())
        content = escape(message.content).replace("\n", "</w:t></w:r></w:p><w:p><w:r><w:t>")
        body_parts.append(
            f"<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>{role}</w:t></w:r></w:p>"
            f"<w:p><w:r><w:t>{content}</w:t></w:r></w:p>"
        )

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(body_parts)}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", rels)
        docx.writestr("word/document.xml", document_xml)


def build_report_prompt(source_file: UploadedFile | None, messages: list) -> str:
    source = (
        f"Source file: {source_file.original_filename}, {source_file.size} bytes"
        if source_file
        else "Source file: Not specified"
    )
    chat_insights = "\n".join(
        f"{message.role.upper()}: {message.content}"
        for message in messages
    )
    return f"""
You are a senior business analyst preparing a formal business report.
Use the insights from the analysis chat below. Do not write it like a chat transcript.

{source}

Analysis chat insights:
{chat_insights}

Return only valid JSON in this exact shape:
{{
  "title": "Business Analysis Report",
  "sections": [
    {{
      "heading": "Executive Summary",
      "paragraphs": ["Concise overview of the business meaning of the data."]
    }},
    {{
      "heading": "Key Findings",
      "paragraphs": ["Finding 1", "Finding 2"]
    }},
    {{
      "heading": "Business Implications",
      "paragraphs": ["What these findings mean for decisions, operations, revenue, risk, or performance."]
    }},
    {{
      "heading": "Recommendations",
      "paragraphs": ["Actionable recommendation 1", "Actionable recommendation 2"]
    }},
    {{
      "heading": "Next Steps",
      "paragraphs": ["Practical next action 1", "Practical next action 2"]
    }}
  ]
}}
""".strip()


def build_local_business_report(source_file: UploadedFile | None, messages: list) -> dict:
    assistant_insights = [
        message.content
        for message in messages
        if message.role == "assistant" and message.content.strip()
    ]
    user_questions = [
        message.content
        for message in messages
        if message.role == "user" and message.content.strip()
    ]
    combined = "\n".join(assistant_insights[-6:]) or "No detailed AI insights were available."
    source_name = source_file.original_filename if source_file else "the selected dataset"
    return {
        "title": "Business Analysis Report",
        "sections": [
            {
                "heading": "Executive Summary",
                "paragraphs": [
                    f"This report summarizes the analysis performed on {source_name}. It consolidates the main observations from the analysis session into a business-ready format for review and decision-making."
                ],
            },
            {
                "heading": "Analysis Scope",
                "paragraphs": user_questions[-4:] or [
                    "The report is based on the questions and prompts submitted during the analysis session."
                ],
            },
            {
                "heading": "Key Findings",
                "paragraphs": assistant_insights[-6:] or [combined],
            },
            {
                "heading": "Business Implications",
                "paragraphs": [
                    "The findings should be reviewed in the context of operational performance, data quality, and decision priorities. Patterns, anomalies, or comparisons identified during the chat may indicate opportunities for optimization or areas that require further validation."
                ],
            },
            {
                "heading": "Recommendations",
                "paragraphs": [
                    "Validate the highlighted findings against the complete dataset before making major business decisions.",
                    "Prioritize follow-up analysis around the strongest trends, unusual values, or performance gaps identified during the session.",
                    "Use the generated charts and observations as a starting point for stakeholder discussion."
                ],
            },
            {
                "heading": "Next Steps",
                "paragraphs": [
                    "Review the selected dataset for missing values, duplicates, and inconsistent fields.",
                    "Run additional targeted prompts for the most important business metrics.",
                    "Share this report with relevant stakeholders and capture decisions or action owners."
                ],
            },
        ],
    }


def generate_business_report_content(source_file: UploadedFile | None, messages: list) -> dict:
    try:
        result = call_gemini(build_report_prompt(source_file, messages))
        if isinstance(result.get("sections"), list):
            return result
    except HTTPException:
        pass
    return build_local_business_report(source_file, messages)


def create_business_docx_report(path: Path, report: dict) -> None:
    title = str(report.get("title") or "Business Analysis Report")
    body_parts = [
        "<w:p><w:r><w:rPr><w:b/><w:sz w:val=\"32\"/></w:rPr><w:t>"
        + escape(title)
        + "</w:t></w:r></w:p>"
    ]
    body_parts.append(
        "<w:p><w:r><w:t>Generated on "
        + escape(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        + "</w:t></w:r></w:p>"
    )
    for section in report.get("sections", []):
        heading = escape(str(section.get("heading", "Section")))
        body_parts.append(
            f"<w:p><w:r><w:rPr><w:b/><w:sz w:val=\"26\"/></w:rPr><w:t>{heading}</w:t></w:r></w:p>"
        )
        for paragraph in section.get("paragraphs", []):
            content = escape(str(paragraph)).replace("\n", "</w:t></w:r></w:p><w:p><w:r><w:t>")
            body_parts.append(f"<w:p><w:r><w:t>{content}</w:t></w:r></w:p>")

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(body_parts)}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", rels)
        docx.writestr("word/document.xml", document_xml)


@app.get("/")
def home():
    return {"message": "App API Running"}


@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = (
        db.query(User)
        .filter((User.username == user.username) | (User.email == user.email))
        .first()
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    new_user = User(
        username=user.username,
        email=user.email,
        password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "message": "User created successfully"
    }


@app.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if user.password == credentials.password:
        user.password = hash_password(credentials.password)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@app.get("/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@app.post("/files", response_model=FileResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_extensions = {".xls", ".xlsx", ".csv"}
    extension = Path(file.filename or "").suffix.lower()
    if extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Only Excel or CSV files are allowed")

    stored_filename = f"{current_user.id}_{uuid4().hex}{extension}"
    destination = UPLOAD_DIR / stored_filename
    contents = await file.read()
    destination.write_bytes(contents)

    db_file = UploadedFile(
        original_filename=file.filename or stored_filename,
        stored_filename=stored_filename,
        content_type=file.content_type,
        size=len(contents),
        owner_id=current_user.id,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


@app.get("/files", response_model=list[FileResponse])
def list_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(UploadedFile)
        .filter(UploadedFile.owner_id == current_user.id)
        .order_by(UploadedFile.uploaded_at.desc())
        .all()
    )


@app.get("/files/{file_id}/download")
def download_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = get_user_file(file_id, current_user, db)
    path = UPLOAD_DIR / db_file.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file missing")

    return DownloadResponse(path, filename=db_file.original_filename, media_type=db_file.content_type)


@app.put("/files/{file_id}", response_model=FileResponse)
def update_file(
    file_id: int,
    payload: FileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    new_name = payload.original_filename.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")

    db_file = get_user_file(file_id, current_user, db)
    db_file.original_filename = new_name
    db.commit()
    db.refresh(db_file)
    return db_file


@app.delete("/files/{file_id}")
def delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = get_user_file(file_id, current_user, db)
    path = UPLOAD_DIR / db_file.stored_filename
    if path.exists():
        path.unlink()

    db.delete(db_file)
    db.commit()
    return {"message": "File deleted successfully"}


@app.post("/analysis/chat", response_model=ChatResponse)
def analyze_chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = get_user_file(request.file_id, current_user, db)
    preview = get_file_preview(db_file)
    gemini_prompt = build_analysis_prompt(db_file, preview, request)
    try:
        result = call_gemini(gemini_prompt)
    except HTTPException as error:
        if error.status_code not in (429, 503):
            raise
        result = build_local_analysis(db_file, preview, request.prompt)

    charts = []
    for chart in result.get("charts", []):
        labels = chart.get("labels", [])
        values = chart.get("values", [])
        if labels and values and len(labels) == len(values):
            charts.append({
                "title": str(chart.get("title", "Chart")),
                "type": str(chart.get("type", "bar")).lower(),
                "labels": [str(label) for label in labels],
                "values": [float(value) for value in values],
            })

    return {
        "answer": str(result.get("answer", "No insight was generated.")),
        "charts": charts,
    }


@app.post("/reports", response_model=ReportResponse)
def generate_report(
    payload: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.messages:
        raise HTTPException(status_code=400, detail="Chat is empty")

    source_file = None
    if payload.file_id is not None:
        source_file = get_user_file(payload.file_id, current_user, db)

    report_content = generate_business_report_content(source_file, payload.messages)
    title = str(report_content.get("title") or "Business Analysis Report")
    stored_filename = f"{current_user.id}_{uuid4().hex}.docx"
    path = REPORT_DIR / stored_filename
    create_business_docx_report(path, report_content)

    db_report = Report(
        title=f"{title} - {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        stored_filename=stored_filename,
        owner_id=current_user.id,
        source_file_id=source_file.id if source_file else None,
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


@app.get("/reports", response_model=list[ReportResponse])
def list_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Report)
        .filter(Report.owner_id == current_user.id)
        .order_by(Report.created_at.desc())
        .all()
    )


@app.get("/reports/{report_id}/download")
def download_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_report = get_user_report(report_id, current_user, db)
    path = REPORT_DIR / db_report.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored report missing")

    return DownloadResponse(
        path,
        filename=f"{db_report.title}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.delete("/reports/{report_id}")
def delete_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_report = get_user_report(report_id, current_user, db)
    path = REPORT_DIR / db_report.stored_filename
    if path.exists():
        path.unlink()

    db.delete(db_report)
    db.commit()
    return {"message": "Report deleted successfully"}
