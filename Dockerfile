FROM python:3.12-slim

WORKDIR /app

# Copy all backend files
COPY requirements.txt .
COPY app.py .
COPY ai.py .
COPY utils.py .
COPY all_words.json .
COPY referee_prompt.txt .
COPY schema.sql .
COPY templates/ ./templates/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model separately (avoids URL label issues in pip)
RUN python -m spacy download en_core_web_sm

EXPOSE 5001

CMD ["python", "app.py"]
