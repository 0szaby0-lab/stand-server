import http.server
import socketserver
import os
import json
import urllib.parse
import secrets
import hashlib
import time
from datetime import datetime, timezone, timedelta

# Port for Render or local
PORT = int(os.environ.get("PORT", 6969))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "standadmin2026")
SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
STRICT_MODE = os.environ.get("STRICT_MODE", "true").lower() in ("true", "1", "yes")

# Discord Integrations
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "")
ROLE_BASIC = os.environ.get("ROLE_BASIC", "")
ROLE_REGULAR = os.environ.get("ROLE_REGULAR", "")
ROLE_ULTIMATE = os.environ.get("ROLE_ULTIMATE", "")

# Active admin sessions: token -> timestamp
admin_sessions = set()

# MongoDB setup (via MONGO_URI env var)
MONGO_URI = os.environ.get("MONGO_URI", "")
mongo_client = None
db = None

# In-memory fallback if MongoDB is not connected
memory_keys = {}
memory_heartbeats = []

def now_utc():
    return datetime.now(timezone.utc)

def is_mongo_alive():
    global mongo_client, db
    if not MONGO_URI:
        return False
    if db is None or mongo_client is None:
        init_mongo()
    if db is not None and mongo_client is not None:
        try:
            mongo_client.admin.command('ping')
            return True
        except Exception:
            return False
    return False

def init_mongo():
    global mongo_client, db
    if MONGO_URI:
        try:
            from pymongo import MongoClient
            mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            db = mongo_client.get_default_database()
            if db is None:
                db = mongo_client["stand_db"]
            mongo_client.admin.command('ping')
            print("[MongoDB] Successfully connected to MongoDB.")
            
            # Ensure indexes
            db.keys.create_index("key", unique=True)
            db.heartbeats.create_index("timestamp")
            db.account_discords.create_index([("account_id", 1), ("discord_id", 1)], unique=True)
        except Exception as e:
            print(f"[MongoDB] Connection failed: {e}. Falling back to in-memory mode.")
            db = None
    else:
        print("[MongoDB] No MONGO_URI configured. Running in in-memory mode.")

init_mongo()

def check_admin_auth(handler):
    cookie_header = handler.headers.get('Cookie', '')
    cookies = urllib.parse.parse_qs(cookie_header.replace('; ', '&'))
    token = cookies.get('stand_admin_token', [''])[0]
    return token in admin_sessions

import urllib.request
import urllib.error

def discord_api_request(method, endpoint, data=None):
    if not DISCORD_BOT_TOKEN: return None
    url = f"https://discord.com/api/v10{endpoint}"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    body = None
    if data:
        body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        print(f"[Discord API Error] {e}")
        return None

def kick_discord_member(user_id):
    if DISCORD_GUILD_ID:
        discord_api_request("DELETE", f"/guilds/{DISCORD_GUILD_ID}/members/{user_id}")

def add_guild_member(user_id, access_token, roles):
    if DISCORD_GUILD_ID:
        data = {"access_token": access_token, "roles": roles}
        discord_api_request("PUT", f"/guilds/{DISCORD_GUILD_ID}/members/{user_id}", data=data)

