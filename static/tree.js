"use strict";

// Просмотр дерева. make, svgElement, money и fmt определены в app.js.
function addSearchTree(box, run) {
  const button = make("button", "Показать дерево");
  const panel = make("div", "", "search-tree");
  panel.hidden = true;
  button.setAttribute("aria-expanded", "false");
  button.onclick = () => {
    panel.hidden = !panel.hidden;
    button.textContent = panel.hidden ? "Показать дерево" : "Скрыть дерево";
    button.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden && !panel.children.length) renderSearchTree(panel, run);
  };
  box.append(button, panel);
}

function renderSearchTree(box, run) {
  const tree = run.tree;
  const names = { branch: "Разветвление", bound: "Отсечено по стоимости",
    capacity: "Нет допустимого продолжения", plan: "Новый лучший план", limit: "Лимит узлов" };
  box.append(make("p", "Узлы — назначения, № — порядок обхода. Пунктир — отсечение; темная рамка — итоговый план."));
  if (run.treeTruncated) box.append(make("p", "Показаны первые " + run.treeLimit + " узлов; поиск продолжался."));
  if (run.status.startsWith("limit")) box.append(make("p", "Достигнут лимит узлов; поиск не завершен."));

  // Листья располагаются по строкам, каждый родитель — между своими детьми.
  const children = tree.map(() => []);
  tree.forEach((node, i) => { if (node.parent !== null) children[node.parent].push(i); });
  const y = [];
  let rows = 0;
  function place(i) {
    children[i].forEach(place);
    y[i] = children[i].length ? (y[children[i][0]] + y[children[i].at(-1)]) / 2 : 45 + rows++ * 90;
  }
  place(0);
  const width = (Math.max(...tree.map((node) => node.depth)) + 1) * 250;
  const height = rows * 90 + 10;
  let step = tree.length - 1;
  let scale = 1;
  let pan = null;

  const controls = make("div", "", "controls");
  function button(text, action) {
    return addButton(controls, text, action);
  }
  const previous = button("Предыдущий шаг", () => showStep(step - 1));
  const next = button("Следующий шаг", () => showStep(step + 1));
  button("К корню", () => center(0));
  button("К текущему шагу", () => center(step));
  button("−", () => zoomTo(Math.floor(scale * 100 / 1.25))).setAttribute("aria-label", "Отдалить дерево");
  const zoomLabel = make("label", "Масштаб, %");
  const zoom = make("input");
  zoom.type = "number";
  zoom.min = "1";
  zoom.max = "300";
  zoom.value = "100";
  zoom.oninput = () => { if (zoom.value) zoomTo(Number(zoom.value)); };
  zoomLabel.append(zoom);
  controls.append(zoomLabel);
  button("+", () => zoomTo(Math.ceil(scale * 100 * 1.25))).setAttribute("aria-label", "Приблизить дерево");
  button("Вписать дерево", fit);
  const label = make("label", "Шаг дерева", "stage");
  const slider = make("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(step);
  slider.oninput = () => showStep(Number(slider.value));
  label.append(slider);
  const description = make("div", "", "preview");
  const viewport = make("div", "", "tree-viewport");
  const canvas = make("div", "", "tree-canvas");
  const svg = svgElement("svg", { viewBox: "0 0 " + width + " " + height, role: "img", "aria-label": "Дерево ветвей и границ" });
  canvas.append(svg);
  viewport.append(canvas);
  box.append(controls, make("p", "Фон можно перетаскивать. Ctrl + колесо — масштаб, нажатие на узел — выбор шага."), label, description, viewport);

  // Схема создается один раз. Дальше меняются только видимость и масштаб.
  const bestPath = [];
  const nodes = tree.map((node, i) => {
    const x = node.depth * 250 + 10;
    bestPath[i] = run.bestAssignment && (node.parent === null || bestPath[node.parent]) &&
      (!node.container || run.bestAssignment[node.container] === node.site);
    const group = svgElement("g", { class: "tree-node " + node.status + (bestPath[i] ? " best-path" : "") });
    if (node.parent !== null) group.append(svgElement("line", {
      x1: tree[node.parent].depth * 250 + 230, y1: y[node.parent], x2: x, y2: y[i], class: "tree-edge" }));
    group.append(svgElement("rect", { x, y: y[i] - 36, width: 220, height: 72, rx: 5 }),
      svgElement("text", { x: x + 7, y: y[i] - 17, class: "current-marker" }, "▶"),
      svgElement("text", { x: x + 24, y: y[i] - 17 }, "№" + (i + 1) + " " + (node.container ? node.container + " → " + node.site : "Корень")),
      svgElement("text", { x: x + 9, y: y[i] + 2 }, "Цена " + fmt.format(node.cost) + "; оценка " + (node.lowerBound === null ? "—" : fmt.format(node.lowerBound))),
      svgElement("text", { x: x + 9, y: y[i] + 22 }, names[node.status]));
    group.onclick = () => showStep(i);
    svg.append(group);
    return group;
  });

  function showStep(value, focus = true) {
    step = Math.max(0, Math.min(tree.length - 1, value));
    slider.value = step;
    nodes.forEach((node, i) => {
      node.style.display = i <= step ? "" : "none";
      node.classList.toggle("active", i === step);
    });
    const active = tree[step];
    const assignments = [];
    for (let i = step; tree[i].parent !== null; i = tree[i].parent) assignments.unshift(tree[i].container + " → " + tree[i].site);
    const price = (value) => value === null ? "не вычислена" : money(value);
    description.replaceChildren(make("p", "Шаг " + (step + 1) + " из " + tree.length + ": " + names[active.status]),
      make("p", "Путь: " + (assignments.join("; ") || "корень")),
      make("p", "Стоимость назначений: " + money(active.cost) + ". Нижняя оценка: " + price(active.lowerBound) +
        ". Лучший план к этому шагу: " + (active.bestCost === null ? "пока нет" : money(active.bestCost)) + "."));
    if (active.status === "bound") description.append(make("p", "Нижняя оценка не лучше известной стоимости: ветвь отсечена."));
    if (active.status === "capacity") description.append(make("p", "Для продолжения не хватает ресурсов или подходящих площадок."));
    previous.disabled = step === 0;
    next.disabled = step === tree.length - 1;
    if (focus) center(step);
  }
  function space(zoom) {
    return { x: Math.max(0, (viewport.clientWidth - width * zoom) / 2),
      y: Math.max(0, (viewport.clientHeight - height * zoom) / 2) };
  }
  function centerPoint(x, y) {
    const padding = space(scale);
    viewport.scrollLeft = x * scale + padding.x - viewport.clientWidth / 2;
    viewport.scrollTop = y * scale + padding.y - viewport.clientHeight / 2;
  }
  function center(i) {
    centerPoint(tree[i].depth * 250 + 120, y[i]);
  }
  function zoomTo(percent, x = viewport.clientWidth / 2, y = viewport.clientHeight / 2) {
    const ratio = Math.max(1, Math.min(300, Math.round(percent) || 100)) / 100 / scale;
    const before = space(scale);
    const after = space(scale * ratio);
    // При смене масштаба сохраняем точку под указателем или центром окна.
    const left = (viewport.scrollLeft + x - before.x) * ratio + after.x - x;
    const top = (viewport.scrollTop + y - before.y) * ratio + after.y - y;
    scale *= ratio;
    zoom.value = Math.round(scale * 100);
    svg.style.width = width * scale + "px";
    svg.style.height = height * scale + "px";
    viewport.scrollLeft = left;
    viewport.scrollTop = top;
  }
  function fit() {
    const bounds = svg.getBBox();
    zoomTo(Math.floor(100 * Math.min(1, viewport.clientWidth / (bounds.width + 30), viewport.clientHeight / (bounds.height + 30))));
    centerPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  }

  viewport.addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    const rect = viewport.getBoundingClientRect();
    zoomTo(event.deltaY < 0 ? Math.ceil(scale * 125) : Math.floor(scale * 80),
      event.clientX - rect.left - viewport.clientLeft, event.clientY - rect.top - viewport.clientTop);
  }, { passive: false });
  viewport.onpointerdown = (event) => {
    if (event.button !== 0 || event.target.closest(".tree-node")) return;
    event.preventDefault();
    pan = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
    viewport.setPointerCapture(event.pointerId);
    viewport.classList.add("panning");
  };
  viewport.onpointermove = (event) => {
    if (!pan) return;
    viewport.scrollLeft = pan.left + pan.x - event.clientX;
    viewport.scrollTop = pan.top + pan.y - event.clientY;
  };
  viewport.onpointerup = viewport.onpointercancel = viewport.onlostpointercapture = () => {
    pan = null;
    viewport.classList.remove("panning");
  };
  showStep(step, false);
  fit();
}
