import json, os, sqlite3, uuid, smtplib, secrets, re, time, hashlib
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
GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID","")
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
 response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://cdn.jsdelivr.net https://accounts.google.com; style-src 'self' 'unsafe-inline' https://accounts.google.com; img-src 'self' data: https://lh3.googleusercontent.com; connect-src 'self' https://cdn.jsdelivr.net https://storage.googleapis.com https://accounts.google.com; frame-src https://accounts.google.com; worker-src 'self' blob:; media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
 response.headers["Referrer-Policy"]="strict-origin-when-cross-origin";response.headers["X-Content-Type-Options"]="nosniff";response.headers["X-Frame-Options"]="DENY";response.headers["Permissions-Policy"]="camera=(self), microphone=(), geolocation=(), payment=()"
 if request.is_secure:response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
 response.headers["Cache-Control"]="no-store" if request.path.startswith(("/admin","/perfil","/equipo","/gestion","/acceso","/registro","/recuperar","/restablecer","/verificar-correo")) else "public, max-age=300"
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
CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY AUTOINCREMENT,usuario_id INTEGER,accion TEXT NOT NULL,detalle TEXT NOT NULL,creado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tokens_cuenta(id INTEGER PRIMARY KEY AUTOINCREMENT,usuario_id INTEGER NOT NULL,tipo TEXT NOT NULL,token_hash TEXT UNIQUE NOT NULL,expira INTEGER NOT NULL,usado INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS invitaciones(id INTEGER PRIMARY KEY AUTOINCREMENT,etiqueta TEXT NOT NULL,codigo_hash TEXT UNIQUE NOT NULL,usos INTEGER NOT NULL DEFAULT 0,max_usos INTEGER NOT NULL DEFAULT 1,expira INTEGER NOT NULL,activo INTEGER NOT NULL DEFAULT 1,creado_por INTEGER,creado TEXT NOT NULL);""")
  user_columns={x["name"] for x in c.execute("PRAGMA table_info(usuarios)").fetchall()}
  if "verificado" not in user_columns:c.execute("ALTER TABLE usuarios ADD COLUMN verificado INTEGER NOT NULL DEFAULT 1")
  if "google_sub" not in user_columns:c.execute("ALTER TABLE usuarios ADD COLUMN google_sub TEXT")
  existing={x["name"] for x in c.execute("PRAGMA table_info(pedidos)").fetchall()}
  for name,definition in {"usuario_id":"INTEGER","direccion":"TEXT NOT NULL DEFAULT ''","subtotal":"INTEGER NOT NULL DEFAULT 0","envio":"INTEGER NOT NULL DEFAULT 0","pago":"TEXT NOT NULL DEFAULT 'Por coordinar'"}.items():
   if name not in existing:c.execute(f"ALTER TABLE pedidos ADD COLUMN {name} {definition}")
  existing={x["name"] for x in c.execute("PRAGMA table_info(pedidos)").fetchall()}
  for name,definition in {"neto_estimado":"INTEGER NOT NULL DEFAULT 0","iva_estimado":"INTEGER NOT NULL DEFAULT 0"}.items():
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
def hash_token(value):return hashlib.sha256(value.encode("utf-8")).hexdigest()
def send_mail(to,subject,body):
 if not os.environ.get("SMTP_HOST") or not os.environ.get("SMTP_FROM"):return False
 m=EmailMessage();m["Subject"]=subject;m["From"]=os.environ["SMTP_FROM"];m["To"]=to;m.set_content(body)
 try:
  with smtplib.SMTP(os.environ["SMTP_HOST"],int(os.environ.get("SMTP_PORT",587)),timeout=15) as s:
   if os.environ.get("SMTP_TLS","true").lower()!="false":s.starttls()
   if os.environ.get("SMTP_USER"):s.login(os.environ["SMTP_USER"],os.environ.get("SMTP_PASSWORD",""))
   s.send_message(m)
  return True
 except (OSError,smtplib.SMTPException):return False
def issue_token(user_id,kind,ttl):
 raw=secrets.token_urlsafe(32);expires=int(time.time())+ttl
 with db() as c:
  c.execute("UPDATE tokens_cuenta SET usado=1 WHERE usuario_id=? AND tipo=? AND usado=0",(user_id,kind))
  c.execute("INSERT INTO tokens_cuenta(usuario_id,tipo,token_hash,expira) VALUES(?,?,?,?)",(user_id,kind,hash_token(raw),expires))
 return raw
def account_redirect(role):return url_for("admin" if role=="admin" else "gestion" if role=="trabajador" else "perfil")
def money(value):return f"${value:,.0f}".replace(",",".")
def order_lines(items):
 lines=[]
 for index,item in enumerate(items,1):
  details=" · ".join(x for x in (item.get("stone"),item.get("stoneVariant"),item.get("metal"),item.get("wire"),item.get("jewelSize")) if x)
  lines.append(f"{index}. {item.get('category','Joya personalizada')} — {details}\n   {money(item.get('price',0))} CLP")
 return "\n".join(lines)
def send_confirmation(to,nombre,oid,items,subtotal,shipping,total,payment):
 body=f"""Hola {nombre},

Recibimos tu solicitud de pedido en Amamora.

Pedido: {oid}
{order_lines(items)}

Subtotal: {money(subtotal)} CLP
Envío: {money(shipping)} CLP
Total informado (IVA incluido): {money(total)} CLP
Medio de pago: {payment}

Te contactaremos para confirmar disponibilidad, fabricación y pago antes de comenzar.
Este mensaje confirma la solicitud y no reemplaza la boleta o factura electrónica correspondiente.

Amamora · Joyería hecha a mano en Chile
"""
 return send_mail(to,f"Recibimos tu pedido {oid} | Amamora",body)
def notify_store(nombre,correo,region,address,oid,items,subtotal,shipping,total,payment,net,vat):
 target=os.environ.get("STORE_EMAIL") or os.environ.get("SMTP_FROM")
 if not target:return False
 body=f"""NUEVO PEDIDO AMAMORA

Pedido: {oid}
Cliente: {nombre}
Correo: {correo}
Entrega: {address}, {region}

{order_lines(items)}

Subtotal: {money(subtotal)} CLP
Envío: {money(shipping)} CLP
Total: {money(total)} CLP
Neto referencial: {money(net)} CLP
IVA referencial incluido (19%): {money(vat)} CLP
Pago: {payment}

Revisar y confirmar desde el panel interno antes de fabricar.
"""
 return send_mail(target,f"Nuevo pedido {oid} · {money(total)} CLP",body)
def send_status_update(to,nombre,oid,status):
 labels={"confirmado":"Tu pedido fue confirmado.","fabricando":"Tu joya ya está en elaboración.","enviado":"Tu pedido fue despachado.","entregado":"Tu pedido fue marcado como entregado.","cancelado":"Tu pedido fue cancelado. Si tienes dudas, responde a este correo."}
 return send_mail(to,f"Actualización de tu pedido {oid} | Amamora",f"Hola {nombre},\n\n{labels.get(status,'Tu pedido fue actualizado.')}\n\nEstado actual: {status.title()}\nPedido: {oid}\n\nAmamora · Joyería hecha a mano en Chile")
@app.context_processor
def globals():return {"usuario_nombre":session.get("nombre"),"es_admin":session.get("rol")=="admin","es_trabajador":session.get("rol") in {"admin","trabajador"},"csrf_token":csrf_token,"google_client_id":GOOGLE_CLIENT_ID}
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
  if u and check_password_hash(u["password"],request.form.get("password","")):
   if not u["verificado"]:return render_template("auth.html",modo="acceso",error="Confirma tu correo antes de ingresar. Revisa también la carpeta de spam."),403
   session.clear();session.permanent=True;session.update(user_id=u["id"],nombre=u["nombre"],rol=u["rol"]);target=request.args.get("next","");return redirect(target if target.startswith("/") and not target.startswith("//") else account_redirect(u["rol"]))
  error="Correo o contraseña incorrectos."
 return render_template("auth.html",modo="acceso",error=error)
@app.route("/registro",methods=["GET","POST"])
def registro():
 error=None
 if request.method=="POST":
  if limited("register",4,600):return render_template("auth.html",modo="registro",error="Espera unos minutos antes de volver a intentarlo."),429
  nombre=request.form.get("nombre","").strip();email=request.form.get("email","").lower().strip();password=request.form.get("password","");company_code=request.form.get("codigo_empresa","").strip().upper()
  if not 2<=len(nombre)<=80 or not EMAIL_RE.fullmatch(email) or len(password)<10:return render_template("auth.html",modo="registro",error="Revisa el nombre, correo y usa una contraseña de al menos 10 caracteres."),400
  try:
   role="cliente";invite=None
   with db() as c:
    if company_code:
     invite=c.execute("SELECT * FROM invitaciones WHERE codigo_hash=? AND activo=1 AND usos<max_usos AND expira>?",(hash_token(company_code),int(time.time()))).fetchone()
     if not invite:return render_template("auth.html",modo="registro",error="El código de equipo no es válido o ya venció."),400
     role="trabajador"
    verified=0 if os.environ.get("SMTP_HOST") else 1
    cur=c.execute("INSERT INTO usuarios(nombre,email,password,rol,creado,verificado) VALUES(?,?,?,?,?,?)",(nombre,email,generate_password_hash(password),role,now(),verified));user_id=cur.lastrowid
    if invite:c.execute("UPDATE invitaciones SET usos=usos+1,activo=CASE WHEN usos+1>=max_usos THEN 0 ELSE activo END WHERE id=?",(invite["id"],))
   if not verified:
    token=issue_token(user_id,"verificacion",3600);send_mail(email,"Confirma tu correo | Amamora",f"Hola {nombre},\n\nConfirma tu cuenta abriendo este enlace:\n{url_for('verificar_correo',token=token,_external=True)}\n\nEl enlace vence en 1 hora.")
    return render_template("auth.html",modo="mensaje",mensaje="Te enviamos un enlace para confirmar tu correo. Revisa también la carpeta de spam.")
   return redirect(url_for("acceso",creada=1))
  except sqlite3.IntegrityError:error="Este correo ya está registrado."
 return render_template("auth.html",modo="registro",error=error)
@app.get("/verificar-correo/<token>")
def verificar_correo(token):
 with db() as c:
  row=c.execute("SELECT * FROM tokens_cuenta WHERE token_hash=? AND tipo='verificacion' AND usado=0 AND expira>?",(hash_token(token),int(time.time()))).fetchone()
  if not row:return render_template("auth.html",modo="mensaje",mensaje="Este enlace venció o ya fue utilizado.",error="Solicita un enlace nuevo desde el inicio de sesión."),400
  c.execute("UPDATE usuarios SET verificado=1 WHERE id=?",(row["usuario_id"],));c.execute("UPDATE tokens_cuenta SET usado=1 WHERE id=?",(row["id"],))
 return render_template("auth.html",modo="mensaje",mensaje="Tu correo quedó confirmado. Ya puedes ingresar.")
@app.route("/recuperar",methods=["GET","POST"])
def recuperar():
 mensaje=None
 if request.method=="POST":
  if limited("recover",4,600):return render_template("auth.html",modo="recuperar",error="Espera unos minutos antes de volver a intentarlo."),429
  email=request.form.get("email","").lower().strip()
  with db() as c:u=c.execute("SELECT id,nombre,email FROM usuarios WHERE email=?",(email,)).fetchone()
  if u and os.environ.get("SMTP_HOST"):
   token=issue_token(u["id"],"recuperacion",1800);send_mail(u["email"],"Restablece tu contraseña | Amamora",f"Hola {u['nombre']},\n\nCrea una contraseña nueva aquí:\n{url_for('restablecer',token=token,_external=True)}\n\nEl enlace vence en 30 minutos.")
  mensaje="Si el correo está registrado, recibirás un enlace seguro en unos minutos."
 return render_template("auth.html",modo="recuperar",mensaje=mensaje)
@app.route("/restablecer/<token>",methods=["GET","POST"])
def restablecer(token):
 with db() as c:row=c.execute("SELECT * FROM tokens_cuenta WHERE token_hash=? AND tipo='recuperacion' AND usado=0 AND expira>?",(hash_token(token),int(time.time()))).fetchone()
 if not row:return render_template("auth.html",modo="mensaje",mensaje="Este enlace venció o ya fue utilizado.",error="Solicita uno nuevo para proteger tu cuenta."),400
 error=None
 if request.method=="POST":
  password=request.form.get("password","")
  if len(password)<10:error="Usa una contraseña de al menos 10 caracteres."
  else:
   with db() as c:c.execute("UPDATE usuarios SET password=? WHERE id=?",(generate_password_hash(password),row["usuario_id"]));c.execute("UPDATE tokens_cuenta SET usado=1 WHERE id=?",(row["id"],))
   return render_template("auth.html",modo="mensaje",mensaje="Tu contraseña fue actualizada. Ya puedes ingresar.")
 return render_template("auth.html",modo="restablecer",error=error)
@app.post("/acceso/google")
def acceso_google():
 if not GOOGLE_CLIENT_ID:return jsonify(error="El acceso con Google aún no está configurado."),503
 if limited("google-login",10,300):return jsonify(error="Demasiados intentos. Espera unos minutos."),429
 try:
  from google.oauth2 import id_token
  from google.auth.transport import requests as google_requests
  payload=id_token.verify_oauth2_token((request.get_json(silent=True) or {}).get("credential",""),google_requests.Request(),GOOGLE_CLIENT_ID)
  email=str(payload.get("email","")).lower().strip();sub=str(payload.get("sub",""));name=str(payload.get("name") or email.split("@")[0])[:80]
  if not payload.get("email_verified") or not EMAIL_RE.fullmatch(email) or not sub:raise ValueError
  with db() as c:
   u=c.execute("SELECT * FROM usuarios WHERE email=?",(email,)).fetchone()
   if not u:
    cur=c.execute("INSERT INTO usuarios(nombre,email,password,rol,creado,verificado,google_sub) VALUES(?,?,?,?,?,1,?)",(name,email,generate_password_hash(secrets.token_urlsafe(40)),"cliente",now(),sub));u=c.execute("SELECT * FROM usuarios WHERE id=?",(cur.lastrowid,)).fetchone()
   else:c.execute("UPDATE usuarios SET verificado=1,google_sub=COALESCE(google_sub,?) WHERE id=?",(sub,u["id"]))
  session.clear();session.permanent=True;session.update(user_id=u["id"],nombre=u["nombre"],rol=u["rol"])
  return jsonify(redirect=account_redirect(u["rol"]))
 except (ValueError,TypeError):return jsonify(error="No pudimos validar tu cuenta de Google."),401
@app.post("/salir")
def salir():session.clear();return redirect(url_for("inicio"))
@app.get("/perfil")
@login_required
def perfil():
 with db() as c:designs=c.execute("SELECT * FROM disenos WHERE usuario_id=? ORDER BY creado DESC",(session["user_id"],)).fetchall();orders=c.execute("SELECT * FROM pedidos WHERE usuario_id=? ORDER BY creado DESC",(session["user_id"],)).fetchall()
 parsed=[]
 for design in designs:
  item=dict(design)
  try:item["config_data"]=json.loads(item["config"])
  except (json.JSONDecodeError,TypeError):item["config_data"]={}
  parsed.append(item)
 return render_template("perfil.html",designs=parsed,orders=orders)
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
@app.get("/equipo")
@admin_required
def equipo():
 code=session.pop("new_invite_code",None)
 with db() as c:
  users=c.execute("SELECT id,nombre,email,rol,verificado,creado FROM usuarios WHERE rol IN ('trabajador','admin') ORDER BY rol,nombre").fetchall()
  invites=c.execute("SELECT * FROM invitaciones ORDER BY id DESC LIMIT 30").fetchall()
 return render_template("equipo.html",users=users,invites=invites,new_code=code,current_time=int(time.time()))
@app.post("/equipo/invitaciones")
@admin_required
def crear_invitacion():
 if limited("invite",10,600):return ("Espera unos minutos antes de crear más invitaciones.",429)
 label=request.form.get("etiqueta","").strip()[:80] or "Nuevo integrante"
 try:days=min(30,max(1,int(request.form.get("dias",7))));max_uses=min(20,max(1,int(request.form.get("max_usos",1))))
 except ValueError:return ("Valores inválidos",400)
 raw=f"AMA-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
 with db() as c:c.execute("INSERT INTO invitaciones(etiqueta,codigo_hash,max_usos,expira,creado_por,creado) VALUES(?,?,?,?,?,?)",(label,hash_token(raw),max_uses,int(time.time())+days*86400,session["user_id"],now()))
 audit("equipo.invitacion",label);session["new_invite_code"]=raw;return redirect(url_for("equipo"))
@app.post("/equipo/invitaciones/<int:invite_id>/revocar")
@admin_required
def revocar_invitacion(invite_id):
 with db() as c:c.execute("UPDATE invitaciones SET activo=0 WHERE id=?",(invite_id,))
 audit("equipo.revocar",f"invitacion={invite_id}");return redirect(url_for("equipo"))
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
 with db() as c:
  order=c.execute("SELECT nombre,correo,estado FROM pedidos WHERE id=?",(oid,)).fetchone()
  if not order:return ("Pedido no encontrado",404)
  c.execute("UPDATE pedidos SET estado=? WHERE id=?",(estado,oid))
 if order["estado"]!=estado:
  try:send_status_update(order["correo"],order["nombre"],oid,estado)
  except Exception:app.logger.exception("Correo de estado no enviado")
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
 oid=f"AMA-{uuid.uuid4().hex[:8].upper()}";total=subtotal+shipping;vat=round(total*19/119);net=total-vat
 with db() as c:c.execute("INSERT INTO pedidos(id,usuario_id,creado,nombre,correo,region,direccion,items,subtotal,envio,total,pago,estado,neto_estimado,iva_estimado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(oid,session.get("user_id"),now(),nombre,correo,customer["region"],direccion,json.dumps(validated,ensure_ascii=False),subtotal,shipping,total,payment,"solicitado",net,vat))
 try:
  send_confirmation(correo,nombre,oid,validated,subtotal,shipping,total,payment)
  notify_store(nombre,correo,customer["region"],direccion,oid,validated,subtotal,shipping,total,payment,net,vat)
 except Exception:app.logger.exception("Correo no enviado")
 return jsonify(id=oid,total=total,estado="solicitado"),201
@app.get("/salud")
def salud():return jsonify(estado="ok")
init_db()
if __name__=="__main__":app.run(debug=True)
