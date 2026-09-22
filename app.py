from flask import Flask, render_template

# Crear la aplicación
app = Flask(__name__)

# Página principal
@app.route("/")
def inicio():
    return render_template("index.html")

# Categorías
@app.route("/categorias")
def categorias():
    return render_template("categorias.html")

# Diseñador de Anillos
@app.route("/anillos")
def anillos():
    return render_template("anillos.html")

# Diseñador de Collares
@app.route("/collares")
def collares():
    return render_template("collares.html")

# Ejecutar la aplicación
if __name__ == "__main__":
    app.run(debug=True)
