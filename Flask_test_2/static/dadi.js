(() => {
  "use strict";

  // ---- Helpers DOM ----
  const $ = (id) => document.getElementById(id);

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function rollDie(sides) {
    return Math.floor(Math.random() * sides) + 1;
  }

  function setDisabled(isRolling) {
    // Disabilita controlli durante l'animazione per evitare spam-click
    const ids = ["rollBtn", "clearBtn", "preset", "count", "mod", "adv"];
    for (const id of ids) {
      const el = $(id);
      if (el) el.disabled = isRolling;
    }
  }

  function getInputs() {
    const sides = parseInt($("preset")?.value ?? "20", 10);
    const count = clamp(parseInt($("count")?.value ?? "1", 10) || 1, 1, 50);
    const mod = clamp(parseInt($("mod")?.value ?? "0", 10) || 0, -50, 50);
    const advMode = $("adv")?.value ?? "normal";
    return { sides, count, mod, advMode };
  }

  // ---- Animazione "fake roll" (numero che cambia mentre anima) ----
    function animateRoll({ sides, count, durationMs, tickMs }) {
      const container = $("diceContainer");
      const out = $("out");
      if (!container) return Promise.resolve();

      // Crea N dadi placeholder
      container.innerHTML = "";
      const diceEls = [];
      for (let i = 0; i < count; i++) {
        const die = document.createElement("div");
        die.className = "dice-face pop";          // usa già la tua animazione
        die.style.animationDelay = `${i * 70}ms`; // sfalsamento
        die.textContent = "?";
        container.appendChild(die);
        diceEls.push(die);
      }

      return new Promise((resolve) => {
        const start = Date.now();

        const timer = setInterval(() => {
          const t = Date.now() - start;

          // Aggiorna ogni dado con un valore fake
          for (let i = 0; i < diceEls.length; i++) {
            diceEls[i].textContent = rollDie(sides);
          }

          // fallback testo
          if (out) out.innerHTML = `<div class="muted">Tiro in corso…</div>`;

          if (t >= durationMs) {
            clearInterval(timer);
            resolve();
          }
        }, tickMs);
      });
    }
  // ---- Logica tiro reale (come la tua) ----
function renderResult({ sides, count, mod, advMode, rolls, sum, total, advExtra }) {
  const out = $("out");
  const container = $("diceContainer");
  if (!container || !out) return;

  container.innerHTML = "";

  // Helper per creare un dado con animazione + classi speciali
      function addDie(value, i, { isD20Nat = false } = {}) {
        const die = document.createElement("div");
        die.className = "dice-face pop";
        die.textContent = value;

        // Delay sfalsato (effetto "uno dopo l'altro")
        die.style.animationDelay = `${i * 70}ms`;

        // Critico/fail solo per d20 naturale
        if (isD20Nat && value === 20) die.classList.add("crit");
        if (isD20Nat && value === 1) die.classList.add("fail");

        container.appendChild(die);
      }

      // Caso vantaggio/svantaggio: è sempre 1d20 naturale (il "chosen")
      if (advExtra && sides === 20 && count === 1 && (advMode === "adv" || advMode === "dis")) {
        addDie(advExtra.chosen, 0, { isD20Nat: true });

        out.innerHTML =
          `Tiro: 1d20 (${advMode === "adv" ? "vantaggio" : "svantaggio"}) ${mod >= 0 ? "+" : ""}${mod}\n` +
          `Dadi: [${advExtra.a}, ${advExtra.b}] → scelto: ${advExtra.chosen}\n` +
          `<div class="big">Totale: ${total}</div>`;
        return;
      }

      // Tiro normale
      const isD20Nat = (sides === 20 && count === 1); // naturale solo se 1d20
      for (let i = 0; i < rolls.length; i++) {
        addDie(rolls[i], i, { isD20Nat });
      }

      out.innerHTML =
        `Tiro: ${count}d${sides} ${mod >= 0 ? "+" : ""}${mod}\n` +
        `Dadi: [${rolls.join(", ")}]\n` +
        `<div class="big">Totale: ${total}</div>`;
    }

  async function rollAnimated() {
    const { sides, count, mod, advMode } = getInputs();

    setDisabled(true);

    // durata animazione (un filo più lunga per multi-dado)
    const durationMs = count > 1 ? 900 : 650;
    await animateRoll({ sides, count, durationMs, tickMs: 60 });

    // Caso speciale: vantaggio/svantaggio solo 1d20
    if (sides === 20 && count === 1 && (advMode === "adv" || advMode === "dis")) {
      const a = rollDie(20);
      const b = rollDie(20);
      const chosen = advMode === "adv" ? Math.max(a, b) : Math.min(a, b);
      const total = chosen + mod;

      renderResult({
        sides,
        count,
        mod,
        advMode,
        rolls: [chosen],
        sum: chosen,
        total,
        advExtra: { a, b, chosen },
      });

      setDisabled(false);
      return;
    }

    // Normale (anche multi-dado)
    const rolls = [];
    let sum = 0;
    for (let i = 0; i < count; i++) {
      const r = rollDie(sides);
      rolls.push(r);
      sum += r;
    }
    const total = sum + mod;

    renderResult({ sides, count, mod, advMode, rolls, sum, total });
    setDisabled(false);
  }

  function resetUI() {
      const preset = $("preset");
      const count = $("count");
      const mod = $("mod");
      const adv = $("adv");
      const out = $("out");
      const container = $("diceContainer");

      if (preset) preset.value = "20";
      if (count) count.value = "1";
      if (mod) mod.value = "0";
      if (adv) adv.value = "normal";

      if (container) container.innerHTML = "";
      if (out) out.innerHTML = `<div class="muted">Reset fatto.</div>`;
  }
  // ---- Init ----
  document.addEventListener("DOMContentLoaded", () => {
    const rollBtn = $("rollBtn");
    const clearBtn = $("clearBtn");

    if (rollBtn) rollBtn.addEventListener("click", rollAnimated);
    if (clearBtn) clearBtn.addEventListener("click", resetUI);
  });
})();