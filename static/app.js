"use strict";

let task;
let calculation;
let selected = "";
let revision = 0;
let requestId = 0;
let drag = null;
let ignoreClickUntil = 0;
let exhaustiveController = null;
const runs = { genetic: null, branch_bound: null, exhaustive: null };
const stages = { genetic: 0, branch_bound: 0, exhaustive: 0 };
const fmt = new Intl.NumberFormat("ru-RU");
const $ = (id) => document.getElementById(id);
const money = (value) => fmt.format(value) + " ₽";

function make(tag, text = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}

function cell(row, value) {
  const td = make("td");
  if (value instanceof Node) td.append(value);
  else td.textContent = value;
  row.append(td);
}

async function post(path, data) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Ошибка сервера");
  return body;
}

async function postStream(data, onProgress, signal) {
  const response = await fetch("/api/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, stream: true }),
    signal
  });
  if (!response.ok) throw new Error("Ошибка сервера");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let answer;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    let end;
    while ((end = pending.indexOf("\n")) >= 0) {
      const event = JSON.parse(pending.slice(0, end));
      pending = pending.slice(end + 1);
      if (event.type === "progress") onProgress(event);
      else if (event.type === "result") answer = event.result;
      else if (event.type === "error") throw new Error(event.error);
    }
  }
  if (!answer) throw new Error("Сервер не вернул результат перебора.");
  return answer;
}

function resetRuns() {
  if (exhaustiveController) exhaustiveController.abort();
  $("exhaustive-progress").replaceChildren();
  revision++;
  for (const method in runs) runs[method] = null;
  $("bb-start").checked = false;
  $("bb-start").disabled = true;
}

function numberField(value, label, change) {
  const input = make("input");
  input.type = "number";
  input.min = "0";
  input.max = "1000000";
  input.step = "1";
  input.value = value;
  input.setAttribute("aria-label", label);
  input.oninput = () => {
    change(Number(input.value));
    resetRuns();
    refresh();
  };
  return input;
}

function removeButton(label, action) {
  const button = make("button", "×");
  button.title = label;
  button.setAttribute("aria-label", label);
  button.onclick = action;
  return button;
}

function renderEditors() {
  const containers = $("containers-body");
  const sites = $("sites-body");
  containers.replaceChildren();
  sites.replaceChildren();

  for (const c of task.containers) {
    const row = make("tr");
    cell(row, c.id);
    for (const [key, label] of [["weight", "Масса"], ["power", "Мощность"], ["storage", "Хранение"]]) {
      cell(row, numberField(c[key], label + " " + c.id, (value) => { c[key] = value; }));
    }
    cell(row, removeButton("Удалить " + c.id, () => {
      if (task.containers.length === 1) return message("Нужен хотя бы один контейнер.");
      task.containers = task.containers.filter((item) => item.id !== c.id);
      delete task.assignment[c.id];
      selected = "";
      resetRuns();
      renderEditors();
      refresh();
    }));
    containers.append(row);
  }

  for (const site of task.sites) {
    const row = make("tr");
    cell(row, site.id);
    for (const [key, label] of [
      ["places", "Места"], ["massLimit", "Масса"], ["powerLimit", "Мощность"],
      ["storageRate", "Тариф хранения"], ["travelTime", "Время пути"], ["travelRate", "Тариф перевозки"]
    ]) {
      cell(row, numberField(site[key], label + " площадки " + site.id, (value) => { site[key] = value; }));
    }
    cell(row, removeButton("Удалить площадку " + site.id, () => {
      if (task.sites.length === 1) return message("Нужна хотя бы одна площадка.");
      task.sites = task.sites.filter((item) => item.id !== site.id);
      for (const id in task.assignment) {
        if (task.assignment[id] === site.id) task.assignment[id] = null;
      }
      resetRuns();
      renderEditors();
      refresh();
    }));
    sites.append(row);
  }
  $("limit-hours").value = task.limitHours;
  $("tariff-mode").value = task.tariffMode;
}

function message(text) {
  $("message").textContent = text;
}

