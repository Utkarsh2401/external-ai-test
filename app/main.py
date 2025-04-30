import logging
import os
import json
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Optional
import base64
from llama_cpp import Llama

from ontology_dc8f06af066e4a7880a5938933236037.config import ConfigClass
from ontology_dc8f06af066e4a7880a5938933236037.input import InputClass
from ontology_dc8f06af066e4a7880a5938933236037.output import OutputClass
from openfabric_pysdk.context import AppModel, State
from core.stub import Stub

configurations: Dict[str, ConfigClass] = dict()

# setting global variables
TEXT_TO_IMAGE_APP_ID = "c25dcd829d134ea98f5ae4dd311d13bc.node3.openfabric.network"
IMAGE_TO_3D_APP_ID = "f0b5f319156c4819b9827000b17e511a.node3.openfabric.network"   
DB_PATH = "/app/datastore/memory.db"
OUTPUT_DIR = "/app/outputs"

llm = None
pipe = None

os.makedirs(OUTPUT_DIR, exist_ok=True)

def init_db():
    """
    Initialize the SQLite database for long-term memory storage.
    """

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS creations (
        id TEXT PRIMARY KEY,
        timestamp TEXT,
        original_prompt TEXT,
        expanded_prompt TEXT,
        image_path TEXT,
        model_path TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tags (
        creation_id TEXT,
        tag TEXT,
        FOREIGN KEY (creation_id) REFERENCES creations(id),
        PRIMARY KEY (creation_id, tag)
    )
    ''')
    
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully")

init_db()

def save_to_memory(original_prompt: str, expanded_prompt: str, image_path: str, model_path: str) -> str:
    """
    Save creation details to long-term memory.
    
    Args:
        original_prompt: The original user prompt
        expanded_prompt: The LLM-expanded prompt
        image_path: Path to the generated image
        model_path: Path to the generated 3D model
        
    Returns:
        str: The ID of the created record
    """

    creation_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO creations VALUES (?, ?, ?, ?, ?, ?)",
        (creation_id, timestamp, original_prompt, expanded_prompt, image_path, model_path)
    )
    
    # Only including words longer than 3 characters to avoid overly common tags
    tags = [word.lower() for word in original_prompt.split() if len(word) > 3]
    for tag in set(tags):
        cursor.execute("INSERT INTO tags VALUES (?, ?)", (creation_id, tag))
    
    conn.commit()
    conn.close()
    
    return creation_id

def find_similar_creations(prompt: str, limit: int = 3) -> List[Dict]:
    """
    Find similar creations based on prompt text.
    
    Args:
        prompt: The user prompt to find similar creations for
        limit: Maximum number of results to return
        
    Returns:
        List[Dict]: List of similar creations with their details
    """

    # Preparing search terms based on significant words in the prompt
    search_terms = [word.lower() for word in prompt.split() if len(word) > 3]
    
    if not search_terms:
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    placeholders = ','.join(['?'] * len(search_terms))

    # Quering the database for creations that share tags with the current prompt, ordered by relevance
    query = f"""
    SELECT c.*, COUNT(t.tag) as match_count
    FROM creations c
    JOIN tags t ON c.id = t.creation_id
    WHERE t.tag IN ({placeholders})
    GROUP BY c.id
    ORDER BY match_count DESC
    LIMIT ?
    """
    
    cursor.execute(query, search_terms + [limit])
    results = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return results

############################################################
# Config callback function
############################################################

def config(configuration: Dict[str, ConfigClass], state: State) -> None:
    """
    Stores user-specific configuration data.

    Args:
        configuration (Dict[str, ConfigClass]): A mapping of user IDs to configuration objects.
        state (State): The current state of the application (not used in this implementation).
    """

    for uid, conf in configuration.items():
        logging.info(f"Saving new config for user with id:'{uid}'")
        configurations[uid] = conf

############################################################
# Execution callback function
# ############################################################

# For swagger-ui execution
def execute(model: AppModel) -> None:
    """
    Main execution entry point for handling a model pass.

    Args:
        model (AppModel): The model object containing request and response structures.
    """
    
    request: InputClass = model.request
    user_prompt = request.prompt
    
    if not user_prompt:
        model.response.message = "Please provide a prompt to generate content."
        return
    
    logging.info(f"User prompt received: {user_prompt}")
    
    user_config: ConfigClass = configurations.get('super-user', None)
    logging.info(f"Configurations: {configurations}")

    app_ids = user_config.app_ids if user_config else []
    stub = Stub(app_ids)

    # ------------------------------
    # TODO : add your magic here
    # ------------------------------

    similar_creations = find_similar_creations(user_prompt)

    # Building context from previous similar prompts to help the LLM generate more consistent expansions
    memory_context = ""
    if similar_creations:
        memory_context = "You have previously created the following scenes:\n"
        for creation in similar_creations:
            memory_context += (
                f"- Title: {creation['original_prompt']}\n"
                f"  Expanded Description: {creation['expanded_prompt']}\n"
                f"  Created on: {creation['timestamp']}\n\n"
            )
        memory_context += "Use the knowledge and style from these creations to inspire the new scene ONLY WHEN THE PROMPT IS MENTIONING SOMETHING FROM PAST CREATIONS.\n"

    response: OutputClass = model.response
    
    try:
        global llm, pipe

        if llm is None:
            logging.info("Initializing LLM for prompt expansion...")
            model_path = "./models/phi-2-Q4-K_M.gguf" # loading model
            try:
                llm = Llama(model_path, n_ctx=2048)
                logging.info("Model loaded successfully.")
                
            except Exception as e:
                logging.info(f"Error loading model: {e}")

            pipe = llm

        expansion_input = user_prompt
        # Appending memory-based context to the user prompt if relevant
        if memory_context:
            expansion_input = f"{memory_context}\nNew request: {user_prompt}"

        # Creating a system prompt to instructing the model
        system_prompt = (
            "You are a visual scene designer AI."
            "Expand the following prompt with rich, detailed visual descriptions for image generation."
            "Take into account previous user creations ONLY WHEN THE PROMPT IS MENTIONING SOMETHING FROM PAST CREATIONS."
            "IMPORTANT: SITCK TO THE PROMPT! DO NOT CREATE DESCRIPTIONS UNRELATED TO THE PROMPT!"
        )
        full_prompt = f"{system_prompt}\n\nUser: {expansion_input}\nAI:"

        try:
            response = pipe(
                prompt=full_prompt,
                temperature=0.5,
                top_p=0.95,
                max_tokens=512
            )
            expanded_prompt = response['choices'][0]['text']
            logging.info(f"Expanded prompt: {expanded_prompt}")

        except Exception as e:
            logging.error(f"Error during prompt expansion: {e}")
            response.message = f"Error during prompt expansion: {e}"
        
        logging.info("Calling Text-to-Image app...")
        image_result = stub.call(TEXT_TO_IMAGE_APP_ID, {'prompt': expanded_prompt}, 'super-user')
        image_data = image_result.get('result')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create a safe filename fragment from the user's prompt
        safe_prompt = "".join([c if c.isalnum() else "_" for c in user_prompt[:20]])
        image_filename = f"{timestamp}_{safe_prompt}.png"
        image_path = os.path.join(OUTPUT_DIR, image_filename)

        manifest = stub.manifest(IMAGE_TO_3D_APP_ID)
        logging.info(f"Manifest: {manifest}")

        input_schema = stub.schema(IMAGE_TO_3D_APP_ID, 'input')
        logging.info(f"Input schema: {input_schema}")

        with open(image_path, 'wb') as f:
            logging.info(f"Saving image to {image_path}")
            f.write(image_data)

        logging.info("Calling Image-to-3D app...")

        # Converting binary image to base64 to send to Image-to-3D
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        payload = {'input_image': image_base64}

        model_result = stub.call(IMAGE_TO_3D_APP_ID, payload, 'super-user')
        for key in model_result.keys():
            logging.info(f"Key: {key}")

        if model_result is None:
            model_data = None
            logging.info("Error: Failed to get a valid response from Image-to-3D app.")
        else:
            model_data = model_result.get('generated_object')
            logging.info("Success")
            response["message"] = "Success!"

        model_filename = f"{timestamp}_{safe_prompt}.glb"
        model_path = os.path.join(OUTPUT_DIR, model_filename)
        
        with open(model_path, 'wb') as f:
            if not model_data:
                logging.info(f"Model data not found")

            else:
                logging.info(f"Saving 3D model to {model_path}")
                f.write(model_data)

        creation_id = save_to_memory(user_prompt, expanded_prompt, image_path, model_path)
        logging.info(f"Creation saved to memory with ID: {creation_id}")
        
        logging.info(json.dumps({
            "status": "success",
            "creation_id": creation_id,
            "original_prompt": user_prompt,
            "expanded_prompt": expanded_prompt,
            "image_path": image_path,
            "model_path": model_path,
            "similar_creations": [c["original_prompt"] for c in similar_creations]
        }))
                    
    except Exception as e:
        logging.error(f"Error in execution: {str(e)}")

# For streamlit-app execution
def execute_streamlit(prompt):
    """
    Main execution entry point for handling a model pass.
    
    Args:
        prompt (str): User text prompt
        
    Returns:
        dict: Results including paths to generated content or None if failed
    """

    user_prompt = prompt
    
    if not user_prompt:
        logging.warning("Empty prompt received")
        return None
    
    logging.info(f"User prompt received: {user_prompt}")
    
    user_config = configurations.get('super-user', None)
    
    app_ids = user_config.app_ids if user_config else []
    stub = Stub(app_ids)
    
    similar_creations = find_similar_creations(user_prompt)
    
    # Building context from previous similar prompts to help the LLM generate more consistent expansions
    memory_context = ""
    if similar_creations:
        memory_context = "You have previously created the following scenes:\n"
        for creation in similar_creations:
            memory_context += (
                f"- Title: {creation['original_prompt']}\n"
                f"  Expanded Description: {creation['expanded_prompt']}\n"
                f"  Created on: {creation['timestamp']}\n\n"
            )
        memory_context += "Use the knowledge and style from these creations to inspire the new scene ONLY WHEN THE PROMPT IS MENTIONING SOMETHING FROM PAST CREATIONS.\n"
    
    try:
        global llm, pipe
        
        if llm is None:
            logging.info("Initializing LLM for prompt expansion...")
            model_path = "./models/phi-2-Q4-K_M.gguf" 
            try:
                llm = Llama(model_path, n_ctx=2048)
                logging.info("Model loaded successfully.")
            except Exception as e:
                logging.error(f"Error loading model: {e}")
                return None

            pipe = llm

        expansion_input = user_prompt
        # Appending memory-based context to the user prompt if relevant
        if memory_context:
            expansion_input = f"{memory_context}\nNew request: {user_prompt}"
        
        # Creating a system prompt to instructing the model
        system_prompt = (
            "You are a visual scene designer AI."
            "Expand the following prompt with rich, detailed visual descriptions for image generation."
            "Take into account previous user creations ONLY WHEN THE PROMPT IS MENTIONING SOMETHING FROM PAST CREATIONS."
            "IMPORTANT: SITCK TO THE PROMPT! DO NOT CREATE DESCRIPTIONS UNRELATED TO THE PROMPT!"
        )
        full_prompt = f"{system_prompt}\n\nUser: {expansion_input}\nAI:"
        
        try:
            response = pipe(
                prompt=full_prompt,
                temperature=0.5,
                top_p=0.95,
                max_tokens=512
            )
            expanded_prompt = response['choices'][0]['text']
            logging.info(f"Expanded prompt: {expanded_prompt}")
        except Exception as e:
            logging.error(f"Error during prompt expansion: {e}")
            return None

        logging.info("Calling Text-to-Image app...")
        try:
            image_result = stub.call(TEXT_TO_IMAGE_APP_ID, {'prompt': expanded_prompt}, 'super-user')
            image_data = image_result.get('result')
            
            if not image_data:
                logging.error("Failed to get image data from Text-to-Image app")
                return None
                
        except Exception as e:
            logging.error(f"Error calling Text-to-Image app: {e}")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Creating a safe filename fragment from the user's prompt
        safe_prompt = "".join([c if c.isalnum() else "_" for c in user_prompt[:20]])
        image_filename = f"{timestamp}_{safe_prompt}.png"
        image_path = os.path.join(OUTPUT_DIR, image_filename)
        
        with open(image_path, 'wb') as f:
            logging.info(f"Saving image to {image_path}")
            f.write(image_data)
        
        logging.info("Calling Image-to-3D app...")
        try:
            # Converting binary image to base64 to send to Image-to-3D
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            payload = {'input_image': image_base64}
            
            model_result = stub.call(IMAGE_TO_3D_APP_ID, payload, 'super-user')
            model_data = model_result.get('generated_object')
            
            if not model_data:
                logging.warning("Failed to get 3D model data from Image-to-3D app")
                
        except Exception as e:
            logging.error(f"Error calling Image-to-3D app: {e}")
            model_data = None

        model_filename = f"{timestamp}_{safe_prompt}.glb"
        model_path = os.path.join(OUTPUT_DIR, model_filename)
        
        if model_data:
            with open(model_path, 'wb') as f:
                logging.info(f"Saving 3D model to {model_path}")
                f.write(model_data)
        else:
            model_path = None
        creation_id = save_to_memory(user_prompt, expanded_prompt, image_path, model_path or "")
        logging.info(f"Creation saved to memory with ID: {creation_id}")
        
        return {
            "status": "success",
            "creation_id": creation_id,
            "original_prompt": user_prompt,
            "expanded_prompt": expanded_prompt,
            "image_path": image_path,
            "model_path": model_path,
            "similar_creations": [c["original_prompt"] for c in similar_creations]
        }

    except Exception as e:
        logging.error(f"Error in execution: {str(e)}")
        return None
