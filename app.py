from flask import Flask, render_template, request, jsonify, Response
import os
import sqlite3
import base64
import secrets
from datetime import datetime

app = Flask(__name__)
DB_PATH = "encoder.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS scripts (id INTEGER PRIMARY KEY AUTOINCREMENT, script_id TEXT UNIQUE NOT NULL, code_encrypted TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.commit()
    conn.close()


def generate_script_id():
    return secrets.token_urlsafe(16)


def encrypt_script(code):
    """Encode code thanh Base64."""
    return base64.b64encode(code.encode("utf-8")).decode("utf-8")


def build_lua_loader(encoded):
    """Tao Lua loader decode Base64 - chay duoc tren Delta X."""
    parts = []
    parts.append("local b='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'")
    parts.append("local function d(s)")
    parts.append("s=string.gsub(s,'[^'..b..'=]','')")
    parts.append("return (s:gsub('.',function(x)")
    parts.append("if x=='=' then return '' end")
    parts.append("local r,f='',(b:find(x,1,true)-1)")
    parts.append("for i=6,1,-1 do r=r..(f%2^i-f%2^(i-1)>0 and '1' or '0') end")
    parts.append("return r")
    parts.append("end):gsub('%d%d%d?%d?%d?%d?%d?%d?',function(x)")
    parts.append("if #x~=8 then return '' end")
    parts.append("local c=0")
    parts.append("for i=1,8 do c=c+(x:sub(i,i)=='1' and 2^(8-i) or 0) end")
    parts.append("return string.char(c)")
    parts.append("end))")
    parts.append("end")
    parts.append("local code=d('" + encoded + "')")
    parts.append("local fn=loadstring or load")
    parts.append("fn(code)()")
    return chr(10).join(parts)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/encode", methods=["POST"])
def api_encode():
    try:
        data = request.get_json()
        code = data.get("code", "").strip()

        if not code:
            return jsonify({"ok": False, "error": "Nhap code Lua!"})

        encoded = encrypt_script(code)
        loader = build_lua_loader(encoded)

        init_db()
        script_id = generate_script_id()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO scripts (script_id, code_encrypted, created_at) VALUES (?, ?, ?)",
                     (script_id, encoded, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()

        host = request.host_url.rstrip("/")
        raw_url = host + "/raw/" + script_id

        return jsonify({
            "ok": True,
            "loader": loader,
            "raw_url": raw_url,
            "loadstring_url": 'loadstring(game:HttpGet("' + raw_url + '"))()',
            "original_size": len(code),
            "encoded_size": len(loader)
        })

    except Exception as e:
        return jsonify({"ok": False, "error": "Loi: " + str(e)})


@app.route("/raw/<script_id>")
def raw_script(script_id):
    """Tra ve loader - chi cho executor."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT code_encrypted FROM scripts WHERE script_id = ?", (script_id,)).fetchone()
    conn.close()

    if not row:
        return "Not found", 404

    loader = build_lua_loader(row["code_encrypted"])

    user_agent = request.headers.get("User-Agent", "").lower()
    executor_keywords = [
        "roblox", "delta", "executor", "synapse", "krnl", "fluxus",
        "evon", "codex", "wave", "solara", "xeno", "hydrogen",
        "argon", "rayfield", "httpget", "http_request", "swift"
    ]
    is_executor = any(kw in user_agent for kw in executor_keywords)

    if not is_executor:
        return render_template("protected.html"), 200

    return Response(loader, mimetype="text/plain")


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
