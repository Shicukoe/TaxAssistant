// Thanh bên: màn hẹp mở thành lớp phủ (☰ mở, bấm ra ngoài đóng); máy tính thu gọn / mở lại.
const narrow = window.matchMedia("(max-width: 1023px)");
for (const toggle of document.querySelectorAll("[data-toggle-sidebar]")) {
  toggle.addEventListener("click", () => {
    document.body.classList.toggle(narrow.matches ? "sidebar-open" : "sidebar-collapsed");
  });
}

// Sáng / tối: chế độ đã đặt trong <head> (base.html); nút này đổi và nhớ lựa chọn trên máy này.
document.getElementById("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch (error) { /* bị chặn → chỉ đổi trong lần mở này */ }
});
