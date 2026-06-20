# AI Data Analytics Platform

An AI-powered Data Analytics Platform that helps users upload CSV or Excel files, analyze data using AI, generate charts, and create business reports.

Built using **FastAPI**, **React**, **PostgreSQL**, and **Google Gemini AI**.

---

## Features

### User Management

- User Registration
- User Login
- JWT Authentication
- Protected User Dashboard

### File Management

- Upload CSV Files
- Upload Excel Files
- View Uploaded Files
- Download Uploaded Files
- Rename Files
- Delete Files

### AI Data Analysis

- Ask Questions About Uploaded Data
- Generate AI-Based Insights
- Analyze CSV and Excel Data
- Get Business-Friendly Answers
- Generate Charts from Data
- Supports Bar Charts, Line Charts, and Pie Charts

### Report Generation

- Generate Business Analysis Reports
- Save Generated Reports
- Download Reports as Word Documents
- Delete Old Reports

---

## Tech Stack

### Backend

- FastAPI
- SQLAlchemy
- PostgreSQL
- JWT Authentication
- Google Gemini API
- Python Dotenv

### Frontend

- React
- HTML
- CSS
- JavaScript

---

## Project Structure

```text
AI Data Analytics Platform
|
|-- backend
|   |-- app
|   |   |-- main.py
|   |   |-- models.py
|   |   |-- schemas.py
|   |   |-- database.py
|   |
|   |-- requirements.txt
|   |-- uploads
|   |-- reports
|
|-- frontend
|   |-- src
|   |-- public
|   |-- package.json
|
|-- README.md
|-- .gitignore
```

---

# Installation

## 1. Open Project Folder

Open terminal inside the project folder:

```bash
cd "AI Data Analytics Platform"
```

---

## 2. Backend Setup

Navigate to backend folder:

```bash
cd backend
```

Create virtual environment:

```bash
python -m venv venv
```

Activate virtual environment:

### Windows

```bash
venv\Scripts\activate
```

### Linux / Mac

```bash
source venv/bin/activate
```

Install backend dependencies:

```bash
pip install -r requirements.txt
```

---

## 3. PostgreSQL Setup

Create a PostgreSQL database for the project.

Example:

```sql
CREATE DATABASE ai_data_analytics;
```

You can also create a separate user:

```sql
CREATE USER ai_analytics_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE ai_data_analytics TO ai_analytics_user;
```

After creating the database, add the database connection inside the backend environment file.

---

## 4. Create Environment File

Inside the backend folder, create a file named:

```text
.env
```

Add these values:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/ai_data_analytics
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Example:

```env
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/ai_data_analytics
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Never share or upload your `.env` file.

---

## 5. Gemini API Setup

1. Open Google AI Studio.
2. Sign in with your Google account.
3. Create a Gemini API key.
4. Copy the API key.
5. Paste it inside the `backend/.env` file:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

The app uses Gemini AI to analyze uploaded files and generate report content.

---

## 6. Run Backend

Inside the backend folder, run:

```bash
uvicorn app.main:app --reload
```

Backend runs on:

```text
http://127.0.0.1:8000
```

---

## 7. Frontend Setup

Open a new terminal and go to the frontend folder:

```bash
cd frontend
```

Install frontend dependencies:

```bash
npm install
```

Start React app:

```bash
npm start
```

Frontend runs on:

```text
http://localhost:3000
```

---

# How to Use

1. Register a new account.
2. Login with your username and password.
3. Upload a CSV or Excel file.
4. Select the uploaded file.
5. Ask questions about your data.
6. Ask for charts if needed.
7. Generate a business report.
8. Download the generated Word report.

Example prompts:

```text
Summarize this dataset.
```

```text
Find important trends in this data.
```

```text
Create a bar chart from this data.
```

```text
Generate business insights from this file.
```

---

# Environment Variables

Create this file:

```text
backend/.env
```

Required variables:

```env
DATABASE_URL=your_postgresql_database_url
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
```

---

# Screenshots

### Login Page

_Add Screenshot Here_

### Dashboard

_Add Screenshot Here_

### File Upload

_Add Screenshot Here_

### AI Analysis Chat

_Add Screenshot Here_

### Generated Report

_Add Screenshot Here_

---

# Future Improvements

- PDF Report Export
- Advanced Dashboard Charts
- File Preview Table
- Data Cleaning Tools
- Admin Dashboard
- Multiple AI Model Support
- Better Report Templates

---

# Author

**Syed Mohd Fasih Naqvi**

---

## If you found this project useful, consider giving it a star.
