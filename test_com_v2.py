try:
    from sense_hat import SenseHat  # real hardware
except Exception:  # fallback for environments without RTIMU
    from sense_emu import SenseHat
from dataclasses import dataclass
from typing import List, Tuple, Dict
import sys
import time
import socket
import threading
import random

sense = SenseHat()

# 色の定義
RED = [255, 0, 0]
GREEN = [0, 255, 0]
BLUE = [0, 0, 255]
YELLOW = [255, 255, 0]
CLEAR = [0, 0, 0]

# 隣接するラズパイが存在しないことを示す値
NO_NEIGHBOR = 9

WHITE = [255, 255, 255]

digit_patterns = {
    0: [
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
    ],
    1: [
        CLEAR, CLEAR, WHITE, WHITE, CLEAR, CLEAR, CLEAR, CLEAR,
        CLEAR, WHITE, WHITE, WHITE, CLEAR, CLEAR, CLEAR, CLEAR,
        CLEAR, CLEAR, WHITE, WHITE, CLEAR, CLEAR, CLEAR, CLEAR,
        CLEAR, CLEAR, WHITE, WHITE, CLEAR, CLEAR, CLEAR, CLEAR,
        CLEAR, CLEAR, WHITE, WHITE, CLEAR, CLEAR, CLEAR, CLEAR,
        CLEAR, CLEAR, WHITE, WHITE, CLEAR, CLEAR, CLEAR, CLEAR,
        CLEAR, CLEAR, WHITE, WHITE, CLEAR, CLEAR, CLEAR, CLEAR,
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
    ],
    2: [
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
        CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR,
        WHITE, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR,
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
    ],
    3: [
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
        CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
        CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, WHITE,
        WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE, WHITE,
    ],
}

def show_digit(digit: int, duration: float = 1.5):
    pattern = digit_patterns.get(digit)
    if pattern:
        sense.set_pixels(pattern)
        time.sleep(duration)
        sense.clear()

def handle_shuffle(new_order: List[int]):
    """Handle layout shuffling and show the identifier of the target Pi."""
    global layout, operation_lock_until

    old_order = layout[:]
    layout = new_order

    # update adjacency for currently active devices
    for dev_id, adj in compute_adj_from_layout(layout).items():
        devices[dev_id].adj = adj

    operation_lock_until = time.time() + 10

    # Map each device to the identifier currently occupying its
    # destination.  Using the old order ensures every displayed digit is
    # drawn exactly once from the set of active Pis.
    dest_map = {}
    for i, dev_id in enumerate(new_order):
        if i < len(old_order):
            dest_map[dev_id] = old_order[i]

    target_pi = dest_map.get(MY_PI_ID, MY_PI_ID)

    show_digit(target_pi)

    # redraw cursors after digit display
    for dev in devices.values():
        if dev.onMyPi:
            draw_cursor(dev.position[0], dev.position[1], dev.color, dev.cursor_size)

# RGB値から変数名を取得する関数
def get_color_name(rgb):
    color_dict = {
        tuple(RED): "RED",
        tuple(GREEN): "GREEN",
        tuple(BLUE): "BLUE",
        tuple(YELLOW): "YELLOW",
        tuple(CLEAR): "CLEAR",
    }
    return color_dict.get(tuple(rgb), "UNKNOWN")

# ラズパイ1台分の情報の定義
@dataclass
class DeviceInfo:
    id: int
    addr: str
    color: Tuple[int, int, int]
    position: List[int]
    adj: Tuple[int, int, int, int]  # (up, right, down, left)
    onMyPi: bool
    alive: bool
    cursor_size: int
    move_step: int

# ラズパイ群（4台）
devices: Dict[int, DeviceInfo] = {
    0: DeviceInfo(0, "192.168.10.1", RED, [2, 2], (2, 9, 9 , 1), False, True, 2, 2),
    1: DeviceInfo(1, "192.168.10.2", GREEN, [2, 2], (3, 0, 9, 9), False, True, 1, 1),
    2: DeviceInfo(2, "192.168.10.3", BLUE, [2, 2], (9, 9, 0, 3), False, True, 1, 1),
    3: DeviceInfo(3, "192.168.10.4", YELLOW, [2, 2], (9, 2, 1, 9), False, True, 1, 1),
}

# 自身のラズパイ（引数にて指定）
args = sys.argv
MY_PI_ID = int(args[1])
MY_PI = devices.get(MY_PI_ID)
SRC_ADDR = MY_PI.addr
MY_PI.onMyPi = True
print(f"Your Pi address: {MY_PI.addr}")

 # 自身のカーソルがいるPiのアドレス（最初は自分のPi）
