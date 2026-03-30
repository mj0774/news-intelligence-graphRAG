const API_BASE = "http://localhost:8000";

let network;
let nodes;
let edges;
let allNodesData = [];
let allEdgesData = [];

const COLOR_BY_LABEL = {
  Article: "#97C2FC",
  Category: "#FFAB91",
  Content: "#A5D6A7",
  Media: "#CE93D8",
};

window.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await initGraph();
});

function bindEvents() {
  const askButton = document.getElementById("askButton");
  askButton.addEventListener("click", askQuestion);

  document.querySelectorAll(".example-query").forEach((item) => {
    item.addEventListener("click", () => {
      document.getElementById("question").value = item.dataset.query || "";
    });
  });

  const legend = document.getElementById("legend");
  legend.addEventListener("click", () => {
    legend.classList.toggle("collapsed");
  });

  const closePanel = document.getElementById("closePanel");
  closePanel.addEventListener("click", closeNodeInfo);
}

async function initGraph() {
  try {
    const response = await fetch(`${API_BASE}/api/graph`);
    if (!response.ok) {
      throw new Error(`그래프 조회 실패 (${response.status})`);
    }

    const data = await response.json();
    allNodesData = data.nodes || [];
    allEdgesData = data.edges || [];

    // 참고자료2처럼 초기 상태는 전체 회색으로 보여준다.
    const visNodes = allNodesData.map((node) => ({
      id: node.id,
      label: shorten(node.label, 25),
      title: `${node.type}: ${node.title || node.label}`,
      color: {
        background: "#E0E0E0",
        border: "#BDBDBD",
      },
      font: { size: 12, color: "#757575" },
      shape: "dot",
      size: 15,
    }));

    const visEdges = allEdgesData.map((edge) => ({
      id: edge.id,
      from: edge.source,
      to: edge.target,
      label: "",
      arrows: "to",
      color: { color: "#E0E0E0", highlight: "#FF6B6B" },
      width: 1,
      font: { size: 9, color: "#999" },
    }));

    nodes = new vis.DataSet(visNodes);
    edges = new vis.DataSet(visEdges);

    const container = document.getElementById("mynetwork");
    const graphData = { nodes, edges };

    const options = {
      physics: {
        enabled: true,
        barnesHut: {
          gravitationalConstant: -8000,
          springConstant: 0.04,
          springLength: 95,
        },
        stabilization: {
          iterations: 200,
        },
      },
      interaction: {
        hover: true,
        tooltipDelay: 100,
        zoomView: true,
        dragView: true,
      },
      nodes: {
        borderWidth: 2,
        shadow: true,
      },
      edges: {
        width: 2,
        shadow: true,
        smooth: {
          type: "continuous",
        },
      },
    };

    network = new vis.Network(container, graphData, options);

    // 참고자료2와 같은 느낌으로 초기 안정화 뒤 physics를 끈다.
    network.once("stabilizationIterationsDone", () => {
      network.setOptions({ physics: false });
    });

    network.on("click", (params) => {
      if (params.nodes.length > 0) {
        showNodeInfo(params.nodes[0]);
      } else {
        closeNodeInfo();
      }
    });
  } catch (error) {
    alert(`그래프 초기화 실패: ${error.message}`);
  }
}

