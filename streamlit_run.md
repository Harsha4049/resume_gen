# Streamlit UI Run Instructions

## 1) Start backend

From project root:

```
uvicorn app.main:app --reload --port 8000
```

## 2) Start Streamlit UI

From project root:

```
streamlit run ui/app.py
```

## Optional: change backend URL

Set env var before running UI:

```
set BACKEND_URL=http://127.0.0.1:8000
```

Or edit the Backend URL field in the UI.
