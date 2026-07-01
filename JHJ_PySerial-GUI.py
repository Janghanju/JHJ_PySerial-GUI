import serial
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.cm as cm
from matplotlib.ticker import FormatStrFormatter
import csv
from serial.tools import list_ports
import threading
import shutil
import datetime
import os
from matplotlib.dates import DateFormatter
import numpy as np
import sys
from collections import deque
import logging

# 로깅 설정
logging.basicConfig(filename='datalogger.log', level=logging.INFO)

# 프로그램이 있는 폴더 경로
current_folder = os.path.dirname(sys.argv[0])

# 자동 저장 폴더 경로
auto_save_folder = os.path.join(current_folder, "Auto_Save")

# 데이터 폴더 경로
data_folder = os.path.join(current_folder, "Data")

# 자동 저장 폴더 생성
if not os.path.exists(auto_save_folder):
    os.makedirs(auto_save_folder)

# 데이터 폴더 생성
if not os.path.exists(data_folder):
    os.makedirs(data_folder)

# 전역 변수
ser = None
receive_thread = None
last_save_time = datetime.datetime.now()  # 프로그램 시작 시간으로 초기화
last_save_index = 0
save_interval = None
save_filename_label = None
auto_save_label = None
last_auto_save_filename = None
port_checker = None

