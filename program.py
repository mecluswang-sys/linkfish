import sys
import time
import logging
import numpy as np
import sounddevice as sd
import win32gui
import win32con
import win32api
import random
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel, QDoubleSpinBox, QComboBox, 
                             QLineEdit, QTextEdit, QMessageBox, QCheckBox, QDialog,
                             QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox)
import pyqtgraph as pg

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class WowFishingGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WoW 钓鱼助手")
        self.resize(1150, 800)
        self.move(self.screen().availableGeometry().center() - self.frameGeometry().center())

        self.target_hwnd = None
        self.FS = 44100
        self.WAVE_PLOT_POINTS = 1500
        self.audio_buffer = np.zeros(self.WAVE_PLOT_POINTS)
        self.x_axis = np.linspace(-15, 0, self.WAVE_PLOT_POINTS)
        
        self.is_running = False
        self.is_cooling_down = False 
        self.bite_threshold = 0.3
        self.start_time = 0.0 
        self.key_hold_range = (0.14, 0.24)
        self.key_gap_range = (0.10, 0.18)
        self.auto_macro_delay_ms_range = (250, 450)
        self.auto_macro_script = '/script T,F=T or 0,F or CreateFrame("frame")if X then X=nil else X=function()local t=GetTime()if t-T>1 then StaticPopup1Button1:Click()T=t end end end F:SetScript ("OnUpdate",X)'
        
        # 自动定时按键配置列表，结构为: [{"key": "3", "interval": 600, "last_time": 0.0, "enabled": True}]
        self.auto_keys = []

        # 1. 初始化 UI
        self.init_ui()
        # 2. 填充数据
        self.refresh_windows_list()
        self.refresh_audio_devices()
        # 3. 启动音频流
        self.restart_audio_stream()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(30)

    def log(self, message):
        timestamp = time.strftime('%H:%M:%S')
        full_msg = f"[{timestamp}] {message}"
        logging.info(full_msg)
        if hasattr(self, 'log_display'):
            self.log_display.append(full_msg)

    def refresh_windows_list(self):
        """扫描当前所有窗口，并尝试自动选中魔兽世界"""
        self.window_combo.clear()
        
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title: windows.append((title, hwnd))
        
        windows = []
        win32gui.EnumWindows(callback, windows)
        
        found_index = -1
        for i, (title, hwnd) in enumerate(windows):
            self.window_combo.addItem(f"{title} ({hwnd})", hwnd)
            if "魔兽世界" in title:
                found_index = i
        
        if found_index != -1:
            self.window_combo.setCurrentIndex(found_index)
            self.log(f"已自动锁定: {self.window_combo.currentText()}")
        else:
            self.log("窗口列表已刷新（未检测到魔兽世界）。")

    def refresh_audio_devices(self):
        self.device_combo.clear()
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0:
                self.device_combo.addItem(f"[{i}] {d['name']}", i)

    def update_threshold_line(self, value):
        self.bite_threshold = value
        self.thresh_line.setPos(value)

    def update_toggle_button_style(self):
        if self.is_running:
            self.btn_toggle.setStyleSheet(
                "QPushButton {"
                "background-color: #c62828;"
                "color: white;"
                "border: 1px solid #8e0000;"
                "border-radius: 6px;"
                "padding: 6px 12px;"
                "font-weight: 600;"
                "}"
                "QPushButton:hover { background-color: #d32f2f; }"
                "QPushButton:pressed { background-color: #8e0000; }"
            )
        else:
            self.btn_toggle.setStyleSheet(
                "QPushButton {"
                "background-color: #2e7d32;"
                "color: white;"
                "border: 1px solid #1b5e20;"
                "border-radius: 6px;"
                "padding: 6px 12px;"
                "font-weight: 600;"
                "}"
                "QPushButton:hover { background-color: #388e3c; }"
                "QPushButton:pressed { background-color: #1b5e20; }"
            )

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        left_panel_width = 540
        control_layout = QVBoxLayout()
        label_width = 90
        
        self.window_combo = QComboBox()
        btn_refresh = QPushButton("刷新窗口列表"); btn_refresh.clicked.connect(self.refresh_windows_list)

        window_row = QHBoxLayout()
        window_label = QLabel("1. 选择游戏窗口:")
        window_label.setFixedWidth(label_width)
        window_row.addWidget(window_label)
        window_row.addWidget(self.window_combo)
        window_row.addWidget(btn_refresh)
        control_layout.addLayout(window_row)

        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.restart_audio_stream)

        audio_row = QHBoxLayout()
        audio_label = QLabel("2. 音源输入设备:")
        audio_label.setFixedWidth(label_width)
        audio_row.addWidget(audio_label)
        audio_row.addWidget(self.device_combo)
        control_layout.addLayout(audio_row)

        self.thresh_spin = QDoubleSpinBox()
        self.thresh_spin.setRange(0.001, 1.0); self.thresh_spin.setSingleStep(0.01)
        self.thresh_spin.setValue(self.bite_threshold)
        self.thresh_spin.valueChanged.connect(self.update_threshold_line)

        thresh_row = QHBoxLayout()
        thresh_label = QLabel("3. 判定阈值:")
        thresh_label.setFixedWidth(label_width)
        thresh_row.addWidget(thresh_label)
        thresh_row.addWidget(self.thresh_spin)
        thresh_row.addStretch()
        control_layout.addLayout(thresh_row)

        self.key_cast = QLineEdit("1"); self.key_interact = QLineEdit("f")
        self.key_cast.setMaximumWidth(45)
        self.key_interact.setMaximumWidth(45)

        self.auto_macro_checkbox = QCheckBox("自动确认宏")
        self.auto_macro_checkbox.setChecked(False)

        self.auto_macro_help_btn = QPushButton("!")
        self.auto_macro_help_btn.setFixedSize(22, 22)
        self.auto_macro_help_btn.setToolTip("查看自动确认宏")
        self.auto_macro_help_btn.setStyleSheet(
            "QPushButton {"
            "border: 1px solid #666;"
            "border-radius: 11px;"
            "font-weight: 700;"
            "background-color: #f2f2f2;"
            "padding: 0px;"
            "}"
            "QPushButton:hover { background-color: #e6e6e6; }"
        )
        self.auto_macro_help_btn.clicked.connect(self.show_auto_macro_dialog)

        self.auto_macro_key = QLineEdit("2")
        self.auto_macro_key.setMaximumWidth(45)
        self.auto_macro_key.setEnabled(False)
        self.auto_macro_checkbox.toggled.connect(self.auto_macro_key.setEnabled)

        key_row = QHBoxLayout()
        key_title = QLabel("4. 基础按键:")
        key_title.setFixedWidth(label_width)
        key_row.addWidget(key_title)
        key_row.addWidget(QLabel("抛竿:"))
        key_row.addWidget(self.key_cast)
        key_row.addWidget(QLabel("起竿:"))
        key_row.addWidget(self.key_interact)
        key_row.addWidget(self.auto_macro_checkbox)
        key_row.addWidget(self.auto_macro_help_btn)
        key_row.addWidget(QLabel("确认宏:"))
        key_row.addWidget(self.auto_macro_key)
        key_row.addStretch()
        control_layout.addLayout(key_row)

        # ----------------- 5. 新增：定时自动按键列表界面 -----------------
        auto_key_title = QLabel("5. 定时按键 (如Buff/鱼饵):")

        self.add_key_input = QLineEdit("3")
        self.add_key_input.setFixedWidth(32)
        self.add_key_input.setPlaceholderText("按键")

        self.add_time_unit_combo = QComboBox()
        self.add_time_unit_combo.addItems(["秒", "分钟"])
        self.add_time_unit_combo.setCurrentIndex(0)
        self.add_time_unit_combo.setFixedWidth(70)

        self.add_interval_input = QSpinBox()
        self.add_interval_input.setRange(1, 86400)
        self.add_interval_input.setValue(30)
        self.add_interval_input.setSuffix("")
        self.add_interval_input.setFixedWidth(70)

        def update_auto_key_unit_suffix():
            unit = self.add_time_unit_combo.currentText()
            if unit == "秒":
                self.add_interval_input.setRange(1, 86400)
            else:
                self.add_interval_input.setRange(1, 1440)

        self.add_time_unit_combo.currentIndexChanged.connect(update_auto_key_unit_suffix)

        btn_add_auto_key = QPushButton("添加")
        btn_add_auto_key.setFixedWidth(52)
        btn_add_auto_key.clicked.connect(self.add_auto_key_item)

        btn_del_auto_key = QPushButton("删除选中")
        btn_del_auto_key.setFixedWidth(72)
        btn_del_auto_key.clicked.connect(self.del_auto_key_item)

        auto_key_control_row = QHBoxLayout()
        auto_key_control_row.setSpacing(8)
        auto_key_control_row.addWidget(auto_key_title, 0)
        auto_key_control_row.addWidget(QLabel("键:"))
        auto_key_control_row.addWidget(self.add_key_input)
        auto_key_control_row.addWidget(QLabel("间隔:"))
        auto_key_control_row.addWidget(self.add_interval_input)
        auto_key_control_row.addWidget(self.add_time_unit_combo)
        auto_key_control_row.addWidget(btn_add_auto_key)
        auto_key_control_row.addWidget(btn_del_auto_key)
        auto_key_control_row.addStretch(1)
        auto_key_control_row.setContentsMargins(0, 0, 0, 0)
        control_layout.addLayout(auto_key_control_row)

        self.auto_key_table = QTableWidget(0, 3)
        self.auto_key_table.setHorizontalHeaderLabels(["按键", "间隔", "状态"])
        self.auto_key_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.auto_key_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.auto_key_table.setFixedHeight(110)
        control_layout.addWidget(self.auto_key_table)
        # -------------------------------------------------------------

        self.btn_toggle = QPushButton("开启自动钓鱼")
        self.btn_toggle.setMinimumSize(170, 44)
        self.btn_toggle.setToolTip("点击开启/关闭自动钓鱼")
        self.update_toggle_button_style()
        self.btn_toggle.clicked.connect(self.toggle_fishing)

        toggle_row = QHBoxLayout()
        toggle_row.addStretch()
        toggle_row.addWidget(self.btn_toggle)
        toggle_row.addStretch()
        control_layout.addLayout(toggle_row)
        
        self.log_display = QTextEdit(); self.log_display.setReadOnly(True)
        control_layout.addWidget(QLabel("操作日志:")); control_layout.addWidget(self.log_display)

        control_widget = QWidget()
        control_widget.setLayout(control_layout)
        control_widget.setFixedWidth(left_panel_width)
        layout.addWidget(control_widget)

        plot_layout = QVBoxLayout()
        self.plot_wave = pg.PlotWidget(title="实时波形"); self.plot_wave.setYRange(0, 1.0)
        self.curve_wave = self.plot_wave.plot(self.x_axis, self.audio_buffer, pen='g')
        self.thresh_line = pg.InfiniteLine(angle=0, pos=self.bite_threshold, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
        self.plot_wave.addItem(self.thresh_line)
        plot_layout.addWidget(self.plot_wave)
        layout.addLayout(plot_layout, stretch=0)
        layout.setStretch(0, 4)
        layout.setStretch(1, 2)

    # ----------------- 新增：定时按键管理逻辑 -----------------
    def format_auto_key_interval(self, seconds):
        minutes = seconds / 60
        if seconds % 60 == 0 and minutes < 60:
            return f"{int(minutes)} 分钟"
        return f"{seconds} 秒"

    def add_auto_key_item(self):
        key = self.add_key_input.text().strip()
        value = self.add_interval_input.value()
        unit = self.add_time_unit_combo.currentText()
        if not key:
            QMessageBox.warning(self, "警告", "按键不能为空！")
            return

        interval_seconds = value * 60 if unit == "分钟" else value
        item_data = {
            "key": key,
            "interval": interval_seconds,
            "last_time": 0.0,
            "enabled": True
        }
        self.auto_keys.append(item_data)

        row = self.auto_key_table.rowCount()
        self.auto_key_table.insertRow(row)
        self.auto_key_table.setItem(row, 0, QTableWidgetItem(key))
        self.auto_key_table.setItem(row, 1, QTableWidgetItem(self.format_auto_key_interval(interval_seconds)))
        self.auto_key_table.setItem(row, 2, QTableWidgetItem("等待运行"))
        self.log(f"添加定时按键: [{key}]，间隔: {self.format_auto_key_interval(interval_seconds)}")

    def del_auto_key_item(self):
        current_row = self.auto_key_table.currentRow()
        if current_row >= 0:
            del self.auto_keys[current_row]
            self.auto_key_table.removeRow(current_row)
            self.log("删除了选中的定时按键配置。")

    def check_and_trigger_auto_keys(self):
        """检查并按需触发定时按键（在未处于上钩冷却中时）"""
        if not self.is_running or self.is_cooling_down:
            return

        now = time.time()
        for idx, item in enumerate(self.auto_keys):
            if item["last_time"] <= 0.0:
                item["last_time"] = now + item["interval"]
                continue

            if now - item["last_time"] >= item["interval"]:
                key = item["key"]
                interval_text = self.format_auto_key_interval(int(item["interval"]))
                self.log(f"⌛ 触发定时按键: [{key}] (间隔: {interval_text})")
                self.send_background_key(key)
                item["last_time"] = now

                self.auto_key_table.setItem(idx, 2, QTableWidgetItem(time.strftime('%H:%M:%S 已触发')))

                self.is_cooling_down = True
                QTimer.singleShot(2500, self.finish_cooldown)
                break
    # --------------------------------------------------------

    def restart_audio_stream(self):
        try:
            if hasattr(self, 'audio_stream'): self.audio_stream.close()
            dev_idx = self.device_combo.currentData()
            self.audio_stream = sd.InputStream(channels=1, samplerate=self.FS, device=dev_idx, blocksize=1024, callback=self.audio_callback)
            self.audio_stream.start()
            self.log("音频流已重连。")
        except Exception as e: self.log(f"音频错误: {e}")

    def audio_callback(self, indata, frames, time_info, status):
        self.current_max_peak = np.max(np.abs(indata[:, 0] - np.mean(indata[:, 0])))
        self.audio_buffer = np.roll(self.audio_buffer, -1)
        self.audio_buffer[-1] = self.current_max_peak

    def is_wow_active(self):
        hwnd = self.window_combo.currentData()
        if hwnd and win32gui.IsWindow(hwnd):
            self.target_hwnd = hwnd
            return True
        return False

    def toggle_fishing(self):
        if not self.is_running:
            if not self.is_wow_active():
                hwnd = win32gui.FindWindow(None, "魔兽世界")
                if not hwnd:
                    QMessageBox.warning(self, "错误", "未检测到窗口，请在下拉列表中手动指定！")
                    return
                index = self.window_combo.findData(hwnd)
                if index != -1: self.window_combo.setCurrentIndex(index)
            
            self.is_running = True
            self.is_cooling_down = False
            
            # 启动后从当前时间开始计时，并延后首个触发一整周期，避免启动瞬间立刻按键
            now = time.time()
            for item in self.auto_keys:
                item["last_time"] = now + item["interval"]

            win32gui.SetWindowPos(self.target_hwnd, win32con.HWND_BOTTOM, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            self.log(f"任务启动，句柄: {self.target_hwnd}")
            self.start_time = time.time() + 5.0
            QTimer.singleShot(5000, self.fishing_loop)
            self.btn_toggle.setText("停止自动钓鱼")
            self.update_toggle_button_style()
        else:
            self.is_running = False
            self.btn_toggle.setText("开启自动钓鱼")
            self.update_toggle_button_style()
            self.log("任务停止。")

    def send_background_key(self, key_char):
        if not self.is_wow_active(): return
        if not key_char: return

        key_char = key_char.strip()
        if not key_char: return
        key_char = key_char[0]
        
        vk_code = win32api.VkKeyScan(key_char) & 0xFF
        scan_code = win32api.MapVirtualKey(vk_code, 0)
        
        lparam_down = (scan_code << 16) | 1
        lparam_up = (scan_code << 16) | 0xC0000001
        
        win32api.PostMessage(self.target_hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)
        time.sleep(random.uniform(*self.key_hold_range))
        win32api.PostMessage(self.target_hwnd, win32con.WM_KEYUP, vk_code, lparam_up)
        time.sleep(random.uniform(*self.key_gap_range))

    def fishing_loop(self):
        if not self.is_running or not self.is_wow_active(): return
        self.start_time = time.time()
        self.send_background_key(self.key_cast.text())
        self.log("抛竿。")

    def update_loop(self):
        self.curve_wave.setData(self.x_axis, self.audio_buffer)
        if not self.is_running: return

        # 检查并触发自定义定时按键 (如补Buff)
        self.check_and_trigger_auto_keys()

        if self.is_cooling_down: return
        
        # 随机超时: 22s + 1~5s
        if (time.time() - self.start_time) > (22.0 + random.randint(1000, 5000) / 1000.0):
            self.log("超时，重抛。")
            self.fishing_loop()
        elif self.current_max_peak > self.thresh_spin.value():
            self.log(f"咬钩！峰值: {self.current_max_peak:.4f}")
            self.send_background_key(self.key_interact.text())
            self.is_cooling_down = True
            base_cooldown_ms = random.randint(1000, 6000)

            if self.auto_macro_checkbox.isChecked():
                macro_delay_ms = random.randint(*self.auto_macro_delay_ms_range)
                QTimer.singleShot(macro_delay_ms, lambda: self.send_background_key(self.auto_macro_key.text()))
                QTimer.singleShot(base_cooldown_ms + macro_delay_ms, self.finish_cooldown)
            else:
                QTimer.singleShot(base_cooldown_ms, self.finish_cooldown)

    def finish_cooldown(self):
        self.is_cooling_down = False
        self.fishing_loop()

    def show_auto_macro_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("自动确认宏")
        dialog.resize(760, 220)

        dialog_layout = QVBoxLayout(dialog)
        macro_text = QTextEdit()
        macro_text.setReadOnly(True)
        macro_text.setPlainText(self.auto_macro_script)
        dialog_layout.addWidget(macro_text)

        action_row = QHBoxLayout()
        action_row.addStretch()
        btn_copy = QPushButton("复制宏")
        btn_close = QPushButton("关闭")

        def copy_macro():
            QApplication.clipboard().setText(self.auto_macro_script)
            self.log("已复制自动确认宏到剪贴板。")

        btn_copy.clicked.connect(copy_macro)
        btn_close.clicked.connect(dialog.accept)

        action_row.addWidget(btn_copy)
        action_row.addWidget(btn_close)
        dialog_layout.addLayout(action_row)

        dialog.exec()

    def closeEvent(self, event):
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = WowFishingGui()
    win.show()
    sys.exit(app.exec())