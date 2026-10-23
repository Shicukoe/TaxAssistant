// Hỏi đáp: bố cục như ChatGPT (docs/ui-context.md, Phong cách).
// Mọi chữ chèn bằng textContent — không bao giờ innerHTML với chữ của người dùng hay của model.
const chat = document.getElementById("chat");
const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const sendButton = document.getElementById("ask-button");
const messages = document.getElementById("messages");
const toBottom = document.getElementById("to-bottom");
// Mã CSRF của phiên — mọi POST gửi kèm trong header (docs/architecture.md, Truy cập và phân quyền)
const csrfToken = document.querySelector('meta[name="csrf"]').content;
let busy = false;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function scrollToEnd(smooth = true) {
  window.scrollTo({ top: document.body.scrollHeight, behavior: smooth ? "smooth" : "auto" });
}

// Chữ đang chạy ra: chỉ cuộn theo khi người đọc đang ở cuối — đang cuộn lên đọc chỗ khác thì để yên.
function followIfNearBottom() {
  if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 200) scrollToEnd(false);
}

function userMessage(question) {
  const wrap = el("div", null, "message-user");
  wrap.append(el("p", question, "bubble-user"));
  return wrap;
}

function botShell() {
  const wrap = el("div", null, "message-bot");
  const body = el("div", null, "bot-body");
  wrap.append(body);
  return { wrap, body };
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

// Chữ để dán vào Word / Zalo: mốc, kết luận, các căn cứ đã kiểm.
function plainText(result) {
  const lines = result.chao_hoi ? [] : [`Áp dụng tại mốc ${result.moc || ""}`];
  lines.push(result.ket_luan);
  const cited = (result.can_cu || []).filter((c) => c.trang_thai === "dat");
  if (cited.length) {
    lines.push("", "Căn cứ:");
    for (const c of cited) lines.push(`- ${c.vi_tri} ${c.loai} ${c.so_hieu}: "${c.trich_dan}"`);
  }
  return lines.join("\n");
}

// navigator.clipboard chỉ có trong secure context (https / localhost) và có thể bị trình duyệt chặn → dùng cách cũ.
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = el("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

function actions(result) {
  const row = el("div", null, "message-actions");
  const button = el("button", null, "icon-button");
  button.type = "button";
  button.setAttribute("aria-label", "Sao chép câu trả lời");
  button.title = "Sao chép câu trả lời";
  button.append(icon("copy"));
  button.addEventListener("click", async () => {
    try {
      await copyText(plainText(result));
      button.replaceChildren(icon("check"));
      button.title = "Đã sao chép";
      setTimeout(() => { button.replaceChildren(icon("copy")); button.title = "Sao chép câu trả lời"; }, 1500);
    } catch (error) {
      button.title = "Không sao chép được — bôi đen rồi Ctrl+C";
    }
  });
  row.append(button);
  if (result.answer_id) row.append(rating(result));
  return row;
}

// Người hỏi chấm câu trả lời — nhãn dùng cho fine-tune / đánh giá (docs/danh-gia.md, Dữ liệu từ lịch sử hỏi đáp).
const VERDICTS = [["dung", "Đúng"], ["sai", "Sai"], ["chua_du", "Chưa đủ"]];

function rating(result) {
  const box = el("div", null, "rating");
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "Đánh giá câu trả lời");
  const saved = result.danh_gia || {};
  const status = el("span", "", "rating-status");
  // Ghi chú đã lưu hiện ngay dưới các nút; ô nhập chỉ mở khi bấm Sai / Chưa đủ, lưu xong thì đóng.
  const savedNote = el("p", saved.ghi_chu ? `Ghi chú: ${saved.ghi_chu}` : "", "rating-saved-note");
  savedNote.hidden = !saved.ghi_chu;
  const note = el("div", null, "rating-note");
  const area = el("textarea");
  area.maxLength = 2000;
  area.placeholder = "Sai chỗ nào, đúng phải là gì (không bắt buộc)";
  area.setAttribute("aria-label", "Ghi chú đánh giá");
  area.value = saved.ghi_chu || "";
  const saveNote = el("button", "Lưu ghi chú");
  saveNote.type = "button";
  note.append(area, saveNote);
  note.hidden = true;
  let current = saved.nhan || null;

  const buttons = VERDICTS.map(([value, text]) => {
    const button = el("button", text);
    button.type = "button";
    button.setAttribute("aria-pressed", String(value === current));
    button.addEventListener("click", () => {
      note.hidden = value === "dung";
      send(value, false);
      if (!note.hidden) area.focus();
    });
    return button;
  });
  saveNote.addEventListener("click", () => current && send(current, true));

  async function send(value, closeNote) {
    const sentNote = note.hidden ? "" : area.value.trim();
    status.textContent = "Đang lưu…";
    try {
      const response = await fetch("/api/danh-gia", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: JSON.stringify({ answer_id: result.answer_id, nhan: value, ghi_chu: sentNote }),
      });
      if (!response.ok) throw new Error(String(response.status));
      current = value;
      buttons.forEach((button, index) => button.setAttribute("aria-pressed", String(VERDICTS[index][0] === value)));
      savedNote.textContent = sentNote ? `Ghi chú: ${sentNote}` : "";
      savedNote.hidden = !sentNote;
      if (closeNote) note.hidden = true;
      status.textContent = "Đã lưu";
    } catch (error) {
      status.textContent = "Chưa lưu được — thử lại";
    }
  }

  box.append(...buttons, status, savedNote, note);
  return box;
}

