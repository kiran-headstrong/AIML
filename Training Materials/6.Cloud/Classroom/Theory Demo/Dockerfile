FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Create the DB tables on first run
# Then run the Flask app



# app.app_context().push() manually pushes the context.
CMD ["python", "-c", "from app import app, db; app.app_context().push(); db.create_all(); import os; os.system('flask run --host=0.0.0.0')"]
# CMD python wait_for_db.py && python -c "from app import app, db; app.app_context().push(); db.create_all()" && flask run --host=0.0.0.0



