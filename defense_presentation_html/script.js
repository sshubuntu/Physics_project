const slides = Array.from(document.querySelectorAll(".slide"));
const deck = document.querySelector(".deck");
const prevButton = document.getElementById("prev");
const nextButton = document.getElementById("next");
const counter = document.getElementById("counter");
const partLabel = document.getElementById("partLabel");
const progressBar = document.getElementById("progressBar");

let index = 0;
const params = new URLSearchParams(window.location.search);

if (params.has("export")) {
  document.body.classList.add("export");
}

const logicalOrder = [];
const logicalMap = new Map();

for (const slide of slides) {
  const logical = slide.dataset.logical || String(logicalOrder.length + 1);
  if (!logicalMap.has(logical)) {
    logicalOrder.push(logical);
    logicalMap.set(logical, logicalOrder.length);
  }
}

function scaleDeck() {
  const slideW = 1200;
  const slideH = 900;
  const scale = Math.min(window.innerWidth / slideW, window.innerHeight / slideH);
  deck.style.transform = `translate(-50%, -50%) scale(${scale})`;
}

function showSlide(nextIndex) {
  index = Math.max(0, Math.min(slides.length - 1, nextIndex));

  slides.forEach((slide, slideIndex) => {
    slide.classList.toggle("active", slideIndex === index);
  });

  const slide = slides[index];
  const logical = slide.dataset.logical || "1";
  const logicalIndex = logicalMap.get(logical) || 1;
  counter.textContent = `${logicalIndex}/${logicalOrder.length}`;
  partLabel.textContent = slide.dataset.part || "";
  progressBar.style.width = `${((logicalIndex - 1) / (logicalOrder.length - 1)) * 100}%`;

  prevButton.disabled = index === 0;
  nextButton.disabled = index === slides.length - 1;
  history.replaceState(null, "", `#${index + 1}`);
}

function go(delta) {
  showSlide(index + delta);
}

prevButton.addEventListener("click", () => go(-1));
nextButton.addEventListener("click", () => go(1));

window.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {
    event.preventDefault();
    go(1);
  }
  if (event.key === "ArrowLeft" || event.key === "PageUp" || event.key === "Backspace") {
    event.preventDefault();
    go(-1);
  }
  if (event.key === "Home") {
    event.preventDefault();
    showSlide(0);
  }
  if (event.key === "End") {
    event.preventDefault();
    showSlide(slides.length - 1);
  }
});

window.addEventListener("resize", scaleDeck);

const hashIndex = Number.parseInt(window.location.hash.replace("#", ""), 10);
if (Number.isFinite(hashIndex) && hashIndex > 0) {
  index = hashIndex - 1;
}

scaleDeck();
showSlide(index);
