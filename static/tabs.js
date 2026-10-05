
    function render(tabs) {
      const bar = document.getElementById("bar");
      bar.innerHTML = (tabs || []).map((tab) => `
        <button class="tab ${tab.active ? "active" : ""}" data-id="${tab.id}" type="button">
          <span>${tab.title || "Blackboard"}</span>
          <i class="close" data-close="${tab.id}">×</i>
        </button>`).join("");
    }
    document.getElementById("bar").addEventListener("click", (event) => {
      const close = event.target.closest("[data-close]");
      const tab = event.target.closest("[data-id]");
      if (close) {
        event.stopPropagation();
        window.chrome.webview.postMessage(JSON.stringify({ kind: "tabs", action: "close", id: close.dataset.close }));
        return;
      }
      if (tab) {
        window.chrome.webview.postMessage(JSON.stringify({ kind: "tabs", action: "activate", id: tab.dataset.id }));
      }
    });
    window.chrome.webview.addEventListener("message", (event) => {
      let message = event.data;
      if (typeof message === "string") {
        try { message = JSON.parse(message); } catch (error) { return; }
      }
      if (message && message.event === "tabs") render(message.tabs || []);
    });
    window.chrome.webview.postMessage(JSON.stringify({ kind: "tabs", action: "ready" }));
  