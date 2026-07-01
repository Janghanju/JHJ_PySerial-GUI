import serial
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv
from serial.tools import list_ports
import threading
import datetime
import os
from matplotlib.dates import DateFormatter
import numpy as np

# 전역 변수
ser = None
receive_thread = None
last_save_time = datetime.datetime.now()  # 프로그램 시작 시간으로 초기화
save_interval = None
save_filename_label = None
auto_save_label = None
last_auto_save_filename = None

# 데이터 수신용 스레드 클래스 정의
class SerialThread(threading.Thread):
    def __init__(self, ser, data_text, lines, ax):
        threading.Thread.__init__(self)
        self.ser = ser
        self.data_text = data_text
        self.lines = lines
        self.ax = ax
        self.running = True
        self.x_data = []
        self.data = [[] for _ in range(16)]  # 16개의 데이터 채널

    def run(self):
        while self.running:
            if self.ser.is_open:
                try:
                    data_bytes = self.ser.readline().strip()  # 이진 데이터로 읽기

                    # 현재 시간 및 날짜 가져오기
                    current_time = datetime.datetime.now()
                    self.x_data.append(current_time)

                    # 시리얼 통신 값을 각 데이터 채널에 추가
                    data_str = data_bytes.decode('utf-8')  # 바이너리 데이터를 문자열로 디코딩
                    data_list = data_str.split(',')  # 쉼표로 분리된 데이터 리스트로 변환
                    data = [float(value) for value in data_list]  # 부동소수점 형태로 변환

                    for i in range(16):
                        self.data[i].append(data[i])

                    # 데이터 표시 업데이트
                    self.data_text.insert("end", f"{current_time.strftime('%Y-%m-%d %H:%M:%S')}: {data_str}\n")
                    self.data_text.see("end")

                    # 그래프 업데이트
                    update_graph()  # 수정된 부분

                    # CSV 파일 자동 저장
                    if save_interval and datetime.datetime.now() - last_save_time >= datetime.timedelta(minutes=save_interval):
                        save_csv(auto=True)
                        last_auto_save_filename = f"data_{datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')}.csv"  # 마지막으로 자동 저장된 파일명 업데이트
                        save_filename_label.config(text=f"Last auto saved as: {last_auto_save_filename}")

                except Exception as e:
                    messagebox.showerror("Error", str(e))
                    break

    def stop(self):
        self.running = False
        if self.ser.is_open:
            self.ser.close()

