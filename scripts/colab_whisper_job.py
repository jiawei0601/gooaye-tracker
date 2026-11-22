"""在 Colab GPU VM 上執行的 Whisper 轉錄工作（由 `colab run --gpu T4` 呼叫）。

用法：colab run --gpu T4 colab_whisper_job.py <audio_url> <ep_key> [model]
stdout：逐字稿（第一行 # 標頭，之後每行 [mm:ss] 文字）
stderr：進度與心跳（colab run 的 [colab] 訊息也在 stderr）
exit  ：0 成功；非 0 失敗（colab run 會原樣回傳）

Colab 環境修補集中在 setup_env()，環境升級壞掉時先看那裡。
"""
import os, sys, time, glob, site, ctypes, threading, subprocess, urllib.request

T0 = time.time()
def log(msg):
    print(f"[{time.time()-T0:6.1f}s] {msg}", file=sys.stderr, flush=True)

# --- 雷二：colab run 在 kernel 30 秒無輸出時中止；模型下載／長段推論期間必須有心跳 ---
_alive = True
def _heartbeat():
    while _alive:
        time.sleep(10)
        if _alive:
            log("...working")
threading.Thread(target=_heartbeat, daemon=True).start()


def setup_env():
    """安裝 faster-whisper 並修補 Colab 的 CUDA 版本錯位。"""
    log("pip install faster-whisper + cu12 runtime")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "faster-whisper", "nvidia-cublas-cu12", "nvidia-cudnn-cu12"], check=True)
    # --- 雷三：Colab 現為 CUDA 13，CTranslate2 wheel 連結 libcublas.so.12 / libcudnn.so.9。
    #     pip 裝的 cu12 .so 不在系統連結路徑，LD_LIBRARY_PATH 在程序啟動後設定無效，
    #     只能在 import 前用 ctypes RTLD_GLOBAL 預載。 ---
    n = 0
    for pat in ("nvidia/cublas/lib/*.so*", "nvidia/cudnn/lib/*.so*"):
        for sp in site.getsitepackages():
            for so in sorted(glob.glob(os.path.join(sp, pat))):
                try:
                    ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL); n += 1
                except OSError as e:
                    log(f"skip {os.path.basename(so)}: {e}")
    log(f"preloaded {n} cu12 libs")


def fetch_audio(url, path="/content/ep.mp3"):
    log("download audio")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())
    log(f"audio {os.path.getsize(path)/1e6:.1f} MB")
    return path


def decode_audio(path):
    """--- 雷一：faster-whisper 內建的 PyAV 解碼與 Colab 新版 PyAV 不相容（metadata_errors 參數已移除）。
    改用 ffmpeg 解成 16 kHz 單聲道 float32，直接餵 numpy 陣列。 ---"""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32)
    log(f"decoded {len(audio)/16000/60:.1f} min")
    return audio


def main():
    global _alive
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr); sys.exit(64)
    url, ep = sys.argv[1], sys.argv[2]
    model_name = sys.argv[3] if len(sys.argv) > 3 else "large-v3"
    setup_env()
    audio = decode_audio(fetch_audio(url))
    from faster_whisper import WhisperModel
    log(f"load {model_name} fp16")
    model = WhisperModel(model_name, device="cuda", compute_type="float16")
    log("transcribe")
    segs, info = model.transcribe(
        audio, language="zh", beam_size=5, vad_filter=True,
        initial_prompt="歡迎收聽股癌，我是謝孟恭。台股、美股、台積電、輝達、聯準會。")
    print(f"# {ep} | whisper {model_name} | audio {info.duration/60:.1f} min")
    n = 0
    for s in segs:
        m, sec = divmod(int(s.start), 60)
        print(f"[{m:02d}:{sec:02d}] {s.text.strip()}", flush=True); n += 1
    _alive = False
    log(f"done {n} segments, total {time.time()-T0:.0f}s, audio {info.duration:.0f}s")
    if n == 0:
        sys.exit(3)


if __name__ == "__main__":
    main()
