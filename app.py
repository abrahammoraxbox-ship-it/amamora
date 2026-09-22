import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / "data"
DATABASE = DATA_DIR / "amamora.db"

def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS pedidos (
            id TEXT PRIMARY KEY, creado TEXT NOT NULL, nombre TEXT NOT NULL,
            correo TEXT NOT NULL, region TEXT NOT NULL, items TEXT NOT NULL,
            total INTEGER NOT NULL, estado TEXT NOT NULL
        )""")

@app.route("/")
def inicio(): return render_template("index.html")

@app.route("/categorias")
def categorias(): return render_template("categorias.html")

@app.route("/disenador")
@app.route("/anillos")
def disenador(): return render_template("disenador.html")

@app.route("/collares")
def collares(): return render_template("disenador.html", categoria_inicial="Collar")

@app.route("/carrito")
def carrito(): return render_template("carrito.html")

@app.post("/api/pedidos")
def crear_pedido():
    data = request.get_json(silent=True) or {}
    customer = data.get("customer", {})
    items = data.get("items", [])
    if not items or not all(customer.get(k) for k in ("nombre", "correo", "region")):
        return jsonify(error="Faltan datos del pedido."), 400
    total = sum(int(item.get("price", 0)) for item in items)
    if total <= 0:
        return jsonify(error="El total del pedido no es válido."), 400
    order_id = f"AMA-{uuid.uuid4().hex[:8].upper()}"
    created = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DATABASE) as db:
        db.execute("INSERT INTO pedidos VALUES (?,?,?,?,?,?,?,?)", (
            order_id, created, customer["nombre"].strip(), customer["correo"].strip(),
            customer["region"], json.dumps(items, ensure_ascii=False), total, "solicitado"
        ))
    return jsonify(id=order_id, total=total, estado="solicitado"), 201

@app.get("/salud")
def salud(): return jsonify(estado="ok")

init_db()

if __name__ == "__main__": app.run(debug=True)
