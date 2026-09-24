import json, os, sqlite3, uuid, smtplib, secrets, re, time
from io import BytesIO
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
app=Flask(__name__)
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
app.secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=12*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=os.environ.get("RENDER")=="true",PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
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
CREATE TABLE IF NOT EXISTS inventario(id INTEGER PRIMARY KEY AUTOINCREMENT,tipo TEXT NOT NULL,nombre TEXT NOT NULL,stock INTEGER NOT NULL,activo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS medios(id TEXT PRIMARY KEY,nombre TEXT NOT NULL,mime TEXT NOT NULL,datos BLOB NOT NULL,creado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS catalogo(id INTEGER PRIMARY KEY AUTOINCREMENT,tipo TEXT NOT NULL,nombre TEXT NOT NULL,precio INTEGER NOT NULL DEFAULT 0,color TEXT NOT NULL DEFAULT '',opciones TEXT NOT NULL DEFAULT '[]',descripcion TEXT NOT NULL DEFAULT '',stock INTEGER NOT NULL DEFAULT 0,imagen_id TEXT,modelo_id TEXT,activo INTEGER NOT NULL DEFAULT 1,orden INTEGER NOT NULL DEFAULT 0,creado TEXT NOT NULL,actualizado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY AUTOINCREMENT,usuario_id INTEGER,accion TEXT NOT NULL,detalle TEXT NOT NULL,creado TEXT NOT NULL);""")
  existing={x["name"] for x in c.execute("PRAGMA table_info(pedidos)").fetchall()}
  for name,definition in {"usuario_id":"INTEGER","direccion":"TEXT NOT NULL DEFAULT ''","subtotal":"INTEGER NOT NULL DEFAULT 0","envio":"INTEGER NOT NULL DEFAULT 0","pago":"TEXT NOT NULL DEFAULT 'Por coordinar'"}.items():
   if name not in existing:c.execute(f"ALTER TABLE pedidos ADD COLUMN {name} {definition}")
  if not c.execute("SELECT 1 FROM inventario").fetchone():c.executemany("INSERT INTO inventario(tipo,nombre,stock) VALUES(?,?,?)",[("piedra","Amatista",25),("piedra","Cuarzo rosa",20),("piedra","Esmeralda",12),("piedra","Lapislázuli",16),("metal","Oro",10),("metal","Plata",20),("metal","Cobre",30)])
  catalog=[("piedra",x,15) for x in ("Ágata","Ónix","Ojo de tigre","Cuarzo","Turquesa","Jade","Granate","Piedra luna","Aventurina","Perla")]+[("metal",x,20) for x in ("Oro golfi","Plata 925","Acero inoxidable")]
  for kind,name,stock in catalog:
   if not c.execute("SELECT 1 FROM inventario WHERE tipo=? AND nombre=?",(kind,name)).fetchone():c.execute("INSERT INTO inventario(tipo,nombre,stock) VALUES(?,?,?)",(kind,name,stock))
  if not c.execute("SELECT 1 FROM catalogo").fetchone():
   rows=[]
   rows += [("categoria",n,p,"","[]","",0,None,None,1,i,now(),now()) for i,(n,p) in enumerate(PRECIOS.items())]
   rows += [("alambrismo",n,p,"","[]","",0,None,None,1,i,now(),now()) for i,(n,p) in enumerate(EXTRAS_ALAMBRE.items())]
   rows += [("material",n,p,{"Oro golfi":"#d8ad55","Plata 925":"#d7dce0","Acero inoxidable":"#aeb7bd","Cobre":"#b96f4a"}[n],"[]","",0,None,None,1,i,now(),now()) for i,(n,p) in enumerate(EXTRAS_METAL.items())]
   variants={"Ágata":[["Azul","#258eb5"],["Verde","#3d9b6b"],["Rosada","#d9899f"]],"Ónix":[["Negro","#111216"],["Verde","#214f3f"]],"Ojo de tigre":[["Dorado","#a56820"],["Rojo","#7e2f21"]],"Amatista":[["Violeta","#8550a7"],["Lavanda","#b48acc"]],"Cuarzo":[["Rosa","#e8a6b4"],["Cristal","#d9edf0"]]}
   rows += [("piedra",n,0,(variants.get(n)or[["Natural","#8b7564"]])[0][1],json.dumps(variants.get(n)or[["Natural","#8b7564"]],ensure_ascii=False),"",15,None,None,1,i,now(),now()) for i,n in enumerate(sorted(PIEDRAS))]
   rows += [("forma",n,0,"","[]","",0,None,None,1,i,now(),now()) for i,n in enumerate(sorted(FORMAS))]
   c.executemany("INSERT INTO catalogo(tipo,nombre,precio,color,opciones,descripcion,stock,imagen_id,modelo_id,activo,orden,creado,actualizado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",rows)
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
def staff_required(fn):
 @wraps(fn)
 def inner(*a,**k):return ("Acceso denegado",403) if session.get("rol") not in {"admin","trabajador"} else fn(*a,**k)
 return inner
def audit(action,detail):
 with db() as c:c.execute("INSERT INTO auditoria(usuario_id,accion,detalle,creado) VALUES(?,?,?,?)",(session.get("user_id"),action,str(detail)[:500],now()))
def save_media(upload,kind):
 if not upload or not upload.filename:return None
 data=upload.read(8*1024*1024+1);name=secure_filename(upload.filename)[:120]
 if not name or len(data)>8*1024*1024:raise ValueError("El archivo supera el límite de 8 MB.")
 if kind=="imagen":
  signatures=((b"\x89PNG\r\n\x1a\n","image/png"),(b"\xff\xd8\xff","image/jpeg"),(b"RIFF","image/webp"));mime=next((m for sig,m in signatures if data.startswith(sig)),None)
  if mime=="image/webp" and data[8:12]!=b"WEBP":mime=None
 else:mime="model/gltf-binary" if data.startswith(b"glTF") else None
 if not mime:raise ValueError("Formato no permitido. Usa JPG, PNG, WEBP o GLB según el campo.")
 mid=uuid.uuid4().hex
 with db() as c:c.execute("INSERT INTO medios VALUES(?,?,?,?,?)",(mid,name,mime,data,now()))
 return mid
def send_confirmation(to,oid,total):
 if not os.environ.get("SMTP_HOST"):return
 m=EmailMessage();m["Subject"]=f"Pedido {oid} recibido | Amamora";m["From"]=os.environ["SMTP_FROM"];m["To"]=to;m.set_content(f"Recibimos tu solicitud {oid}. Total: {total} CLP.")
 with smtplib.SMTP(os.environ["SMTP_HOST"],int(os.environ.get("SMTP_PORT",587))) as s:s.starttls();s.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"]);s.send_message(m)
@app.context_processor
def globals():return {"usuario_nombre":session.get("nombre"),"es_admin":session.get("rol")=="admin","es_trabajador":session.get("rol") in {"admin","trabajador"},"csrf_token":csrf_token}
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
 with db() as c:orders=c.execute("SELECT * FROM pedidos ORDER BY creado DESC").fetchall();stock=c.execute("SELECT * FROM inventario ORDER BY tipo,nombre").fetchall();users=c.execute("SELECT id,nombre,email,rol,creado FROM usuarios ORDER BY creado DESC").fetchall();logs=c.execute("SELECT a.*,u.nombre FROM auditoria a LEFT JOIN usuarios u ON u.id=a.usuario_id ORDER BY a.id DESC LIMIT 50").fetchall()
 return render_template("admin.html",orders=orders,stock=stock,users=users,logs=logs)
@app.post("/admin/usuario/<int:user_id>/rol")
@admin_required
def cambiar_rol(user_id):
 role=request.form.get("rol","")
 if role not in {"cliente","trabajador","admin"}:return ("Rol inválido",400)
 if user_id==session.get("user_id") and role!="admin":return ("No puedes quitarte tu propio acceso administrativo",400)
 with db() as c:c.execute("UPDATE usuarios SET rol=? WHERE id=?",(role,user_id))
 audit("usuario.rol",f"usuario={user_id} rol={role}");return redirect(url_for("admin"))
@app.get("/gestion")
@staff_required
def gestion():
 with db() as c:items=c.execute("SELECT * FROM catalogo ORDER BY tipo,orden,nombre").fetchall()
 return render_template("gestion.html",items=items)
@app.post("/gestion/catalogo")
@staff_required
def guardar_catalogo():
 try:
  item_id=int(request.form.get("item_id") or 0);tipo=request.form.get("tipo","");nombre=request.form.get("nombre","").strip();precio=int(request.form.get("precio") or 0);stock=int(request.form.get("stock") or 0);orden=int(request.form.get("orden") or 0);color=request.form.get("color","").strip();descripcion=request.form.get("descripcion","").strip();opciones=[]
  if tipo not in {"categoria","piedra","material","alambrismo","forma"} or not 2<=len(nombre)<=80 or not -1000000<=precio<=10000000 or not 0<=stock<=100000:raise ValueError("Revisa los campos del elemento.")
  for line in request.form.get("opciones","").splitlines():
   if not line.strip():continue
   parts=[x.strip() for x in line.split(":",1)];opciones.append([parts[0][:40],parts[1] if len(parts)>1 and re.fullmatch(r"#[0-9a-fA-F]{6}",parts[1]) else color or "#8b7564"])
  image_id=save_media(request.files.get("imagen"),"imagen");model_id=save_media(request.files.get("modelo"),"modelo")
  with db() as c:
   if item_id:
    old=c.execute("SELECT imagen_id,modelo_id FROM catalogo WHERE id=?",(item_id,)).fetchone()
    if not old:raise ValueError("El elemento no existe.")
    c.execute("UPDATE catalogo SET tipo=?,nombre=?,precio=?,color=?,opciones=?,descripcion=?,stock=?,imagen_id=?,modelo_id=?,orden=?,actualizado=? WHERE id=?",(tipo,nombre,precio,color,json.dumps(opciones,ensure_ascii=False),descripcion[:500],stock,image_id or old["imagen_id"],model_id or old["modelo_id"],orden,now(),item_id))
   else:c.execute("INSERT INTO catalogo(tipo,nombre,precio,color,opciones,descripcion,stock,imagen_id,modelo_id,orden,creado,actualizado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(tipo,nombre,precio,color,json.dumps(opciones,ensure_ascii=False),descripcion[:500],stock,image_id,model_id,orden,now(),now()))
  audit("catalogo.guardar",f"id={item_id or 'nuevo'} tipo={tipo} nombre={nombre}")
 except (ValueError,TypeError) as e:return render_template("gestion.html",items=[],error=str(e)),400
 return redirect(url_for("gestion"))
@app.post("/gestion/catalogo/<int:item_id>/toggle")
@staff_required
def toggle_catalogo(item_id):
 with db() as c:c.execute("UPDATE catalogo SET activo=CASE activo WHEN 1 THEN 0 ELSE 1 END,actualizado=? WHERE id=?",(now(),item_id))
 audit("catalogo.estado",f"id={item_id}");return redirect(url_for("gestion"))
@app.get("/media/<media_id>/<path:filename>")
def media(media_id,filename):
 with db() as c:item=c.execute("SELECT * FROM medios WHERE id=?",(media_id,)).fetchone()
 if not item:return ("Archivo no encontrado",404)
 return send_file(BytesIO(item["datos"]),mimetype=item["mime"],download_name=item["nombre"],max_age=86400,conditional=True)
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
@app.get("/api/catalogo")
def api_catalogo():
 with db() as c:rows=c.execute("SELECT id,tipo,nombre,precio,color,opciones,descripcion,stock,imagen_id,modelo_id,orden FROM catalogo WHERE activo=1 ORDER BY tipo,orden,nombre").fetchall()
 result=[]
 for row in rows:
  item=dict(row);item["opciones"]=json.loads(item["opciones"] or "[]");image_id=item.pop("imagen_id");model_id=item.pop("modelo_id");item["imagen_url"]=url_for("media",media_id=image_id,filename="imagen") if image_id else None;item["modelo_url"]=url_for("media",media_id=model_id,filename="modelo.glb") if model_id else None;result.append(item)
 return jsonify(result)
@app.post("/api/pedidos")
def crear_pedido():
 data=request.get_json(silent=True) or {};customer=data.get("customer",{});items=data.get("items",[])
 if limited("orders",5,600):return jsonify(error="Demasiados intentos. Espera unos minutos."),429
 if not isinstance(customer,dict) or not isinstance(items,list) or not 1<=len(items)<=20 or not all(customer.get(k) for k in ("nombre","correo","region","direccion")):return jsonify(error="Faltan datos del pedido."),400
 nombre=str(customer["nombre"]).strip();correo=str(customer["correo"]).lower().strip();direccion=str(customer["direccion"]).strip();shipping=REGIONES.get(customer["region"]);payment=data.get("payment")
 if not 2<=len(nombre)<=80 or not EMAIL_RE.fullmatch(correo) or not 5<=len(direccion)<=200 or shipping is None or payment not in PAGOS:return jsonify(error="Los datos del pedido no son válidos."),400
 with db() as c:catalog_rows=c.execute("SELECT tipo,nombre,precio FROM catalogo WHERE activo=1").fetchall()
 catalog={kind:{r["nombre"]:r["precio"] for r in catalog_rows if r["tipo"]==kind} for kind in ("categoria","alambrismo","material","piedra","forma")}
 validated=[];subtotal=0
 for raw in items:
  if not isinstance(raw,dict):return jsonify(error="Hay una joya inválida en el carrito."),400
  category,wire,metal,stone,shape=map(lambda k:str(raw.get(k,"")),("category","wire","metal","stone","shape"))
  try:size=int(raw.get("size",0))
  except (TypeError,ValueError):return jsonify(error="El tamaño de una joya no es válido."),400
  if category not in catalog["categoria"] or wire not in catalog["alambrismo"] or metal not in catalog["material"] or stone not in catalog["piedra"] or shape not in catalog["forma"] or not 4<=size<=18:return jsonify(error="Hay una configuración de joya inválida."),400
  price=catalog["categoria"][category]+catalog["alambrismo"][wire]+catalog["material"][metal]+max(0,size-10)*1200;subtotal+=price
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
