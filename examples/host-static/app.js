// Simple interactive demo for the static site
let count = 0;

function increment() {
    count++;
    document.getElementById("count").textContent = count;

    // Add a little visual feedback
    const btn = document.getElementById("btn");
    btn.style.transform = "scale(1.1)";
    setTimeout(() => { btn.style.transform = ""; }, 150);
}

// Show deployment timestamp
document.addEventListener("DOMContentLoaded", () => {
    const footer = document.querySelector("footer p");
    const now = new Date().toLocaleString();
    footer.innerHTML += `<br><small>Page loaded: ${now}</small>`;
});
