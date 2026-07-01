import sys
import os
import csv
import datetime
import logging
import shutil
from collections import deque
import serial
from serial.tools import list_ports

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QIcon, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QComboBox, QLineEdit, QPushButton,
    QTextEdit, QFileDialog, QMessageBox, QStatusBar, QSizePolicy,
    QSystemTrayIcon, QMenu, QCheckBox
)
import pyqtgraph as pg
import numpy as np

# 로깅 설정
logging.basicConfig(filename='datalogger.log', level=logging.INFO)

# 프로그램이 있는 폴더 경로
current_folder = os.path.dirname(os.path.abspath(sys.argv[0]))

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

# 16개 채널의 구분을 극대화하기 위한 선명하고 세련된 네온 컬러 팔레트
CHANNEL_COLORS = [
    "#FF1744", "#D500F9", "#2979FF", "#00E5FF", 
    "#00E676", "#76FF03", "#FFEA00", "#FF9100",
    "#FF3D00", "#FF4081", "#3F51B5", "#009688",
    "#4CAF50", "#FFEB3B", "#9C27B0", "#E91E63"
]

class AutoResizingComboBox(QComboBox):
    """클릭하여 드롭다운이 활성화될 때 실시간으로 사용 가능한 포트 목록을 갱신하는 콤보박스"""
    def showPopup(self):
        current_text = self.currentText()
        self.clear()
        ports = [port.device for port in list_ports.comports()]
        self.addItems(ports)
        if current_text in ports:
            self.setCurrentText(current_text)
        elif ports:
            self.setCurrentIndex(0)
        super().showPopup()

class SerialReceiverThread(QThread):
    """백그라운드에서 시리얼 데이터를 수신하고 즉각적인 CSV 파일 기록을 수행하는 QThread"""
    data_received = Signal(float, list, str)
    connection_lost = Signal(str)

    def __init__(self, port, baudrate, auto_save_path, data_csv_path):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.auto_save_path = auto_save_path
        self.data_csv_path = data_csv_path
        self.running = True
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=1)
        except Exception as e:
            self.connection_lost.emit(str(e))
            return

        # 헤더 자동 작성
        for path in [self.auto_save_path, self.data_csv_path]:
            if path and not os.path.exists(path):
                try:
                    with open(path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            'Time', 'CH1', 'CH2', 'CH3', 'CH4', 'CH5', 'CH6', 'CH7', 
                            'CH8', 'CH9', 'CH10', 'CH11', 'CH12', 'CH13', 'CH14', 'CH15', 'CH16'
                        ])
                except Exception as ex:
                    logging.error(f"Failed to write header to {path}: {ex}")

        while self.running:
            if self.ser and self.ser.is_open:
                try:
                    data_bytes = self.ser.readline().strip()
                    if not data_bytes:
                        continue

                    raw_str = data_bytes.decode('utf-8', errors='ignore')
                    current_time = datetime.datetime.now()
                    timestamp = current_time.timestamp()

                    # 데이터 파싱 (16채널)
                    data_list = raw_str.split(',')
                    if len(data_list) == 16:
                        try:
                            values = [float(val) for val in data_list]

                            # 즉시 디바이스에 데이터 쓰기 (Append 모드)로 메모리 및 데이터 유실 최적화
                            time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
                            row = [time_str] + values

                            for path in [self.auto_save_path, self.data_csv_path]:
                                if path:
                                    try:
                                        with open(path, 'a', newline='', encoding='utf-8') as f:
                                            writer = csv.writer(f)
                                            writer.writerow(row)
                                    except Exception as write_err:
                                        logging.error(f"Error writing data to {path}: {write_err}")

                            # 메인 UI 스레드에 파싱 완료 데이터 전송
                            self.data_received.emit(timestamp, values, raw_str)

                        except ValueError as ve:
                            logging.error(f"Value conversion error for raw data: {raw_str} ({ve})")
                except Exception as e:
                    logging.error(f"Error in Serial read loop: {e}")
                    self.connection_lost.emit(str(e))
                    break
            else:
                self.msleep(100)

    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception as e:
                logging.error(f"Error closing serial port: {e}")