def update_member_role(user_id, add_roles, remove_roles):
    if not DISCORD_GUILD_ID: return
    for r in add_roles:
        if r: discord_api_request("PUT", f"/guilds/{DISCORD_GUILD_ID}/members/{user_id}/roles/{r}")
    for r in remove_roles:
        if r: discord_api_request("DELETE", f"/guilds/{DISCORD_GUILD_ID}/members/{user_id}/roles/{r}")

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode('utf-8')
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
        client_ip = self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[0].strip()

        # ==========================================
        # 1. ADMIN AUTHENTICATION
        # ==========================================
        if self.path == '/api/admin/login':
            data = self.parse_body()
            password = data.get("password", "")
            if password == ADMIN_PASSWORD:
                token = secrets.token_hex(24)
                admin_sessions.add(token)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Set-Cookie', f'stand_admin_token={token}; Path=/; HttpOnly; SameSite=Lax')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
                return
            else:
                return self.send_json({"success": False, "error": "Hibás jelszó!"}, status=401)

        if self.path == '/api/admin/logout':
            cookie_header = self.headers.get('Cookie', '')
            cookies = urllib.parse.parse_qs(cookie_header.replace('; ', '&'))
            token = cookies.get('stand_admin_token', [''])[0]
            if token in admin_sessions:
                admin_sessions.remove(token)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Set-Cookie', 'stand_admin_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            return

        # ==========================================
        # 1.5. DISCORD OAUTH CALLBACK LOGIC
        # ==========================================
        if self.path.startswith('/api/discord/join_callback') or self.path.startswith('/api/discord/update_callback'):
            data = self.parse_body()
            account_id = data.get("account_id")
            discord_id = data.get("discord_id")
            access_token = data.get("access_token")
            is_update = "update" in self.path
            
            if not account_id or not discord_id:
                return self.send_json({"error": "Missing parameters"}, status=400)
                
            key_doc = None
            if db is not None:
                key_doc = db.keys.find_one({"key": account_id})
            
            if not key_doc or key_doc.get("status") == "banned":
                return self.send_json({"error": "Invalid or banned account"}, status=403)
                
            last_discord = key_doc.get("last_known_discord_id")
            
            if is_update:
                if last_discord != discord_id:
                    return self.send_json({"error": "You need to join our Discord before you can use this."}, status=403)
            else:
                if last_discord != discord_id:
                    # Kick old account
                    if last_discord:
                        kick_discord_member(last_discord)
                    
                    if db is not None:
                        db.keys.update_one({"key": account_id}, {"$set": {"last_known_discord_id": discord_id}})
                        
                        # Tally discords linked
                        ads = list(db.account_discords.find({"account_id": account_id}))
                        is_new = True
                        num_recent_ads = 1
                        forty_five_days_ago = now_utc() - timedelta(days=45)
                        
                        for ad in ads:
                            if ad.get("discord_id") == discord_id:
                                is_new = False
                                db.account_discords.update_one({"_id": ad["_id"]}, {"$set": {"last_join": now_utc()}})
                                break
                            elif ad.get("last_join") and ad.get("last_join") > forty_five_days_ago:
                                num_recent_ads += 1
                                
                        if is_new:
                            db.account_discords.insert_one({"account_id": account_id, "discord_id": discord_id, "last_join": now_utc()})
                            
                        # Suspend if too many recent discord accounts
                        if num_recent_ads >= 4:
                            db.keys.update_one({"key": account_id}, {"$set": {"status": "banned", "suspended_for": "account sharing or ban evasion"}})
                            return self.send_json({"error": "Banned for account sharing or ban evasion."}, status=403)

            # Assign roles based on privilege
            priv = int(key_doc.get("privilege", 3))
            roles_to_add = []
            roles_to_remove = []
            
            if priv == 1:
                roles_to_add = [ROLE_BASIC]
                roles_to_remove = [ROLE_REGULAR, ROLE_ULTIMATE]
            elif priv == 2:
                roles_to_add = [ROLE_REGULAR]
                roles_to_remove = [ROLE_BASIC, ROLE_ULTIMATE]
            elif priv == 3:
                roles_to_add = [ROLE_ULTIMATE]
                roles_to_remove = [ROLE_BASIC, ROLE_REGULAR]
                
            if is_update:
                update_member_role(discord_id, roles_to_add, roles_to_remove)
            else:
                add_guild_member(discord_id, access_token, roles_to_add)
                
            return self.send_json({"success": True, "message": "Discord linked successfully."})

        # ==========================================
        # 2. ADMIN ACTIONS (PASSWORD PROTECTED)
        # ==========================================
        if self.path.startswith('/api/admin/'):
            if not check_admin_auth(self):
                return self.send_json({"error": "Unauthorized"}, status=401)

            # Generate new key
            if self.path == '/api/admin/keys/create':
                data = self.parse_body()
                tier = data.get("tier", "Ultimate") # Basic, Regular, Ultimate
                note = data.get("note", "")
                days = int(data.get("days", 0)) # 0 = lifetime

                chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                rand_part = "".join(secrets.choice(chars) for _ in range(24))
                key = f"Stand-{tier}-{rand_part}"
                
                expires_at = None
                if days > 0:
                    expires_at = now_utc() + timedelta(days=days)

                privilege = "3"
                root_name = f"Stand ({tier})"
                unlocks = 255 if tier == "Ultimate" else 0
                if tier == "Basic":
                    privilege = "1"
                elif tier == "Regular":
                    privilege = "2"

                key_doc = {
                    "key": key,
                    "tier": tier,
                    "privilege": privilege,
                    "unlocks": unlocks,
                    "root_name": root_name,
                    "note": note,
                    "status": "active", # active, banned
                    "created_at": now_utc(),
                    "expires_at": expires_at,
                    "hwid": "",
                    "last_ip": "",
                    "last_seen": None,
                    "uses": 0
                }

                if db is not None:
                    db.keys.insert_one(key_doc)
                    key_doc.pop("_id", None)
                else:
                    memory_keys[key] = key_doc

                return self.send_json({"success": True, "key": key_doc})

            # Toggle ban
            if self.path == '/api/admin/keys/toggle-ban':
                data = self.parse_body()
                key = data.get("key", "")
                new_status = data.get("status", "banned")

                if db is not None:
                    res = db.keys.update_one({"key": key}, {"$set": {"status": new_status}})
                    return self.send_json({"success": res.modified_count > 0, "status": new_status})
                else:
                    if key in memory_keys:
                        memory_keys[key]["status"] = new_status
                        return self.send_json({"success": True, "status": new_status})
                return self.send_json({"success": False, "error": "Key not found"}, status=404)

            # Delete key
            if self.path == '/api/admin/keys/delete':
                data = self.parse_body()
                key = data.get("key", "")

                if db is not None:
                    res = db.keys.delete_one({"key": key})
                    return self.send_json({"success": res.deleted_count > 0})
                else:
                    if key in memory_keys:
                        del memory_keys[key]
                        return self.send_json({"success": True})
                return self.send_json({"success": False, "error": "Key not found"}, status=404)

        # ==========================================
        # 3. CLIENT HEARTBEAT (STRICT KEY VALIDATION)
        # ==========================================
        if self.path == '/api/heartbeat':
            data = self.parse_body()
            activation_key = data.get("a", "").strip()
            hwid = data.get("h", "")

            # Look up key in DB
            key_doc = None
            if db is not None:
                key_doc = db.keys.find_one({"key": activation_key})
            else:
                key_doc = memory_keys.get(activation_key)

            # --- STRICT VALIDATION ENFORCEMENT ---
            if STRICT_MODE:
                if not key_doc:
                    # Log failed attempt
                    log_entry = {
                        "key": activation_key,
                        "status": "REJECTED_NOT_FOUND",
                        "client_ip": client_ip,
                        "hwid": hwid,
                        "timestamp": now_utc()
                    }
                    if db is not None:
                        db.heartbeats.insert_one(log_entry)
                    return self.send_json({"m": "Érvénytelen licenc kulcs! Vegye fel a kapcsolatot az adminnal."}, status=403)

                if key_doc.get("status") == "banned":
                    log_entry = {
                        "key": activation_key,
                        "status": "REJECTED_BANNED",
                        "client_ip": client_ip,
                        "hwid": hwid,
                        "timestamp": now_utc()
                    }
                    if db is not None:
                        db.heartbeats.insert_one(log_entry)
                    return self.send_json({"m": "Ez a licenc kulcs tiltva van az adminisztrátor által!"}, status=403)

                # Check expiration
                expires_at = key_doc.get("expires_at")
                if expires_at:
                    if isinstance(expires_at, datetime):
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        if now_utc() > expires_at:
                            log_entry = {
                                "key": activation_key,
                                "status": "REJECTED_EXPIRED",
                                "client_ip": client_ip,
                                "hwid": hwid,
                                "timestamp": now_utc()
                            }
                            if db is not None:
                                db.heartbeats.insert_one(log_entry)
                            return self.send_json({"m": "Ez a licenc kulcs lejárt!"}, status=403)

            # Extract privileges from validated key
            if key_doc:
                privilege = str(key_doc.get("privilege", "3"))
                unlocks = int(key_doc.get("unlocks", 255))
                root_name = key_doc.get("root_name", "Stand (Ultimate)")
                
                # Update usage stats
                update_fields = {
                    "last_seen": now_utc(),
                    "last_ip": client_ip,
                }
                if hwid and not key_doc.get("hwid"):
                    update_fields["hwid"] = hwid

                if db is not None:
                    db.keys.update_one({"key": activation_key}, {
                        "$set": update_fields,
                        "$inc": {"uses": 1}
                    })
                else:
                    key_doc.update(update_fields)
                    key_doc["uses"] = key_doc.get("uses", 0) + 1
            else:
                # If strict mode is somehow turned off, fallback
                privilege = "3"
                unlocks = 255
                root_name = "Stand (Ultimate)"

            # Log heartbeat
            log_entry = {
                "key": activation_key,
                "status": "SUCCESS",
                "privilege": privilege,
                "root_name": root_name,
                "client_ip": client_ip,
                "hwid": hwid,
                "timestamp": now_utc()
            }
            if db is not None:
                try:
                    db.heartbeats.insert_one(log_entry)
                except Exception as err:
                    print(f"[MongoDB] Heartbeat log error: {err}")
            else:
                memory_heartbeats.append(log_entry)
                if len(memory_heartbeats) > 200:
                    memory_heartbeats.pop(0)

            response = {
                "s": privilege + "stand_signature_ok",
                "u": unlocks,
                "r": root_name,
                "t": "ACTVTE_SUCC2"
            }
            return self.send_json(response)

        # 4. Basic Account Info (Web UI /account/)
        if self.path in ('/api/basic_account_info', '/api/basic_account_info.php', '/api/basic_account_info.html'):
            data = self.parse_body()
            account_id = data.get("account_id", "")
            
            # Look up account in MongoDB keys
            key_doc = None
            if db is not None and account_id:
                try:
                    key_doc = db.keys.find_one({"key": account_id})
                except Exception as e:
                    print(f"[MongoDB] Account info error: {e}")

            if not key_doc and account_id in memory_keys:
                key_doc = memory_keys.get(account_id)

            if key_doc:
                return self.send_json({
                    "activation_key": key_doc.get("key"),
                    "privilege": int(key_doc.get("privilege", 3)),
                    "suspended_for": "Banned by Admin" if key_doc.get("status") == "banned" else "",
                    "coins": 0,
                    "created_quiz_success": True
                })
            else:
                return self.send_json({
                    "activation_key": account_id if account_id else "Stand-Activate-UltimateMockKey",
                    "privilege": 3,
                    "suspended_for": "",
                    "coins": 0,
                    "created_quiz_success": True
                })

        # 5. Redeem License Key (Web UI /account/register)
        if self.path in ('/api/redeem', '/api/redeem.php', '/api/redeem.html'):
            data = self.parse_body()
            license_key = data.get("license_key", "").strip()
            
            key_doc = None
            if db is not None:
                key_doc = db.keys.find_one({"key": license_key, "status": "active"})
            else:
                key_doc = memory_keys.get(license_key)
                if key_doc and key_doc.get("status") != "active":
                    key_doc = None
            
            if key_doc:
                return self.send_json({
                    "account_id": key_doc["key"],
                    "activation_key": key_doc["key"],
                    "privilege": int(key_doc.get("privilege", 3)),
                    "created_quiz_success": True
                })
            else:
                return self.send_json({"error": "Érvénytelen vagy már felhasznált licenc kulcs!"})

        # 6. Telemetry / Event logging
        if self.path in ('/api/event', '/api/event.php', '/api/event.html'):
            data = self.parse_body()
            if db is not None:
                try:
                    db.events.insert_one({
                        "data": data,
                        "client_ip": client_ip,
                        "timestamp": now_utc()
                    })
                except Exception:
                    pass
            return self.send_text("1")

        # Fallback for unhandled POSTs (never call super().do_POST() as SimpleHTTPRequestHandler doesn't implement it)
        return self.send_json({"error": "Endpoint not found"}, status=404)

    def do_GET(self):
        # Health check endpoint for Render
        if self.path in ('/healthz', '/ping'):
            return self.send_text("OK")

        # ==========================================
        # OLD API STAND ONE ENDPOINTS
        # ==========================================
        if self.path.startswith('/api/internal_whack_a_mole') or self.path.startswith('/internal_whack_a_mole'):
            parsed_path = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed_path.query)
            account_id = query.get('0', [''])[0]
            source = query.get('1', [''])[0]
            
            def get_reason(src):
                if src == "discord": return "account id sharing (D)"
                if src == "telegram": return "compromised account (T)"
                return None
                
            reason = get_reason(source)
            if account_id and source and reason:
                if db is not None:
                    db.keys.update_one({"key": account_id}, {"$set": {"status": "banned", "suspended_for": reason}})
                    return self.send_text("1")
                else:
                    if account_id in memory_keys:
                        memory_keys[account_id]["status"] = "banned"
                        memory_keys[account_id]["suspended_for"] = reason
                        return self.send_text("1")
            return self.send_text("0")

        if self.path.startswith('/api/internal_get_alts') or self.path.startswith('/internal_get_alts'):
            parsed_path = urllib.parse.urlparse(self.path)
            discord_id = urllib.parse.parse_qs(parsed_path.query).get('0', [''])[0]
            if discord_id and db is not None:
                key_doc = db.keys.find_one({"last_known_discord_id": discord_id, "status": "active"})
                if key_doc:
                    alts = list(db.account_discords.find(
                        {"account_id": key_doc["key"], "discord_id": {"$ne": discord_id}},
                        {"_id": 0, "discord_id": 1, "last_join": 1}
                    ))
                    # Convert datetime to timestamp for API compatibility
                    for alt in alts:
                        if isinstance(alt.get("last_join"), datetime):
                            alt["last_join"] = int(alt["last_join"].timestamp())
                    return self.send_json(alts)
            return self.send_json([])

        if self.path.startswith('/api/internal_check_pinkeye') or self.path.startswith('/internal_check_pinkeye'):
            parsed_path = urllib.parse.urlparse(self.path)
            account_id = urllib.parse.parse_qs(parsed_path.query).get('0', [''])[0]
            if account_id and db is not None:
                key_doc = db.keys.find_one({"key": account_id, "status": "active"})
                if key_doc:
                    return self.send_json({"dev": False, "pinkeyed": False})
            return self.send_json({"dev": False, "pinkeyed": False})

        if self.path.startswith('/api/internal_get_privilege') or self.path.startswith('/internal_get_privilege'):
            parsed_path = urllib.parse.urlparse(self.path)
            account_id = urllib.parse.parse_qs(parsed_path.query).get('0', [''])[0]
            if account_id and db is not None:
                key_doc = db.keys.find_one({"key": account_id, "status": "active"})
                if key_doc:
                    return self.send_text(str(key_doc.get("privilege", 3)))
            return self.send_text("0")

        # ==========================================
        # ADMIN API (GET)
        # ==========================================
        if self.path == '/api/admin/check':
            return self.send_json({"authenticated": check_admin_auth(self)})

        if self.path == '/api/admin/stats':
            if not check_admin_auth(self):
                return self.send_json({"error": "Unauthorized"}, status=401)

            total_keys = 0
            active_keys = 0
            banned_keys = 0
            heartbeats_count = 0

            if db is not None:
                total_keys = db.keys.count_documents({})
                active_keys = db.keys.count_documents({"status": "active"})
                banned_keys = db.keys.count_documents({"status": "banned"})
                since_yesterday = now_utc() - timedelta(hours=24)
                heartbeats_count = db.heartbeats.count_documents({"timestamp": {"$gte": since_yesterday}})
            else:
                total_keys = len(memory_keys)
                active_keys = sum(1 for k in memory_keys.values() if k.get("status") == "active")
                banned_keys = sum(1 for k in memory_keys.values() if k.get("status") == "banned")
                heartbeats_count = len(memory_heartbeats)

            return self.send_json({
                "total_keys": total_keys,
                "active_keys": active_keys,
                "banned_keys": banned_keys,
                "heartbeats_24h": heartbeats_count,
                "strict_mode": STRICT_MODE,
                "db_connected": is_mongo_alive()
            })

        if self.path == '/api/admin/keys':
            if not check_admin_auth(self):
                return self.send_json({"error": "Unauthorized"}, status=401)

            keys_list = []
            if db is not None:
                cursor = db.keys.find({}, {"_id": 0}).sort("created_at", -1).limit(500)
                keys_list = list(cursor)
            else:
                keys_list = list(memory_keys.values())
                keys_list.sort(key=lambda x: x.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

            return self.send_json(keys_list)

        if self.path == '/api/admin/logs':
            if not check_admin_auth(self):
                return self.send_json({"error": "Unauthorized"}, status=401)

            logs_list = []
            if db is not None:
                cursor = db.heartbeats.find({}, {"_id": 0}).sort("timestamp", -1).limit(100)
                logs_list = list(cursor)
            else:
                logs_list = list(reversed(memory_heartbeats[-100:]))

            return self.send_json(logs_list)

        # Stand Menu APIs
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

        # Redirect /admin to /admin.html
        if self.path == '/admin' or self.path == '/admin/':
            self.send_response(302)
            self.send_header('Location', '/admin.html')
            self.end_headers()
            return

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
        print(f"Admin Panel available at http://localhost:{PORT}/admin.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.server_close()
