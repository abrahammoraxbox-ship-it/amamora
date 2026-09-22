import json, os, sqlite3, uuid, smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
app=Flask(__name__);app.secret_key=os.environ.get("SECRET_KEY","amamora-desarrollo")
DATA_DIR=Path(__file__).parent/"data";DATABASE=DATA_DIR/"amamora.db"
REGIONES={"Metropolitana":3990,"Valparaíso":4490,"O’Higgins":4490,"Maule":4990,"Ñuble":5490,"Biobío":5490,"La Araucanía":5990,"Los Ríos":6490,"Los Lagos":6490,"Coquimbo":5490,"Atacama":6490,"Antofagasta":6990,"Tarapacá":7490,"Arica y Parinacota":7990,"Aysén":8990,"Magallanes":9990}
def now():return datetime.now(timezone.utc).isoformat()
def db():c=sqlite3.connect(DATABASE);c.row_factory=sqlite3.Row;return c
def init_db():
 DATA_DIR.mkdir(exist_ok=True)
 with db() as c:
  c.executescript("""CREATE TABLE IF NOT EXISTS usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT,nombre TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,rol TEXT NOT NULL DEFAULT 'cliente',creado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS disenos(id TEXT PRIMARY KEY,usuario_id INTEGER NOT NULL,nombre TEXT NOT NULL,config TEXT NOT NULL,creado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pedidos(id TEXT PRIMARY KEY,usuario_id INTEGER,creado TEXT NOT NULL,nombre TEXT NOT NULL,correo TEXT NOT NULL,region TEXT NOT NULL,direccion TEXT NOT NULL,items TEXT NOT NULL,subtotal INTEGER NOT NULL,envio INTEGER NOT NULL,total INTEGER NOT NULL,pago TEXT NOT NULL,estado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventario(id INTEGER PRIMARY KEY AUTOINCREMENT,tipo TEXT NOT NULL,nombre TEXT NOT NULL,stock INTEGER NOT NULL,activo INTEGER NOT NULL DEFAULT 1);""")
  existing={x["name"] for x in c.execute("PRAGMA table_info(pedidos)").fetchall()}
  for name,definition in {"usuario_id":"INTEGER","direccion":"TEXT NOT NULL DEFAULT ''","subtotal":"INTEGER NOT NULL DEFAULT 0","envio":"INTEGER NOT NULL DEFAULT 0","pago":"TEXT NOT NULL DEFAULT 'Por coordinar'"}.items():
   if name not in existing:c.execute(f"ALTER TABLE pedidos ADD COLUMN {name} {definition}")
  if not c.execute("SELECT 1 FROM inventario").fetchone():c.executemany("INSERT INTO inventario(tipo,nombre,stock) VALUES(?,?,?)",[("piedra","Amatista",25),("piedra","Cuarzo rosa",20),("piedra","Esmeralda",12),("piedra","Lapislázuli",16),("metal","Oro",10),("metal","Plata",20),("metal","Cobre",30)])
  email=os.environ.get("ADMIN_EMAIL");password=os.environ.get("ADMIN_PASSWORD")
  if email and password and not c.execute("SELECT 1 FROM usuarios WHERE email=?",(email.lower(),)).fetchone():c.execute("INSERT INTO usuarios(nombre,email,password,rol,creado) VALUES(?,?,?,?,?)",("Administrador",email.lower(),generate_password_hash(password),"admin",now()))
def login_required(fn):
 @wraps(fn)
 def inner(*a,**k):return redirect(url_for("acceso",next=request.path)) if not session.get("user_id") else fn(*a,**k)
 return inner
def admin_required(fn):
 @wraps(fn)
 def inner(*a,**k):return ("Acceso denegado",403) if session.get("rol")!="admin" else fn(*a,**k)
 return inner
def send_confirmation(to,oid,total):
 if not os.environ.get("SMTP_HOST"):return
 m=EmailMessage();m["Subject"]=f"Pedido {oid} recibido | Amamora";m["From"]=os.environ["SMTP_FROM"];m["To"]=to;m.set_content(f"Recibimos tu solicitud {oid}. Total: {total} CLP.")
 with smtplib.SMTP(os.environ["SMTP_HOST"],int(os.environ.get("SMTP_PORT",587))) as s:s.starttls();s.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"]);s.send_message(m)