my_cursor_locator = MY_PI.addr

# 逆引き辞書の作成（IPアドレス → ID）
addr_to_id = {dev.addr: dev.id for dev in devices.values()}

# ネットワーク設定
SRC_PORT = 5005
DST_PORT = 5005
BUFFER_SIZE = 1024

# LEDマトリクスとカーソルの設定
WIDTH, HEIGHT = 8, 8

# センサー感度
TILT_THRESHOLD = 0.3

# カーソルの優先順位
cursor_priority = sorted(devices.keys())

#鬼のラズパイのID
HUNTER_ID=0

# --- layout handling ---
layout = [0, 1, 2, 3]  # [top-left, top-right, bottom-left, bottom-right]

def compute_adj_from_layout(order: List[int]) -> Dict[int, Tuple[int, int, int, int]]:
    """Compute (up, right, down, left) adjacency from the current layout."""

    # Map layout positions to their neighbour positions on a 2x2 grid
    mapping = {
        0: {"up": None, "right": 1, "down": 2, "left": None},
        1: {"up": None, "right": None, "down": 3, "left": 0},
        2: {"up": 0, "right": 3, "down": None, "left": None},
        3: {"up": 1, "right": None, "down": None, "left": 2},
    }

    padded = order + [NO_NEIGHBOR] * (4 - len(order))
    result = {}

    for pos, dev_id in enumerate(padded):
        if dev_id == NO_NEIGHBOR:
            continue
        neighbours = mapping[pos]
        adj = (
            padded[neighbours["up"]] if neighbours["up"] is not None else NO_NEIGHBOR,
            padded[neighbours["right"]] if neighbours["right"] is not None else NO_NEIGHBOR,
            padded[neighbours["down"]] if neighbours["down"] is not None else NO_NEIGHBOR,
            padded[neighbours["left"]] if neighbours["left"] is not None else NO_NEIGHBOR,
        )
        result[dev_id] = adj

    return result

for dev_id, adj in compute_adj_from_layout(layout).items():
    devices[dev_id].adj = adj

operation_lock_until = 0  # when normal operation resumes

exit_flag = False  # プログラム終了要求フラグ


# 指定された座標にカーソルを描画する
def draw_cursor(x, y, color, size):
    for dx in range(size):
        for dy in range(size):
            # 念のため範囲外描画を防ぐ
            if 0 <= x + dx < WIDTH and 0 <= y + dy < HEIGHT:
                sense.set_pixel(x + dx, y + dy, color)

# そのピクセルに現在存在するカーソルのリストを取得
def cursor_covers_pixel(dev: DeviceInfo, x: int, y: int) -> bool:
    """Return True if the given pixel is within dev's cursor area."""
    dev_x, dev_y = dev.position
    return (
        dev_x <= x < dev_x + dev.cursor_size and
        dev_y <= y < dev_y + dev.cursor_size
    )


def get_overlapping_cursors(x, y):
    print_all_cursor_status()
    overlapping = []
    for dev_id in cursor_priority:
        dev = devices[dev_id]
        if dev.onMyPi and cursor_covers_pixel(dev, x, y):
            overlapping.append(dev)

    return overlapping
            

# カーソルがあるマスから動いた時に、元居たマスのカーソルを消す
#（重複判定し、カーソルの移動後のマスに白か、別のカーソルを表示するかも判定）
def cursor_leave(x, y, target_id):
    size = devices[target_id].cursor_size
    for dx in range(size):
        for dy in range(size):
            cx, cy = x + dx, y + dy
            overlapping = get_overlapping_cursors(cx, cy)
            filtered = [dev for dev in overlapping if dev.id != target_id]
            if len(filtered) > 0:
                top = min(filtered, key=lambda d: cursor_priority.index(d.id))
                sense.set_pixel(cx, cy, top.color)
            else:
                sense.set_pixel(cx, cy, CLEAR)