async function askQuestion() {
  const question = document.getElementById("question").value.trim();
  if (!question) {
    alert("질문을 입력해주세요.");
    return;
  }

  const askButton = document.getElementById("askButton");
  const loading = document.getElementById("loading");

  askButton.disabled = true;
  loading.classList.add("active");

  try {
    resetGraph();

    const response = await fetch(`${API_BASE}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: question }),
    });

    if (!response.ok) {
      throw new Error(`검색 실패 (${response.status})`);
    }

    const data = await response.json();
    renderAnswer(data);
    highlightSubgraph(data.highlighted_node_ids || [], data.highlighted_edge_ids || []);
  } catch (error) {
    alert(`검색 실패: ${error.message}`);
  } finally {
    askButton.disabled = false;
    loading.classList.remove("active");
  }
}

function renderAnswer(data) {
  const answerBox = document.getElementById("answerBox");
  const answerEl = document.getElementById("answer");
  const infoBox = document.getElementById("infoBox");
  const resultBox = document.getElementById("resultBox");

  const usedTool = data.used_tool || "unknown";
  const answer = data.answer || "답변이 없습니다.";

  answerEl.innerHTML = marked.parse(answer);
  answerBox.style.display = "block";

  // 검색 방법은 답변 박스 하단(info-box)에서 표시한다.
  infoBox.style.display = "block";
  infoBox.innerHTML = `<strong>검색 방법:</strong> ${usedTool}`;
  resultBox.style.display = "none";
}
function resetGraph() {
  if (!nodes || !edges) return;

  // 검색 전 기본 상태를 다시 회색으로 맞춘다.
  nodes.get().forEach((node) => {
    nodes.update({
      id: node.id,
      color: {
        background: "#E0E0E0",
        border: "#BDBDBD",
      },
      borderWidth: 2,
      size: 15,
      font: { size: 12, color: "#757575" },
    });
  });

  edges.get().forEach((edge) => {
    edges.update({
      id: edge.id,
      color: { color: "#E0E0E0" },
      width: 1,
      label: "",
    });
  });
}

function highlightSubgraph(nodeIds, edgeIds) {
  if (!nodes || !edges) return;

  const nodeIdSet = new Set(nodeIds);
  const edgeIdSet = new Set(edgeIds);

  // 검색 결과에 해당하는 노드만 타입 색상으로 활성화한다.
  nodeIds.forEach((id) => {
    const sourceNode = allNodesData.find((n) => n.id === id);
    const color = COLOR_BY_LABEL[sourceNode?.type] || "#97C2FC";

    nodes.update({
      id,
      color: {
        background: color,
        border: "#C92A2A",
      },
      borderWidth: 4,
      size: 25,
      font: { size: 14, color: "#000" },
    });
  });

  allEdgesData.forEach((edge) => {
    if (!edgeIdSet.has(edge.id)) return;
    if (!nodeIdSet.has(edge.source) || !nodeIdSet.has(edge.target)) return;

    edges.update({
      id: edge.id,
      color: { color: "#FF6B6B" },
      width: 3,
      label: edge.type,
    });
  });

  if (nodeIds.length) {
    network.fit({
      nodes: nodeIds,
      animation: {
        duration: 1000,
        easingFunction: "easeInOutQuad",
      },
    });
  }
}

function pickNodeFields(node) {
  const props = node.properties || {};

  const byType = {
    Article: ["article_id", "title", "published_date", "url"],
    Category: ["name"],
    Media: ["name"],
    Content: ["content_id", "article_id", "chunk_index", "chunk"],
  };

  const keys = byType[node.type] || Object.keys(props);
  const rows = [["id", node.id], ["type", node.type]];

  keys.forEach((key) => {
    if (key === "embedding" || key === "embeddings") return;
    const value = props[key];
    if (value === undefined || value === null || value === "") return;
    rows.push([key, value]);
  });

  return rows;
}

function renderNodeValue(key, value) {
  if (typeof value !== "string") {
    return escapeHtml(JSON.stringify(value));
  }

  if (key === "url" && value.startsWith("http")) {
    const safeUrl = escapeHtml(value);
    return `<a href="${safeUrl}" target="_blank" rel="noreferrer">${safeUrl}</a>`;
  }

  if (key === "chunk" && value.length > 160) {
    return escapeHtml(`${value.slice(0, 160)}...`);
  }

  return escapeHtml(value);
}

function showNodeInfo(nodeId) {
  const panel = document.getElementById("nodeInfoPanel");
  const title = document.getElementById("nodeInfoTitle");
  const content = document.getElementById("nodeInfoContent");

  const node = allNodesData.find((n) => n.id === nodeId);
  if (!node) return;

  title.textContent = `${node.type}: ${node.title || node.label}`;
  const rows = pickNodeFields(node);

  content.innerHTML = rows
    .map(
      ([k, v]) => `
      <div class="node-info-item">
        <span class="node-info-key">${escapeHtml(String(k))}:</span>
        <span class="node-info-value">${renderNodeValue(String(k), v)}</span>
      </div>
    `,
    )
    .join("");

  panel.classList.add("active");
}
function closeNodeInfo() {
  document.getElementById("nodeInfoPanel").classList.remove("active");
}

function shorten(text, maxLen) {
  if (!text) return "";
  return text.length > maxLen ? `${text.slice(0, maxLen)}...` : text;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
