import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "SHEMMS Analytics Skeleton is running!"

if __name__ == '__main__':
    # Grab the port from the .env file, fallback to 5000
    port = int(os.environ.get('FLASK_PORT', 5000))
    print(f"✅ Analytics Flask server starting on port {port}")
    
    # host='0.0.0.0' is required for Docker to expose the port outside the container
    app.run(host='0.0.0.0', port=port)