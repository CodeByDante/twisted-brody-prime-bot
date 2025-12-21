FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    p7zip-full \
    git \
    git-lfs \
    build-essential \
    && git lfs install \
    && rm -rf /var/lib/apt/lists/*

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Set working directory to the user's home directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies as the new user
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY --chown=user . .

# Create necessary directories and set permissions
RUN mkdir -p downloads tmp tools cookies data sessions && \
    chown -R user:user /app && \
    chmod -R 777 /app/downloads /app/tmp /app/cookies /app/data /app/sessions

# Switch to the "user" user
USER user

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port for Hugging Face Spaces
EXPOSE 7860

# Command to run the bot: Start Aria2 daemon and then the Python bot
CMD aria2c --enable-rpc --rpc-listen-all=false --rpc-listen-port=6800 --daemon && python main.py
