from sense_hat import SenseHat
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
    adj: Tuple[int, int] # [上下のPiのID, 左右のPiのID]
    onMyPi: bool
    alive: bool

# ラズパイ群（4台）
devices: Dict[int, DeviceInfo] = {
    0: DeviceInfo(0, "192.168.10.1", RED, [2, 2], (2, 1), False, True),
    1: DeviceInfo(1, "192.168.10.2", GREEN, [2, 2], (3, 0), False, True),
    2: DeviceInfo(2, "192.168.10.3", BLUE, [2, 2], (0, 3), False, True),
    3: DeviceInfo(3, "192.168.10.4", YELLOW, [2, 2], (1, 2), False, True),
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
CURSOR_SIZE = 2
MOVE_STEP = 2

# センサー感度
TILT_THRESHOLD = 0.3

# カーソルの優先順位
cursor_priority = sorted(devices.keys())

#鬼のラズパイのID
HUNTER_ID=0

exit_flag = False  # プログラム終了要求フラグ


# 指定された座標にカーソルを描画する
def draw_cursor(x, y, color):
    for dx in range(CURSOR_SIZE):
        for dy in range(CURSOR_SIZE):
            # 念のため範囲外描画を防ぐ
            if 0 <= x + dx < WIDTH and 0 <= y + dy < HEIGHT:
                sense.set_pixel(x + dx, y + dy, color)

# そのピクセルに現在存在するカーソルのリストを取得
def get_overlapping_cursors(x, y):
    print_all_cursor_status()
    overlapping = []
    for dev_id in cursor_priority:
        dev = devices[dev_id]
        if dev.onMyPi and dev.position == [x, y]:
            overlapping.append(dev)
    
    return overlapping
            

# カーソルがあるマスから動いた時に、元居たマスのカーソルを消す
#（重複判定し、カーソルの移動後のマスに白か、別のカーソルを表示するかも判定）
def cursor_leave(x, y, target_id):
    overlapping = get_overlapping_cursors(x, y)
    overlapping_display = [(dev.id, get_color_name(dev.color)) for dev in overlapping]
    print(f"[{x},{y}] overlapping: {overlapping_display}")
    filtered = [dev for dev in overlapping if dev.id != target_id]
    filtered_display = [(dev.id, get_color_name(dev.color)) for dev in filtered]
    print(f"[{x},{y}] overlapping: {filtered_display} in cursor_leave target_id={target_id}")
    if len(filtered) > 0:
        top = min(filtered, key=lambda d: cursor_priority.index(d.id))
        draw_cursor(x, y, top.color)
    else:
        draw_cursor(x, y, CLEAR)

# カーソルがあるマスから動いた時に、移動先のカーソルを表示
#（重複判定し、カーソルの移動後の移動先が自身のカーソルか、別のカーソルを表示するかも判定）
def cursor_enter(new_x, new_y, color, target_id):
    overlapping = get_overlapping_cursors(new_x, new_y)
    overlapping.append(devices[target_id]) #移動先には自カーソルがないので、自カーソルを追加
    overlapping_display = [(dev.id, get_color_name(dev.color)) for dev in overlapping]
    print(f"[{new_x},{new_y}] overlapping: {overlapping_display} in cursor_enter")

    top = min(overlapping, key=lambda d: cursor_priority.index(d.id))
    draw_cursor(new_x, new_y, top.color)
    

    # 捕獲判定
    res=[] #捕まった逃走者のdeviceリスト
    if target_id != HUNTER_ID:
        #注目するカーソル(target_id)が逃走者
        # 鬼でないカーソルが移動してきた場合：そこに鬼がいるか確認
        hunter_present = any(dev.id == HUNTER_ID for dev in overlapping)
        print(f"hunter_present = {hunter_present} in side of runner")
        if hunter_present:
            res = [devices[target_id]]
        print(f"cursor_enter res = {debug_device_list(res)} in side of runner")
    else:
        #注目するカーソル(target_id)が鬼
        # 鬼が移動してきた場合：そこに逃走者がいるか確認（鬼以外）
        res = [dev for dev in overlapping if dev.id != HUNTER_ID]
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
    sense = SenseHat()
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
            return "right"
        elif -90 <= pitch <= -20:
            return "left"
    else:
        if 20 <= roll <= 90:
            return "up"
        elif -90 <= roll <= -20:
            return "down"
    return None

# 指定されたメッセージを指定された宛先のPiにUDPで送信する
def send_message(message, dst_addr):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # sock.bind((SRC_ADDR, SRC_PORT))
        sock.sendto(message.encode(), (dst_addr, DST_PORT))
        print(f"Send {message} to {dst_addr}")

# 移動先の座標を求める & 遷移判定
def get_new_position(old_x, old_y, direction):
    hasCrossed = True

    # 現在位置から移動先を計算
    new_x, new_y = old_x, old_y
    if direction == "up":    new_y += MOVE_STEP
    if direction == "down":  new_y -= MOVE_STEP
    if direction == "left":  new_x += MOVE_STEP
    if direction == "right": new_x -= MOVE_STEP

    # 1. 左右の壁の処理 (画面内に収める)
    # if next_x < 0:
    #     next_x = 0
    # if next_x > WIDTH - CURSOR_SIZE:
    #     next_x = WIDTH - CURSOR_SIZE

    if new_y > HEIGHT - CURSOR_SIZE: new_y = 0   # 上のラズパイに遷移
    elif new_y < 0: new_y = HEIGHT - CURSOR_SIZE # 下のラズパイに遷移
    elif new_x > WIDTH - CURSOR_SIZE: new_x = 0  # 左のラズパイに遷移
    elif new_x < 0: new_x = WIDTH - CURSOR_SIZE  # 右のラズパイに遷移
    else: hasCrossed = False                     # 遷移しない
    
    return new_x, new_y, hasCrossed

# 遷移先のPiを求める
def get_next_pi(direction, adj: Tuple[int, int]):
    if direction in ["up", "down"]:
        return adj[0] if adj[0] is not None else -1  # -1: 無効な移動先
    else:
        return adj[1] if adj[1] is not None else -1

 # 偶数のみを選ぶ範囲でランダムに座標を決定   
def random_even_coordinate(max_value):
    even_range = list(range(0, max_value + 1, 2))  # 0, 2, 4, 6 ...
    return random.choice(even_range)

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
           

            if command == "MOVE":
                direction = parts[1]
                cursor_id = int(parts[2])

                

                # 送信元Piを特定
                sender_ip = addr_port[0]
                sender_id = addr_to_id.get(sender_ip)
                sender = devices[sender_id]
                
                # カーソルの現在位置
                x = sender.position[0]
                y = sender.position[1]

                # 移動先座標の計算と遷移判定
                new_x, new_y, hasCrossed = get_new_position(x, y, direction)
                print(f"[MOVE] cursor_id={cursor_id} (x, y)=({x}, {y}), new=({new_x}, {new_y})")

                if hasCrossed: # 座標の境界を超える
                    next_pi = get_next_pi(direction, MY_PI.adj)
                    if next_pi == -1:
                        print(f"[MOVE] Cannot move {direction}, no adjacent alive Pi.")
                        continue  # 無効な移動先なので処理スキップ
                    if next_pi == MY_PI_ID:
                        #if is_movable(new_x, new_y): # 重複判定
                        cursor_leave(x, y, cursor_id)
                        cursor_enter(new_x, new_y, sender.color, cursor_id)
                        sender.position = [new_x, new_y]
                    else:
                        send_message(f"CROSS {next_pi} {new_x} {new_y} {cursor_id}", sender.addr)
                        sender.onMyPi = False
                        cursor_leave(x, y, cursor_id)
                else:
                    #update_position(x, y, new_x, new_y, sender)
                    cursor_leave(x, y, cursor_id)
                    cursor_enter(new_x, new_y, sender.color, cursor_id)
                    sender.position = [new_x, new_y]

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
            elif command == "CATCH":
                num = int(parts[1])
                caught_ids = list(map(int, parts[2:2+num])) #捕獲された逃走者のID
                print(f"[CATCH] Received catch list: {caught_ids}")
                # devicesのalive情報を更新
                for cid in caught_ids:
                    devices[cid].alive = False #@
                    print(f"[CATCH] Marked Pi{cid} as not alive.")

                # CATCHコマンドを受け取ったラズパイが捕獲されていなかった場合、
                # 自身のadjを生存Piだけに制限する
                if MY_PI_ID not in caught_ids:
                    new_adj = list(devices[MY_PI_ID].adj)  # 一旦リスト化して変更可能に

                    for i, neighbor_id in enumerate(new_adj):
                        if not devices[neighbor_id].alive:
                            print(f"[CATCH] Pi{neighbor_id} is dead. Removing from adj of Pi{MY_PI_ID}")
                            new_adj[i] = None  # 生存していないなら無効化

                    devices[MY_PI_ID].adj = tuple(new_adj)
                    print(f"[CATCH] Updated adj for Pi{MY_PI_ID}: {devices[MY_PI_ID].adj}")
                # 生存PiのID一覧（ソートしておくと循環割り当てが安定）
                alive_ids = sorted([dev.id for dev in devices.values() if dev.alive])

                n = len(alive_ids)
                for i, pi_id in enumerate(alive_ids):
                    up_down_id = alive_ids[(i + 1) % n]  # 次の生存Piを上下に
                    left_right_id = alive_ids[(i + 2) % n] if n > 2 else alive_ids[(i + 1) % n]  # 2台だけなら上下=左右
                    devices[pi_id].adj = (up_down_id, left_right_id)
                    print(f"[CATCH] Reconnected Pi{pi_id}: adj={devices[pi_id].adj}")


                # 自分自身が捕まっているかチェックして終了処理
                if MY_PI_ID in caught_ids and MY_PI_ID != HUNTER_ID:
                    print(f"[CATCH] You (Pi{MY_PI_ID}, {get_color_name(devices[MY_PI_ID].color)}) were caught by the hunter.")
                    local_alive_devices = [dev for dev in devices.values() if dev.alive and dev.onMyPi]
                    print(f"[CATCH] Local alive devices on Pi{MY_PI_ID}: {[dev.id for dev in local_alive_devices]}")

                    # === ここでテレポート処理を追加 ===
                    alive_pi_ids = [dev.id for dev in devices.values() if dev.alive] #テレポート先候補
                    random.shuffle(alive_pi_ids) 
                    for dev, target_pi_id in zip(local_alive_devices, alive_pi_ids):
                        target_x = random_even_coordinate(WIDTH - CURSOR_SIZE)
                        target_y = random_even_coordinate(HEIGHT - CURSOR_SIZE)
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
                    time.sleep(1)
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
    draw_cursor(MY_PI.position[0], MY_PI.position[1], MY_PI.color)

    print_all_cursor_status()

    try:
        while not exit_flag:
            direction = get_direction()

            if direction:
                if MY_PI.onMyPi:
                    x, y = MY_PI.position
                    new_x, new_y, hasCrossed = get_new_position(x, y, direction)

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
