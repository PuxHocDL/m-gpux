# M-GPUX — VS Code Extension

> Modal GPU Orchestrator ngay trong VS Code. Quản lý tài khoản, chạy GPU workloads, theo dõi billing — không cần rời editor.

---

## Yêu cầu

- **VS Code** ≥ 1.85
- **Modal CLI** đã cài (`pip install modal`) và đã login ít nhất 1 lần
- **m-gpux CLI** (khuyến khích): `pip install m-gpux` — cần cho lệnh Load Probe

---

## Cài đặt

```bash
# Từ file VSIX
code --install-extension m-gpux-1.0.7.vsix

# Hoặc trong VS Code: Ctrl+Shift+P → "Install from VSIX..."
```

Sau khi cài, **Reload Window** (`Ctrl+Shift+P` → `Reload Window`).

---

## Giao diện

Sau khi cài, bạn sẽ thấy:

### 1. Sidebar Icon (Activity Bar)

Nhìn thanh Activity Bar bên trái — icon hình GPU card sẽ xuất hiện. Click vào sẽ mở 2 panel:

- **Accounts** — Danh sách các Modal profile đã cấu hình
- **Quick Actions** — Các thao tác nhanh

### 2. Status Bar (thanh dưới cùng)

Góc trái dưới hiện `☁ M-GPUX: <profile-name>` — profile đang active. Click để switch.

---

## Hướng dẫn sử dụng

### Thêm tài khoản Modal

1. Click **+** trên panel **Accounts**, hoặc `Ctrl+Shift+P` → `M-GPUX: Add Account`
2. Bạn có 2 cách:
   - **Paste nhanh**: Dán nguyên dòng `modal token set --token-id ak-xxx --token-secret as-xxx --profile=tên` → extension tự parse
   - **Nhập thủ công**: Bỏ trống → nhập Token ID, Token Secret, Profile Name lần lượt
3. Profile đầu tiên sẽ tự động được set Active

### Chuyển tài khoản

- Click vào tên profile trong sidebar → tự switch
- Hoặc click status bar `☁ M-GPUX: ...` → chọn profile
- Hoặc `Ctrl+Shift+P` → `M-GPUX: Switch Account`

### Xóa tài khoản

- Right-click profile trong sidebar → **Remove Account**
- Hoặc `Ctrl+Shift+P` → `M-GPUX: Remove Account`

---

### GPU Hub — Chạy workload trên GPU

Đây là tính năng chính. Click **GPU Hub** trong Quick Actions, hoặc `Ctrl+Shift+P` → `M-GPUX: Open GPU Hub`.

Extension sẽ dẫn bạn qua 4 bước:

#### Bước 1: Chọn Profile
- Chọn 1 profile Modal, hoặc **AUTO** (tự chọn profile đang active)

#### Bước 2: Chọn GPU
- T4, L4, A10G, A100, H100, H200, B200... đầy đủ 13 loại

#### Bước 3: Chọn ứng dụng

| Ứng dụng | Mô tả |
|-----------|-------|
| **Jupyter Lab** | Mở Jupyter trên GPU, tự mount code workspace hiện tại |
| **Run Python Script** | Chọn file `.py` trong workspace → chạy trên GPU |
| **Bash Shell** | Terminal web (ttyd + tmux), có thể đóng browser rồi mở lại |
| **vLLM Inference** | Deploy LLM server (Qwen, Llama, Gemma, Mistral) với API OpenAI-compatible |

#### Bước 4: Cấu hình & Chạy

- Với Jupyter/Python: hỏi có dùng `requirements.txt` không, và pattern exclude file
- Extension sẽ **tạo file `modal_runner.py`** trong workspace → mở để bạn xem/sửa
- Chọn **Execute** → mở Terminal mới chạy `modal run modal_runner.py`
- Sau khi chạy xong, hỏi có muốn xóa file tạm không

---

### Probe Hardware

Kiểm tra thông số GPU/CPU/RAM của một container Modal.

1. Click **Probe Hardware** trong Quick Actions, hoặc `Ctrl+Shift+P` → `M-GPUX: Probe GPU Hardware`
2. Chọn GPU muốn probe (T4, L4, A10G, A100, H100)
3. Mở Terminal chạy `m-gpux load probe --gpu <type>` → hiển thị metrics

> ⚠️ Cần cài `m-gpux` CLI: `pip install m-gpux`

### Billing Dashboard

Click **Billing Dashboard** → mở trang https://modal.com/settings/usage trong browser.

### Xem thông tin

`Ctrl+Shift+P` → `M-GPUX: Show Info` — hiện version, số profile, profile đang active.

---

## Tất cả Commands

Mở Command Palette (`Ctrl+Shift+P`) và gõ `M-GPUX`:

| Command | Phím tắt | Mô tả |
|---------|----------|-------|
| `M-GPUX: Open GPU Hub` | — | Wizard chạy workload GPU |
| `M-GPUX: Add Account` | — | Thêm profile Modal |
| `M-GPUX: Switch Account` | — | Chuyển profile đang active |
| `M-GPUX: Remove Account` | — | Xóa profile |
| `M-GPUX: Refresh Accounts` | — | Làm mới danh sách |
| `M-GPUX: Probe GPU Hardware` | — | Kiểm tra hardware metrics |
| `M-GPUX: Open Billing Dashboard` | — | Mở trang billing Modal |
| `M-GPUX: Show Info` | — | Thông tin extension |

---

## Cấu hình được lưu ở đâu?

Extension đọc/ghi trực tiếp file `~/.modal.toml` — cùng file mà Modal CLI sử dụng. Không có config riêng.

Ví dụ `~/.modal.toml`:

```toml
[personal]
token_id = "ak-xxxx"
token_secret = "as-xxxx"
active = true

[work]
token_id = "ak-yyyy"
token_secret = "as-yyyy"
```

---

## Workflow nhanh

```
1. Mở VS Code với project Python của bạn
2. Click icon M-GPUX trên sidebar
3. Thêm account nếu chưa có (nút +)
4. Click "GPU Hub" → chọn GPU → chọn Jupyter
5. Extension tạo script → mở Terminal → chạy
6. Copy URL tunnel → mở browser → code trên GPU
```

---

## Troubleshooting

**Extension không hiện trên sidebar?**
→ `Ctrl+Shift+P` → `Reload Window`

**Lỗi "modal: command not found"?**
→ Cài Modal: `pip install modal`

**Probe không chạy?**
→ Cài m-gpux CLI: `pip install m-gpux`

**Profile không switch được?**
→ Kiểm tra file `~/.modal.toml` có đúng format không
