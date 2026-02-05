async function fetchStatus(){
  const res = await fetch("/api/status");
  return await res.json();
}

function applyStatus(data){
  const pcs = document.querySelectorAll(".pc[data-pc]");
  let busyCount = 0;

  pcs.forEach(btn => {
    const id = btn.dataset.pc;
    const info = data[id];

    if (!info) return;

    const isBusy = info.is_busy === true;
    btn.classList.toggle("busy", isBusy);
    btn.classList.toggle("free", !isBusy);

    const userSpan = btn.querySelector(".pc-user");
    userSpan.textContent = isBusy ? (info.user_name || "In use") : "";

    if (isBusy) busyCount++;
  });

  const statusText = document.getElementById("statusText");
  statusText.textContent = `Busy: ${busyCount} • Free: ${pcs.length - busyCount} • Updated: ${new Date().toLocaleTimeString()}`;
}

async function togglePC(pcId){
  const studentName = document.getElementById("studentName").value.trim();

  await fetch("/api/toggle", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ pc_id: pcId, user_name: studentName || null })
  });

  // refresh after toggle
  const data = await fetchStatus();
  applyStatus(data);
}

async function init(){
  // click handlers
  document.querySelectorAll(".pc[data-pc]").forEach(btn => {
    btn.addEventListener("click", () => togglePC(btn.dataset.pc));
  });

  document.getElementById("refreshBtn").addEventListener("click", async () => {
    const data = await fetchStatus();
    applyStatus(data);
  });

  // initial load
  const data = await fetchStatus();
  applyStatus(data);

  // auto-refresh every 2 seconds
  setInterval(async () => {
    const data = await fetchStatus();
    applyStatus(data);
  }, 2000);
}

init();