function stepsBlock(steps, seconds, debugText, open) {
  const details = el("details", null, "steps");
  details.open = open;
  const label = seconds === null || seconds === undefined
    ? `Đang chạy — ${steps.length} bước` : `Đã kiểm qua ${steps.length} bước · ${String(seconds).replace(".", ",")} giây`;
  details.append(el("summary", label));
  const list = el("ol");
  for (const step of steps) list.append(el("li", step.text, step.running ? "running" : ""));
  details.append(list);
  if (debugText) details.append(el("pre", debugText));
  return details;
}

function renderResult(body, result) {
  if (result.chao_hoi) {  // lời chào: không mốc thời gian, không cảnh báo căn cứ
    body.append(el("p", result.ket_luan, "conclusion"));
    return;
  }
  renderAnswer(body, result);
  body.append(actions(result));
}

function renderAnswer(body, result) {
  const chips = el("div", null, "chips");
  chips.append(el("span", `Áp dụng tại mốc ${result.moc || ""}`, "chip"));
  if (result.ngu_canh) chips.append(el("span", `Mang từ câu trước: ${result.ngu_canh}`, "chip"));
  body.append(chips);
  if (!result.co_can_cu) body.append(el("p", "Không có căn cứ trong dữ liệu đã tìm.", "callout callout-no-basis"));
  body.append(el("p", result.ket_luan, "conclusion"));
  if (result.con_so_chua_can_cu && result.con_so_chua_can_cu.length) {
    body.append(el("p", `Con số chưa có căn cứ trong đoạn trích: ${result.con_so_chua_can_cu.join(", ")}`, "callout callout-warning"));
  }
  if (result.can_cu.length) {
    body.append(el("p", "Căn cứ", "sources-title"));
    const list = el("div", null, "sources");
    for (const c of result.can_cu) {
      const card = el("div", null, "source");
      const head = el("div", null, "source-head");
      const title = c.trang_thai === "dat" ? `${c.vi_tri} · ${c.loai} ${c.so_hieu}` : c.so_hieu;
      if (c.link) {
        const link = el("a", title);
        link.href = c.link;
        head.append(link);
      } else head.append(el("span", title));
      card.append(head);
      if (c.tieu_de) card.append(el("div", c.tieu_de, "source-title"));  // để biết định nghĩa / quy định của văn bản nào
      if (c.het_hieu_luc) card.append(el("span", c.het_hieu_luc, "label label-expired"));
      else if (c.can_kiem_hieu_luc) card.append(el("span", "Cần kiểm hiệu lực — văn bản cũ", "label label-check"));
      if (c.trang_thai === "dat") card.append(el("blockquote", c.trich_dan, "quote"));
      else if (c.trang_thai === "bo_chu_ocr") card.append(el("span", "Bản scan — chỉ số hiệu, xem bản gốc", "label label-ocr"));
      else if (c.trang_thai === "bo_cach_ly") card.append(el("span", "Chữ đang chờ kiểm — xem bản gốc", "label label-check"));
      list.append(card);
    }
    body.append(list);
  }
  if (result.so_trich_dan_bi_bo) {
    body.append(el("p", `${result.so_trich_dan_bi_bo} trích dẫn bị bỏ vì không khớp nguyên văn với văn bản gốc.`, "footnote"));
  }
}

// Các lượt đã lưu (bản ghi chính thức) — dựng bằng đúng hàm dùng cho câu trả lời trực tiếp.
for (const turn of JSON.parse(document.getElementById("turns-data").textContent)) {
  messages.append(userMessage(turn.cau_hoi));
  const { wrap, body } = botShell();
  renderResult(body, turn.ket_qua);
  messages.append(wrap);
}
if (messages.querySelector(".message-user")) scrollToEnd(false);

