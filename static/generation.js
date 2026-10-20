"use strict";

let generationDetailsOpen = false;

function addGenerationDetails(box, run, index) {
  const details = make("details", "", "generation-details");
  const panel = make("div");
  details.append(make("summary", "Поколение " + run.history[index].generation), panel);
  details.open = generationDetailsOpen;
  details.ontoggle = () => {
    generationDetailsOpen = details.open;
    if (details.open && !panel.children.length) renderGenerationDetails(panel, run, index);
  };
  box.append(details);
  if (details.open) renderGenerationDetails(panel, run, index);
}

function renderGenerationDetails(box, run, index) {
  const stage = run.history[index];
  const before = index ? run.history[index - 1].population : [];
  const formatPlan = (id) => id === null ? "не найден" : "П" + (id + 1);
  function price(id) {
    if (id === null) return "—";
    return run.plans[id].valid ? money(run.plans[id].cost) : "недопустим";
  }
  const controls = make("div", "", "controls");
  function chooseGeneration(value) {
    stages.genetic = value;
    renderRun("genetic");
  }
  addButton(controls, "Предыдущее поколение", () => chooseGeneration(index - 1)).disabled = index === 0;
  const label = make("label", "Поколение");
  const generation = make("select");
  run.history.forEach((item, i) => {
    const option = make("option", item.generation + " · " + money(item.bestCost));
    option.value = i;
    generation.append(option);
  });
  generation.value = index;
  generation.onchange = () => chooseGeneration(Number(generation.value));
  label.append(generation);
  controls.append(label);
  addButton(controls, "Следующее поколение", () => chooseGeneration(index + 1)).disabled = index === run.history.length - 1;
  box.append(controls, make("p", index === 0 ? "Начальная популяция." :
    run.selectionMethod === "best_half" ? "Верхняя половина по стоимости — родители, нижняя — резерв." :
      "Родитель — самый дешевый участник турнира из максимум трех планов."));
  box.append(make("p", "Порядок контейнеров: " + task.containers.map((c) => c.id).join(", ") +
    ". В хромосоме указаны площадки. В паре всегда разные родители."));

  function populationTable(title, ids, roles = false) {
    const section = make("details");
    section.append(make("summary", title + " (" + ids.length + ")"));
    const scroll = make("div", "", "scroll");
    const table = make("table");
    const head = make("tr");
    for (const text of ["План", "Стоимость", "Хромосома", ...(roles ? ["Отбор"] : [])]) head.append(make("th", text));
    table.append(head);
    const eligible = new Set(stage.parentPool);
    const used = new Set(stage.events.flatMap((event) => event.parents || []));
    const reserved = new Set(stage.events.filter((event) => event.kind === "reserve").map((event) => event.result));
    const carried = new Set(stage.events.filter((event) => event.kind === "carry").map((event) => event.result));
    function role(id) {
      if (reserved.has(id)) return run.selectionMethod === "best_half"
        ? "Из резерва нижней половины" : "Из резерва; исключен из родителей";
      if (used.has(id)) return "Выбран родителем";
      if (carried.has(id)) return "Добран из резерва";
      if (eligible.has(id)) return "Доступен для выбора";
      return run.selectionMethod === "best_half" ? "Резерв нижней половины" : "Не использован";
    }
    [...ids].sort((a, b) => run.plans[a].cost - run.plans[b].cost).forEach((id) => {
      const row = make("tr");
      row.append(make("td", formatPlan(id)), make("td", price(id)),
        make("td", run.plans[id].chromosome.map((j) => task.sites[j].id).join(" ")));
      if (roles) row.append(make("td", role(id)));
      table.append(row);
    });
    scroll.append(table);
    section.append(scroll);
    box.append(section);
  }
  if (before.length) populationTable("Популяция до отбора", before, true);

  const kinds = { manual: "Ручной план", initial: "Начальный поиск", elite: "Сохранение лучшего",
    crossover: "Скрещивание", reserve: "Резерв после исправления",
    carry: "Добор из прежней популяции", generate: "Поиск нового плана",
    refresh: "Новый план после повторения популяции" };
  const statuses = { accepted: "Добавлен в популяцию", duplicate: "Отклонен: повтор",
    retired: "Отклонен: выбывший план", not_found: "План не найден" };
  box.append(make("h4", "Действия поколения"));
  const actions = make("div", "", "controls");
  const actionLabel = make("label", "Действие поколения");
  const action = make("select");
  stage.events.forEach((event, i) => {
    const option = make("option", (i + 1) + ". " + kinds[event.kind] + " · " + statuses[event.status]);
    option.value = i;
    action.append(option);
  });
  actionLabel.append(action);
  const previous = addButton(actions, "Предыдущее действие", () => showAction(Number(action.value) - 1));
  actions.append(actionLabel);
  const next = addButton(actions, "Следующее действие", () => showAction(Number(action.value) + 1));
  const preview = make("div", "", "preview");
  box.append(actions, preview);
  action.onchange = () => showAction(Number(action.value));

  function showAction(value) {
    action.value = value;
    previous.disabled = value === 0;
    next.disabled = value === stage.events.length - 1;
    const event = stage.events[value];
    preview.replaceChildren(make("h4", kinds[event.kind] + ": " + statuses[event.status]));
    const columns = [];
    if (event.parents) {
      event.parents.forEach((id, i) => {
        columns.push({ label: "Родитель " + (i + 1), id });
        const participants = event.participants[i];
        if (participants.length) preview.append(make("p", "Турнир " + (i + 1) + ": " +
          participants.map((p) => formatPlan(p) + " (" + price(p) + ")").join("; ") + ". Победитель: " + formatPlan(id) + "."));
      });
      columns.push({ label: "После скрещивания", id: event.crossed, compare: event.parents[0] });
      if ("repaired" in event) {
        columns.push({ label: "После исправления", id: event.repaired, compare: event.crossed });
        preview.append(make("p", "Исправление: " + fmt.format(event.repairNodes) + " проверок назначений." +
          (event.repairLimited ? " Достигнут предел 5 000 проверок." : "")));
        if ("reserve" in event) {
          preview.append(make("p", event.reserve === null ? "Резерв пуст; выбирается следующая пара." :
            "Замена из резерва: " + formatPlan(event.reserve) +
            (run.selectionMethod === "best_half" ? " из нижней половины." :
              "; в этом поколении больше не выбирается родителем.")));
          if (event.reserve !== null) columns.push({ label: "Из резерва", id: event.reserve });
        }
      } else preview.append(make("p", "Исправление не требуется."));
      if (event.mutation) {
        const messages = { disabled: "Мутации выключены.", skipped: "Мутация пропущена.",
          changed: "Мутация изменила план.", unchanged: "Допустимой мутации нет." };
        preview.append(make("p", messages[event.mutation] + (event.mutationAttempts ?
          " Попыток: " + event.mutationAttempts + ". Пропущено выбывших планов: " + event.mutationRetiredSkips + "." : "")));
        columns.push({ label: "После мутации", id: event.result, compare: columns.at(-1).id });
      }
    } else if (event.result !== null) columns.push({ label: "План", id: event.result });
    if (event.kind === "refresh") preview.append(make("p",
      "После поколения без новых особей. Все прежние и выбывшие планы исключены; лучший сохранен."));
    if (event.nodes !== undefined) preview.append(make("p", "Проверок назначений: " + fmt.format(event.nodes) +
      (event.limited ? ". Поиск остановлен по пределу проверок." : ". Поиск этой попытки завершен.")));
    if (event.kind === "carry") preview.append(make("p", run.selectionMethod === "best_half" ?
      "Добор из нижней половины." :
      "План не выбирался родителем и еще не добавлен."));
    if (event.kind === "reserve") preview.append(make("p", run.selectionMethod === "best_half" ?
      "Исправление не удалось. Взят самый дешевый доступный план нижней половины." :
      "Исправление не удалось. Взят самый дешевый неиспользованный план; из родителей он исключен."));
    if (event.kind === "elite") preview.append(make("p", "Лучший план сохранен."));
    if (!columns.length) return;
    const scroll = make("div", "", "scroll");
    const table = make("table");
    const head = make("tr");
    head.append(make("th", "Контейнер"));
    columns.forEach((column) => head.append(make("th", column.label + " · " + formatPlan(column.id) + " · " + price(column.id))));
    table.append(head);
    task.containers.forEach((container, i) => {
      const row = make("tr");
      row.append(make("td", container.id));
      columns.forEach((column) => {
        const j = column.id === null ? null : run.plans[column.id].chromosome[i];
        const changed = column.compare != null && j !== null && j !== run.plans[column.compare].chromosome[i];
        row.append(make("td", j === null ? "—" : task.sites[j].id, changed ? "gene-changed" : ""));
      });
      table.append(row);
    });
    scroll.append(table);
    preview.append(scroll);
    if (event.parents) preview.append(make("p", "Рамка — изменение: скрещивание относительно родителя 1, дальше относительно предыдущего этапа."));
  }
  showAction(0);
  populationTable("Итоговая популяция", stage.population);
  populationTable("Планы, выбывшие в этом поколении", stage.discarded);
  box.append(make("p", "Выбывшие планы не возвращаются в этом запуске."));
}
