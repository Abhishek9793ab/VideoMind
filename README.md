# LearnLens AI / VideoMind AI
Django-only YouTube transcript RAG learning assistant.

## Windows PowerShell
```powershell
cd C:\Users\ACER\VideoMind-AI
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set GEMINI_API_KEY
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```
Open http://127.0.0.1:8000/

First run downloads the Sentence Transformers embedding model. Processing works only when a video's transcript/captions are accessible. This is a local MVP; add production security, rate limits, async processing, and storage before public deployment.
