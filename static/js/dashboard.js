document.addEventListener("DOMContentLoaded", () => {
  const countdownElem = document.getElementById("countdown");
  if (!countdownElem) return;

  const nextCheckStr = countdownElem.getAttribute("data-next");
  const nextCheckDate = new Date(nextCheckStr);

  function updateCountdown() {
    const now = new Date();
    const diff = nextCheckDate - now;
    if (diff <= 0) {
      countdownElem.textContent = "Executando verificação agora...";
      return;
    }
    const seconds = Math.floor(diff / 1000) % 60;
    const minutes = Math.floor(diff / 60000);
    countdownElem.textContent = minutes + "m " + seconds + "s";
  }

  updateCountdown();
  setInterval(updateCountdown, 1000);
});
