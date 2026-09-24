import json, os, sqlite3, uuid, smtplib, secrets, re, time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
app=Flask(__name__)
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
app.secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=64*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=os.environ.get("RENDER")=="true",PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
DATA_DIR=Path(__file__).parent/"data";DATABASE=DATA_DIR/"amamora.db"
REGIONES={"Metropolitana":3990,"Valparaíso":4490,"O’Higgins":4490,"Maule":4990,"Ñuble":5490,"Biobío":5490,"La Araucanía":5990,"Los Ríos":6490,"Los Lagos":6490,"Coquimbo":5490,"Atacama":6490,"Antofagasta":6990,"Tarapacá":7490,"Arica y Parinacota":7990,"Aysén":8990,"Magallanes":9990}
PRECIOS={"Anillo":39990,"Pulsera":45990,"Collar":52990,"Aretes":42990};EXTRAS_ALAMBRE={"Abrazo clásico":0,"Espiral solar":4000,"Trenza infinita":7000,"Nido floral":9000,"Órbita doble":6500,"Lágrima real":8000};EXTRAS_METAL={"Oro golfi":7000,"Plata 925":10000,"Acero inoxidable":0,"Cobre":-3000};PIEDRAS={"Ágata","Ónix","Ojo de tigre","Amatista","Cuarzo","Turquesa","Jade","Lapislázuli","Granate","Piedra luna","Aventurina","Perla"};FORMAS={"Redonda","Ovalada","Gota","Corazón"};PAGOS={"Mercado Pago (próximamente)","Transbank Webpay (próximamente)","Transferencia bancaria"}
EMAIL_RE=re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$")
ATTEMPTS=defaultdict(deque)
def now():return datetime.now(timezone.utc).isoformat()
def db():c=sqlite3.connect(DATABASE,timeout=10);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
def limited(bucket,maximum,window=60):
 key=f"{bucket}:{request.remote_addr or 'unknown'}";cutoff=time.monotonic()-window;q=ATTEMPTS[key]
 while q and q[0]<cutoff:q.popleft()
 if len(q)>=maximum:return True
 q.append(time.monotonic());return False
def csrf_token():
 if "csrf_token" not in session:session["csrf_token"]=secrets.token_urlsafe(32)
 return session["csrf_token"]
@app.before_request
def csrf_protect():
 if request.method in {"POST","PUT","PATCH","DELETE"}:
  supplied=request.form.get("csrf_token") or request.headers.get("X-CSRF-Token","")
  if not secrets.compare_digest(str(supplied),str(session.get("csrf_token",""))):return jsonify(error="Solicitud de seguridad inválida. Actualiza la página."),403
@app.after_request
def security_headers(response):
 response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://cdn.jsdelivr.net https://storage.googleapis.com; worker-src 'self' blob:; media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
 response.headers["Referrer-Policy"]="strict-origin-when-cross-origin";response.headers["X-Content-Type-Options"]="nosniff";response.headers["X-Frame-Options"]="DENY";response.headers["Permissions-Policy"]="camera=(self), microphone=(), geolocation=(), payment=()"
 if request.is_secure:response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
 response.headers["Cache-Control"]="no-store" if request.path.startswith(("/admin","/perfil","/api")) else "public, max-age=300"
 return response
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
  catalog=[("piedra",x,15) for x in ("Ágata","Ónix","Ojo de tigre","Cuarzo","Turquesa","Jade","Granate","Piedra luna","Aventurina","Perla")]+[("metal",x,20) for x in ("Oro golfi","Plata 925","Acero inoxidable")]
  for kind,name,stock in catalog:
   if not c.execute("SELECT 1 FROM inventario WHERE tipo=? AND nombre=?",(kind,name)).fetchone():c.execute("INSERT INTO inventario(tipo,nombre,stock) VALUES(?,?,?)",(kind,name,stock))
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
def globals():return {"usuario_nombre":session.get("nombre"),"es_admin":session.get("rol")=="admin","csrf_token":csrf_token}
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
  if limited("login",5,300):return render_template("auth.html",modo="acceso",error="Demasiados intentos. Espera 5 minutos."),429
  with db() as c:u=c.execute("SELECT * FROM usuarios WHERE email=?",(request.form.get("email","").lower().strip()[:254],)).fetchone()
  if u and check_password_hash(u["password"],request.form.get("password","")):session.clear();session.permanent=True;session.update(user_id=u["id"],nombre=u["nombre"],rol=u["rol"]);target=request.args.get("next","");return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("perfil"))
  error="Correo o contraseña incorrectos."
 return render_template("auth.html",modo="acceso",error=error)
