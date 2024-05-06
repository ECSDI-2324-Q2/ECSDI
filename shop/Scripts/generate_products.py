import sys
sys.path.append('../')
from rdflib import Graph, Literal, RDF
from AgentUtil.OntoNamespaces import ECSDI

def add_product(g, product_id, product_name, product_description, weight_grams, price):
    g.add((ECSDI[product_id], RDF.type, Literal(ECSDI.producte)))
    g.add((ECSDI[product_id], ECSDI.nom, Literal(product_name)))
    g.add((ECSDI[product_id], ECSDI.id, Literal(product_id)))
    g.add((ECSDI[product_id], ECSDI.descripcio, Literal(product_description)))
    g.add((ECSDI[product_id], ECSDI.pes, Literal(weight_grams)))
    g.add((ECSDI[product_id], ECSDI.preu, Literal(price)))


def main():
    graph = Graph()

    add_product(graph, "001", "Camisa de algodón", "Camisa de manga corta de algodón suave", 200, 25.99)
    add_product(graph, "002", "Pantalones vaqueros", "Pantalones vaqueros ajustados de mezclilla", 500, 39.99)
    add_product(graph, "003", "Zapatillas deportivas", "Zapatillas deportivas ligeras y transpirables", 300, 49.99)
    add_product(graph, "004", "Vestido floral", "Vestido corto con estampado floral y cinturón ajustable", 400, 29.99)
    add_product(graph, "005", "Mochila resistente al agua", "Mochila con múltiples compartimentos y resistente al agua", 700, 34.99)


    graph.serialize('database_test.rdf')
    print('Created product_test.rdf')



main()