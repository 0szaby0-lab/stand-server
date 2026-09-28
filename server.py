import http.server
import socketserver
import os
import json
import sys
from datetime import datetime

# Port for Render or local
PORT = int(os.environ.get("PORT", 6969))

# MongoDB setup (optional via MONGO_URI env var)
MONGO_URI = os.environ.get("MONGO_URI", "")
mongo_client = None
db = None

if MONGO_URI:
    try:
        from pymongo import MongoClient
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = mongo_client.get_default_database()
        if db is None:
            db = mongo_client["stand_db"]
        # Trigger quick connection check
        mongo_client.admin.command('ping')
        print("[MongoDB] Successfully connected to MongoDB.")
    except Exception as e:
        print(f"[MongoDB] Connection failed: {e}. Falling back to standalone mode.")
        db = None
else:
    print("[MongoDB] No MONGO_URI configured. Running in standalone mode.")

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/heartbeat':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
            except Exception:
                data = {}

            activation_key = data.get("a", "")
            
            # Default fallback tier logic
            privilege = "3" # Default to Ultimate if standalone
            unlocks = 255
            root_name = "Stand (Ultimate)"

            if "Basic-" in activation_key:
                privilege = "1"
                unlocks = 0
                root_name = "Stand (Basic)"
            elif "Regular-" in activation_key:
                privilege = "2"
                unlocks = 0
                root_name = "Stand (Regular)"
            elif "Ultimate-" in activation_key:
                privilege = "3"
                unlocks = 255
                root_name = "Stand (Ultimate)"
            elif "Free-" in activation_key:
                privilege = "0"
                unlocks = 0
                root_name = "Stand (Free)"

            # If MongoDB is connected, query key collection
            if db is not None:
                try:
                    key_record = db.keys.find_one({"key": activation_key})
                    if key_record:
                        privilege = str(key_record.get("privilege", privilege))
                        unlocks = int(key_record.get("unlocks", unlocks))
                        root_name = key_record.get("root_name", root_name)
                    else:
                        # Auto-register new key if not present
                        db.keys.insert_one({
                            "key": activation_key,
                            "privilege": privilege,
                            "unlocks": unlocks,
                            "root_name": root_name,
                            "first_seen": datetime.utcnow()
                        })

                    # Log heartbeat
                    db.heartbeats.insert_one({
                        "key": activation_key,
                        "privilege": privilege,
                        "root_name": root_name,
                        "client_ip": self.client_address[0],
                        "payload": data,
                        "timestamp": datetime.utcnow()
                    })
                except Exception as err:
                    print(f"[MongoDB] Error during query/logging: {err}")

            response = {
                "s": privilege + "fake_signature",
                "u": unlocks,
                "r": root_name,
                "t": "ACTVTE_SUCC2"
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return
            
        return super().do_POST()

    def do_GET(self):
        # Health check endpoint for Render
        if self.path == '/healthz' or self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
            return
        return super().do_GET()

    def translate_path(self, path):
        # Default translation relative to current script directory
        translated = super().translate_path(path)
        
        # If it's a directory, let standard handler deal with index.html
        if os.path.isdir(translated):
            return translated
            
        # If the file exists exactly as requested, serve it
        if os.path.isfile(translated):
            return translated
            
        # Try appending .html (for extensionless URLs like /account/register)
        if os.path.isfile(translated + '.html'):
            return translated + '.html'
            
        # If requested .php, try .html instead
        if translated.endswith('.php'):
            html_path = translated[:-4] + '.html'
            if os.path.isfile(html_path):
                return html_path
                
        return translated

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == '__main__':
    # Ensure working dir is script dir
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    server_address = ('0.0.0.0', PORT)
    with ThreadingHTTPServer(server_address, CustomHandler) as httpd:
        print(f"Stand Server running on port {PORT} (0.0.0.0)...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.server_close()
