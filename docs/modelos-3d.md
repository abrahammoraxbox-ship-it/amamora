# Estándar de modelos 3D de Amamora

Cada pieza debe tener una identidad estable para poder encontrar su foto, modelo 3D y configuración sin confusiones.

## Ficha inicial

- Producto: `PUL-001 · Pulsera Eclipse Dorado`
- Alambrismo: `ALA-001 · Trenza Doble Eclipse`
- Tipo: Pulsera
- Piedra: Ónix negro facetado
- Material: Oro golfi
- Foto: `pul-001-eclipse-dorado.webp`
- Modelo: `pul-001-trenza-doble-eclipse.glb`

## Requisitos del archivo GLB

- Escala real en milímetros y proporciones tomadas de la pieza física.
- Texturas PBR incluidas en el GLB: color, rugosidad, metal y normales.
- Piedra y metal en materiales separados y claramente nombrados.
- Facetas irregulares y variación sutil en cada piedra; no usar esferas perfectas.
- Alambrismo con grosor real, cruces limpios y sin atravesar las piedras.
- Geometría optimizada para celular y archivo final inferior a 8 MB.
- Centro y orientación correctos para que el configurador encuadre la joya automáticamente.

## Flujo de publicación

1. Crear el modelo desde fotografías claras de frente, lado, arriba y detalle.
2. Corregir geometría, escala y materiales en Blender o Meshy.
3. Exportar un único archivo GLB con las texturas incorporadas.
4. Entrar al gestor, crear o editar el alambrismo, indicar su categoría compatible y subir foto + GLB.
5. Revisar la pieza en escritorio y celular antes de publicarla.

La fotografía sirve como referencia comercial. El GLB es el archivo que determina el aspecto real dentro del configurador.
