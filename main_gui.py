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

class GameGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("鬼ごっこ")

        # === 设置全局字体、背景色 ===
        default_font = ("Yu Gothic UI", 12)
        title_font = ("Yu Gothic UI", 14, "bold")
        timer_font = ("Yu Gothic UI", 28, "bold")

        self.root.configure(bg="#f0f0f5")  # 主窗口背景统一

        # 主容器：水平排列
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 左侧：信息面板
        self.left_frame = tk.Frame(self.main_frame, bg="#f0f0f5", bd=2, relief="ridge")
        self.left_frame.pack(side=tk.LEFT, padx=20, pady=20, anchor="n")

        # ====== ⏱️ 剩余时间区域 ======
        time_frame = tk.Frame(self.left_frame, bg="#f0f0f5")
        time_frame.pack(pady=(10, 30), anchor="w")  # 留更大间隔和玩家状态分开

        time_title = tk.Label(time_frame, text="🕒  残り時間", font=title_font, bg="#f0f0f5", fg="#333333")
        time_title.pack(anchor="w")

        self.timer_label = tk.Label(time_frame, text="   00:00", font=timer_font,  fg="#008080", bg="#f0f0f5")
        self.timer_label.pack(anchor="w", pady=5)  # 更好看的蓝绿色

        # ====== 👥 玩家状态区域 ======
        status_frame = tk.Frame(self.left_frame, bg="#f0f0f5")
        status_frame.pack(anchor="w")

        status_title = tk.Label(status_frame, text="👥 プレイヤー状態", font=title_font, bg="#f0f0f5", fg="#333333")
        status_title.pack(anchor="w")

        self.player_status = DEFAULT_STATUS.copy()
        self.status_text = tk.StringVar()
        self.status_text.set(self.build_status_text())

        self.status_label = tk.Label(status_frame, textvariable=self.status_text,
                                     font=title_font, justify="left", anchor="nw", bg="#f0f0f5", fg="#333333")
        self.status_label.pack(anchor="w", padx=10, pady=5)

        self.time_left = 30
        # self.player_status = DEFAULT_STATUS.copy()

        # 右侧：LED平台
        self.right_frame = tk.Frame(self.main_frame)
        self.right_frame.pack(side=tk.RIGHT, padx=20, pady=20)

        self.led_canvases = {}
        self.led_names = ["oni", "play1", "play2", "play3"]


        # 新增变量
        self.timer_running = False
        self.timer_paused = False
        self.timer_after_id = None  # after ID 用于取消计时

        # 输入框区域
        input_frame = tk.Frame(self.left_frame, bg="#f0f0f5")
        input_frame.pack(pady=(5, 10), anchor="w")

        tk.Label(input_frame, text="分:", bg="#f0f0f5", fg="#333333").pack(side=tk.LEFT)
        self.min_entry = tk.Entry(input_frame, width=3, font=default_font, bg="#ffffff", fg="#333333")
        self.min_entry.insert(0, "00")  # 默认 00 分
        self.min_entry.pack(side=tk.LEFT)

        tk.Label(input_frame, text="秒:", bg="#f0f0f5", fg="#333333").pack(side=tk.LEFT)
        self.sec_entry = tk.Entry(input_frame, width=3, font=default_font, bg="#ffffff", fg="#333333")
        self.sec_entry.insert(0, "00")  # 默认 00 秒
        self.sec_entry.pack(side=tk.LEFT)


        # 按钮区域
        button_frame = tk.Frame(self.left_frame, bg="#f0f0f5")
        button_frame.pack(pady=5, anchor="w")

        self.start_button = tk.Button(button_frame, text="▶ 開始", command=self.start_timer, font=default_font, bg="#d6eaff")
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.pause_button = tk.Button(button_frame, text="⏸ 停止", command=self.pause_timer, font=default_font, bg="#d6eaff")
        self.pause_button.pack(side=tk.LEFT, padx=5)

        self.reset_button = tk.Button(button_frame, text="⏹ リセット", command=self.reset_timer, font=default_font, bg="#d6eaff")
        self.reset_button.pack(side=tk.LEFT, padx=5)


        for idx, name in enumerate(self.led_names):
            row, col = divmod(idx, 2)

            canvas = tk.Canvas(self.right_frame, width=160, height=160, bg="white")
            canvas.grid(row=row * 2, column=col, padx=10, pady=5)

            # 绘制 8x8 小格子，每个格子 20x20 像素
            cell_size = 20
            for r in range(8):
                for c in range(8):
                    x1 = c * cell_size
                    y1 = r * cell_size
                    x2 = x1 + cell_size
                    y2 = y1 + cell_size
                    canvas.create_rectangle(x1, y1, x2, y2, outline="gray", fill="white")

            #label = tk.Label(self.right_frame, text=f"{name}", font=("Arial", 12))
            #label.grid(row=row * 2 + 1, column=col)

            self.led_canvases[name] = canvas

        self.update_timer()


    def build_status_text(self):
        status = "\n"
        status += f"鬼：{self.player_status['oni']}\n\n"
        for i in range(1, 4):
            name = f"play{i}"
            status += f"P{i}：{self.player_status[name]}\n\n"

        return status

    def update_status_display(self):
        self.status_text.set(self.build_status_text())


    def start_timer(self):
        if not self.timer_running:
            try:
                minutes = int(self.min_entry.get())
                seconds = int(self.sec_entry.get())
                self.time_left = minutes * 60 + seconds
            except ValueError:
                self.time_left = 30  # 默认30秒

            self.timer_running = True
            self.timer_paused = False
            self.update_timer()

        elif self.timer_paused:
            self.timer_paused = False
            self.update_timer()

    def pause_timer(self):
        self.timer_paused = True
        if self.timer_after_id:
            self.root.after_cancel(self.timer_after_id)
            self.timer_after_id = None

    def reset_timer(self):
        self.timer_running = False
        self.timer_paused = False

        if self.timer_after_id:
            self.root.after_cancel(self.timer_after_id)
            self.timer_after_id = None

        # 重新读取输入框的值作为时间
        try:
            minutes = int(self.min_entry.get())
            seconds = int(self.sec_entry.get())
            self.time_left = minutes * 60 + seconds
        except ValueError:
            self.time_left = 30  # 默认30秒

        minutes = self.time_left // 60
        seconds = self.time_left % 60
        self.timer_label.config(text=f"   {minutes:02}:{seconds:02}")

    def update_timer(self):
        if self.timer_running and not self.timer_paused:
            if self.time_left > 0:
                minutes = self.time_left // 60
                seconds = self.time_left % 60
                time_text = f"   {minutes:02}:{seconds:02}"
                #self.timer_label.config(text=f"   {minutes:02}:{seconds:02}")
                # 剩余时间小于等于 10 秒时字体变红，否则恢复青绿色
                if self.time_left <= 10:
                    self.timer_label.config(text=time_text, fg="#ff0000")  # 红色警告
                else:
                    self.timer_label.config(text=time_text, fg="#008080")  # 正常颜色

                self.time_left -= 1
                self.timer_after_id = self.root.after(1000, self.update_timer)
            else:
                self.timer_label.config(text="00:00")
                self.player_status["oni"] = "時間切れ - 失敗"
                self.update_status_display()
                self.timer_running = False




    def draw_led_matrix(self, name, matrix):
        if name not in self.led_canvases:
            return

        if name in self.player_status and self.player_status[name] == "捕まった":
            return

        canvas = self.led_canvases[name]
        canvas.delete("led")
        cell_size = 20
        oni_drawn = False  # 是否画了大的鬼

        # === 检查是否存在2x2红色区域 ===
        for i in range(7):
            for j in range(7):
                try:
                    if (
                            matrix[i][j] == [255, 0, 0] and
                            matrix[i][j + 1] == [255, 0, 0] and
                            matrix[i + 1][j] == [255, 0, 0] and
                            matrix[i + 1][j + 1] == [255, 0, 0]
                    ):
                        # 在整个2x2区域中心绘制大鬼图标
                        x_center = (j + 1) * cell_size
                        y_center = (i + 1) * cell_size
                        canvas.create_text(
                            x_center, y_center, text="👹", fill="red",
                            font=("Arial", 36), tags="led"
                        )
                        oni_drawn = True
                        break
                except:
                    continue
            if oni_drawn:
                break

        # === 绘制其他非红色像素 ===
        for i in range(8):
            for j in range(8):
                try:
                    r, g, b = matrix[i][j]
                    if (r, g, b) == (0, 0, 0):
                        continue

                    # 忽略红色鬼图标的四个像素
                    if oni_drawn and matrix[i][j] == [255, 0, 0]:
                        continue

                    color = f"#{r:02x}{g:02x}{b:02x}"
                    x1 = j * cell_size
                    y1 = i * cell_size
                    x2 = x1 + cell_size
                    y2 = y1 + cell_size
                    canvas.create_rectangle(x1, y1, x2, y2, outline="gray", fill=color, tags="led")
                except:
                    continue

    def handle_event(self, event):
        if event["type"] == "catch":
            target = event["target"]
            self.player_status[target] = "捕まった"
            self.update_status_display()

            # 3️⃣ 所有玩家都被吃掉 → 鬼胜利（但仅当剩余时间大于0）
            if all(self.player_status[p] == "捕まった" for p in ["play1", "play2", "play3"]):
                if self.time_left > 0:
                    self.player_status["oni"] = "勝利"
                    self.update_status_display()

        elif event["type"] == "escaped":
            target = event["target"]
            self.player_status[target] = "逃げ切り"
            self.update_status_display()

            # 4️⃣ 有玩家逃脱 → 鬼失败（但仅当剩余时间大于0）
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



def listen_broadcast(gui):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 12345))
    print("Listening for broadcasts on UDP 12345...")
    while True:
        data, _ = sock.recvfrom(4096)
        try:
            msg = json.loads(data.decode())
            if msg["type"] == "matrix":
                gui.draw_led_matrix(msg["name"], msg["matrix"])
                print("1234")
            elif msg["type"] in ["catch", "escaped", "win", "lose"]:
                gui.handle_event(msg)
        except:
            continue

if __name__ == "__main__":
    root = tk.Tk()
    gui = GameGUI(root)
    threading.Thread(target=listen_broadcast, args=(gui,), daemon=True).start()
    root.mainloop()
