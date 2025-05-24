const nodes = new vis.DataSet();
const edges = new vis.DataSet();

fetch("/api/graph")
  .then(res => res.json())
  .then(data => {
    data.nodes.forEach(n => nodes.add(n));
    data.edges.forEach(e => edges.add(e));

    const container = document.getElementById("network");
    const dataSet = { nodes: nodes, edges: edges };
    const options = { physics: { stabilization: false }, layout: { hierarchical: false } };
    new vis.Network(container, dataSet, options);
  });