class SerialThread(threading.Thread):
    def __init__(self, ser, data_text, lines, ax, max_length=None):  # max_length를 None으로 설정
        threading.Thread.__init__(self)
        self.ser = ser
        self.data_text = data_text
        self.lines = lines
        self.ax = ax
        self.running = True
        self.x_data = deque(maxlen=max_length) if max_length is not None else deque()  # max_length에 따라 deque 초기화
        self.data = [deque(maxlen=max_length) if max_length is not None else deque() for _ in range(16)]  # deque 사용하여 메모리 관리 개선
        self.max_length = max_length

    # def run(self):
    #     while self.running:
    #         if self.ser.is_open:
    #             try:
    #                 data_bytes = self.ser.readline().strip()  # 이진 데이터로 읽기

    #                 # 현재 시간 및 날짜 가져오기
    #                 current_time = datetime.datetime.now()
    #                 self.x_data.append(current_time)

    #                 # 시리얼 통신 값을 각 데이터 채널에 추가
    #                 data_str = data_bytes.decode('utf-8')  # 바이너리 데이터를 문자열로 디코딩
    #                 if data_str:  # 빈 문자열이 아닌 경우에만 처리
    #                     data_list = data_str.split(',')  # 쉼표로 분리된 데이터 리스트로 변환
    #                     data = [float(value) for value in data_list]  # 부동소수점 형태로 변환

    #                     for i in range(16):
    #                         self.data[i].append(data[i])

    #                     # 데이터 표시 업데이트
    #                     self.data_text.insert("end", f"{current_time.strftime('%Y-%m-%d %H:%M:%S')}: {data_str}\n")
    #                     self.data_text.see("end")

    #                     # 텍스트 창에 표시되는 행 수 제한
    #                     line_count = data_text.index('end').split('.')[0]  # 현재 행 수 확인
    #                     if int(line_count) > 1000:  # 행 수가 1000개를 초과하면
    #                         data_text.delete('1.0', '2.0')  # 첫 번째 행 삭제하여 제한

    #                     # 그래프 업데이트
    #                     self.update_graph()

    #                     # CSV 파일 자동 저장
    #                     if save_interval and datetime.datetime.now() - last_save_time >= datetime.timedelta(minutes=save_interval):
    #                         save_csv(auto=True)
    #                         last_auto_save_filename = f"data_{datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')}.csv"  # 마지막으로 자동 저장된 파일명 업데이트
    #                         save_filename_label.config(text=f"Last auto saved as: {last_auto_save_filename}")

    #             except ValueError as ve:
    #                 logging.error("ValueError in SerialThread: %s", str(ve))
    #                 continue  # 값을 변환할 수 없는 경우 스킵하고 다음 루프로 이동
    #             except Exception as e:
    #                 logging.error("Error in SerialThread: %s", str(e))
    #                 self.stop()  # 에러 발생 시 스레드 종료
    #                 break
    #         else:
    #             time.sleep(1)  # 포트가 열리지 않았으면 잠시 대기합니다.

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
                    if data_str:  # 빈 문자열이 아닌 경우에만 처리
                        data_list = data_str.split(',')  # 쉼표로 분리된 데이터 리스트로 변환
                        if len(data_list) == 16:  # 데이터 리스트의 길이 확인
                            try:
                                data = [float(value) for value in data_list]  # 부동소수점 형태로 변환
                                for i in range(16):
                                    self.data[i].append(data[i])
                            except ValueError as ve:
                                logging.error("Could not convert string to float: %s", ve)
                                continue  # 값을 변환할 수 없는 경우 스킵하고 다음 루프로 이동

                        # 데이터 표시 업데이트
                        self.data_text.insert("end", f"{current_time.strftime('%Y-%m-%d %H:%M:%S')}: {data_str}\n")
                        self.data_text.see("end")

                        # 텍스트 창에 표시되는 행 수 제한
                        line_count = self.data_text.index('end').split('.')[0]  # 현재 행 수 확인
                        if int(line_count) > 1000:  # 행 수가 1000개를 초과하면
                            self.data_text.delete('1.0', '2.0')  # 첫 번째 행 삭제하여 제한

                        # 그래프 업데이트
                        self.update_graph()

                        # CSV 파일 자동 저장
                        if save_interval and datetime.datetime.now() - last_save_time >= datetime.timedelta(minutes=save_interval):
                            save_csv(auto=True)
                            last_auto_save_filename = f"data_{datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')}.csv"  # 마지막으로 자동 저장된 파일명 업데이트
                            save_filename_label.config(text=f"Last auto saved as: {last_auto_save_filename}")

                except Exception as e:
                    logging.error("Error in SerialThread: %s", str(e))
                    self.stop()  # 에러 발생 시 스레드 종료
                    break
            else:
                time.sleep(1)  # 포트가 열리지 않았으면 잠시 대기합니다.

    # update_graph 함수
    # def update_graph(self):
    #     # 이 함수 내부에서 전역 변수 lines를 사용하여 그래프를 업데이트합니다.
    #     for i in range(16):
    #         if len(self.data[i]) > 0:
    #             x_data = list(self.x_data)[-1000:]
    #             y_data = list(self.data[i])[-1000:]
    #             lines[i].set_xdata(x_data)
    #             lines[i].set_ydata(y_data)
    #     self.ax.relim()
    #     self.ax.autoscale_view(True, True, True)
    #     self.ax.figure.canvas.draw_idle()

    def update_graph(self):
        # 그래프 업데이트 로직에서 길이 불일치 해결
        min_length = min(len(self.x_data), *[len(data) for data in self.data])
        x_data = list(self.x_data)[:min_length]  # x_data 길이 조정
        for i, line in enumerate(self.lines):
            y_data = list(self.data[i])[:min_length]  # y_data 길이 조정
            line.set_data(x_data, y_data)
        self.ax.relim()
        self.ax.autoscale_view(True, True, True)
        self.ax.figure.canvas.draw_idle()

    def stop(self):
        self.running = False
        if self.ser.is_open:
            self.ser.close()
        clear_graph()  # 그래프 초기화
        
