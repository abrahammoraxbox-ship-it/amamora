from flask import Flask, render_template

app = Flask(__name__)

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

if __name__ == "__main__": app.run(debug=True)
