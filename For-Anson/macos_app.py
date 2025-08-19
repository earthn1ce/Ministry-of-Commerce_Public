
import webview
import threading
import time
from main import app

def start_flask():
    """Start the Flask app in a separate thread"""
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)

def create_macos_app():
    """Create a macOS app window"""
    # Start Flask server in background
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    # Wait for Flask to start
    time.sleep(2)
    
    # Create webview window
    webview.create_window(
        title="URL Date Gap Calculator",
        url="http://127.0.0.1:5001",
        width=1000,
        height=800,
        min_size=(800, 600)
    )
    
    webview.start(debug=False)

if __name__ == '__main__':
    create_macos_app()