@app.route("/registro",methods=["GET","POST"])
def registro():
 error=None
 if request.method=="POST":
  if limited("register",4,600):return render_template("auth.html",modo="registro",error="Espera unos minutos antes de volver a intentarlo."),429
  nombre=request.form.get("nombre","").strip();email=request.form.get("email","").lower().strip();password=request.form.get("password","")
  if not 2<=len(nombre)<=80 or not EMAIL_RE.fullmatch(email) or len(password)<10:return render_template("auth.html",modo="registro",error="Revisa el nombre, correo y usa una contraseña de al menos 10 caracteres."),400
  try:
   with db() as c:c.execute("INSERT INTO usuarios(nombre,email,password,creado) VALUES(?,?,?,?)",(nombre,email,generate_password_hash(password),now()))
   return redirect(url_for("acceso"))
  except sqlite3.IntegrityError:error="Este correo ya está registrado."
 return render_template("auth.html",modo="registro",error=error)
@app.post("/salir")
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
 estado=request.form.get("estado","")
 if estado not in {"solicitado","confirmado","fabricando","enviado","entregado","cancelado"}:return ("Estado inválido",400)
 with db() as c:c.execute("UPDATE pedidos SET estado=? WHERE id=?",(estado,oid))
 return redirect(url_for("admin"))
@app.post("/admin/stock/<int:item_id>")
@admin_required
def actualizar_stock(item_id):
 try:stock=min(100000,max(0,int(request.form.get("stock",0))))
 except ValueError:return ("Stock inválido",400)
 with db() as c:c.execute("UPDATE inventario SET stock=? WHERE id=?",(stock,item_id))
 return redirect(url_for("admin"))
@app.post("/api/disenos")
@login_required
def guardar_diseno():
 data=request.get_json() or {};did=f"DIS-{uuid.uuid4().hex[:8].upper()}"
 nombre=str(data.get("nombre","Mi joya")).strip()[:80];config=data.get("config",{})
 if not isinstance(config,dict) or not nombre:return jsonify(error="Diseño inválido."),400
 with db() as c:c.execute("INSERT INTO disenos VALUES(?,?,?,?,?)",(did,session["user_id"],nombre,json.dumps(config,ensure_ascii=False)[:10000],now()))
 return jsonify(id=did),201
@app.get("/api/inventario")
def inventario():
 with db() as c:rows=c.execute("SELECT tipo,nombre,stock FROM inventario WHERE activo=1").fetchall()
 return jsonify([dict(x) for x in rows])
@app.post("/api/pedidos")
def crear_pedido():
 data=request.get_json(silent=True) or {};customer=data.get("customer",{});items=data.get("items",[])
 if limited("orders",5,600):return jsonify(error="Demasiados intentos. Espera unos minutos."),429
 if not isinstance(customer,dict) or not isinstance(items,list) or not 1<=len(items)<=20 or not all(customer.get(k) for k in ("nombre","correo","region","direccion")):return jsonify(error="Faltan datos del pedido."),400
 nombre=str(customer["nombre"]).strip();correo=str(customer["correo"]).lower().strip();direccion=str(customer["direccion"]).strip();shipping=REGIONES.get(customer["region"]);payment=data.get("payment")
 if not 2<=len(nombre)<=80 or not EMAIL_RE.fullmatch(correo) or not 5<=len(direccion)<=200 or shipping is None or payment not in PAGOS:return jsonify(error="Los datos del pedido no son válidos."),400
 validated=[];subtotal=0
 for raw in items:
  if not isinstance(raw,dict):return jsonify(error="Hay una joya inválida en el carrito."),400
  category,wire,metal,stone,shape=map(lambda k:str(raw.get(k,"")),("category","wire","metal","stone","shape"))
  try:size=int(raw.get("size",0))
  except (TypeError,ValueError):return jsonify(error="El tamaño de una joya no es válido."),400
  if category not in PRECIOS or wire not in EXTRAS_ALAMBRE or metal not in EXTRAS_METAL or stone not in PIEDRAS or shape not in FORMAS or not 4<=size<=18:return jsonify(error="Hay una configuración de joya inválida."),400
  price=PRECIOS[category]+EXTRAS_ALAMBRE[wire]+EXTRAS_METAL[metal]+max(0,size-10)*1200;subtotal+=price
  validated.append({k:str(raw.get(k,""))[:80] for k in ("category","wire","metal","stone","stoneVariant","stoneColor","shape","jewelSize")}|{"size":size,"price":price})
 oid=f"AMA-{uuid.uuid4().hex[:8].upper()}";total=subtotal+shipping
 with db() as c:c.execute("INSERT INTO pedidos(id,usuario_id,creado,nombre,correo,region,direccion,items,subtotal,envio,total,pago,estado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(oid,session.get("user_id"),now(),nombre,correo,customer["region"],direccion,json.dumps(validated,ensure_ascii=False),subtotal,shipping,total,payment,"solicitado"))
 try:send_confirmation(customer["correo"],oid,total)
 except Exception:app.logger.exception("Correo no enviado")
 return jsonify(id=oid,total=total,estado="solicitado"),201
@app.get("/salud")
def salud():return jsonify(estado="ok")
init_db()
if __name__=="__main__":app.run(debug=True)
