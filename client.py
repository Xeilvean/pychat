import pygame
from tkinter import ttk
import glob
import socket
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext
from tkinterdnd2 import TkinterDnD, DND_FILES 
from datetime import datetime
import base64
from tkinter import filedialog
import os
import sys
import shutil
import subprocess

import io
import requests
from PIL import Image

 

_root_ref = None


def play_notification_sound(sound_file):
    if not sound_file or sound_file == "Нет файлов":
        sound_file = "rtone.wav"
        
    sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), sound_file)
    
    if not os.path.isfile(sound_path):
        # Если файла нет — стандартный бип
        try:
            if _root_ref is not None:
                _root_ref.bell()
        except Exception:
            pass
        return

    try:
        if sys.platform.startswith("win"):
            # Инициализируем микшер один раз
            if not pygame.mixer.get_init():
                pygame.mixer.init()
                
            # Загружаем звук и играем его
            sound = pygame.mixer.Sound(sound_path)
            sound.play()
            return
            
        if sys.platform == "darwin":
            if shutil.which("afplay"):
                subprocess.Popen(["afplay", sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
                
        for player in ("paplay", "aplay", "ffplay"):
            if shutil.which(player):
                if player == "ffplay":
                    cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", sound_path]
                else:
                    cmd = [player, sound_path]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
    except Exception as e:
        print(f"Ошибка звука: {e}")
        try:
            if _root_ref is not None:
                _root_ref.bell()
        except Exception:
            pass

def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf

def get_name_color(name):
    """Генерирует стабильный цвет для ника на основе его имени."""
    # Красивая палитра цветов
    colors = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#008080", "#9a6324"]
    # Суммируем коды символов имени
    color_index = sum(ord(c) for c in name) % len(colors)
    return colors[color_index]

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

def url_to_ascii(url, width=40):
    """Скачивает картинку по ссылке и переводит её в текст."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        # Открываем картинку из памяти
        img = Image.open(io.BytesIO(response.content))
        
        # Переводим в ч/б для лучшего восприятия
        img = img.convert("L")
        
        # Вычисляем высоту с учетом того, что символы в высоту больше, чем в ширину
        w, h = img.size
        aspect_ratio = h / w
        new_height = int(aspect_ratio * width * 0.5)
        img = img.resize((width, new_height))
        
        # Символы от самого темного к самому светлому
        ascii_chars = "@%#*+=-:. "
        
        pixels = img.getdata()
        ascii_str = ""
        for i, pixel in enumerate(pixels):
            # Находим подходящий символ (0 - черный, 255 - белый)
            ascii_str += ascii_chars[pixel // 25]
            if (i + 1) % width == 0:
                ascii_str += "\n"
                
        return ascii_str
    except Exception as e:
        return f"[Хрен тебе, кожаный, а не картинка: {e}]"


class ChatClient:

    def choose_color(self):
        from tkinter import colorchooser
        color = colorchooser.askcolor(title="Выбери цвет своего ника")[1]
        if color:
            self.chosen_color = color
            self.color_btn.config(bg=color)

    def __init__(self, root):
        global _root_ref  
        self.root = root
        _root_ref = root
        self.root.title("Болото на общем сервере")
        self.root.geometry("650x480")
        self.sock = None
        self.username = ""
        self.connected = False

        # ---------- панель подключения ----------
        top = tk.Frame(root)
        top.pack(fill=tk.X, padx=5, pady=5)

        # 1. Выбор сервера (с историей)
        tk.Label(top, text="Сервер:").pack(side=tk.LEFT)
        self.host_entry = ttk.Combobox(top, width=15)
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.load_recent_servers() # Загружаем историю серверов

        # 2. Порт
        tk.Label(top, text="Порт:").pack(side=tk.LEFT)
        self.port_entry = tk.Entry(top, width=6)
        self.port_entry.insert(0, "5555")
        self.port_entry.pack(side=tk.LEFT, padx=(0, 5))

        # 3. Имя
        tk.Label(top, text="Имя:").pack(side=tk.LEFT)
        self.name_entry = tk.Entry(top, width=10)
        self.name_entry.insert(0, "user")
        self.name_entry.pack(side=tk.LEFT, padx=(0, 5))

        # Выбор цвета
        tk.Label(top, text="Цвет:").pack(side=tk.LEFT)
        self.color_btn = tk.Button(top, text="🎨", command=self.choose_color, bg="black", width=3)
        self.color_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.chosen_color = "black" # Цвет по умолчанию

        # 4. Выбор рингтона
        tk.Label(top, text="Звук:").pack(side=tk.LEFT)
        self.sound_combo = ttk.Combobox(top, width=12, state="readonly")
        self.sound_combo.pack(side=tk.LEFT, padx=(0, 5))
        self.load_sounds() # Загружаем список .wav файлов
        print("Доступные звуки:", glob.glob("*.wav"))

        # 5. Кнопка подключения
        self.connect_btn = tk.Button(top, text="В болото", command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT)


        # ---------- основная область (список слева, чат справа) ----------
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.user_listbox = tk.Listbox(main_frame, width=20, font=("Consolas", 10), bg="#f0f0f0")
        self.user_listbox.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))

        self.chat = scrolledtext.ScrolledText(main_frame, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 10))
        self.chat.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Привязка клика для функции "Ответить"
        self.chat.bind("<Button-1>", self.on_chat_click)
        self.chat.drop_target_register(DND_FILES)
        self.chat.dnd_bind('<<Drop>>', self.on_drop_file)

        # ---------- строка ввода ----------
        bottom = tk.Frame(root)
        bottom.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.msg_entry = tk.Entry(bottom)
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.msg_entry.bind("<Return>", lambda e: self.send())

        self.send_btn = tk.Button(bottom, text="Отправить почтового голубя", command=self.send, state=tk.DISABLED)
        self.send_btn.pack(side=tk.LEFT, padx=(5, 0))
        self.file_btn = tk.Button(bottom, text="Файл", command=self.send_file, state=tk.DISABLED)
        self.file_btn.pack(side=tk.LEFT, padx=(5, 0))

    # ---------- логика ----------\
    def load_recent_servers(self):
        """Загружает последние 5 серверов из файла."""
        self.recent_servers_file = "recent_servers.txt"
        if os.path.exists(self.recent_servers_file):
            with open(self.recent_servers_file, "r", encoding="utf-8") as f:
                servers = [line.strip() for line in f if line.strip()]
                self.host_entry['values'] = servers[:5]

    def save_recent_server(self, host):
        """Сохраняет сервер в историю (максимум 5)."""
        servers = list(self.host_entry['values'])
        if host in servers:
            servers.remove(host)
        servers.insert(0, host) # Новый сервер в начало
        servers = servers[:5]   # Оставляем только 5
        self.host_entry['values'] = servers
        
        with open(self.recent_servers_file, "w", encoding="utf-8") as f:
            for s in servers:
                f.write(f"{s}\n")

    def load_sounds(self):
        """Ищет все .wav файлы в папке и добавляет их в список."""
        sounds = glob.glob("*.wav")
        if not sounds:
            sounds = ["Нет файлов"]
        self.sound_combo['values'] = sounds
        if "rtone.wav" in sounds:
            self.sound_combo.set("rtone.wav")
        else:
            self.sound_combo.current(0)

    def toggle_connection(self):
        if self.connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        host = self.host_entry.get().strip()
        try:
            port = int(self.port_entry.get().strip())
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный порт")
            return
        name = self.name_entry.get().strip() or "user"

        try:
            sock = socket.create_connection((host, port), timeout=5)
            sock.settimeout(None) 
        except OSError as e:
            messagebox.showerror("Ошибка подключения", str(e))
            return

        self.sock = sock
        self.username = name
        self.connected = True
        self.connect_btn.config(text="Отключиться от этого ада")
        self.send_btn.config(state=tk.NORMAL)
        self.file_btn.config(state=tk.NORMAL)
        self.save_recent_server(host)
        self.append_system(f'Ты подключился к болоту "{host}:{port}" с дурацким именем «{name}»')
        try:
            send_msg(self.sock, f"LOGIN:{name}|{self.chosen_color}")
        except OSError:
            pass

        # --------------------------------

        threading.Thread(target=self.receive_loop, daemon=True).start()

    def disconnect(self):
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self.connect_btn.config(text="Открыть портал в болото")
        self.send_btn.config(state=tk.DISABLED)
        self.file_btn.config(state=tk.DISABLED)
        
        self.user_listbox.delete(0, tk.END)
        self.append_system("Вы отключились и вернули свое психическое здоровье")

    def receive_loop(self):
        while self.connected and self.sock:
            try:
                msg = recv_msg(self.sock)
            except OSError:
                msg = None
            if msg is None:
                if self.connected:
                    self.root.after(0, self.on_disconnect)
                return
            self.root.after(0, self.on_incoming_message, msg)

          

    def on_disconnect(self):
        if self.connected:
            self.disconnect()
            self.append_system("Соединение с сервером потеряно, он выше этого")

    def on_incoming_message(self, msg):
        if msg.startswith("LOGIN_ERROR:"):
            err_msg = msg[12:]
            messagebox.showerror("Отказ", err_msg)
            self.disconnect()
            return

        if msg.startswith("USERLIST:"):
            users = msg[9:].split(",")
            self.user_listbox.delete(0, tk.END)
            for u in users:
                if u:
                    if "|" in u:
                        uname, ucolor = u.split("|", 1)
                        self.user_listbox.insert(tk.END, "🟢 " + uname)
                        self.user_listbox.itemconfig(tk.END, {'fg': ucolor})
                    else:
                        self.user_listbox.insert(tk.END, "🟢 " + u)
            return 
        if msg.startswith("FILE:"):
            try:
                # Отделяем имя файла от данных
                parts = msg.split(":", 2)
                filename = parts[1]
                file_data = parts[2]
                
                self.append_message(f"[Получен файл: {filename}]")
                play_notification_sound(self.sound_combo.get())
                
                # Спрашиваем, куда сохранить
                save_path = filedialog.asksaveasfilename(
                    title="Сохранить файл",
                    initialfile=filename,
                    defaultextension=".*"
                )
                if save_path:
                    with open(save_path, "wb") as f:
                        f.write(base64.b64decode(file_data))
                    self.append_system(f"Файл сохранён: {save_path}")
            except Exception as e:
                self.append_system(f"Ошибка при получении файла: {e}")
            return

        # Выводим сообщение на экран
        self.append_message(msg)
        
        # Проверяем, нужно ли играть звук
        # Проверяем, нужно ли играть звук
        if not msg.startswith("***") and "--- ИСТОРИЯ" not in msg:
            # Ищем ваш ник в начале сообщения
            if f"{self.username}|" not in msg and f"{self.username}:" not in msg:
                chosen_sound = self.sound_combo.get()
                print(f"ВХОДЯЩЕЕ! Играю звук: {chosen_sound}") # Для отладки
                play_notification_sound(chosen_sound)
                
    def on_chat_click(self, event):
        index = self.chat.index(f"@{event.x},{event.y}")
        line = int(index.split(".")[0])
        line_text = self.chat.get(f"{line}.0", f"{line}.end").strip()
        
        # Ищем квадратные скобки и двоеточие
        if line_text.startswith("[") and "]" in line_text and ":" in line_text:
            try:
                # Вырезаем время
                close_bracket = line_text.find("]")
                rest = line_text[close_bracket+1:].strip()
                
                if rest.startswith(":"):
                    rest = rest[1:].strip()
                    
                # Вырезаем имя
                if ":" in rest:
                    name, msg_text = rest.split(":", 1)
                    name = name.strip()
                    msg_text = msg_text.strip()
                else:
                    name = rest.strip()
                    msg_text = ""
                
                # Вставляем в поле ввода
                self.msg_entry.delete(0, tk.END) 
                self.msg_entry.insert(0, f"Ответ для {name} {{{msg_text}}} ")
                self.msg_entry.focus()
                self.msg_entry.icursor(tk.END) 
            except Exception:
                pass
 
    def send(self):
        if not self.connected or not self.sock:
            return
        text = self.msg_entry.get().strip()
        if not text:
            return
        
        self.msg_entry.delete(0, tk.END)
        self.send_btn.config(state=tk.DISABLED)
        
        # Формируем базовую строку с цветом
        full = f"[{self.timestamp()}] {self.username}|{self.chosen_color}: "
        
        if text.startswith("http") and " " not in text:
            self.append_system("Скачиваем картинку и переводим в псевдографику, ждите, кожаные")
            self.root.update()
            
            ascii_art = url_to_ascii(text, width=40)
            
            if ascii_art.startswith("Хрен"):
                self.append_system(ascii_art)
                full += text
            else:
                # Картинка отделяется переносом строки
                full += f"\n{ascii_art}"
        else:
            # Если это ответ (есть перенос строки), склеиваем в одну строку
            if "\n" in text:
                text = text.replace("\n", " ")
            full += text
            
        try:
            send_msg(self.sock, full)
             
        except OSError as e:
            self.append_system(f"Почтовый голубь сдох по дороге: {e}")
        finally:
            self.send_btn.config(state=tk.NORMAL)
        return "break"

    def send_file(self):
        if not self.connected or not self.sock:
            return
            
        filepath = filedialog.askopenfilename(title="Выбери файл для отправки")
        if not filepath:
            return
            
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "rb") as f:
                file_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл: {e}")
            return
            
        # Формат: FILE:Имя_файла:Base64_данные
        full_msg = f"FILE:{filename}:{file_data}"
        
        try:
            send_msg(self.sock, full_msg)
            self.append_message(f"[Файл отправлен: {filename}]")
        except OSError as e:
            self.append_system(f"Файл не улетел: {e}")

    def on_drop_file(self, event):
        if not self.connected or not self.sock:
            messagebox.showerror("Ошибка", "Сначала подключитесь к болоту!")
            return
            
        # tkinterdnd2 присылает пути к файлам в фигурных скобках, если в пути есть пробелы
        filepath = event.data.strip()
        if filepath.startswith('{') and filepath.endswith('}'):
            filepath = filepath[1:-1]
            
        if not os.path.isfile(filepath):
            return
            
        filename = os.path.basename(filepath)
        
        # Спрашиваем подтверждение (чтобы случайно не отправить секретный файл)
        if not messagebox.askyesno("Отправка файла", f"Отправить файл «{filename}» в чат?"):
            return
            
        try:
            with open(filepath, "rb") as f:
                file_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл: {e}")
            return
            
        full_msg = f"FILE:{filename}:{file_data}"
        
        try:
            send_msg(self.sock, full_msg)
            self.append_message(f"[Файл отправлен перетаскиванием: {filename}]")
        except OSError as e:
            self.append_system(f"Файл не улетел: {e}")
    def append_message(self, text):
        self.chat.config(state=tk.NORMAL)
        
        # Разбиваем текст на строки
        lines = text.split("\n")
        
        for line in lines:
            if not line.strip():
                continue
                
            # 1. Системные сообщения
            if line.startswith("***") or line.startswith("--- ИСТОРИЯ") or line.startswith("-------"):
                self.chat.tag_config("system_tag", foreground="blue", font=("Consolas", 10, "italic"))
                self.chat.insert(tk.END, line + "\n", "system_tag")
                
            # 2. Обычные сообщения
            elif line.startswith("[") and "]" in line and ":" in line:
                try:
                    close_bracket = line.find("]")
                    time_part = line[1:close_bracket]
                    rest = line[close_bracket+1:].strip()
                    
                    if rest.startswith(":"):
                        rest = rest[1:].strip()
                    
                    # Отделяем текст сообщения от "Имя|Цвет"
                    if ":" in rest:
                        name_color, msg_text = rest.split(":", 1)
                        msg_text = msg_text.strip()
                        
                        # Разделяем имя и цвет (если есть символ |)
                        if "|" in name_color:
                            name, color = name_color.split("|", 1)
                        else:
                            name, color = name_color, "black"
                        name = name.strip()
                    else:
                        name = rest.strip()
                        color = "black"
                        msg_text = ""
                    
                    # Убираем лишние пробелы из цвета
                    color = color.strip()
                    
                    # А) Время
                    self.chat.tag_config("time_tag", foreground="gray", font=("Consolas", 10, "italic"))
                    self.chat.insert(tk.END, f"[{time_part}] ", "time_tag")
                    
                    # Б) Имя с выбранным цветом (если цвет некорректный, будет черным)
                    tag_name = f"color_{name}"
                    self.chat.tag_config(tag_name, foreground=color, font=("Consolas", 10, "bold"))
                    self.chat.insert(tk.END, name, tag_name)
                    
                    # В) Текст сообщения
                    self.chat.insert(tk.END, f": {msg_text}\n")
                    
                except Exception:
                    self.chat.insert(tk.END, line + "\n")
                    
            # 3. Всё остальное (псевдографика)
            else:
                self.chat.insert(tk.END, line + "\n")
            
        self.chat.see(tk.END)
        self.chat.config(state=tk.DISABLED)
             

    def append_system(self, text):
        self.append_message(f"*** {text} ***")

    @staticmethod
    def timestamp():
        return datetime.now().strftime("%H:%M:%S")


def main():
    root = TkinterDnD.Tk() # <--- Новое окно с поддержкой DnD
    ChatClient(root)
    root.mainloop()


if __name__ == "__main__":
    main()

   