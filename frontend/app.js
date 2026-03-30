const queryInput = document.getElementById("queryInput");
const searchBtn = document.getElementById("searchBtn");
const statusText = document.getElementById("statusText");
const answerText = document.getElementById("answerText");
const resultList = document.getElementById("resultList");
const graphSvg = document.getElementById("graphSvg");

const NODE_COLOR = {
  Article: "#6fa3ff",
  Category: "#f9a56c",
  Content: "#7bc47f",
  Media: "#d486d8",
};

function renderResults(data) {
  answerText.textContent = data.answer;
  resultList.innerHTML = "";

  data.articles.forEach((a) => {
    const li = document.createElement("li");
    li.className = "result-item";
    li.innerHTML = `
      <p><strong>${a.title}</strong></p>
      <p>${a.published_date}</p>
      <p>${a.source} · ${a.category}</p>
      <p>${a.summary}</p>
      <p><a href="${a.url}" target="_blank" rel="noreferrer">${a.url}</a></p>
    `;
    resultList.appendChild(li);
  });
}

function drawNode(node, x, y) {
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  const r = node.type === "Article" ? 16 : 12;

  c.setAttribute("cx", x);
  c.setAttribute("cy", y);
  c.setAttribute("r", r);
  c.setAttribute("fill", NODE_COLOR[node.type] || "#bbb");
  c.setAttribute("stroke", "#453428");
  c.setAttribute("stroke-opacity", "0.3");

  const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
  t.setAttribute("x", x + r + 6);
  t.setAttribute("y", y + 4);
  t.setAttribute("font-size", "12");
  t.setAttribute("fill", "#2a231f");
  t.textContent = node.type === "Article" ? node.label.slice(0, 24) + "..." : node.label;

  g.appendChild(c);
  g.appendChild(t);
  graphSvg.appendChild(g);
}

function drawEdge(p1, p2, type) {
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", p1.x);
  line.setAttribute("y1", p1.y);
  line.setAttribute("x2", p2.x);
  line.setAttribute("y2", p2.y);
  line.setAttribute("stroke", type === "BELONGS_TO" ? "#bf6a1c" : "#8f7f72");
  line.setAttribute("stroke-width", type === "BELONGS_TO" ? "2.2" : "1.4");
  line.setAttribute("stroke-opacity", "0.65");
  graphSvg.appendChild(line);
}

function renderGraph(data) {
  graphSvg.innerHTML = "";

  const nodes = data.nodes;
  const edges = data.edges;
  const positions = new Map();

  // 타입별 레인 배치: 시연 단계에서 구조를 직관적으로 보여주기 위한 단순 레이아웃
  const lanes = {
    Category: 150,
    Media: 250,
    Article: 430,
    Content: 690,
  };

  const typeCount = {
    Category: 0,
    Media: 0,
    Article: 0,
    Content: 0,
  };

  nodes.forEach((node) => {
    const x = lanes[node.type] ?? 780;
    const y = 100 + typeCount[node.type] * 72;
    typeCount[node.type] += 1;
    positions.set(node.id, { x, y, node });
  });

  edges.forEach((edge) => {
    const p1 = positions.get(edge.source);
    const p2 = positions.get(edge.target);
    if (!p1 || !p2) return;
    drawEdge(p1, p2, edge.type);
  });

  positions.forEach((p) => drawNode(p.node, p.x, p.y));
}

async function runSearch() {
  const query = queryInput.value.trim();
  if (!query) return;

  statusText.textContent = "검색 중...";

  try {
    const res = await fetch("http://localhost:8000/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    if (!res.ok) {
      throw new Error(`API error: ${res.status}`);
    }

    const data = await res.json();
    renderResults(data);
    renderGraph(data);
    statusText.textContent = `검색 완료 · 사용 도구: ${data.used_tool}`;
  } catch (err) {
    statusText.textContent = "백엔드 연결 실패";
    answerText.textContent = `오류: ${err.message}`;
  }
}

searchBtn.addEventListener("click", runSearch);
queryInput.value = "생활/문화 카테고리 뉴스 3개 알려줘";
