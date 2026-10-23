// Sáng / tối đặt TRƯỚC khi trang hiện — nạp đồng bộ trong <head>, không chớp trắng. File riêng vì CSP không cho
// script nội tuyến. Mặc định theo máy; lựa chọn lưu ở localStorage chỉ là tiện ích (trình duyệt chặn thì vẫn chạy
// theo máy). docs/ui-context.md, Phong cách.
(function () {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (error) { /* bị chặn → theo máy */ }
  const dark = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
