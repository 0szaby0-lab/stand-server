import http.server
import socketserver
import os
import json
import urllib.parse
from datetime import datetime

# Port for Render or local
PORT = int(os.environ.get("PORT", 6969))

# MongoDB setup (via MONGO_URI env var)
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
        mongo_client.admin.command('ping')
        print("[MongoDB] Successfully connected to MongoDB.")
    except Exception as e:
        print(f"[MongoDB] Connection failed: {e}. Falling back to standalone mode.")
        db = None
else:
    print("[MongoDB] No MONGO_URI configured. Running in standalone mode.")

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, status=200, content_type='text/plain'):
        body = text.encode('utf-8') if isinstance(text, str) else text
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def parse_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            return {}
        post_data = self.rfile.read(content_length)
        content_type = self.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            try:
                return json.loads(post_data.decode('utf-8'))
            except Exception:
                return {}
        else:
            try:
                parsed = urllib.parse.parse_qs(post_data.decode('utf-8'))
                return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            except Exception:
                return {}

    def do_POST(self):
        # 1. Menü Heartbeat
        if self.path == '/api/heartbeat':
            data = self.parse_body()
            activation_key = data.get("a", "")
            
            # Default fallback tier logic (Ultimate)
            privilege = "3"
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

            # MongoDB lookup & logging
            if db is not None:
                try:
                    key_record = db.accounts.find_one({"activation_key": activation_key})
                    if not key_record:
                        key_record = db.keys.find_one({"key": activation_key})
                    
                    if key_record:
                        privilege = str(key_record.get("privilege", privilege))
                        unlocks = int(key_record.get("unlocks", unlocks))
                        root_name = key_record.get("root_name", root_name)
                    else:
                        db.accounts.insert_one({
                            "activation_key": activation_key,
                            "privilege": privilege,
                            "unlocks": unlocks,
                            "root_name": root_name,
                            "created": datetime.utcnow()
                        })

                    db.heartbeats.insert_one({
                        "key": activation_key,
                        "privilege": privilege,
                        "root_name": root_name,
                        "client_ip": self.client_address[0],
                        "payload": data,
                        "timestamp": datetime.utcnow()
                    })
                except Exception as err:
                    print(f"[MongoDB] Heartbeat error: {err}")

            response = {
                "s": privilege + "fake_signature",
                "u": unlocks,
                "r": root_name,
                "t": "ACTVTE_SUCC2"
            }
            return self.send_json(response)

        # 2. Basic Account Info (Web UI /account/)
        if self.path in ('/api/basic_account_info', '/api/basic_account_info.php', '/api/basic_account_info.html'):
            data = self.parse_body()
            account_id = data.get("account_id", "")
            
            acc = None
            if db is not None and account_id:
                try:
                    acc = db.accounts.find_one({"id": account_id})
                except Exception as e:
                    print(f"[MongoDB] Account info error: {e}")

            if not acc:
                # Default mock account response so web UI always works
                acc = {
                    "activation_key": f"Stand-Activate-{account_id[-16:]}" if account_id else "Stand-Activate-UltimateMockKey",
                    "privilege": 3,
                    "suspended_for": "",
                    "coins": 0,
                    "created_quiz_success": True
                }

            return self.send_json({
                "activation_key": acc.get("activation_key", "Stand-Activate-UltimateMockKey"),
                "privilege": int(acc.get("privilege", 3)),
                "suspended_for": acc.get("suspended_for", ""),
                "coins": int(acc.get("coins", 0)),
                "created_quiz_success": bool(acc.get("created_quiz_success", True))
            })

        # 3. Redeem License Key (Web UI /account/register)
        if self.path in ('/api/redeem', '/api/redeem.php', '/api/redeem.html'):
            data = self.parse_body()
            license_key = data.get("license_key", "")
            
            chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            import random
            account_id = "acc_" + "".join(random.choice(chars) for _ in range(27))
            activation_key = "Stand-Activate-" + "".join(random.choice(chars) for _ in range(16))
            privilege = 3

            if db is not None:
                try:
                    db.accounts.insert_one({
                        "id": account_id,
                        "license_key": license_key,
                        "activation_key": activation_key,
                        "privilege": privilege,
                        "created": datetime.utcnow()
                    })
                except Exception as e:
                    print(f"[MongoDB] Redeem error: {e}")

            return self.send_json({
                "account_id": account_id,
                "activation_key": activation_key,
                "privilege": privilege,
                "created_quiz_success": True
            })

        # 4. Telemetry / Event logging
        if self.path in ('/api/event', '/api/event.php', '/api/event.html'):
            data = self.parse_body()
            if db is not None:
                try:
                    db.events.insert_one({
                        "data": data,
                        "client_ip": self.client_address[0],
                        "timestamp": datetime.utcnow()
                    })
                except Exception as e:
                    print(f"[MongoDB] Event logging error: {e}")
            return self.send_text("1")

        return super().do_POST()

    def do_GET(self):
        # Health check endpoint for Render
        if self.path in ('/healthz', '/ping'):
            return self.send_text("OK")

        # Specific API endpoints that return JSON
        if self.path in ('/api/tuna.json', '/api/tuna.json.php', '/api/tuna.json.html'):
            bg54 = ""
            bg55 = ""
            blob = ""
            if os.path.exists("api/bgscript-5.4.txt"):
                with open("api/bgscript-5.4.txt", "r", encoding="utf-8", errors="ignore") as f:
                    bg54 = f.read()
            if os.path.exists("api/bgscript-5.5.txt"):
                with open("api/bgscript-5.5.txt", "r", encoding="utf-8", errors="ignore") as f:
                    bg55 = f.read()
            if os.path.exists("api/blobfish.txt"):
                with open("api/blobfish.txt", "r", encoding="utf-8", errors="ignore") as f:
                    blob = f.read()

            tuna_data = {
                "v": 1337420,
                "lnv": "3407a",
                "repo": [],
                "b": bg54,
                "b2": bg55,
                "ba": [],
                "f": blob,
                "a": []
            }
            return self.send_json(tuna_data)

        if self.path in ('/api/packages.json', '/api/packages.json.php', '/api/packages.json.html'):
            return self.send_json([])

        if self.path in ('/stand-versions.txt', '/stand-versions.txt.html', '/versions.txt', '/versions.txt.html'):
            ver_text = "111.1\n"
            if os.path.exists("stand-versions.txt"):
                with open("stand-versions.txt", "r", encoding="utf-8", errors="ignore") as f:
                    ver_text = f.read()
            return self.send_text(ver_text)

        return super().do_GET()

    def translate_path(self, path):
        translated = super().translate_path(path)
        
        if os.path.isdir(translated):
            return translated
            
        if os.path.isfile(translated):
            return translated
            
        if os.path.isfile(translated + '.html'):
            return translated + '.html'
            
        if translated.endswith('.php'):
            html_path = translated[:-4] + '.html'
            if os.path.isfile(html_path):
                return html_path
                
        return translated

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    server_address = ('0.0.0.0', PORT)
    with ThreadingHTTPServer(server_address, CustomHandler) as httpd:
        print(f"Stand MongoDB Server running on port {PORT} (0.0.0.0)...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.server_close()