# CSV 파일 저장 함수
def save_csv(auto=False):
    global last_save_time, save_filename_label, last_auto_save_filename
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    if auto:
        filename = f"data_{current_time}.csv"
        if last_auto_save_filename:
            save_filename_label.config(text=f"Last saved as: {os.path.basename(last_auto_save_filename)}")
        else:
            save_filename_label.config(text="Last saved as: N/A")
    else:
        filename = filedialog.asksaveasfilename(initialfile=f"data_{current_time}.csv", defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        last_auto_save_filename = filename  # 마지막으로 자동 저장된 파일명 업데이트
    
    if filename:
        if receive_thread:  # receive_thread 객체가 존재하는지 확인
            with open(filename, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['Time', 'CH1', 'CH2', 'CH3', 'CH4', 'CH5', 'CH6', 'CH7', 'CH8', 'CH9', 'CH10', 'CH11', 'CH12', 'CH13', 'CH14', 'CH15', 'CH16'])
                min_length = min(len(receive_thread.x_data), min(len(data) for data in receive_thread.data))
                for i in range(min_length):
                    writer.writerow([receive_thread.x_data[i].strftime('%Y-%m-%d %H:%M:%S')] + [receive_thread.data[j][i] for j in range(16)])
                last_save_time = datetime.datetime.now()
                if not auto and filename:
                    messagebox.showinfo("Success", f"CSV file saved successfully as {filename}")
        else:
            messagebox.showerror("Error", "No data received yet. Please establish serial connection and start receiving data before saving.")

# Clear Monitor 버튼 클릭 시 데이터 수신 창 지우기
def clear_data():
    data_text.delete("1.0", "end")

# 자동 저장 간격 설정 함수
def set_save_interval():
    global save_interval, auto_save_label
    interval = entry_auto_save.get()
    try:
        save_interval = int(interval)
        auto_save_label.config(text=f"Auto Save Interval: {save_interval} minutes")
    except ValueError:
        messagebox.showerror("Error", "Invalid input. Please enter a valid integer for the save interval.")

# 그래프 초기화 함수
def clear_graph():
    global receive_thread
    if receive_thread:
        # 데이터를 비웁니다.
        for i in range(16):
            receive_thread.data[i] = []
        
        # 데이터를 비운 후에 그래프를 다시 그립니다.
        update_graph()

    else:
        messagebox.showerror("Error", "No data received yet.")

# 그래프 업데이트 함수
def update_graph():
    global receive_thread
    if receive_thread:
        if len(receive_thread.x_data) > 0 and len(receive_thread.x_data) == len(receive_thread.data[0]):
            for i in range(16):
                if len(receive_thread.data[i]) > 0 and len(receive_thread.x_data) == len(receive_thread.data[i]):  # 데이터 길이가 충분한 경우에만 업데이트
                    lines[i].set_xdata(receive_thread.x_data)
                    lines[i].set_ydata(receive_thread.data[i])
            ax.relim()
            ax.autoscale_view(True, True, True)
            canvas.draw()
    else:
        messagebox.showerror("Error", "No data received yet.")

# GUI 생성
root = tk.Tk()
root.title("JHJ Datalogger")
root.geometry("1200x1000")

def on_closing():
    close_port()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# Configure row and column size
root.rowconfigure(0, weight=1)
root.rowconfigure(1, weight=1)
root.columnconfigure(0, weight=1)
root.columnconfigure(1, weight=1)

# 시리얼 포트 설정 프레임
serial_frame = ttk.LabelFrame(root, text="Serial Port Config")
serial_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

# 포트 번호 라벨과 콤보박스
port_label = ttk.Label(serial_frame, text="Port:")
port_label.grid(row=0, column=0, padx=5, pady=5)
port_combo = ttk.Combobox(serial_frame, values=[])  
port_combo.grid(row=0, column=1, padx=5, pady=5)

# 통신 속도 라벨과 콤보박스
baud_label = ttk.Label(serial_frame, text="Baud Rate:")
baud_label.grid(row=1, column=0, padx=5, pady=5)
baud_combo = ttk.Combobox(serial_frame, values=["9600", "115200"])  
baud_combo.grid(row=1, column=1, padx=5, pady=5)
baud_combo.current(1)

# 연결 버튼
def open_port():
    global ser, receive_thread
    try:
        ser = serial.Serial(port=port_combo.get(), baudrate=int(baud_combo.get()))
        messagebox.showinfo("Success", f"Serial port opened successfully on port {ser.portstr}")
        receive_thread = SerialThread(ser, data_text, lines, ax)  # 스레드 생성 및 실행
        receive_thread.start()
        connect_btn.config(state="disabled")  # 연결 버튼 비활성화
        disconnect_btn.config(state="normal")  # 연결 해제 버튼 활성화
    except Exception as e:
        messagebox.showerror("Error", str(e))

connect_btn = ttk.Button(serial_frame, text="Connect", command=open_port)
connect_btn.grid(row=0, column=2, rowspan=2, padx=5, pady=5, sticky="nsew")

# 연결 해제 버튼
def close_port():
    global ser, receive_thread
    if ser and ser.is_open:
        ser.close()
        messagebox.showinfo("Success", "Serial port closed successfully!")
    if receive_thread:
        receive_thread.stop()  # 스레드 종료
    connect_btn.config(state="normal")  # 연결 버튼 활성화
    disconnect_btn.config(state="disabled")  # 연결 해제 버튼 비활성화

disconnect_btn = ttk.Button(serial_frame, text="Disconnect", command=close_port, state="disabled")
disconnect_btn.grid(row=0, column=3, rowspan=2, padx=5, pady=5, sticky="nsew")

# 포트 목록 업데이트
def update_port_list():
    ports = [port.device for port in list_ports.comports()]
    port_combo["values"] = ports
    if ports:
        port_combo.current(0)

update_port_list()

# Save CSV 버튼 프레임
save_frame = ttk.LabelFrame(root, text="Save CSV")
save_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

# Auto Save 프레임
auto_save_frame = ttk.LabelFrame(save_frame, text="Auto Save Config")
auto_save_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

# Manual Save 프레임
manual_save_frame = ttk.LabelFrame(save_frame, text="Manual Save Config")
manual_save_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

# 자동 저장 간격 입력 라벨
entry_auto_save = ttk.Entry(auto_save_frame, width=10)
entry_auto_save.grid(row=0, column=1, padx=5, pady=5)
entry_auto_save.insert(0, "10")  # 기본값: 10분

# 자동 저장 간격 설정 버튼
set_interval_button = ttk.Button(auto_save_frame, text="Set Interval", command=set_save_interval)
set_interval_button.grid(row=1, column=1, padx=5, pady=5)

# 자동 저장 라벨
auto_save_label = ttk.Label(auto_save_frame, text="Auto Save Interval: N/A minutes")
auto_save_label.grid(row=0, column=0, padx=10, pady=10)

# Manual Save 버튼
save_button = ttk.Button(manual_save_frame, text="Manual Save CSV", width=10, command=lambda: save_csv(auto=False))
save_button.grid(row=0, column=1, rowspan=2, padx=5, pady=5, sticky="nsew")

save_filename_label = ttk.Label(auto_save_frame, text="Last auto saved as: N/A")
save_filename_label.grid(row=1, column=0, padx=10, pady=10)

# 데이터 수신 프레임
data_frame = ttk.LabelFrame(root, text="Received Data")
data_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

# 데이터 수신 창
data_text = tk.Text(data_frame, wrap="word", height=10)
data_text.pack(fill=tk.BOTH, expand=True)

# Clear Monitor 버튼
clear_btn = ttk.Button(data_frame, text="Clear Monitor", command=clear_data)
clear_btn.pack(side="right", padx=5, pady=5)

# 그래프 프레임
graph_frame = ttk.LabelFrame(root, text="Graph")
graph_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

# Matplotlib figure 및 canvas 생성 및 설정
fig, ax = plt.subplots(figsize=(10, 5))  # 그래프 크기 조정
canvas = FigureCanvasTkAgg(fig, master=graph_frame)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# 그래프 설정
ax.set_title('Real-time Voltage Data', fontsize=10)
#ax.set_xlabel('Date', fontsize=8)
ax.set_ylabel('Voltage(mV)', fontsize=8, labelpad=10)
ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d %H:%M:%S'))  # X축 레이블을 날짜 형식으로 설정
ax.tick_params(axis='x', labelsize=8)  # X축 레이블 크기 설정
ax.tick_params(axis='y', labelsize=8)  # Y축 레이블 크기 설정
colors = plt.cm.viridis(np.linspace(0, 1, 16))
lines = [ax.plot([], [], 'o-', lw=2)[0] for _ in range(16)]  # 16개의 데이터 채널에 대한 그래프 선 생성
ax.legend([f"CH_{i+1}" for i in range(16)], loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0)  # legend 위치를 그래프 우측 상단으로 조정
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")  # X축 레이블 회전 및 정렬 설정
plt.subplots_adjust(left=0.1, right=0.85, bottom=0.25, top=0.95)  # 여백 조절
plt.xticks(rotation=45)  # x축 눈금 텍스트 각도조절
#plt.subplots_adjust(right=0.85, bottom=0.2)  # 좌측 여백 조절


# 그래프 초기화 버튼
clear_graph_button = ttk.Button(graph_frame, text="Clear Graph", command=clear_graph)
clear_graph_button.pack(side="right", padx=5, pady=5)
clear_btn.pack(side="right", padx=5, pady=5)

root.mainloop()
