import tkinter as tk
import socket
import threading
import json

PLAYER_COLORS = {
    "oni": "red",
    "play1": "yellow",
    "play2": "blue",
    "play3": "green"
}

DEFAULT_STATUS = {
    "oni": "未判定",
    "play1": "逃走中",
    "play2": "逃走中",
    "play3": "逃走中"
}

EMOJI_MAP = {
    "oni": "👹",
    "play1": "🎮",
    "play2": "🎮",
    "play3": "🎮"
}

class GameGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("鬼ごっこ")

        # === 屏幕初始化 ===
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = int(screen_width * 0.8)
        window_height = int(screen_height * 0.8)
        window_x = (screen_width - window_width) // 2
        window_y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        self.root.minsize(800, 600)
        self.root.configure(bg="#e8f0fc")
        self.root.bind("<Configure>", self.on_resize)

        # === 字体样式 ===
        self.base_font_size = int(max(10, min(window_width // 80, window_height // 60)) * 3)
        title_font = ("Yu Gothic UI", int(self.base_font_size * 1.2), "bold")
        timer_font = ("Yu Gothic UI", int(self.base_font_size * 2.3), "bold")

        # 主容器
        self.main_frame = tk.Frame(root, bg="#e8f0fc")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 左侧信息面板
        self.left_frame = tk.Frame(self.main_frame, bg="white", bd=2, relief="groove")
        self.left_frame.pack(side=tk.LEFT, padx=20, pady=20, fill=tk.BOTH, expand=False)

        # 剩余时间区域
        self.time_frame = tk.Frame(self.left_frame, bg="white")
        self.time_frame.pack(pady=(10, 30), fill=tk.X)
        self.time_title = tk.Label(self.time_frame, text="🕒  残り時間", font=title_font, bg="white", fg="#0055cc")
        self.time_title.pack(anchor="w")
        self.timer_label = tk.Label(self.time_frame, text="00:00", font=timer_font, fg="#0077dd", bg="white")
        self.timer_label.pack(anchor="w", pady=5)

        # 玩家状态区域
        self.status_frame = tk.Frame(self.left_frame, bg="white")
        self.status_frame.pack(fill=tk.X)
        self.status_title = tk.Label(self.status_frame, text="👥 プレイヤー状態", font=title_font, bg="white", fg="#0055cc")
        self.status_title.pack(anchor="w")
        self.player_status = DEFAULT_STATUS.copy()
        self.status_text = tk.StringVar()
        self.status_text.set(self.build_status_text())
        self.status_label = tk.Label(self.status_frame, textvariable=self.status_text,
                                     font=title_font, justify="left", anchor="nw", bg="white", fg="#333333")
        self.status_label.pack(anchor="w", padx=10, pady=5)

        # 右侧 LED 区域
        self.right_frame = tk.Frame(self.main_frame, bg="#e8f0fc")
        self.right_frame.pack(side=tk.RIGHT, padx=20, pady=20, fill=tk.BOTH, expand=True)
        self.led_canvases = {}
        self.led_names = ["oni", "play1", "play2", "play3"]

        for idx, name in enumerate(self.led_names):
            row, col = divmod(idx, 2)
            canvas = tk.Canvas(self.right_frame, bg="white", highlightthickness=0)
            canvas.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
            self.led_canvases[name] = canvas

        for i in range(2):
            self.right_frame.grid_rowconfigure(i, weight=1)
            self.right_frame.grid_columnconfigure(i, weight=1)


        # 初始变量
        self.time_left = 30
        self.timer_running = False
        self.timer_paused = False
        self.timer_after_id = None
        self.last_matrices = {
            name: [[(0, 0, 0) for _ in range(8)] for _ in range(8)]
            for name in self.led_names
        }
        self.update_timer()
    def on_resize(self, event):
        self.draw_empty_grids()

    def draw_empty_grids(self):
        for name in self.led_names:
            canvas = self.led_canvases[name]
            canvas.delete("all")
            width = canvas.winfo_width()
            height = canvas.winfo_height()
            cell_width = width / 8
            cell_height = height / 8
            for r in range(8):
                for c in range(8):
                    x1 = c * cell_width
                    y1 = r * cell_height
                    x2 = x1 + cell_width
                    y2 = y1 + cell_height
                    canvas.create_rectangle(x1, y1, x2, y2, outline="gray", fill="white", tags="grid")

    def build_status_text(self):
        status = ""
        status += f"{EMOJI_MAP['oni']} 鬼：{self.player_status['oni']}\n"
        for i in range(1, 4):
            name = f"play{i}"
            status += f"{EMOJI_MAP[name]} P{i}：{self.player_status[name]}\n"
        return status.strip()

    def update_status_display(self):
        self.status_text.set(self.build_status_text())

    def update_timer(self):
        if self.timer_running and not self.timer_paused:
            if self.time_left > 0:
                minutes = self.time_left // 60
                seconds = self.time_left % 60
                self.timer_label.config(text=f"{minutes:02}:{seconds:02}")
                self.time_left -= 1
                self.timer_after_id = self.root.after(1000, self.update_timer)
            else:
                self.timer_label.config(text="00:00")
                if all(self.player_status[p] == "捕まった" for p in ["play1", "play2", "play3"]):
                    self.player_status["oni"] = "勝利"
                else:
                    self.player_status["oni"] = "失敗"
                self.update_status_display()
                self.timer_running = False

    def start_timer_from_network(self, duration):
        if self.timer_after_id:
            self.root.after_cancel(self.timer_after_id)
            self.timer_after_id = None
        self.time_left = duration
        self.timer_running = True
        self.timer_paused = False
        self.update_timer()

    def draw_led_matrix(self, name, matrix):
        if name not in self.led_canvases:
            return
        canvas = self.led_canvases[name]
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        cell_width = canvas_width / 8
        cell_height = canvas_height / 8

        # 当前帧 vs 上一帧比对
        last_matrix = self.last_matrices[name]

        for i in range(8):
            for j in range(8):
                r, g, b = matrix[i][j]
                if (r, g, b) != last_matrix[i][j]:
                    color = f"#{r:02x}{g:02x}{b:02x}" if (r, g, b) != (0, 0, 0) else "#ffffff"
                    x1 = j * cell_width
                    y1 = i * cell_height
                    x2 = x1 + cell_width
                    y2 = y1 + cell_height
                    # 覆盖小格子内容，不清除整层
                    canvas.create_rectangle(x1, y1, x2, y2, outline="gray", fill=color, tags="led")

        # 保存当前为下一帧基准
        self.last_matrices[name] = [row[:] for row in matrix]

    def handle_event(self, event):
        if event["type"] == "catch":
            target = event["target"]
            self.player_status[target] = "捕まった"
            self.update_status_display()
        elif event["type"] == "escaped":
            target = event["target"]
            self.player_status[target] = "逃げ切り"
            self.update_status_display()
            if any(self.player_status[p] == "逃げ切り" for p in ["play1", "play2", "play3"]):
                if self.time_left > 0:
                    self.player_status["oni"] = "失敗"
                    self.update_status_display()
        elif event["type"] == "win":
            self.player_status["oni"] = "勝利"
            self.update_status_display()
        elif event["type"] == "lose":
            self.player_status["oni"] = "失敗"
            self.update_status_display()

# 广播监听线程
# 广播监听线程
def listen_broadcast(gui):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 12345))
    while True:
        try:
            data, _ = sock.recvfrom(4096)
            msg = json.loads(data.decode())
            if msg["type"] == "matrix":
                gui.draw_led_matrix(msg["name"], msg["matrix"])
            elif msg["type"] in ["catch", "escaped", "win", "lose"]:
                gui.handle_event(msg)
            elif msg["type"] == "start_timer":
                gui.start_timer_from_network(msg.get("duration", 30))
            elif msg["type"] == "start":  # 新增对"start"事件的处理
                # 可选：重置游戏状态
                gui.reset_game()
                # 启动倒计时
                gui.start_timer_from_network(msg.get("duration", 30))
        except Exception as e:
            print("Broadcast Error:", e)

# 主程序入口
if __name__ == "__main__":
    root = tk.Tk()
    gui = GameGUI(root)
    threading.Thread(target=listen_broadcast, args=(gui,), daemon=True).start()
    root.mainloop()