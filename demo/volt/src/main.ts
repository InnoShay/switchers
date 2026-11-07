import "./style.css";

const form = document.querySelector<HTMLFormElement>("#waitlist")!;
const count = document.querySelector<HTMLSpanElement>("#count")!;
const thanks = document.querySelector<HTMLParagraphElement>("#thanks")!;

form.addEventListener("submit", (event) => {
  event.preventDefault();
  count.textContent = String(Number(count.textContent) + 1);
  thanks.hidden = false;
  form.reset();
});