async function refresh() {
  const current = ++requestId;
  try {
    const next = await post("/api/evaluate", task);
    if (current !== requestId) return;
    calculation = next;
    message("");
  } catch (error) {
    if (current !== requestId) return;
    calculation = null;
    message(error.message);
  }
  renderBoard();
  renderSummary();
  renderCosts();
  for (const method in runs) renderRun(method);
}

function move(id, siteId) {
  task.assignment[id] = siteId;
  selected = "";
  refresh();
}

function renderBoard() {
  const board = $("board");
  board.replaceChildren();
  for (const site of task.sites) {
    const load = calculation && calculation.loads.find((item) => item.id === site.id);
    const card = make("article", "", "site");
    card.dataset.site = site.id;
    card.tabIndex = 0;
    card.append(make("h3", "Площадка " + site.id));
    card.append(make("p", load ? money(load.cost) : "—", "site-cost"));
    card.append(make("p", "Места: " + (load ? load.count : 0) + " / " + site.places));
    card.append(make("p", "Масса: " + (load ? load.weight : 0) + " / " + site.massLimit + " т"));
    card.append(make("p", "Мощность: " + (load ? load.power : 0) + " / " + site.powerLimit + " кВт"));
    if (load && load.issues.length) card.classList.add("invalid");
    for (const c of task.containers) {
      if (task.assignment[c.id] === site.id) card.append(chip(c.id));
    }
    board.append(card);
  }
  const tray = make("div", "", "site tray");
  tray.dataset.site = "";
  tray.tabIndex = 0;
  tray.append(make("h3", "Без площадки"));
  for (const c of task.containers) {
    if (!task.sites.some((site) => site.id === task.assignment[c.id])) tray.append(chip(c.id));
  }
  board.append(tray);
}

function chip(id) {
  const button = make("button", id, "chip");
  button.dataset.id = id;
  if (selected === id) button.classList.add("selected");
  return button;
}

$("board").onclick = (event) => {
  if (Date.now() < ignoreClickUntil) return;
  const chipButton = event.target.closest(".chip");
  if (chipButton) {
    selected = selected === chipButton.dataset.id ? "" : chipButton.dataset.id;
    for (const node of document.querySelectorAll(".chip")) {
      node.classList.toggle("selected", node.dataset.id === selected);
    }
    return;
  }
  const site = event.target.closest("[data-site]");
  if (selected && site) move(selected, site.dataset.site || null);
};

$("board").onkeydown = (event) => {
  if (selected && (event.key === "Enter" || event.key === " ") && event.target.matches("[data-site]")) {
    event.preventDefault();
    move(selected, event.target.dataset.site || null);
  }
};

// Один обработчик перетаскивания работает и с мышью, и с касанием.
$("board").onpointerdown = (event) => {
  const button = event.target.closest(".chip");
  if (button && event.button === 0) {
    drag = { id: button.dataset.id, x: event.clientX, y: event.clientY, ghost: null };
  }
};

document.onpointermove = (event) => {
  if (!drag) return;
  if (!drag.ghost && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 6) return;
  if (!drag.ghost) {
    drag.ghost = make("div", drag.id, "ghost");
    document.body.append(drag.ghost);
  }
  event.preventDefault();
  drag.ghost.style.left = event.clientX + 12 + "px";
  drag.ghost.style.top = event.clientY + 12 + "px";
  for (const card of document.querySelectorAll("[data-site]")) card.classList.remove("over");
  const target = document.elementFromPoint(event.clientX, event.clientY);
  target?.closest("[data-site]")?.classList.add("over");
};

document.onpointerup = (event) => {
  if (!drag) return;
  const id = drag.id;
  const active = Boolean(drag.ghost);
  drag.ghost?.remove();
  drag = null;
  for (const card of document.querySelectorAll("[data-site]")) card.classList.remove("over");
  if (active) {
    ignoreClickUntil = Date.now() + 400;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-site]");
    if (target) move(id, target.dataset.site || null);
  }
};
document.onpointercancel = () => {
  drag?.ghost?.remove();
  drag = null;
  for (const card of document.querySelectorAll("[data-site]")) card.classList.remove("over");
};

