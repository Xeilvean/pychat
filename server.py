import socket
import threading
import os
from datetime import datetime

HOST = "0.0.0.0"    
PORT = 5555

clients = []
client_names = {}
client_colors = {}
lock = threading.Lock()


HISTORY_FILE = "history.log"

def log_to_history(text):
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"{text}\n")
    except Exception as e:
        print(f"Ошибка записи истории: {e}")

def get_history():
    """Читает весь файл истории."""
    if not os.path.exists(HISTORY_FILE):
        return ""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_msg(sock):
    header = recv_exact(sock, 4)
    if header is None:
        return None
    length = int.from_bytes(header, "big")
    if length == 0:
        return ""
    data = recv_exact(sock, length)
    if data is None:
        return None
    return data.decode("utf-8")


def send_msg(sock, text):
    data = text.encode("utf-8")
    sock.sendall(len(data).to_bytes(4, "big") + data)


def broadcast(text, sender_conn=None):
    with lock:
        for c in list(clients):
            if c is sender_conn:
                continue
            try:
                send_msg(c, text)
            except OSError:
                pass
def broadcast_user_list():
    with lock:
        # Формат: Имя1|Цвет1,Имя2|Цвет2
        user_data = [f"{name}|{client_colors.get(conn, '#000000')}" for conn, name in client_names.items()]
        text = "USERLIST:" + ",".join(user_data)
        for c in list(clients):
            try:
                send_msg(c, text)
            except OSError:
                pass

def handle_client(conn, addr):
    print(f"[+] Подключился еще один бедняга {addr}")
    with lock:
        clients.append(conn)
    
    history = get_history()
    if history:
        try:
            send_msg(conn, "--- ИСТОРИЯ СООБЩЕНИЙ ---\n" + history + "--------------------------")
        except OSError:
            pass

    try:
        while True:
            msg = recv_msg(conn)
            if msg is None:
                break
            
            # Если клиент прислал имя при подключении
            if msg.startswith("LOGIN:"):
                payload = msg[6:]
                if "|" in payload:
                    username, color = payload.split("|", 1)
                else:
                    username, color = payload, "black"
                
                # ПРОВЕРКА НА ОДИНАКОВЫЕ ИМЕНА
                with lock:
                    existing_names = list(client_names.values())
                
                if username in existing_names:
                    try:
                        send_msg(conn, "LOGIN_ERROR:Ты тут не один такой умный.")
                    except OSError:
                        pass
                    break # Отключаем клиента
                
                with lock:
                    client_names[conn] = username
                    client_colors[conn] = color
                
                broadcast_user_list()
                continue

            if msg.startswith("FILE:"):
                print(f"[{addr}] Отправляет файл...")
                broadcast(msg) # Пересылаем всем, но НЕ сохраняем в историю
                continue

            # ОБЫЧНАЯ ОТПРАВКА СООБЩЕНИЙ
            print(f"[{addr}] {msg}")
            log_to_history(msg) 
            broadcast(msg) # Отправляем ВСЕМ, включая отправителя
            
    except OSError:
        pass
    finally:
        # УБОРКА ПРИ ОТКЛЮЧЕНИИ
        with lock:
            if conn in clients:
                clients.remove(conn)
            if conn in client_names:
                del client_names[conn]
            if conn in client_colors:
                del client_colors[conn]
        conn.close()
        print(f"[-] Отключился {addr}")
        broadcast("*** Участник покинул это болото ***")
        broadcast_user_list()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen()
    print(f"Сервер слушает на {HOST}:{PORT}")
    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nСервер остановился и сдох")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
