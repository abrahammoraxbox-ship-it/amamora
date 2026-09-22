# Amamora

Configurador interactivo de joyas en 3D para Chile.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/abrahammoraxbox-ship-it/amamora)

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
- Registro, inicio de sesión, perfiles y diseños guardados.
- Cálculo de despacho para las 16 regiones de Chile.
- Panel administrativo de pedidos e inventario.
- Confirmaciones por correo mediante variables SMTP.
- Vista de prueba con cámara para dispositivos móviles.
- Configuración de despliegue para Render.

## Pagos

El flujo actual registra solicitudes. Para cobrar se deben añadir credenciales comerciales de Mercado Pago o Transbank como variables de entorno.
