# Amamora

Configurador interactivo de joyas en 3D para Chile.

## Ejecutar localmente

```bash
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Abre `http://127.0.0.1:5000`.

## Funciones

- Configurador 3D para anillos, pulseras, collares y aretes.
- Selección de alambrismo, metal, piedra, forma y tamaño.
- Precios en CLP y carrito persistente.
- Solicitudes de pedido guardadas en SQLite.
- Configuración de despliegue para Render.

## Pagos

El flujo actual registra solicitudes. Para cobrar se deben añadir credenciales comerciales de Mercado Pago o Transbank como variables de entorno.