# カーソルがあるマスから動いた時に、移動先のカーソルを表示
#（重複判定し、カーソルの移動後の移動先が自身のカーソルか、別のカーソルを表示するかも判定）
def cursor_enter(new_x, new_y, color, target_id):
    size = devices[target_id].cursor_size
    all_overlapping = []
    for dx in range(size):
        for dy in range(size):
            cx, cy = new_x + dx, new_y + dy
            overlapping = get_overlapping_cursors(cx, cy)
            overlapping.append(devices[target_id])
            top = min(overlapping, key=lambda d: cursor_priority.index(d.id))
            sense.set_pixel(cx, cy, top.color)
            all_overlapping.extend(overlapping)

    # 捕獲判定
    res = []
    if target_id != HUNTER_ID:
        hunter_present = any(dev.id == HUNTER_ID for dev in all_overlapping)
        print(f"hunter_present = {hunter_present} in side of runner")
        if hunter_present:
            res = [devices[target_id]]
        print(f"cursor_enter res = {debug_device_list(res)} in side of runner")
    else:
        res = [dev for dev in all_overlapping if dev.id != HUNTER_ID]
        print(f"cursor_enter res = {debug_device_list(res)} in side of hunter")
    # 捕獲後の通知
    if len(res)>0:
        caught_ids = [str(dev.id) for dev in res]
        message = f"CATCH {len(caught_ids)} " + " ".join(caught_ids)
        for dev in devices.values():
            if dev.alive:
                send_message(message, dev.addr)

                
def print_all_cursor_status():
    print("=== Cursor Status ======================")
    for dev_id, dev in devices.items():
        status = "ON" if dev.onMyPi else "OFF"
        print(f"Pi{dev_id}: pos={dev.position}, onMyPi={status}, {get_color_name(dev.color)}")
    print("========================================")

def debug_device_list(devices_list):
    debug_info = [(dev.id, get_color_name(dev.color)) for dev in devices_list]
    return f"{debug_info}"

# 加速度センサーの値から傾きの方向を判定する
def get_direction():
    orientation = sense.get_orientation_radians()

    # ピッチとロールを整数値として抽出（四捨五入）
    pitch = 100 * orientation['pitch']
    roll = 100 * orientation['roll']

    # xとyの大きい方を選択
    flag = 0
    if abs(pitch) >= abs(roll):
        flag = 1

    if (flag == 1):
        if 20 <= pitch <= 90:
            return "left"
        elif -90 <= pitch <= -20:
            return "right"
    else:
        if 20 <= roll <= 90:
            return "down"
        elif -90 <= roll <= -20:
            return "up"
    return None

# 指定されたメッセージを指定された宛先のPiにUDPで送信する
def send_message(message, dst_addr):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # sock.bind((SRC_ADDR, SRC_PORT))
        sock.sendto(message.encode(), (dst_addr, DST_PORT))
        print(f"Send {message} to {dst_addr}")

def broadcast_message(message):
    for dev in devices.values():
        send_message(message, dev.addr)

def trigger_shuffle():
    """Shuffle the layout of currently active devices."""
    active = [dev.id for dev in devices.values() if dev.alive]
    if len(active) <= 1:
        return

    original = active[:]
    new_layout = active[:]
    while new_layout == original:
        random.shuffle(new_layout)

    msg = "SHUFFLE " + ",".join(str(i) for i in new_layout)
    broadcast_message(msg)
    handle_shuffle(new_layout)

def check_shuffle_button():
    for event in sense.stick.get_events():
        if event.action == 'pressed' and event.direction == 'middle':
            return True
    return False

# 移動先の座標を求める & 遷移判定
def get_new_position(old_x, old_y, direction, size, step, adj):
    """Return the next position of a cursor and whether it crossed to another Pi."""
    hasCrossed = False

    # Compute tentative position based on direction and step size
    new_x, new_y = old_x, old_y
    if direction == "up":
        new_y -= step
    if direction == "down":
        new_y += step
    if direction == "left":
        new_x -= step
    if direction == "right":
        new_x += step

    # Vertical bounds
    if new_y < 0:
        if adj[0] != NO_NEIGHBOR:
            new_y = HEIGHT - size
            hasCrossed = True
        else:
            new_y = 0
    elif new_y > HEIGHT - size:
        if adj[2] != NO_NEIGHBOR:
            new_y = 0
            hasCrossed = True
        else:
            new_y = HEIGHT - size

    # Horizontal bounds
    if new_x < 0:
        if adj[3] != NO_NEIGHBOR:
            new_x = WIDTH - size
            hasCrossed = True
        else:
            new_x = 0
    elif new_x > WIDTH - size:
        if adj[1] != NO_NEIGHBOR:
            new_x = 0
            hasCrossed = True
        else:
            new_x = WIDTH - size

    return new_x, new_y, hasCrossed

# 遷移先のPiを求める
def get_next_pi(direction, adj: Tuple[int, int, int, int]):
    mapping = {"up": 0, "right": 1, "down": 2, "left": 3}
    idx = mapping.get(direction)
    if idx is None:
        return -1
    return adj[idx] if adj[idx] != NO_NEIGHBOR else -1