# 보장된 코드
def save_csv(auto=False):
    global last_save_time, last_save_index, save_filename_label, last_auto_save_filename
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    if auto:
        auto_save_filename = os.path.join(auto_save_folder, f"data_{current_time}.csv")
        data_save_filename = os.path.join(data_folder, "data.csv")
        if last_auto_save_filename:
            save_filename_label.config(text=f"Last saved as: {os.path.basename(last_auto_save_filename)}")
        else:
            save_filename_label.config(text="Last saved as: N/A")
    else:
        auto_save_filename = filedialog.asksaveasfilename(initialfile=f"data_{current_time}.csv", defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        data_save_filename = auto_save_filename

    try:
        if auto_save_filename:
            if receive_thread:  # receive_thread 객체가 존재하는지 확인
                file_exists = os.path.exists(auto_save_filename)  # 파일이 이미 존재하는지 확인
                data_file_exists = os.path.exists(data_save_filename)  # 파일이 이미 존재하는지 확인
                with open(auto_save_filename, 'a', newline='') as auto_file:  # 'w' 대신 'a' 모드로 열어 추가 모드로 변경
                    writer = csv.writer(auto_file)
                    # 파일이 존재하지 않을 때만 헤더를 씁니다.
                    if not file_exists:
                        writer.writerow(['Time', 'CH1', 'CH2', 'CH3', 'CH4', 'CH5', 'CH6', 'CH7', 'CH8', 'CH9', 'CH10', 'CH11', 'CH12', 'CH13', 'CH14', 'CH15', 'CH16'])
                    min_length = min(len(receive_thread.x_data), min(len(data) for data in receive_thread.data))
                    for i in range(min_length):
                        writer.writerow([receive_thread.x_data[i].strftime('%Y-%m-%d %H:%M:%S')] + [receive_thread.data[j][i] for j in range(16)])
                    last_save_time = datetime.datetime.now()
                if auto and datetime.datetime.now() - last_save_time >= datetime.timedelta(minutes=save_interval):
                    last_auto_save_filename = auto_save_filename
                    last_save_time = datetime.datetime.now()
            if data_save_filename and receive_thread:
                with open(data_save_filename, 'a', newline='') as data_file:
                    writer = csv.writer(data_file)
                    if not data_file_exists:
                        writer.writerow(['Time', 'CH1', 'CH2', 'CH3', 'CH4', 'CH5', 'CH6', 'CH7', 'CH8', 'CH9', 'CH10', 'CH11', 'CH12', 'CH13', 'CH14', 'CH15', 'CH16'])
                    # last_save_index부터 데이터 저장
                    for i in range(last_save_index, min_length):
                        writer.writerow([receive_thread.x_data[i].strftime('%Y-%m-%d %H:%M:%S')] + [receive_thread.data[j][i] for j in range(16)])
                    if not auto and data_save_filename:
                        messagebox.showinfo("Success", f"CSV file saved successfully as {data_save_filename}")
                    # 마지막 저장 인덱스 업데이트
                    last_save_index = min_length

    except PermissionError as e:
        logging.error("PermissionError: %s", str(e))
        messagebox.showerror("Error", f"Failed to save CSV file: {e}. Please close the file if it is already open.")

# Manual Save 함수
def save_manual():
    save_csv(auto=False)

# Clear Monitor 버튼 클릭 시 데이터 수신 창 지우기
def clear_data():
    data_text.delete("1.0", "end")

# 자동 저장 간격 설정 함수
def set_save_interval():
    global save_interval, auto_save_label
    interval = entry_auto_save.get()
    try:
        save_interval = int(interval)
        auto_save_label.config(text=f"Auto Save Interval: {save_interval} min")
    except ValueError as e:
        logging.error("Invalid input for save interval: %s", str(e))
        messagebox.showerror("Error", "Invalid input. Please enter a valid integer for the save interval.")

# 그래프 초기화 함수
def clear_graph():
    global lines  # 'lines'는 전역 변수로 사용되어야 합니다.
    if receive_thread and receive_thread.is_alive():
        # 데이터 저장용 변수를 초기화합니다.
        receive_thread.x_data.clear()
        for channel_data in receive_thread.data:
            channel_data.clear()

        # 그래프의 축과 데이터 라인을 초기화합니다.
        ax.cla()  # 축을 지웁니다.

        # 그래프 설정
        ax.set_title('Real-time Voltage Data', fontsize=10)
        ax.set_ylabel('Voltage(V)', fontsize=10, labelpad=10)
        ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d %H:%M:%S'))  # X축 레이블을 날짜 형식으로 설정
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.4f'))
        ax.tick_params(axis='x', labelsize=8)  # X축 레이블 크기 설정
        ax.tick_params(axis='y', labelsize=8)  # Y축 레이블 크기 설정
        ax.grid(True)
        
        # 새로운 데이터 라인을 생성합니다.
        colors = cm.tab20(np.linspace(0, 1, 20))  # 색상 맵 설정
        lines = [ax.plot([], [], 'o-', lw=2, color=colors[i])[0] for i in range(16)]  # 데이터 라인 생성
        ax.legend([f"CH_{i+1}" for i in range(16)], loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0)  # 범례 설정

        # 그래프 레이아웃 조정
        plt.xticks(rotation=45)  # X축 눈금 텍스트 각도 조정
        plt.subplots_adjust(left=0.1, right=0.85, bottom=0.25, top=0.95)

        # 그래프를 다시 그립니다.
        canvas.draw()

    #else:
        #messagebox.showinfo("Information", "No data received yet or thread is not running.")

# GUI 생성
root = tk.Tk()
root.title("[HelixKorea JHJ] Serial Datalogger v1.0.0.5")
root.geometry("1100x900")
#icon_path = 'logo.ico'
#root.iconbitmap(default='D:\SynologyDrive\지원사업\김창만교수님\JHJ_PySerial-GUI\logo.ico')
#root.iconbitmap(default=icon_path)

# 프로그램 종료
def on_closing():
    global port_checker
    port_checker = 0  # 백그라운드 스레드 종료
    close_port()
    clear_data()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# 행 및 열 크기 구성
root.rowconfigure(0, weight=1)
root.rowconfigure(1, weight=1)
root.rowconfigure(2, weight=1)
root.columnconfigure(0, weight=3)
root.columnconfigure(1, weight=3)
root.columnconfigure(2, weight=1)

# 시리얼 포트 설정 프레임
serial_frame = ttk.LabelFrame(root, text="Serial Port Config")
serial_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
serial_frame.grid_propagate(False)
serial_frame.config(height=100)
root.grid_rowconfigure(0, weight=0, minsize=100)  # 첫 번째 행의 높이를 100으로 고정

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
    global port_checker
    port_checker = 1
    global ser, receive_thread
    selected_port = port_combo.get()
    if selected_port not in port_combo['values']:
        messagebox.showerror("Error", f"The selected port {selected_port} is not available.")
        return

    try:
        ser = serial.Serial(port=selected_port, baudrate=int(baud_combo.get()), timeout=1)
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
    global port_checker
    port_checker = 0
    global ser, receive_thread
    if ser and ser.is_open:
        ser.close()
        clear_data()
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
    else:
        messagebox.showerror("Error", "No ports found. Please connect a device and refresh the list.")

update_port_list()

# 포트 연결 확인 및 재연결을 담당하는 함수
def check_serial_connection():
    global ser, receive_thread, port_checker
    while port_checker:  # port_checker 값이 0이 되면 종료됩니다.
        if ser and not ser.is_open:
            try:
                ser.open()
                receive_thread = SerialThread(ser, data_text, lines, ax)  # 스레드 생성 및 실행
                receive_thread.start()
                connect_btn.config(state="disabled")  # 연결 버튼 비활성화
                disconnect_btn.config(state="normal")  # 연결 해제 버튼 활성화
                messagebox.showinfo("Success", f"Serial port reopened successfully on port {ser.portstr}")
            except Exception as e:
                logging.error("Error in check_serial_connection: %s", str(e))
                messagebox.showerror("Error", "Failed to reopen serial port. Please check the connection.")
        time.sleep(1)  # 1초마다 포트 상태 확인

# 프로그램 시작 시 포트 연결 확인 및 재연결 스레드 시작
connection_thread = threading.Thread(target=check_serial_connection)
connection_thread.daemon = True
connection_thread.start()

# Auto Save 프레임
auto_save_frame = ttk.LabelFrame(root, text="Auto Save Config")
auto_save_frame.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
auto_save_frame.grid_propagate(False)
auto_save_frame.config(height=100)
root.grid_rowconfigure(0, weight=0, minsize=100)

# Manual Save 프레임
manual_save_frame = ttk.LabelFrame(root, text="Manual Save Config")
manual_save_frame.grid(row=0, column=2, padx=10, pady=10, sticky="ew")
manual_save_frame.grid_propagate(False)
manual_save_frame.config(height=100)
root.grid_rowconfigure(0, weight=0, minsize=100)

# 자동 저장 간격 입력 라벨
entry_auto_save = ttk.Entry(auto_save_frame, width=10)
entry_auto_save.grid(row=0, column=1, padx=5, pady=5)
entry_auto_save.insert(0, "10")  # 기본값: 10분

# 자동 저장 간격 설정 버튼
set_interval_button = ttk.Button(auto_save_frame, text="Set Interval", command=set_save_interval)
set_interval_button.grid(row=1, column=1, padx=5, pady=5)

# 자동 저장 라벨
auto_save_label = ttk.Label(auto_save_frame, text="Auto Save Interval: N/A min")
auto_save_label.grid(row=0, column=0, padx=10, pady=10)

# Manual Save 버튼
save_button = ttk.Button(manual_save_frame, text="Manual Save", width=15, command=save_manual)
save_button.grid(row=0, column=0, rowspan=2, padx=10, pady=10, sticky="nsew")

save_filename_label = ttk.Label(auto_save_frame, text="Last auto saved as: N/A")
save_filename_label.grid(row=1, column=0, padx=10, pady=10)

# 데이터 수신 프레임
data_frame = ttk.LabelFrame(root, text="Received Data Monitor")
data_frame.grid(row=1, column=0, rowspan=2, columnspan=3, padx=10, pady=10, sticky="nsew")

# 데이터 수신 창
data_text = tk.Text(data_frame, wrap="word", height=10)
data_text.pack(fill=tk.BOTH, expand=True)

# 채널 라벨
ch_list = ttk.Label(data_frame, text="               Date                CH_01   CH_02   CH_03   CH_04    CH_05   CH_06   CH_07   CH_08    CH_09   CH_10   CH_11   CH_12    CH_13   CH_14   CH_15   CH_16")
ch_list.pack(side="left", padx=5, pady=5)

# Clear Monitor 버튼
clear_btn = ttk.Button(data_frame, text="Clear Monitor", command=clear_data)
clear_btn.pack(side="right", padx=5, pady=5)

# 그래프 프레임
graph_frame = ttk.LabelFrame(root, text="Graph")
graph_frame.grid(row=3, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")

# Matplotlib figure 및 canvas 생성 및 설정
fig, ax = plt.subplots(figsize=(10, 5))  # 그래프 크기 조정
canvas = FigureCanvasTkAgg(fig, master=graph_frame)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# 그래프 설정
ax.set_title('Real-time Voltage Data', fontsize=10)
ax.set_ylabel('Voltage(V)', fontsize=10, labelpad=10)
ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d %H:%M:%S'))  # X축 레이블을 날짜 형식으로 설정
ax.yaxis.set_major_formatter(FormatStrFormatter('%.4f'))
ax.tick_params(axis='x', labelsize=8)  # X축 레이블 크기 설정
ax.tick_params(axis='y', labelsize=8)  # Y축 레이블 크기 설정
ax.grid(True)

# 새로운 데이터 라인을 생성합니다.
colors = cm.tab20(np.linspace(0, 1, 20))  # 색상 맵 설정
lines = [ax.plot([], [], 'o-', lw=2, color=colors[i])[0] for i in range(16)]  # 데이터 라인 생성
ax.legend([f"CH_{i+1}" for i in range(16)], loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0)  # 범례 설정

# 그래프 레이아웃 조정
plt.xticks(rotation=45)  # X축 눈금 텍스트 각도 조정
plt.subplots_adjust(left=0.1, right=0.85, bottom=0.25, top=0.95)

# 그래프 초기화 버튼
clear_graph_button = ttk.Button(graph_frame, text="Clear Graph", command=clear_graph)
clear_graph_button.pack(side="right", padx=5, pady=5)

if __name__ == "__main__":
    try:
        # GUI 실행
        root.mainloop()
    except Exception as e:
        logging.critical("Unhandled exception: %s", str(e))
        messagebox.showerror("Critical Error", "An unhandled exception occurred. Please see the log file for details.")