function renderSummary() {
  $("total-cost").textContent = calculation ? money(calculation.totalCost) : "—";
  $("evaluation-time").textContent = calculation ? "Время пересчёта: " + seconds(calculation.elapsedSeconds) : "";
  $("plan-status").textContent = !calculation ? "Проверьте данные" :
    calculation.valid ? "План допустим" : "План недопустим";
  const issues = $("issues");
  issues.replaceChildren();
  if (calculation) {
    for (const issue of calculation.issues) issues.append(make("li", issue));
  }
}

function renderCosts() {
  const body = $("cost-body");
  body.replaceChildren();
  if (!calculation) return;
  for (const item of calculation.rows) {
    const row = make("tr");
    for (const value of [item.id, item.site || "—", money(item.storageCost),
      money(item.travelCost), money(item.cost)]) cell(row, value);
    const select = make("select");
    select.setAttribute("aria-label", "Площадка для " + item.id);
    const none = make("option", "Без площадки");
    none.value = "";
    select.append(none);
    for (const site of task.sites) {
      const option = make("option", site.id);
      option.value = site.id;
      select.append(option);
    }
    select.value = item.site || "";
    select.onchange = () => move(item.id, select.value || null);
    cell(row, select);
    body.append(row);
  }
}

function svgElement(tag, attributes, text = "") {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const name in attributes) node.setAttribute(name, attributes[name]);
  node.textContent = text;
  return node;
}

function plot(records, keys, index, title) {
  const values = records.flatMap((item) => keys.map((key) => item[key]).filter((value) => value !== null));
  if (!values.length) return make("p", "Допустимый план пока не найден.");
  const low = keys.length === 1 ? Math.min(...values) : 0;
  const range = Math.max(1, Math.max(...values) - low);
  const svg = svgElement("svg", { viewBox: "0 0 640 180", role: "img", "aria-label": title });
  const x = (i) => 15 + i * 610 / Math.max(1, records.length - 1);
  const y = (value) => 155 - (value - low) * 125 / range;
  keys.forEach((key, color) => {
    const points = records.map((item, i) => item[key] === null ? "" : x(i) + "," + y(item[key])).filter(Boolean);
    svg.append(svgElement("polyline", { points: points.join(" "), class: "line line-" + color }));
    if (records[index][key] !== null) {
      svg.append(svgElement("circle", { cx: x(index), cy: y(records[index][key]), r: 5, class: "dot dot-" + color }));
    }
  });
  return svg;
}

function metric(name, value) {
  const box = make("div", "", "metric");
  box.append(make("small", name), make("strong", value));
  return box;
}

function addSearchTree(box, run) {
  const button = make("button", "Показать дерево поиска");
  const panel = make("div", "", "search-tree");
  panel.hidden = true;
  button.setAttribute("aria-expanded", "false");
  button.onclick = () => {
    panel.hidden = !panel.hidden;
    button.textContent = panel.hidden ? "Показать дерево поиска" : "Скрыть дерево поиска";
    button.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden && !panel.children.length) renderSearchTree(panel, run);
  };
  box.append(button, panel);
}

