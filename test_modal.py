import modal

# Declare a simple Modal app
app = modal.App("test-connection")

# This function will run on Modal's servers
@app.function()
def check_connection():
    import os
    cloud_provider = os.environ.get("MODAL_CLOUD_PROVIDER", "Unknown Cloud")
    return f"Bạn đã kết nối thành công với Modal! Container này đang chạy trên: {cloud_provider}"

@app.local_entrypoint()
def main():
    print("⏳ Đang thử kết nối lên Modal bằng cấu hình hiện tại của bạn...")
    try:
        # Gọi hàm remote
        result = check_connection.remote()
        print(f"\n✅ [THÀNH CÔNG] {result}")
        print("Tài khoản của bạn đã sãn sàng để dùng tính năng m-gpux hub!")
    except Exception as e:
        print("\n❌ [THẤT BẠI] Lỗi kết nối. Token của bạn có thể không đúng hoặc profile chưa được set Active.")
        print(f"Chi tiết: {e}")