def random_coordinate(max_value, step):
    values = list(range(0, max_value + 1, step))
    return random.choice(values)

# ネットワークリスナー（サーバプログラム）
def network_listener():
    global my_cursor_locator
    global exit_flag
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((MY_PI.addr, DST_PORT))
        while True:
            data, addr_port = sock.recvfrom(BUFFER_SIZE)
            
            msg = data.decode()
            print(f"Received {msg} from {addr_port[0]}")
            parts = msg.split(' ')
            command = parts[0]

            if time.time() < operation_lock_until and command in {"MOVE", "DRAW", "CROSS"}:
                continue
           

            if command == "MOVE":
                direction = parts[1]
                cursor_id = int(parts[2])



                # 送信元Piを特定（操作しているPi）
                sender_ip = addr_port[0]
                sender_id = addr_to_id.get(sender_ip)
                sender = devices[sender_id]

                # 実際に動かすカーソルのデバイス情報
                cursor_dev = devices[cursor_id]

                # カーソルの現在位置
                x = cursor_dev.position[0]
                y = cursor_dev.position[1]

                # 移動先座標の計算と遷移判定
                new_x, new_y, hasCrossed = get_new_position(
                    x,
                    y,
                    direction,
                    cursor_dev.cursor_size,
                    cursor_dev.move_step,
                    MY_PI.adj,
                )
                print(f"[MOVE] cursor_id={cursor_id} (x, y)=({x}, {y}), new=({new_x}, {new_y})")

                if hasCrossed: # 座標の境界を超える
                    next_pi = get_next_pi(direction, MY_PI.adj)
                    if next_pi == -1:
                        print(f"[MOVE] Cannot move {direction}, no adjacent alive Pi.")
                        continue  # 無効な移動先なので処理スキップ
                    if next_pi == MY_PI_ID:
                        #if is_movable(new_x, new_y): # 重複判定
                        cursor_leave(x, y, cursor_id)
                        cursor_enter(new_x, new_y, cursor_dev.color, cursor_id)
                        cursor_dev.position = [new_x, new_y]
                    else:
                        send_message(f"CROSS {next_pi} {new_x} {new_y} {cursor_id}", sender.addr)
                        cursor_dev.onMyPi = False
                        cursor_leave(x, y, cursor_id)
                else:
                    #update_position(x, y, new_x, new_y, cursor_dev)
                    cursor_leave(x, y, cursor_id)
                    cursor_enter(new_x, new_y, cursor_dev.color, cursor_id)
                    cursor_dev.position = [new_x, new_y]

            elif command == "DRAW": # 他のPiのカーソルを新たに描画
                x, y, pi, cursor_id = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                cursor_pi = devices.get(pi)
                cursor_pi.onMyPi = True
                cursor_pi.position = [x, y]
                cursor_enter(x, y, cursor_pi.color, cursor_id)
                print(f"[DRAW] cursor_id={cursor_id}, {cursor_pi.position}")
            
            elif command == "CROSS": # 自身のカーソルが遷移
                next_pi, x, y, cursor_id = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                print(f"[CROSS] cursor_id={cursor_id}")
                if next_pi == MY_PI_ID: # 遷移先が自身のPi
                    MY_PI.onMyPi = True
                    MY_PI.position = [x, y]
                    cursor_enter(x, y, MY_PI.color, cursor_id)
                else:
                    next_addr = devices.get(next_pi).addr
                    send_message(f"DRAW {x} {y} {MY_PI_ID} {cursor_id}", next_addr)
                    my_cursor_locator = next_addr
            elif command == "SHUFFLE":
                new_order = list(map(int, parts[1].split(',')))
                handle_shuffle(new_order)
            elif command == "CATCH":
                num = int(parts[1])
                caught_ids = list(map(int, parts[2:2+num])) #捕獲された逃走者のID
                print(f"[CATCH] Received catch list: {caught_ids}")
                # devicesのalive情報を更新
                for cid in caught_ids:
                    devices[cid].alive = False  #@
                    print(f"[CATCH] Marked Pi{cid} as not alive.")
                    if cid in layout:
                        layout.remove(cid)

                # Update adjacency info for remaining devices
                for dev_id, adj in compute_adj_from_layout(layout).items():
                    devices[dev_id].adj = adj
                    print(f"[CATCH] Reconnected Pi{dev_id}: adj={devices[dev_id].adj}")


                # 自分自身が捕まっているかチェックして終了処理
                if MY_PI_ID in caught_ids and MY_PI_ID != HUNTER_ID:
                    print(f"[CATCH] You (Pi{MY_PI_ID}, {get_color_name(devices[MY_PI_ID].color)}) were caught by the hunter.")
                    local_alive_devices = [dev for dev in devices.values() if dev.alive and dev.onMyPi]
                    print(f"[CATCH] Local alive devices on Pi{MY_PI_ID}: {[dev.id for dev in local_alive_devices]}")

                    # === ここでテレポート処理を追加 ===
                    alive_pi_ids = [dev.id for dev in devices.values() if dev.alive] #テレポート先候補
                    random.shuffle(alive_pi_ids) 
                    for dev, target_pi_id in zip(local_alive_devices, alive_pi_ids):
                        target_x = random_coordinate(WIDTH - dev.cursor_size, dev.move_step)
                        target_y = random_coordinate(HEIGHT - dev.cursor_size, dev.move_step)
                        dest_pos = [target_x, target_y]

                        print(f"[CATCH] Teleporting Pi{dev.id} to Pi{target_pi_id} at {dest_pos}")

                        if target_pi_id == MY_PI_ID:
                            # 自分のPiなら直接描画
                            cursor_leave(dev.position[0], dev.position[1], dev.id)
                            dev.position = dest_pos
                            cursor_enter(dest_pos[0], dest_pos[1], dev.color, dev.id)
                        else:
                            # 他のPiに転送
                            send_message(f"CROSS {target_pi_id} {dest_pos[0]} {dest_pos[1]} {dev.id}", dev.addr)
                            cursor_leave(dev.position[0], dev.position[1], dev.id)

                    #MY_PI.alive = False
                    sense.show_message("CAUGHT!", text_colour=RED)
                    time.sleep(1.5)
                    sense.clear()
                    exit_flag = True  # プログラム全体の終了を通知
                    return    # スレッド終了

            elif command == "CHECK":
                x, y, cursor_pi, cursor_id = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                device = devices.get(cursor_pi)
                
                if device.id == MY_PI_ID: MY_PI.onMyPi = True
                
                cursor_enter(x, y, device.color, cursor_id)
                device.position = [x, y]

