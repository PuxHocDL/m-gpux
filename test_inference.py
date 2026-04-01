import torch
import time

def test_gpu_calculation():
    print("\n" + "="*60)
    print("STARTING GPU CALCULATION TEST")
    print("="*60)
    
    # 1. Check GPU
    if not torch.cuda.is_available():
        print("[ERROR] No GPU found! Code is falling back to CPU.")
        return
        
    device = torch.device("cuda")
    print(f"[OK] Detected device: {torch.cuda.get_device_name(0)}")
    print(f"[OK] Total VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB\n")
    
    # 2. Benchmark massive matrices
    size = 15000
    print(f"[WAIT] Allocating two {size} x {size} square matrices on GPU memory...")
    
    a = torch.randn(size, size, device=device)
    b = torch.randn(size, size, device=device)
    
    # Warmup GPU
    _ = torch.matmul(a, b)
    torch.cuda.synchronize()
    
    # 3. Time calculation
    print("[RUNNING] Executing heavy matrix multiplication...")
    start_time = time.time()
    
    # Lặp lại phép nhân 10 lần
    num_iterations = 10
    for _ in range(num_iterations):
        c = torch.matmul(a, b)
        
    torch.cuda.synchronize()
    end_time = time.time()
    
    # 4. Results
    avg_time = (end_time - start_time) / num_iterations
    TFLOPs = (2 * size**3 * num_iterations) / ((end_time - start_time) * 1e12)
    
    print("\n" + "="*60)
    print("HEAVY LOAD BENCHMARK COMPLETED!")
    print(f"-> Average execution time: {avg_time:.4f} seconds/iteration")
    print(f"-> Estimated Performance: {TFLOPs:.2f} TFLOPs (Trillion Floating Point Operations per Second)")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_gpu_calculation()
