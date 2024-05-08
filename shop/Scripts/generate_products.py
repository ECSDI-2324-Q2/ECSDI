import sys
sys.path.append('../')
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

# Definir el namespace
default = Namespace("http://www.owl-ontologies.com/ECSDIstore#")

# Crear un grafo RDF
g = Graph()

# Definir los productos
productos = [
    {"id": 1, "nombre": "Patatas", "descripcion": "Esto son Patatas", "precio": 308.0, "peso": 23.0},
    {"id": 2, "nombre": "Mouse", "descripcion": "Esto es un Mouse", "precio": 32.0, "peso": 1.0},
    {"id": 3, "nombre": "Teclado", "descripcion": "Esto es un Teclado", "precio": 55.0, "peso": 2.0},
    {"id": 4, "nombre": "Barco", "descripcion": "Esto es un Barco", "precio": 20000.0, "peso": 1000.0},
    {"id": 5, "nombre": "Ordenador", "descripcion": "Esto es un Ordenador", "precio": 1000.0, "peso": 2.0},
    {"id": 6, "nombre": "Auriculares", "descripcion": "Esto son unos Auriculares", "precio": 20.0, "peso": 0.5},
    {"id": 7, "nombre": "Cable", "descripcion": "Esto es un Cable", "precio": 5.0, "peso": 0.5},
    {"id": 8, "nombre": "Platano", "descripcion": "Esto es un Platano", "precio": 1.0, "peso": 0.5},
    {"id": 9, "nombre": "Nuria Bruch", "descripcion": "Esto es una Nuria", "precio": 23000000.0, "peso": 55.0}
]

# Agregar los productos al grafo RDF
for producto in productos:
    producto_uri = default[f"Producto{producto['id']}"]
    g.add((producto_uri, RDF.type, default.Producto))
    g.add((producto_uri, default.Id, Literal(producto['id'], datatype=XSD.integer)))
    g.add((producto_uri, default.Nombre, Literal(producto['nombre'])))
    g.add((producto_uri, default.Descripcion, Literal(producto['descripcion'])))
    g.add((producto_uri, default.Precio, Literal(producto['precio'], datatype=XSD.float)))
    g.add((producto_uri, default.Peso, Literal(producto['peso'], datatype=XSD.float)))

# Guardar el grafo RDF en un archivo OWL
g.serialize(destination="BDProductos.owl")
