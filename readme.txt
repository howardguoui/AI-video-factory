backend:
launch docker: docker update --restart always redis
 & ".\venv\Scripts\uvicorn.exe" app.main:app --host 0.0.0.0 --port 8000

 & ".\venv\Scripts\python.exe" -m celery -A app.worker worker --loglevel=info -P solo -n worker1@%COMPUTERNAME%


delete all task: 
& ".\venv\Scripts\python.exe" -m celery -A app.worker purge
frontend:

npm run dev