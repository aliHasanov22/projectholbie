async function fetchStatus(){
  const res = await fetch("/api/status");
  return await res.json();
}

function applyStatus(data){
  const pcs = document.querySelectorAll("[data-pc]");
  let busyCount = 0;

  pcs.forEach(el => {
    const id = el.dataset.pc;
    const info = data[id];
    if (!info) return;

    const isBusy = info.is_busy === true;
    el.classList.toggle("busy", isBusy);
    el.classList.toggle("free", !isBusy);

    const userSpan = el.querySelector(".pc-user");
    userSpan.textContent = isBusy ? (info.user_name || "In use") : "";

    if (isBusy) busyCount++;
  });

  const total = pcs.length;
  const free = total - busyCount;

  document.getElementById("statusText").textContent =
    `Busy: ${busyCount} • Free: ${free} • Updated: ${new Date().toLocaleTimeString()}`;

  const statsPill = document.getElementById("statsPill");
  if (statsPill) statsPill.textContent = `Busy: ${busyCount} • Free: ${free} • Total: ${total}`;
}

async function refresh(){
  const data = await fetchStatus();
  applyStatus(data);
}

async function init(){
  document.getElementById("refreshBtn").addEventListener("click", refresh);
  await refresh();

  // Auto refresh every 2 seconds
  setInterval(refresh, 2000);
}

init();
