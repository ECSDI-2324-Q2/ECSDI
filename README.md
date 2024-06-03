# ECSDI 2023/2024
Pràctica ECSDI 2023-2024 Q2.
Enunciat pràctica: [ECSDIPractica.pdf](https://github.com/ECSDI-2324-Q2/ECSDI/blob/main/ECSDIPractica.pdf)

## 🫂 Integrants
- Amorín Díaz, Miquel
- Mostazo González, Marc
- Tajahuerce Brulles, Arnau

## ⚙️ Instruccions
> EXECUTAR TOTES LES COMANDES AL DIRECTORI `./shop/Agents`

Per instalar les dependencies:
```sh
pip install -r requirements.txt
```

Per executar tots els agents:
```sh
./run.sh
```

Per parar tots els agents:
```sh
./stop.sh
```

Per executar un agent concret:
```sh
python NOMAGENT.py
```

## 🎲 Jocs de Prova

### 🔍 Búsqueda de productos
- **Búsqueda sin filtro:** Te deben salir todos los productos.
- **Buscar por nombre ‘Patatas’:** Retorna un producto llamado ‘Patatas’.
- **Buscar por precio máximo:** Retorna productos con precio inferior al indicado.
- **Buscar por precio mínimo:** Retorna productos con precio mayor al indicado.
- **Buscar por precio máximo y mínimo:** Retorna productos con precio entre los dos valores.

### 🛒 Compra
- **Compra de Barco con código postal 8028:** Te devuelve la factura y te envía el producto el Centro Logístico 1.
- **Compra de Barco con código postal 3029:** Te devuelve la factura y te envía el producto el Centro Logístico 2.
- **Compra  de Mouse y Ordenador a código postal cualquiera:** Te devuelve la factura y el Ordenador te lo envía Centro Logístico 1 y el Mouse Centro Logístico 2.
- **Comprar producto con prioridad 1 día:** El envío te llegará en un día.
- **Comprar producto con prioridad entre 3 y 5 días:** El envío te llega entre 3 y 5 días.
- **Comprar producto con prioridad cuando sea:** El envío te llega entre 1 y 20 días.
- **Comprar un producto de peso menor a 48 cuando los centros logísticos no tienen nada pendiente de envío:** El paquete será enviado por el Transportista 2.
- **Comprar un producto de peso mayor a 49 cuando los centros logísticos no tienen nada pendiente de envío:** El paquete será enviado por el Transportista 1.
- **Comprar producto externo con gestión externa:** El paquete no será enviado por ningún transportista sino por el vendedor externo.
- **Comprar producto externo con gestión interna:** El paquete será enviado por un centro logístico.

### 💳 Devoluciones
- **Hacer una devolución con una tarjeta con la que se ha hecho la compra previamente y poner de  motivo ‘Producto defectuoso’:** Nos dirá que nuestra devolución está siendo procesada
- **Hacer una devolución con una tarjeta con la que se ha hecho la compra previamente y poner de motivo ‘Producto equivocado’:** Nos dirá que nuestra devolución está siendo procesada.
- **Hacer una devolución con una tarjeta con la que se ha hecho la compra previamente hace menos de 15 días y poner de motivo ‘No Satisfactorio’:** Nos dirá que nuestra devolución está siendo procesada.
- **Hacer una devolución con una tarjeta con la que se ha hecho la compra previamente hace más de 15 días y poner de motivo ‘No Satisfactorio’:** Nos dirá que nuestra devolución no es válida.
