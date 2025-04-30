FROM openfabric/tee-python-cpu:dev

# Copy only necessary files for Poetry installation

COPY pyproject.toml ./

RUN apt-get update && apt-get install -y git cmake build-essential

# Install dependencies using Poetry
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install --upgrade poetry && \
    python3 -m poetry install --only main && \
    python3 -m pip install --upgrade transformers accelerate && \
    python3 -m pip install --upgrade llama-cpp-python && \
    python3 -m pip install --upgrade streamlit && \
    rm -rf ~/.cache/pypoetry/{cache,artifacts}

# Copy the rest of the source code into the container
COPY . .

# Expose port 5000 for the Flask app
EXPOSE 8888

# Start the Flask app using the start.sh script
# Uncomment the below line to use swagger-ui
# CMD ["sh","start.sh"]

# For streamlit-app
CMD ["streamlit", "run", "streamlit.py"]
