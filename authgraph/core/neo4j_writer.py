
from py2neo import Graph, Node, Relationship

def push_to_neo4j(routes):
    graph = Graph("bolt://localhost:7688", auth=("neo4j", "test1234"))
    graph.run("MATCH (n) DETACH DELETE n")
    for route in routes:
        role = Node("Role", name=route["role"])
        path = Node("Path", url=route["path"])
        method = Node("Method", type=route["method"])
        graph.merge(role, "Role", "name")
        graph.merge(path, "Path", "url")
        graph.merge(method, "Method", "type")
        graph.merge(Relationship(role, "CAN_ACCESS", path))
        graph.merge(Relationship(path, "ALLOWS", method))