# メイン関数（クライアントプログラム）
if __name__ == "__main__":
    
    # Initialization
    listener_thread = threading.Thread(target=network_listener, daemon=True)
    listener_thread.start()

    sense.clear()
    draw_cursor(MY_PI.position[0], MY_PI.position[1], MY_PI.color, MY_PI.cursor_size)

    print_all_cursor_status()

    try:
        while not exit_flag:
            if time.time() > operation_lock_until and check_shuffle_button():
                trigger_shuffle()
                continue

            if time.time() < operation_lock_until:
                time.sleep(0.1)
                continue

            direction = get_direction()

            if direction:
                if MY_PI.onMyPi:
                    x, y = MY_PI.position
                    new_x, new_y, hasCrossed = get_new_position(
                        x,
                        y,
                        direction,
                        MY_PI.cursor_size,
                        MY_PI.move_step,
                        MY_PI.adj,
                    )

                    if hasCrossed: # 座標の境界を超える
                        next_pi = get_next_pi(direction, MY_PI.adj)
                        if next_pi == -1:
                            print(f"[MOVE] Cannot move {direction}, no adjacent alive Pi.")
                            continue  # 無効な移動先なので処理スキップ
                        if next_pi == MY_PI_ID:
                            #if is_movable(new_x, new_y): # 重複判定
                                cursor_leave(x, y, MY_PI.id)
                                cursor_enter(new_x, new_y, MY_PI.color, MY_PI.id)
                                MY_PI.position = [new_x, new_y]
                        else: # 他のPiに遷移
                            send_message(f"DRAW {new_x} {new_y} {MY_PI_ID} {MY_PI.id}", devices.get(next_pi).addr)
                            cursor_leave(x, y, MY_PI.id)
                            MY_PI.onMyPi = False
                            my_cursor_locator = devices.get(next_pi).addr
                    else: 
                        #update_position(x, y, new_x, new_y, MY_PI)
                        cursor_leave(x, y, MY_PI.id)
                        cursor_enter(new_x, new_y, MY_PI.color, MY_PI.id)
                        MY_PI.position = [new_x, new_y]
                else:
                    send_message(f"MOVE {direction} {MY_PI.id}", my_cursor_locator)
            
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("プログラムを終了します。")
    finally:
        sense.clear()
