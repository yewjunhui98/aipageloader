const pageViewEl = document.getElementById("redirect-page-view");
const backBtn = document.getElementById("back-dashboard");

backBtn.addEventListener("click", () => {
  window.location.href = "./index.html";
});

const targetUrl = sessionStorage.getItem("redirect-target-url");
const payloadRaw = sessionStorage.getItem("redirect-target-page");

if (targetUrl && payloadRaw) {
  try {
    const payload = JSON.parse(payloadRaw);
    pageViewEl.innerHTML = `
      <h2>${payload.title}</h2>
      <p><strong>URL:</strong> ${targetUrl}</p>
      <p><strong>Status:</strong> Preloaded from saved prediction before redirect.</p>
      <p>${payload.content || "No content available."}</p>
    `;
  } catch (_err) {
    pageViewEl.textContent = "Failed to parse preloaded page payload.";
  }
}