// Câu hỏi đầu tiên của cuộc hội thoại mới → thêm lên đầu danh sách ở thanh bên (không cần tải lại trang).
function addCurrentThreadToSidebar(question) {
  const threads = document.querySelector(".threads");
  if (!threads || threads.querySelector('a[aria-current="true"]')) return;
  threads.querySelector(".threads-empty")?.remove();
  const item = el("li");
  const link = el("a", question);
  link.href = "/hoi";
  link.title = question;
  link.setAttribute("aria-current", "true");
  item.append(link);
  threads.prepend(item);
}

function autoGrow() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 200)}px`;
}

function setBusy(value) {
  busy = value;
  sendButton.disabled = value || !input.value.trim();
}

async function ask(question) {
  if (busy || !question) return;
  chat.classList.remove("is-empty");  // ô nhập từ giữa màn hình xuống đáy
  setBusy(true);
  input.value = "";
  autoGrow();
  messages.append(userMessage(question));
  const { wrap, body } = botShell();
  const typing = el("div");
  const dots = el("span", null, "typing");
  dots.append(el("span"), el("span"), el("span"));
  const status = el("span", "Đang đọc câu hỏi…", "status");
  typing.append(dots, status);
  body.append(typing);
  messages.append(wrap);
  scrollToEnd();

  const steps = [];
  const debug = [];
  let stepsNode = null;
  let draft = null;
  let draftText = null;
  const redrawSteps = (seconds, open) => {
    const next = stepsBlock(steps, seconds, debug.join("\n\n"), open);
    if (stepsNode) stepsNode.replaceWith(next); else body.append(next);
    stepsNode = next;
  };
  try {
    const response = await fetch("/api/hoi", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify({ cau_hoi: question }),
    });
    if (!response.ok) {  // 401: phiên hết hạn; 403: mã CSRF không khớp (trang mở từ phiên cũ)
      typing.remove();
      body.append(el("p", "Phiên đăng nhập đã hết — tải lại trang để đăng nhập rồi hỏi lại.", "callout callout-no-basis"));
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const message = JSON.parse(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
        if (message.viet_them !== undefined || message.dang_viet !== undefined) {
          // kết luận đang viết — luôn ghi rõ chưa kiểm căn cứ; bản đã kiểm thay thế khi xong
          if (!draft) {
            draft = el("div", null, "draft");
            draft.append(el("span", "Đang viết — chưa kiểm căn cứ", "label label-check"));
            draftText = el("p", "", "conclusion drafting");
            draft.append(draftText);
            body.append(draft);
            status.textContent = "Đang viết câu trả lời…";
          }
          draftText.textContent = message.dang_viet !== undefined
            ? message.dang_viet : draftText.textContent + message.viet_them;
          followIfNearBottom();
          continue;
        }
        if (message.loi) {
          typing.remove();
          draft?.remove();  // chữ chưa kiểm không được ở lại khi lỗi
          body.append(el("p", message.loi, "callout callout-no-basis"));
          continue;
        }
        if (message.ket_qua) {
          addCurrentThreadToSidebar(question);
          typing.remove();
          draft?.remove();
          draft = null;
          if (stepsNode) stepsNode.remove();
          renderResult(body, message.ket_qua);
          for (const step of steps) step.running = false;
          stepsNode = stepsBlock(steps, message.giay, debug.join("\n\n"), false);
          body.prepend(stepsNode);  // "Đã kiểm qua … bước" nằm trên câu trả lời, như ChatGPT
          continue;
        }
        for (const step of steps) step.running = false;
        steps.push({ text: message.ms !== undefined ? `${message.ten} — ${message.ms} ms` : message.ten, running: true });
        status.textContent = `${message.ten}…`;
        if (message.debug) debug.push(`[${message.buoc}] ${message.ms} ms\n${JSON.stringify(message.debug, null, 1)}`);
        redrawSteps(null, false);
      }
    }
  } catch (error) {
    typing.remove();
    body.append(el("p", "Mất kết nối tới laptop. Kiểm mạng (Tailscale đang bật?) rồi hỏi lại.", "callout callout-no-basis"));
  } finally {
    setBusy(false);
    input.focus();
    scrollToEnd();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input.value.trim());
});
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {  // isComposing: đang gõ dấu (Telex/VNI)
    event.preventDefault();
    ask(input.value.trim());
  }
});
input.addEventListener("input", () => { autoGrow(); setBusy(busy); });
for (const sample of document.querySelectorAll(".sample")) {
  sample.addEventListener("click", () => ask(sample.dataset.question));
}
toBottom.addEventListener("click", () => scrollToEnd());
window.addEventListener("scroll", () => {
  toBottom.hidden = window.innerHeight + window.scrollY >= document.body.scrollHeight - 120;
});
setBusy(false);
