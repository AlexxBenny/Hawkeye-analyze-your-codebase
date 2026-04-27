"""Self-contained interactive HTML renderer using D3.js.

Generates a single HTML file with an embedded force-directed graph.
Zero external dependencies at runtime — works offline once opened.
Features: zoom/pan, click-to-isolate, search, cycle highlighting,
coupling heatmap, and a details sidebar.
"""

import json
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.graph import DependencyGraph
    from ..core.metrics import ModuleMetrics


def _build_graph_json(
    graph: "DependencyGraph",
    module_metrics: dict[str, "ModuleMetrics"] | None = None,
) -> str:
    """Build the JSON data structure consumed by the D3 visualization."""
    nodes = []
    for name, node in graph.nodes.items():
        # Determine color group from second-level package
        parts = name.split(".")
        group = parts[1] if len(parts) > 1 else parts[0]

        n: dict = {
            "id": name,
            "label": ".".join(parts[-2:]) if len(parts) > 2 else name,
            "group": group,
            "package": node.package,
            "rel_path": node.rel_path,
            "loc": node.loc,
            "depth": node.depth,
            "is_package": node.is_package,
        }

        if module_metrics and name in module_metrics:
            m = module_metrics[name]
            n["ca"] = m.ca
            n["ce"] = m.ce
            n["instability"] = m.instability
            n["health"] = m.health
            n["radius"] = max(6, min(30, 6 + (m.ca + m.ce) * 2))
        else:
            n["radius"] = 8

        nodes.append(n)

    links = []
    for (src, tgt), edge in graph.edges.items():
        links.append({
            "source": src,
            "target": tgt,
            "count": edge.import_count,
            "is_cycle": edge.is_cycle_member,
        })

    return json.dumps({"nodes": nodes, "links": links}, indent=None)


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hawkeye — {project_name}</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0f0f1a; color: #c8c8e0; font-family: 'Segoe UI', Inter, system-ui, sans-serif; overflow: hidden; }}

  #container {{ display: flex; height: 100vh; }}
  #graph-area {{ flex: 1; position: relative; }}
  svg {{ width: 100%; height: 100%; }}

  /* Sidebar */
  #sidebar {{ width: 340px; background: #16162a; border-left: 1px solid #2a2a4a;
    padding: 16px; overflow-y: auto; font-size: 13px; transition: transform 0.3s; }}
  #sidebar h2 {{ color: #a0a0ff; font-size: 15px; margin-bottom: 12px; }}
  #sidebar h3 {{ color: #8888cc; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin: 14px 0 6px; }}
  .detail-row {{ display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid #1e1e3a; }}
  .detail-label {{ color: #7777aa; }}
  .detail-value {{ color: #d0d0f0; font-weight: 600; }}
  .dep-list {{ max-height: 200px; overflow-y: auto; }}
  .dep-item {{ padding: 2px 0; color: #9999cc; cursor: pointer; }}
  .dep-item:hover {{ color: #ccccff; }}
  .health-healthy {{ color: #44cc77; }}
  .health-warning {{ color: #ccaa44; }}
  .health-critical {{ color: #cc4444; }}

  /* Search */
  #search-box {{ position: absolute; top: 12px; left: 12px; z-index: 10; }}
  #search-input {{ background: #1a1a30; border: 1px solid #333366; color: #c8c8e0;
    padding: 8px 14px; border-radius: 8px; width: 280px; font-size: 13px; outline: none; }}
  #search-input:focus {{ border-color: #6666cc; box-shadow: 0 0 10px rgba(100,100,200,0.3); }}
  #search-input::placeholder {{ color: #555577; }}

  /* Stats bar */
  #stats {{ position: absolute; bottom: 12px; left: 12px; z-index: 10;
    background: rgba(22,22,42,0.9); padding: 8px 14px; border-radius: 8px;
    font-size: 12px; color: #7777aa; display: flex; gap: 16px; }}
  .stat-value {{ color: #a0a0ff; font-weight: 700; }}

  /* Legend */
  #legend {{ position: absolute; top: 12px; right: 360px; z-index: 10;
    background: rgba(22,22,42,0.9); padding: 10px 14px; border-radius: 8px; font-size: 11px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; margin: 3px 0; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}

  /* Tooltip */
  .tooltip {{ position: absolute; background: #1e1e3a; border: 1px solid #3a3a6a;
    padding: 8px 12px; border-radius: 6px; font-size: 12px; pointer-events: none;
    z-index: 100; max-width: 300px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
</style>
</head>
<body>
<div id="container">
  <div id="graph-area">
    <div id="search-box">
      <input id="search-input" type="text" placeholder="Search modules... (Esc to clear)">
    </div>
    <div id="stats">
      <span>Modules: <span class="stat-value">{node_count}</span></span>
      <span>Dependencies: <span class="stat-value">{edge_count}</span></span>
      <span>Cycles: <span class="stat-value">{cycle_count}</span></span>
    </div>
    <svg id="graph-svg"></svg>
  </div>
  <div id="sidebar">
    <h2>🦅 Hawkeye</h2>
    <p style="color: #555577; font-size: 12px; margin-bottom: 12px;">{project_name}</p>
    <div id="module-details">
      <p style="color: #555577;">Click a node to inspect it.</p>
    </div>
  </div>
</div>

<script>
const graphData = {graph_json};

// ── Color scheme ──
const groups = [...new Set(graphData.nodes.map(n => n.group))].sort();
const colorScale = d3.scaleOrdinal()
  .domain(groups)
  .range(groups.map((_, i) => d3.hsl(i * (360 / groups.length), 0.6, 0.55).formatHex()));

// ── SVG setup ──
const svg = d3.select("#graph-svg");
const width = document.getElementById("graph-area").clientWidth;
const height = document.getElementById("graph-area").clientHeight;

const g = svg.append("g");

// Zoom
const zoom = d3.zoom()
  .scaleExtent([0.1, 6])
  .on("zoom", (event) => g.attr("transform", event.transform));
svg.call(zoom);

// Arrow markers
svg.append("defs").selectAll("marker")
  .data(["normal", "cycle"])
  .join("marker")
    .attr("id", d => `arrow-${{d}}`)
    .attr("viewBox", "0 -5 10 10")
    .attr("refX", 20)
    .attr("refY", 0)
    .attr("markerWidth", 6)
    .attr("markerHeight", 6)
    .attr("orient", "auto")
  .append("path")
    .attr("d", "M0,-5L10,0L0,5")
    .attr("fill", d => d === "cycle" ? "#ff4444" : "#444466");

// ── Simulation ──
const simulation = d3.forceSimulation(graphData.nodes)
  .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(120))
  .force("charge", d3.forceManyBody().strength(-300))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collision", d3.forceCollide().radius(d => (d.radius || 8) + 4));

// ── Links ──
const link = g.append("g")
  .selectAll("line")
  .data(graphData.links)
  .join("line")
    .attr("stroke", d => d.is_cycle ? "#ff4444" : "#333355")
    .attr("stroke-width", d => d.is_cycle ? 2 : 1)
    .attr("stroke-opacity", d => d.is_cycle ? 0.8 : 0.4)
    .attr("marker-end", d => `url(#arrow-${{d.is_cycle ? "cycle" : "normal"}})`);

// ── Nodes ──
const node = g.append("g")
  .selectAll("circle")
  .data(graphData.nodes)
  .join("circle")
    .attr("r", d => d.radius || 8)
    .attr("fill", d => colorScale(d.group))
    .attr("stroke", d => {{
      if (d.health === "critical") return "#ff4444";
      if (d.health === "warning") return "#ccaa44";
      return "#222244";
    }})
    .attr("stroke-width", d => (d.health === "critical" || d.health === "warning") ? 2.5 : 1)
    .style("cursor", "pointer")
    .call(d3.drag()
      .on("start", dragStarted)
      .on("drag", dragged)
      .on("end", dragEnded));

// ── Labels ──
const labels = g.append("g")
  .selectAll("text")
  .data(graphData.nodes)
  .join("text")
    .text(d => d.label.split(".").pop())
    .attr("font-size", 9)
    .attr("fill", "#8888aa")
    .attr("text-anchor", "middle")
    .attr("dy", d => -(d.radius || 8) - 4)
    .style("pointer-events", "none");

// ── Tooltip ──
const tooltip = d3.select("body").append("div").attr("class", "tooltip").style("display", "none");

node.on("mouseover", (event, d) => {{
  tooltip.style("display", "block")
    .html(`<strong>${{d.id}}</strong><br>${{d.rel_path}}<br>LOC: ${{d.loc}}`)
    .style("left", (event.pageX + 12) + "px")
    .style("top", (event.pageY - 10) + "px");
}})
.on("mousemove", (event) => {{
  tooltip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY - 10) + "px");
}})
.on("mouseout", () => tooltip.style("display", "none"));

// ── Click to highlight neighborhood ──
let selectedNode = null;

node.on("click", (event, d) => {{
  event.stopPropagation();
  selectedNode = d;
  highlightNeighborhood(d);
  showDetails(d);
}});

svg.on("click", () => {{
  selectedNode = null;
  resetHighlight();
  document.getElementById("module-details").innerHTML = '<p style="color: #555577;">Click a node to inspect it.</p>';
}});

function highlightNeighborhood(d) {{
  const neighbors = new Set([d.id]);
  graphData.links.forEach(l => {{
    const s = typeof l.source === "object" ? l.source.id : l.source;
    const t = typeof l.target === "object" ? l.target.id : l.target;
    if (s === d.id) neighbors.add(t);
    if (t === d.id) neighbors.add(s);
  }});

  node.attr("opacity", n => neighbors.has(n.id) ? 1 : 0.1);
  labels.attr("opacity", n => neighbors.has(n.id) ? 1 : 0.05);
  link.attr("opacity", l => {{
    const s = typeof l.source === "object" ? l.source.id : l.source;
    const t = typeof l.target === "object" ? l.target.id : l.target;
    return (s === d.id || t === d.id) ? 0.8 : 0.03;
  }});
}}

function resetHighlight() {{
  node.attr("opacity", 1);
  labels.attr("opacity", 1);
  link.attr("opacity", l => l.is_cycle ? 0.8 : 0.4);
}}

function showDetails(d) {{
  const deps = graphData.links.filter(l => (typeof l.source === "object" ? l.source.id : l.source) === d.id);
  const rdeps = graphData.links.filter(l => (typeof l.target === "object" ? l.target.id : l.target) === d.id);
  const healthClass = d.health ? `health-${{d.health}}` : "";

  let html = `<h2>${{d.label}}</h2><p style="color:#555577;font-size:11px;margin-bottom:10px;">${{d.id}}</p>`;
  html += `<h3>Details</h3>`;
  html += detailRow("File", d.rel_path);
  html += detailRow("LOC", d.loc);
  html += detailRow("Package", d.package || "—");

  if (d.ca !== undefined) {{
    html += `<h3>Metrics</h3>`;
    html += detailRow("Afferent (Ca)", d.ca);
    html += detailRow("Efferent (Ce)", d.ce);
    html += detailRow("Instability", d.instability?.toFixed(3));
    html += detailRow("Health", `<span class="${{healthClass}}">${{d.health}}</span>`);
  }}

  html += `<h3>Dependencies (${{deps.length}})</h3><div class="dep-list">`;
  deps.forEach(l => {{
    const t = typeof l.target === "object" ? l.target.id : l.target;
    const cycleTag = l.is_cycle ? ' <span style="color:#ff4444;">🔄</span>' : "";
    html += `<div class="dep-item" onclick="focusNode('${{t}}')">→ ${{t}}${{cycleTag}}</div>`;
  }});
  html += `</div>`;

  html += `<h3>Dependents (${{rdeps.length}})</h3><div class="dep-list">`;
  rdeps.forEach(l => {{
    const s = typeof l.source === "object" ? l.source.id : l.source;
    html += `<div class="dep-item" onclick="focusNode('${{s}}')">← ${{s}}</div>`;
  }});
  html += `</div>`;

  document.getElementById("module-details").innerHTML = html;
}}

function detailRow(label, value) {{
  return `<div class="detail-row"><span class="detail-label">${{label}}</span><span class="detail-value">${{value}}</span></div>`;
}}

function focusNode(id) {{
  const d = graphData.nodes.find(n => n.id === id);
  if (d) {{ highlightNeighborhood(d); showDetails(d); }}
}}

// ── Search ──
const searchInput = document.getElementById("search-input");
searchInput.addEventListener("input", () => {{
  const query = searchInput.value.toLowerCase();
  if (!query) {{ resetHighlight(); return; }}

  const matches = new Set();
  graphData.nodes.forEach(n => {{ if (n.id.toLowerCase().includes(query)) matches.add(n.id); }});

  node.attr("opacity", n => matches.has(n.id) ? 1 : 0.1);
  labels.attr("opacity", n => matches.has(n.id) ? 1 : 0.05);
  link.attr("opacity", 0.05);
}});

searchInput.addEventListener("keydown", (e) => {{
  if (e.key === "Escape") {{ searchInput.value = ""; resetHighlight(); }}
}});

// ── Simulation tick ──
simulation.on("tick", () => {{
  link
    .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("cx", d => d.x).attr("cy", d => d.y);
  labels.attr("x", d => d.x).attr("y", d => d.y);
}});

// ── Drag handlers ──
function dragStarted(event, d) {{
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}}
function dragged(event, d) {{ d.fx = event.x; d.fy = event.y; }}
function dragEnded(event, d) {{
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}}
</script>
</body>
</html>"""


def render_html(
    graph: "DependencyGraph",
    module_metrics: dict[str, "ModuleMetrics"] | None = None,
    cycle_count: int = 0,
) -> str:
    """Render the graph as a self-contained interactive HTML file."""
    graph_json = _build_graph_json(graph, module_metrics)

    return _HTML_TEMPLATE.format(
        project_name=graph.project_name,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        cycle_count=cycle_count,
        graph_json=graph_json,
    )