@app.context_processor
def globals():return {"usuario_nombre":session.get("nombre"),"es_admin":session.get("rol")=="admin"}
@app.get("/")
def inicio():return render_template("index.html")
@app.get("/categorias")
def categorias():return render_template("categorias.html")
@app.get("/disenador")
@app.get("/anillos")
def disenador():return render_template("disenador.html")
@app.get("/collares")
def collares():return render_template("disenador.html",categoria_inicial="Collar")
@app.get("/carrito")
def carrito():return render_template("carrito.html",regiones=REGIONES)
@app.get("/realidad-aumentada")
def realidad_aumentada():return render_template("ar.html")
@app.route("/acceso",methods=["GET","POST"])
def acceso():
 error=None
 if request.method=="POST":
  with db() as c:u=c.execute("SELECT * FROM usuarios WHERE email=?",(request.form["email"].lower().strip(),)).fetchone()
  if u and check_password_hash(u["password"],request.form["password"]):session.update(user_id=u["id"],nombre=u["nombre"],rol=u["rol"]);return redirect(request.args.get("next") or url_for("perfil"))
  error="Correo o contraseña incorrectos."
 return render_template("auth.html",modo="acceso",error=error)
@app.route("/registro",methods=["GET","POST"])
def registro():
 error=None
 if request.method=="POST":
  try:
   with db() as c:c.execute("INSERT INTO usuarios(nombre,email,password,creado) VALUES(?,?,?,?)",(request.form["nombre"].strip(),request.form["email"].lower().strip(),generate_password_hash(request.form["password"]),now()))
   return redirect(url_for("acceso"))
  except sqlite3.IntegrityError:error="Este correo ya está registrado."
 return render_template("auth.html",modo="registro",error=error)
@app.get("/salir")
def salir():session.clear();return redirect(url_for("inicio"))
@app.get("/perfil")
@login_required
def perfil():
 with db() as c:designs=c.execute("SELECT * FROM disenos WHERE usuario_id=? ORDER BY creado DESC",(session["user_id"],)).fetchall();orders=c.execute("SELECT * FROM pedidos WHERE usuario_id=? ORDER BY creado DESC",(session["user_id"],)).fetchall()
 return render_template("perfil.html",designs=designs,orders=orders)
@app.get("/admin")
@admin_required
def admin():
 with db() as c:orders=c.execute("SELECT * FROM pedidos ORDER BY creado DESC").fetchall();stock=c.execute("SELECT * FROM inventario ORDER BY tipo,nombre").fetchall()
 return render_template("admin.html",orders=orders,stock=stock)
@app.post("/admin/pedido/<oid>")
@admin_required
def estado_pedido(oid):
 with db() as c:c.execute("UPDATE pedidos SET estado=? WHERE id=?",(request.form["estado"],oid))
 return redirect(url_for("admin"))
@app.post("/admin/stock/<int:item_id>")
@admin_required
def actualizar_stock(item_id):
 with db() as c:c.execute("UPDATE inventario SET stock=? WHERE id=?",(max(0,int(request.form["stock"])),item_id))
 return redirect(url_for("admin"))
@app.post("/api/disenos")
@login_required
def guardar_diseno():
 data=request.get_json() or {};did=f"DIS-{uuid.uuid4().hex[:8].upper()}"
 with db() as c:c.execute("INSERT INTO disenos VALUES(?,?,?,?,?)",(did,session["user_id"],data.get("nombre","Mi joya"),json.dumps(data.get("config",{}),ensure_ascii=False),now()))
 return jsonify(id=did),201
@app.get("/api/inventario")
def inventario():
 with db() as c:rows=c.execute("SELECT tipo,nombre,stock FROM inventario WHERE activo=1").fetchall()
 return jsonify([dict(x) for x in rows])
@app.post("/api/pedidos")
def crear_pedido():
 data=request.get_json(silent=True) or {};customer=data.get("customer",{});items=data.get("items",[])
 if not items or not all(customer.get(k) for k in ("nombre","correo","region","direccion")):return jsonify(error="Faltan datos del pedido."),400
 subtotal=sum(int(x.get("price",0)) for x in items);shipping=REGIONES.get(customer["region"])
 if subtotal<=0 or shipping is None:return jsonify(error="El pedido no es válido."),400
 oid=f"AMA-{uuid.uuid4().hex[:8].upper()}";total=subtotal+shipping
 with db() as c:c.execute("INSERT INTO pedidos(id,usuario_id,creado,nombre,correo,region,direccion,items,subtotal,envio,total,pago,estado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(oid,session.get("user_id"),now(),customer["nombre"].strip(),customer["correo"].strip(),customer["region"],customer["direccion"].strip(),json.dumps(items,ensure_ascii=False),subtotal,shipping,total,data.get("payment","Por coordinar"),"solicitado"))
 try:send_confirmation(customer["correo"],oid,total)
 except Exception:app.logger.exception("Correo no enviado")
 return jsonify(id=oid,total=total,estado="solicitado"),201
@app.get("/salud")
def salud():return jsonify(estado="ok")
init_db()
if __name__=="__main__":app.run(debug=True)