class SerialDataloggerApp(QMainWindow):
    """현대적인 다크 플랫 테마 스타일의 메인 윈도우 클래스"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("[HelixKorea JHJ] Serial Datalogger v1.0.0.8")
        self.resize(1100, 900)

        # 아이콘 설정
        self.icon_path = os.path.join(current_folder, 'logo.ico')
        if os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))

        # 전역 상태 변수
        self.receiver_thread = None
        self.port_checker = False  # 자동 재연결 활성화 상태 플래그
        self.save_interval = 10    # 기본값: 10분
        self.last_save_time = datetime.datetime.now()
        
        # 파일 경로 초기화
        session_time_str = self.last_save_time.strftime('%Y-%m-%d %H-%M-%S')
        self.auto_save_path = os.path.join(auto_save_folder, f"data_{session_time_str}.csv")
        self.data_csv_path = os.path.join(data_folder, "data.csv")

        # 메모리 큐 최적화 (가비지 컬렉터 부하를 예방하기 위해 최대 1000개로 고정)
        self.x_data = deque(maxlen=1000)
        self.data_channels = [deque(maxlen=1000) for _ in range(16)]

        self.setup_ui()
        self.apply_styles()
        self.init_reconnect_timer()
        self.setup_tray_icon()

    def setup_ui(self):
        # 메인 위젯 및 메인 레이아웃
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ---------------------------------------------
        # 상단 설정 레이아웃 (세 가로 그룹 배치)
        # ---------------------------------------------
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        # 1. 시리얼 포트 설정 그룹
        serial_group = QGroupBox("Serial Port Config")
        serial_grid = QGridLayout(serial_group)
        serial_grid.setContentsMargins(10, 15, 10, 10)
        serial_grid.setSpacing(8)

        serial_grid.addWidget(QLabel("Port:"), 0, 0)
        self.port_combo = AutoResizingComboBox()
        serial_grid.addWidget(self.port_combo, 0, 1)

        serial_grid.addWidget(QLabel("Baud Rate:"), 1, 0)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "115200"])
        self.baud_combo.setCurrentText("115200")
        serial_grid.addWidget(self.baud_combo, 1, 1)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("connect_btn")
        self.connect_btn.clicked.connect(self.start_serial)
        serial_grid.addWidget(self.connect_btn, 0, 2, 2, 1)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setObjectName("disconnect_btn")
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.clicked.connect(self.stop_serial)
        serial_grid.addWidget(self.disconnect_btn, 0, 3, 2, 1)

        top_layout.addWidget(serial_group, 3)

        # 2. 자동 저장 설정 그룹
        autosave_group = QGroupBox("Auto Save Config")
        autosave_grid = QGridLayout(autosave_group)
        autosave_grid.setContentsMargins(10, 15, 10, 10)
        autosave_grid.setSpacing(8)

        self.auto_save_label = QLabel(f"Auto Save Interval: {self.save_interval} min")
        autosave_grid.addWidget(self.auto_save_label, 0, 0)

        self.entry_auto_save = QLineEdit("10")
        autosave_grid.addWidget(self.entry_auto_save, 0, 1)

        self.set_interval_btn = QPushButton("Set Interval")
        self.set_interval_btn.clicked.connect(self.set_save_interval)
        autosave_grid.addWidget(self.set_interval_btn, 1, 1)

        session_time_str = self.last_save_time.strftime('%Y-%m-%d %H-%M-%S')
        self.save_filename_label = QLabel(f"Last auto saved as: data_{session_time_str}.csv")
        self.save_filename_label.setStyleSheet("color: #888888;")
        autosave_grid.addWidget(self.save_filename_label, 1, 0)

        top_layout.addWidget(autosave_group, 3)

        # 3. 수동 저장 설정 그룹
        manual_group = QGroupBox("Manual Save Config")
        manual_layout = QVBoxLayout(manual_group)
        manual_layout.setContentsMargins(10, 15, 10, 10)
        manual_layout.setSpacing(6)

        self.manual_save_btn = QPushButton("Manual Save")
        self.manual_save_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.manual_save_btn.clicked.connect(self.save_manual)
        manual_layout.addWidget(self.manual_save_btn)

        self.chk_minimize_to_tray = QCheckBox("Minimize to Tray on Close")
        self.chk_minimize_to_tray.setChecked(True)
        self.chk_minimize_to_tray.setStyleSheet("color: #aaaaaa; font-size: 10px;")
        manual_layout.addWidget(self.chk_minimize_to_tray)

        top_layout.addWidget(manual_group, 2)

        main_layout.addLayout(top_layout, 0)

        # ---------------------------------------------
        # 중간 데이터 모니터 레이아웃
        # ---------------------------------------------
        monitor_group = QGroupBox("Received Data Monitor")
        monitor_layout = QVBoxLayout(monitor_group)
        monitor_layout.setContentsMargins(10, 15, 10, 10)
        monitor_layout.setSpacing(5)

        # 고정폭 폰트의 채널 헤더 라벨
        self.ch_list_label = QLabel(
            "               Date                CH_01   CH_02   CH_03   CH_04    CH_05   CH_06   CH_07   CH_08    CH_09   CH_10   CH_11   CH_12    CH_13   CH_14   CH_15   CH_16"
        )
        self.ch_list_label.setFont(QFont("Consolas", 9))
        self.ch_list_label.setStyleSheet("color: #00ffcc; font-weight: normal;")
        monitor_layout.addWidget(self.ch_list_label)

        # 터미널 스타일의 데이터 텍스트 창 (성능 병목을 방지하기 위해 사용)
        self.data_text = QTextEdit()
        self.data_text.setReadOnly(True)
        self.data_text.setFont(QFont("Consolas", 9))
        monitor_layout.addWidget(self.data_text)

        monitor_btn_layout = QHBoxLayout()
        monitor_btn_layout.addStretch()
        self.clear_monitor_btn = QPushButton("Clear Monitor")
        self.clear_monitor_btn.clicked.connect(self.clear_data)
        monitor_btn_layout.addWidget(self.clear_monitor_btn)
        monitor_layout.addLayout(monitor_btn_layout)

        main_layout.addWidget(monitor_group, 3)

        # ---------------------------------------------
        # 하단 실시간 PyQtGraph 레이아웃
        # ---------------------------------------------
        graph_group = QGroupBox("Graph")
        graph_layout = QVBoxLayout(graph_group)
        graph_layout.setContentsMargins(10, 15, 10, 10)
        graph_layout.setSpacing(5)

        # PyQtGraph 가속 차트 위젯 설정
        # 날짜/시간을 X축에 렌더링하기 위해 DateAxisItem 적용
        self.date_axis = pg.DateAxisItem(orientation='bottom')
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': self.date_axis})
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Voltage', units='V')
        self.plot_widget.addLegend(offset=(10, 10))

        # 16개 라인 및 범례 초기화
        self.lines = []
        for i in range(16):
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            pen = pg.mkPen(color=color, width=2)
            line = self.plot_widget.plot(pen=pen, name=f"CH_{i+1}")
            self.lines.append(line)

        graph_layout.addWidget(self.plot_widget)

        graph_btn_layout = QHBoxLayout()
        graph_btn_layout.addStretch()
        self.clear_graph_btn = QPushButton("Clear Graph")
        self.clear_graph_btn.clicked.connect(self.clear_graph)
        graph_btn_layout.addWidget(self.clear_graph_btn)
        graph_layout.addLayout(graph_btn_layout)

        main_layout.addWidget(graph_group, 5)

        # ---------------------------------------------
        # 상태 표시줄 구성
        # ---------------------------------------------
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # 포트 목록 초기 갱신
        self.update_port_list()

    def apply_styles(self):
        """현대적이고 수려한 플랫 다크 테마 QSS 적용"""
        qss = """
        QMainWindow {
            background-color: #121212;
        }
        QLabel {
            color: #e0e0e0;
            font-family: "Segoe UI", "맑은 고딕", sans-serif;
            font-size: 11px;
        }
        QGroupBox {
            background-color: #1e1e1e;
            border: 1px solid #333333;
            border-radius: 8px;
            margin-top: 12px;
            font-family: "Segoe UI", "맑은 고딕", sans-serif;
            font-size: 11px;
            font-weight: bold;
            color: #00bcd4;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 5px;
        }
        QComboBox, QLineEdit {
            background-color: #2a2a2a;
            border: 1px solid #444444;
            border-radius: 4px;
            color: #ffffff;
            padding: 4px 8px;
            min-height: 20px;
            font-family: "Segoe UI", "맑은 고딕", sans-serif;
        }
        QComboBox:hover, QLineEdit:hover {
            border: 1px solid #00bcd4;
        }
        QComboBox::drop-down {
            border: none;
        }
        QPushButton {
            background-color: #2a2a2a;
            border: 1px solid #444444;
            border-radius: 4px;
            color: #ffffff;
            padding: 6px 12px;
            font-family: "Segoe UI", "맑은 고딕", sans-serif;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #333333;
            border: 1px solid #00bcd4;
        }
        QPushButton:pressed {
            background-color: #1a1a1a;
        }
        QPushButton:disabled {
            background-color: #1a1a1a;
            border: 1px solid #2d2d2d;
            color: #555555;
        }
        QPushButton#connect_btn {
            background-color: #004d40;
            border: 1px solid #00796b;
        }
        QPushButton#connect_btn:hover {
            background-color: #00796b;
        }
        QPushButton#connect_btn:disabled {
            background-color: #142522;
            border: 1px solid #1a302c;
            color: #444444;
        }
        QPushButton#disconnect_btn {
            background-color: #880e4f;
            border: 1px solid #ad1457;
        }
        QPushButton#disconnect_btn:hover {
            background-color: #ad1457;
        }
        QPushButton#disconnect_btn:disabled {
            background-color: #2b1721;
            border: 1px solid #371d2b;
            color: #444444;
        }
        QTextEdit {
            background-color: #141414;
            border: 1px solid #2d2d2d;
            border-radius: 6px;
            color: #33ff33;
            font-family: "Consolas", monospace;
            font-size: 11px;
        }
        QStatusBar {
            background-color: #1a1a1a;
            color: #888888;
        }
        """
        self.setStyleSheet(qss)

    def update_port_list(self):
        ports = [port.device for port in list_ports.comports()]
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if ports:
            self.port_combo.setCurrentIndex(0)
        else:
            self.status_bar.showMessage("No serial ports found.")

    def init_reconnect_timer(self):
        """1초 단위로 감시하며 연결 해제 시 안전하게 재연결을 진행하는 QTimer"""
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.check_reconnection)
        self.reconnect_timer.start(1000)

    @Slot()
    def start_serial(self):
        selected_port = self.port_combo.currentText()
        if not selected_port:
            QMessageBox.critical(self, "Error", "No port selected. Please refresh or connect a device.")
            return

        self.port_checker = True  # 재연결 루프 활성화
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.status_bar.showMessage(f"Connecting to {selected_port}...")

        # 새로운 파일 세션 생성
        self.last_save_time = datetime.datetime.now()
        session_time_str = self.last_save_time.strftime('%Y-%m-%d %H-%M-%S')
        self.auto_save_path = os.path.join(auto_save_folder, f"data_{session_time_str}.csv")

        self.receiver_thread = SerialReceiverThread(
            port=selected_port, 
            baudrate=int(self.baud_combo.currentText()),
            auto_save_path=self.auto_save_path,
            data_csv_path=self.data_csv_path
        )
        self.receiver_thread.data_received.connect(self.on_data_received)
        self.receiver_thread.connection_lost.connect(self.on_connection_lost)
        self.receiver_thread.start()

    @Slot()
    def stop_serial(self):
        self.port_checker = False  # 재연결 비활성화
        if self.receiver_thread:
            self.receiver_thread.stop()
            self.receiver_thread.wait()
            self.receiver_thread = None

        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.status_bar.showMessage("Disconnected successfully.")

    @Slot(float, list, str)
    def on_data_received(self, timestamp, values, raw_str):
        current_time = datetime.datetime.now()
        time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')

        # 1. 텍스트 로그 모니터 추가 및 1000행 제한 최적화 (메모리 누수 방지)
        self.data_text.append(f"{time_str}: {raw_str}")
        document = self.data_text.document()
        if document.blockCount() > 1000:
            cursor = self.data_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar() # 빈 줄 삭제

        # 2. 실시간 데이터 큐 적재 (최대 1000개 유지)
        self.x_data.append(timestamp)
        for i in range(16):
            self.data_channels[i].append(values[i])

        # 3. PyQtGraph 차트 실시간 렌더링 최적화
        x_list = list(self.x_data)
        for i in range(16):
            self.lines[i].setData(x_list, list(self.data_channels[i]))

        self.status_bar.showMessage(f"Connected - Receiving data: {raw_str}", 2000)

        # 4. 자동 저장 주기 체크 및 세션 파일 교체
        if self.save_interval and (current_time - self.last_save_time).total_seconds() >= self.save_interval * 60:
            self.last_save_time = current_time
            new_session_time = current_time.strftime('%Y-%m-%d %H-%M-%S')
            self.auto_save_path = os.path.join(auto_save_folder, f"data_{new_session_time}.csv")
            
            # 스레드 파일 쓰기 타겟 경로 실시간 교체
            if self.receiver_thread and self.receiver_thread.isRunning():
                self.receiver_thread.auto_save_path = self.auto_save_path

            self.save_filename_label.setText(f"Last auto saved as: data_{new_session_time}.csv")

    @Slot(str)
    def on_connection_lost(self, err_msg):
        logging.error(f"Serial connection lost: {err_msg}")
        self.status_bar.showMessage(f"Connection lost: {err_msg}. Waiting for reconnect...")
        if self.receiver_thread:
            self.receiver_thread.stop()
            self.receiver_thread.wait()
            self.receiver_thread = None

    def check_reconnection(self):
        """포트 자동 재연결 로직"""
        if self.port_checker and (self.receiver_thread is None or not self.receiver_thread.isRunning()):
            selected_port = self.port_combo.currentText()
            ports = [port.device for port in list_ports.comports()]
            
            if selected_port in ports:
                self.status_bar.showMessage(f"Attempting to reconnect on {selected_port}...")
                self.receiver_thread = SerialReceiverThread(
                    port=selected_port,
                    baudrate=int(self.baud_combo.currentText()),
                    auto_save_path=self.auto_save_path,
                    data_csv_path=self.data_csv_path
                )
                self.receiver_thread.data_received.connect(self.on_data_received)
                self.receiver_thread.connection_lost.connect(self.on_connection_lost)
                self.receiver_thread.start()
            else:
                self.status_bar.showMessage(f"Target port {selected_port} not available. Checking...")

    @Slot()
    def save_manual(self):
        """실시간 기록 중이던 자동 저장 파일(세션 데이터)을 지정된 경로에 빠른 복사 수행"""
        if not os.path.exists(self.auto_save_path):
            QMessageBox.warning(self, "Warning", "No active session data to save yet. Start port connection first.")
            return

        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        target_filename, _ = QFileDialog.getSaveFileName(
            self, "Save CSV As", f"data_{current_time_str}.csv", "CSV files (*.csv)"
        )

        if target_filename:
            try:
                # 빠른 대용량 파일 복사로 I/O 점유 방지
                shutil.copy(self.auto_save_path, target_filename)
                QMessageBox.information(self, "Success", f"CSV file saved successfully to:\n{target_filename}")
            except Exception as e:
                logging.error(f"Manual save failed: {e}")
                QMessageBox.critical(self, "Error", f"Failed to save CSV file: {e}")

    @Slot()
    def set_save_interval(self):
        interval_str = self.entry_auto_save.text()
        try:
            val = int(interval_str)
            if val <= 0:
                raise ValueError
            self.save_interval = val
            self.auto_save_label.setText(f"Auto Save Interval: {self.save_interval} min")
            self.status_bar.showMessage(f"Auto save interval updated to {self.save_interval} minutes.", 3000)
        except ValueError:
            logging.error(f"Invalid input for save interval: {interval_str}")
            QMessageBox.critical(self, "Error", "Please enter a positive integer for the save interval.")

    @Slot()
    def clear_data(self):
        self.data_text.clear()
        self.status_bar.showMessage("Monitor cleared.", 2000)

    @Slot()
    def clear_graph(self):
        self.x_data.clear()
        for channel in self.data_channels:
            channel.clear()
        for line in self.lines:
            line.setData([], [])
        self.status_bar.showMessage("Graph cleared.", 2000)

    def setup_tray_icon(self):
        """시스템 트레이 아이콘 설정 및 우클릭 메뉴 정의"""
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(self.icon_path):
            self.tray_icon.setIcon(QIcon(self.icon_path))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
            
        self.tray_icon.setToolTip("HelixKorea Serial Datalogger")

        # 트레이 메뉴 생성
        self.tray_menu = QMenu()
        show_action = QAction("Show Application", self)
        show_action.triggered.connect(self.showNormal)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_application)

        self.tray_menu.addAction(show_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """트레이 아이콘 클릭/더블클릭 시 창 복원"""
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.showNormal()
            self.activateWindow()

    def exit_application(self):
        """트레이 메뉴 종료 클릭 시 강제 종료 진행"""
        self.chk_minimize_to_tray.setChecked(False)
        self.close()

    def closeEvent(self, event):
        """창 닫기 시 트레이 최소화 처리 혹은 자원 안전하게 회수"""
        if self.chk_minimize_to_tray.isChecked():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "HelixKorea Serial Datalogger",
                "Program minimized to system tray and still running in background.",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            self.port_checker = False
            if self.receiver_thread:
                self.receiver_thread.stop()
                self.receiver_thread.wait()
            self.tray_icon.hide()
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SerialDataloggerApp()
    window.show()
    sys.exit(app.exec())