function renderSearchTree(box, run) {
  const tree = run.tree;
  const names = { branch: "Разветвление", bound: "Отсечено по стоимости",
    capacity: "Нет допустимого продолжения", plan: "Новый лучший план", limit: "Лимит узлов" };
  box.append(make("p", "Узел — очередное назначение контейнера. № — порядок проверки. Пунктир — отсечение, тёмная рамка — назначения итогового плана. Нажмите узел или выберите шаг ползунком."));
  if (run.treeTruncated) box.append(make("p", "Сохранены первые " + run.treeLimit + " шагов дерева. Сам поиск продолжался; схема показана частично."));
  if (run.status.startsWith("limit")) box.append(make("p", "Поиск остановлен по лимиту. Непроверенные продолжения в схему не входят."));
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
  const controls = make("div", "", "controls");
  const previous = make("button", "Предыдущий шаг");
  const next = make("button", "Следующий шаг");
  const zoom = make("select");
  zoom.setAttribute("aria-label", "Масштаб дерева");
  for (const scale of [0.5, 1, 1.5]) {
    const option = make("option", scale * 100 + "%");
    option.value = scale;
    zoom.append(option);
  }
  zoom.value = "1";
  controls.append(previous, next, zoom);
  const label = make("label", "Шаг дерева", "stage");
  const slider = make("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(tree.length - 1);
  slider.value = slider.max;
  label.append(slider);
  const description = make("div", "", "preview");
  const viewport = make("div", "", "tree-viewport");
  box.append(controls, label, description, viewport);
  function draw() {
    const step = Number(slider.value);
    const active = tree[step];
    const assignments = pathTo(step).reverse().filter((node) => node.container)
      .map((node) => node.container + " → " + node.site);
    description.replaceChildren(make("p", "Шаг " + (step + 1) + " из " + tree.length + ": " + names[active.status]),
      make("p", "Путь: " + (assignments.join("; ") || "корень — контейнеры ещё не размещены")),
      make("p", "Стоимость назначений: " + money(active.cost) + ". Нижняя оценка: " + (active.lowerBound === null ? "не вычислена" : money(active.lowerBound)) +
        ". Лучший план к этому шагу: " + (active.bestCost === null ? "пока нет" : money(active.bestCost)) + "."));
    if (active.status === "bound") description.append(make("p", "Нижняя оценка не меньше стоимости известного плана: продолжение не даст более дешёвого размещения."));
    if (active.status === "capacity") description.append(make("p", "Нарушено ограничение либо одному из оставшихся контейнеров не подходит ни одна площадка."));
    const svg = svgElement("svg", { viewBox: "0 0 " + width + " " + height, role: "img", "aria-label": "Дерево ветвей и границ" });
    const scale = Number(zoom.value);
    svg.style.width = width * scale + "px";
    svg.style.height = height * scale + "px";
    tree.slice(0, step + 1).forEach((node, i) => {
      const x = node.depth * 250 + 10;
      if (node.parent !== null) svg.append(svgElement("line", {
        x1: tree[node.parent].depth * 250 + 230, y1: y[node.parent], x2: x, y2: y[i], class: "tree-edge" }));
      const onBestPath = run.bestAssignment && pathTo(i).every((item) => !item.container || run.bestAssignment[item.container] === item.site);
      const group = svgElement("g", { class: "tree-node " + node.status + (onBestPath ? " best-path" : "") + (i === step ? " active" : "") });
      group.append(svgElement("rect", { x, y: y[i] - 36, width: 220, height: 72, rx: 5 }),
        svgElement("text", { x: x + 9, y: y[i] - 17 }, (i === step ? "▶ " : "") + "№" + (i + 1) + " " + (node.container ? node.container + " → " + node.site : "Корень")),
        svgElement("text", { x: x + 9, y: y[i] + 2 }, "Цена " + fmt.format(node.cost) + "; оценка " + (node.lowerBound === null ? "—" : fmt.format(node.lowerBound))),
        svgElement("text", { x: x + 9, y: y[i] + 22 }, names[node.status]));
      group.onclick = () => { slider.value = i; draw(); };
      svg.append(group);
    });
    viewport.replaceChildren(svg);
    viewport.scrollLeft = Math.max(0, active.depth * 250 * scale - 30);
    viewport.scrollTop = Math.max(0, y[step] * scale - viewport.clientHeight / 2);
    previous.disabled = step === 0;
    next.disabled = step === tree.length - 1;
  }
  function pathTo(i) {
    const path = [];
    for (; i !== null; i = tree[i].parent) path.push(tree[i]);
    return path;
  }
  previous.onclick = () => { slider.value = Number(slider.value) - 1; draw(); };
  next.onclick = () => { slider.value = Number(slider.value) + 1; draw(); };
  slider.oninput = zoom.onchange = draw;
  draw();
}

function duration(seconds) {
  if (seconds < 60) return Math.ceil(seconds) + " с";
  if (seconds < 3600) return Math.ceil(seconds / 60) + " мин";
  if (seconds < 86400) return Math.ceil(seconds / 3600) + " ч";
  if (seconds < 31536000) return Math.ceil(seconds / 86400) + " сут";
  return "более года";
}

function seconds(value) {
  return value < 0.001 ? "< 0,001 с" : value.toFixed(3).replace(".", ",") + " с";
}

function renderExhaustiveProgress(state, finished = false) {
  const box = $("exhaustive-progress");
  const done = BigInt(state.checkedCount);
  const total = BigInt(state.totalCombinations);
  const percent = Number(done * 10000n / total) / 100;
  const speed = state.elapsedSeconds ? state.checkedCount / state.elapsedSeconds : 0;
  const remaining = speed ? duration(Number(total - done) / speed) : "—";
  const bar = make("progress");
  bar.max = 100;
  bar.value = percent;
  const stats = make("div", "", "metrics");
  stats.append(metric("Проверено", fmt.format(done) + " / " + fmt.format(total)),
    metric("Прогресс", percent === 0 && done > 0 ? "< 0,01 %" : percent + " %"),
    metric("Процессов", fmt.format(state.workers)),
    metric("Скорость", speed ? fmt.format(Math.round(speed)) + " назнач./с" : "—"),
    metric("Прошло", seconds(state.elapsedSeconds)),
    metric("Осталось примерно", finished ? "0 с" : remaining));
  box.replaceChildren(make("p", finished ? "Перебор завершён" : "Перебор выполняется"), bar, stats);
}

function renderRun(method) {
  const box = $(method + "-result");
  box.replaceChildren();
  const run = runs[method];
  if (!run) return;
  if (run.error) return box.append(make("p", run.error));
  const hasPlan = run.bestCost !== undefined;
  let title = "План пока не найден";
  if (run.provenOptimal) title = "Доказанный минимум: " + money(run.bestCost);
  else if (hasPlan) title = "Лучший найденный план: " + money(run.bestCost);
  else if (run.provenInfeasible) title = "Допустимого плана нет";
  box.append(make("h3", title));
  box.append(make("p", "Время расчёта: " + seconds(run.elapsedSeconds)));
  if (run.message) box.append(make("p", run.message));
  if (method === "genetic") {
    const selection = run.selectionMethod === "best_half" ? "лучшая половина" : "турнир из трёх";
    box.append(make("p", "Отбор родителей: " + selection + "."));
    const mutation = run.mutationType === "swap" ? "обмен двух контейнеров" : "перенос контейнера";
    box.append(make("p", run.mutationEnabled ? "Мутация: " + mutation + ". Вероятность: " + run.mutationProbability + "%." : "Мутации выключены."));
    if (run.mutationEnabled && run.mutationProbability > 0 &&
        run.history?.every((stage) => stage.mutations === 0)) {
      box.append(make("p", "За этот запуск допустимых мутаций выбранного типа не получилось. Вероятность задаёт попытку, а не гарантирует изменение плана."));
    }
  }
  if (hasPlan && calculation?.valid) {
    box.append(make("p", "Текущий план: " + money(calculation.totalCost)));
  }
  if (method === "branch_bound") {
    box.append(make("p", "Начальный план: " + run.initialSource + ". Лимит узлов: " + fmt.format(run.nodeLimit) + "."));
    if (run.tree?.length) addSearchTree(box, run);
  }
  if (method === "exhaustive") {
    box.append(make("p", "Всего назначений: " + fmt.format(BigInt(run.totalCombinations)) +
      ". Проверено: " + fmt.format(run.checkedCount) + "."));
  }

  const records = run.history || [];
  if (!records.length) return;
  const index = Math.min(stages[method], records.length - 1);
  const stage = records[index];
  box.append(make("h4", "Лучшая стоимость"));
  box.append(plot(records, ["bestCost"], index, "Лучшая стоимость по этапам"));
  if (method === "branch_bound") {
    box.append(make("h4", "Отсечённые ветви"));
    box.append(plot(records, ["prunedBound", "prunedCapacity"], index, "Отсечения по оценке и ресурсам"));
    box.append(make("p", "Тёмная линия — по оценке, светлая — по ресурсам."));
  }
  const event = stage.event || "Поколение " + stage.generation;
  const label = make("label", "Этап " + (index + 1) + " из " + records.length + ": " + event, "stage");
  const slider = make("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(records.length - 1);
  slider.value = String(index);
  slider.onchange = () => { stages[method] = Number(slider.value); renderRun(method); };
  label.append(slider);
  box.append(label);

  const stats = make("div", "", "metrics");
  if (method === "genetic") {
    stats.append(metric("Поколение", stage.generation), metric("Разных планов", stage.distinctPlans + " / " + run.populationSize),
      metric("Скрещивания", stage.crossovers), metric("Мутации", stage.mutations),
      metric("Исправления", stage.repairs), metric("Разных родителей", stage.parentsUsed),
      metric("Добрано из прежних", stage.carriedOver));
    if (stage.generation === 0) {
      stats.append(metric("Попыток начального поиска", fmt.format(run.initialAttempts)),
        metric("Проверок назначений", fmt.format(run.initialNodesVisited)));
    }
  } else if (method === "branch_bound") {
    stats.append(metric("Узлов", fmt.format(stage.nodesVisited)),
      metric("Отсечено по оценке", fmt.format(stage.prunedBound)),
      metric("Отсечено по ресурсам", fmt.format(stage.prunedCapacity)),
      metric("Глубина", stage.depth + " / " + task.containers.length));
  } else {
    stats.append(metric("Проверено", fmt.format(stage.checkedCount)),
      metric("Допустимо", fmt.format(stage.validCount)),
      metric("Недопустимо", fmt.format(stage.invalidCount)));
    const percent = Number(BigInt(stage.checkedCount) * 10000n / BigInt(run.totalCombinations)) / 100;
    const progress = make("progress");
    progress.max = 100;
    progress.value = percent;
    box.append(progress);
  }
  stats.append(metric("Лучшая цена", stage.bestCost === null ? "Пока нет" : money(stage.bestCost)));
  box.append(stats);

  if (stage.bestChromosome) {
    const preview = make("div", "", "preview");
    task.sites.forEach((site, j) => {
      const ids = task.containers.filter((_, i) => stage.bestChromosome[i] === j).map((c) => c.id);
      preview.append(make("p", "Площадка " + site.id + ": " + (ids.join(", ") || "—")));
    });
    box.append(preview);
  }
  if (run.bestAssignment) {
    const button = make("button", "Применить лучший план");
    button.onclick = () => { task.assignment = { ...run.bestAssignment }; refresh(); };
    box.append(button);
  }
}

async function runMethod(method) {
  const buttons = { genetic: "ga-run", branch_bound: "bb-run", exhaustive: "full-run" };
  const button = $(buttons[method]);
  let options;
  if (method === "genetic") {
    options = {
      generations: Number($("ga-generations").value),
      populationSize: Number($("ga-population").value),
      seed: Number($("ga-seed").value),
      selectionMethod: $("ga-selection").value,
      mutationEnabled: $("ga-mutation-enabled").checked,
      mutationType: $("ga-mutation-type").value,
      mutationProbability: Number($("ga-mutation-probability").value)
    };
  } else if (method === "branch_bound") {
    options = { nodeLimit: Number($("bb-limit").value) };
  } else {
    options = { workers: Number($("full-workers").value) };
  }
  if (method === "branch_bound" && $("bb-start").checked && runs.genetic?.bestAssignment) {
    options.incumbentAssignment = runs.genetic.bestAssignment;
  }
  const started = revision;
  const controller = method === "exhaustive" ? new AbortController() : null;
  if (controller) {
    exhaustiveController = controller;
    $("full-stop").hidden = false;
    $("exhaustive-progress").replaceChildren();
  }
  button.disabled = true;
  const pending = make("p", "Вычисляется…");
  $(method + "-result").replaceChildren(pending);
  const began = performance.now();
  const timer = setInterval(() => {
    if (started === revision) pending.textContent = "Вычисляется… Прошло: " + seconds((performance.now() - began) / 1000);
  }, 250);
  try {
    const answer = controller
      ? await postStream({ method, task, options }, (state) => {
          if (started === revision) renderExhaustiveProgress(state);
        }, controller.signal)
      : await post("/api/solve", { method, task, options });
    if (started !== revision) return;
    runs[method] = answer;
    stages[method] = Math.max(0, (answer.history || []).length - 1);
    if (controller) renderExhaustiveProgress(answer, true);
    if (method === "genetic") $("bb-start").disabled = !answer.bestAssignment;
  } catch (error) {
    if (started === revision) {
      runs[method] = { error: error.name === "AbortError" ? "Расчёт остановлен." : error.message };
      if (controller) $("exhaustive-progress").replaceChildren();
    }
  } finally {
    clearInterval(timer);
    button.disabled = false;
    if (controller && exhaustiveController === controller) {
      exhaustiveController = null;
      $("full-stop").hidden = true;
    }
    if (started === revision) renderRun(method);
  }
}

function showMethod(method) {
  for (const name of ["manual", "genetic", "branch_bound", "exhaustive"]) {
    $(name + "-panel").hidden = name !== method;
    document.querySelector('[data-method="' + name + '"]').classList.toggle("active", name === method);
  }
}

$("generate-button").onclick = async () => {
  try {
    const next = await post("/api/generate", {
      containerCount: Number($("generate-count").value),
      siteCount: Number($("generate-sites").value),
      seed: Number($("generate-seed").value)
    });
    task = next;
    selected = "";
    resetRuns();
    renderEditors();
    refresh();
  } catch (error) { message(error.message); }
};

$("add-container").onclick = () => {
  if (task.containers.length >= 80) return message("Допустимо не более 80 контейнеров.");
  let n = 1;
  while (task.containers.some((c) => c.id === "К" + String(n).padStart(2, "0"))) n++;
  const id = "К" + String(n).padStart(2, "0");
  task.containers.push({ id, weight: 18, power: 5, storage: 16 });
  task.assignment[id] = null;
  resetRuns();
  renderEditors();
  refresh();
};

$("add-site").onclick = () => {
  if (task.sites.length >= 10) return message("Допустимо не более 10 площадок.");
  const id = [..."ABCDEFGHIJ"].find((name) => !task.sites.some((s) => s.id === name));
  task.sites.push({ id, places: 5, massLimit: 110, powerLimit: 35,
    storageRate: 145, travelTime: 2, travelRate: 550 });
  resetRuns();
  renderEditors();
  refresh();
};

$("limit-hours").oninput = (event) => {
  task.limitHours = Number(event.target.value);
  resetRuns();
  refresh();
};
$("tariff-mode").onchange = (event) => {
  task.tariffMode = event.target.value;
  resetRuns();
  refresh();
};
document.querySelectorAll("[data-method]").forEach((button) => {
  button.onclick = () => showMethod(button.dataset.method);
});
$("ga-run").onclick = () => runMethod("genetic");
function updateMutationControls() {
  const disabled = !$("ga-mutation-enabled").checked;
  $("ga-mutation-type").disabled = disabled;
  $("ga-mutation-probability").disabled = disabled;
}
$("ga-mutation-enabled").onchange = updateMutationControls;
updateMutationControls();
$("bb-run").onclick = () => runMethod("branch_bound");
$("full-run").onclick = () => runMethod("exhaustive");
$("full-stop").onclick = () => exhaustiveController?.abort();

fetch("/api/example").then((response) => response.json()).then((data) => {
  task = data;
  renderEditors();
  refresh();
}).catch((error) => message(error.message));
