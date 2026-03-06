#!/bin/bash
source venv/bin/activate
echo "🚀 Starting AI Interviewer on http://localhost:8000"
uvicorn src.main:app --reload --port 8000
```

---

**Folder structure should look like:**
```
ai-interviewer/
├── .env
├── requirements.txt
├── run.sh
├── src/
│   └── main.py
└── public/
    └── index.html