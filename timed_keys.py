import logging
import random
import sys
import time

import win32api
import win32con
import win32gui
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")


class TimedKeysGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("定时按键工具")
        self.resize(620, 500)

        self.target_hwnd = None
        self.is_running = False
        self.auto_keys = []
        self.auto_key_queue = []
        self.auto_key_sending = False
        self.key_send_generation = 0
        self.current_key = None
        self.pickup_next_time = 0.0
        self.pickup_until = 0.0
        self.pickup_pending = False
        self.key_hold_range = (0.03, 0.06)
        self.key_gap_range = (0.02, 0.04)

        self.init_ui()
        self.refresh_windows_list()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_and_trigger_auto_keys)
        self.timer.start(30)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        window_row = QHBoxLayout()
        window_row.addWidget(QLabel("目标窗口:"))
        self.window_combo = QComboBox()
        window_row.addWidget(self.window_combo)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh_windows_list)
        window_row.addWidget(refresh_button)
        layout.addLayout(window_row)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("按键:"))
        self.add_key_input = QLineEdit("3")
        self.add_key_input.setFixedWidth(50)
        key_row.addWidget(self.add_key_input)
        key_row.addWidget(QLabel("间隔:"))
        self.add_interval_input = QDoubleSpinBox()
        self.add_interval_input.setDecimals(2)
        self.add_interval_input.setRange(0.01, 86400)
        self.add_interval_input.setValue(0.3)
        self.add_interval_input.setSingleStep(0.01)
        self.add_interval_input.setFixedWidth(80)
        key_row.addWidget(self.add_interval_input)
        self.add_time_unit_combo = QComboBox()
        self.add_time_unit_combo.addItems(["秒", "分钟"])
        self.add_time_unit_combo.currentTextChanged.connect(self.update_interval_range)
        key_row.addWidget(self.add_time_unit_combo)
        add_button = QPushButton("添加")
        add_button.clicked.connect(self.add_auto_key_item)
        key_row.addWidget(add_button)
        delete_button = QPushButton("删除选中")
        delete_button.clicked.connect(self.del_auto_key_item)
        key_row.addWidget(delete_button)
        key_row.addStretch()
        layout.addLayout(key_row)

        pickup_row = QHBoxLayout()
        pickup_row.addWidget(QLabel("拾取键:"))
        self.pickup_key_input = QLineEdit("2")
        self.pickup_key_input.setPlaceholderText("可选")
        self.pickup_key_input.setFixedWidth(50)
        pickup_row.addWidget(self.pickup_key_input)
        pickup_row.addWidget(QLabel("间隔:"))
        self.pickup_interval_input = QDoubleSpinBox()
        self.pickup_interval_input.setDecimals(2)
        self.pickup_interval_input.setRange(0.01, 86400)
        self.pickup_interval_input.setValue(15)
        self.pickup_interval_input.setFixedWidth(80)
        pickup_row.addWidget(self.pickup_interval_input)
        self.pickup_time_unit_combo = QComboBox()
        self.pickup_time_unit_combo.addItems(["秒", "分钟"])
        self.pickup_time_unit_combo.currentTextChanged.connect(self.update_pickup_interval_range)
        self.pickup_time_unit_combo.setFixedWidth(70)
        pickup_row.addWidget(self.pickup_time_unit_combo)
        pickup_row.addWidget(QLabel("技能时长:"))
        self.pickup_duration_input = QDoubleSpinBox()
        self.pickup_duration_input.setDecimals(2)
        self.pickup_duration_input.setRange(0.1, 60.0)
        self.pickup_duration_input.setValue(1.0)
        self.pickup_duration_input.setSuffix(" 秒")
        self.pickup_duration_input.setFixedWidth(90)
        pickup_row.addWidget(self.pickup_duration_input)
        pickup_row.addStretch()
        layout.addLayout(pickup_row)

        self.auto_key_table = QTableWidget(0, 3)
        self.auto_key_table.setHorizontalHeaderLabels(["按键", "间隔", "状态"])
        self.auto_key_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.auto_key_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.auto_key_table)

        self.toggle_button = QPushButton("开始定时按键")
        self.toggle_button.setMinimumHeight(42)
        self.toggle_button.clicked.connect(self.toggle_running)
        layout.addWidget(self.toggle_button)

        layout.addWidget(QLabel("操作日志:"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)

    def log(self, message):
        full_message = f"[{time.strftime('%H:%M:%S')}] {message}"
        logging.info(full_message)
        self.log_display.append(full_message)

    def refresh_windows_list(self):
        current_hwnd = self.window_combo.currentData()
        self.window_combo.clear()

        windows = []

        def collect_window(hwnd, result):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    result.append((title, hwnd))

        win32gui.EnumWindows(collect_window, windows)
        for title, hwnd in windows:
            self.window_combo.addItem(f"{title} ({hwnd})", hwnd)

        wow_window = next(
            (
                (title, hwnd)
                for title, hwnd in windows
                if "魔兽世界" in title or "world of warcraft" in title.casefold()
            ),
            None,
        )
        if wow_window:
            title, hwnd = wow_window
            self.window_combo.setCurrentIndex(self.window_combo.findData(hwnd))
            self.log(f"已自动选择魔兽世界窗口: {title}")
            return

        index = self.window_combo.findData(current_hwnd)
        if index >= 0:
            self.window_combo.setCurrentIndex(index)
        self.log("窗口列表已刷新（未找到魔兽世界窗口）。")

    def update_interval_range(self, unit):
        self.add_interval_input.setRange(0.01, 1440 if unit == "分钟" else 86400)

    def format_interval(self, seconds):
        if seconds % 60 == 0 and seconds < 3600:
            return f"{seconds / 60:g} 分钟"
        return f"{seconds:g} 秒"

    def add_auto_key_item(self):
        key = self.add_key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "警告", "按键不能为空。")
            return

        interval = self.add_interval_input.value()
        if self.add_time_unit_combo.currentText() == "分钟":
            interval *= 60

        self.auto_keys.append({"key": key, "interval": interval, "next_time": 0.0})
        row = self.auto_key_table.rowCount()
        self.auto_key_table.insertRow(row)
        self.auto_key_table.setItem(row, 0, QTableWidgetItem(key))
        self.auto_key_table.setItem(row, 1, QTableWidgetItem(self.format_interval(interval)))
        self.auto_key_table.setItem(row, 2, QTableWidgetItem("等待开始"))
        self.log(f"添加定时按键: [{key}]，间隔: {self.format_interval(interval)}")

    def del_auto_key_item(self):
        row = self.auto_key_table.currentRow()
        if row < 0:
            return
        del self.auto_keys[row]
        self.auto_key_table.removeRow(row)
        self.log("已删除选中的定时按键。")

    def toggle_running(self):
        if self.is_running:
            self.is_running = False
            self.toggle_button.setText("开始定时按键")
            self.log("定时按键已停止。")
            return

        if not self.auto_keys and not self.pickup_key_input.text().strip():
            QMessageBox.warning(self, "警告", "请先添加定时按键或设置拾取键。")
            return
        if not self.is_target_window_valid():
            QMessageBox.warning(self, "错误", "请选择有效的目标窗口。")
            return

        now = time.time()
        for row, item in enumerate(self.auto_keys):
            item["next_time"] = now + item["interval"]
            self.auto_key_table.setItem(row, 2, QTableWidgetItem("等待首次触发"))
        self.pickup_next_time = (
            now + self.pickup_interval_seconds()
            if self.pickup_key_input.text().strip()
            else 0.0
        )

        self.is_running = True
        self.toggle_button.setText("停止定时按键")
        self.log("定时按键已启动。")

    def is_target_window_valid(self):
        hwnd = self.window_combo.currentData()
        if hwnd and win32gui.IsWindow(hwnd):
            self.target_hwnd = hwnd
            return True
        return False

    def pickup_interval_seconds(self):
        interval = self.pickup_interval_input.value()
        if self.pickup_time_unit_combo.currentText() == "分钟":
            interval *= 60
        return interval

    def update_pickup_interval_range(self, unit):
        self.pickup_interval_input.setRange(0.01, 1440 if unit == "分钟" else 86400)

    def check_and_trigger_auto_keys(self):
        if not self.is_running:
            return
        if not self.is_target_window_valid():
            self.is_running = False
            self.toggle_button.setText("开始定时按键")
            self.log("目标窗口已关闭，定时按键已停止。")
            return

        now = time.time()
        pickup_key = self.pickup_key_input.text().strip()
        pickup_triggered = False
        if pickup_key:
            if self.pickup_next_time <= 0.0:
                self.pickup_next_time = now + self.pickup_interval_seconds()
            elif now >= self.pickup_next_time:
                self.pickup_next_time = now + self.pickup_interval_seconds()
                if not self.pickup_pending:
                    self.auto_key_queue.insert(0, (pickup_key, True))
                    self.pickup_pending = True
                    pickup_triggered = True
                    self.log(f"触发拾取键: [{pickup_key}]")
                    self.preempt_current_key_for_pickup()

        pickup_locked = pickup_triggered or time.monotonic() < self.pickup_until
        due_keys = []
        for row, item in enumerate(self.auto_keys):
            if now < item["next_time"]:
                continue

            due_keys.append((row, item))
            item["next_time"] = now + item["interval"]

        for row, item in due_keys:
            status = "拾取期间跳过" if pickup_locked else time.strftime("%H:%M:%S 已触发")
            self.auto_key_table.setItem(row, 2, QTableWidgetItem(status))
            if pickup_locked:
                self.log(f"拾取施法期间跳过定时按键: [{item['key']}]")
                continue
            self.log(f"触发定时按键: [{item['key']}] (间隔: {self.format_interval(item['interval'])})")
            self.auto_key_queue.append((item["key"], False))
        self.send_next_auto_key()

    def send_next_auto_key(self):
        if self.auto_key_sending:
            return
        if not self.auto_key_queue:
            return
        if time.monotonic() < self.pickup_until:
            return
        if not self.is_running or not self.is_target_window_valid():
            self.auto_key_queue.clear()
            self.pickup_pending = False
            return

        key, is_pickup = self.auto_key_queue.pop(0)
        key = key.strip()
        if not key:
            self.send_next_auto_key()
            return

        virtual_key = win32api.VkKeyScan(key[0]) & 0xFF
        scan_code = win32api.MapVirtualKey(virtual_key, 0)
        key_down_lparam = (scan_code << 16) | 1
        key_up_lparam = (scan_code << 16) | 0xC0000001
        hwnd = self.target_hwnd

        self.auto_key_sending = True
        self.key_send_generation += 1
        generation = self.key_send_generation
        self.current_key = {
            "hwnd": hwnd,
            "virtual_key": virtual_key,
            "key_down_lparam": key_down_lparam,
            "key_up_lparam": key_up_lparam,
            "is_pickup": is_pickup,
            "key_down": True,
            "presses_remaining": 2 if is_pickup else 1,
        }
        if is_pickup:
            self.auto_key_queue.clear()
            duration_ms = int(self.pickup_duration_input.value() * 1000)
            self.pickup_until = time.monotonic() + duration_ms / 1000
            QTimer.singleShot(duration_ms, self.finish_pickup_lock)
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, virtual_key, key_down_lparam)
        hold_ms = int(random.uniform(*self.key_hold_range) * 1000)
        gap_ms = int(random.uniform(*self.key_gap_range) * 1000)
        QTimer.singleShot(
            hold_ms,
            lambda: self.release_auto_key(hwnd, virtual_key, key_up_lparam, gap_ms, generation),
        )

    def preempt_current_key_for_pickup(self):
        current_key = self.current_key
        if not self.auto_key_sending or not current_key or current_key["is_pickup"]:
            return

        if current_key["key_down"] and win32gui.IsWindow(current_key["hwnd"]):
            win32api.PostMessage(
                current_key["hwnd"],
                win32con.WM_KEYUP,
                current_key["virtual_key"],
                current_key["key_up_lparam"],
            )

        self.key_send_generation += 1
        self.current_key = None
        self.auto_key_sending = False

    def release_auto_key(self, hwnd, virtual_key, key_up_lparam, gap_ms, generation):
        if generation != self.key_send_generation:
            return
        if win32gui.IsWindow(hwnd):
            win32api.PostMessage(hwnd, win32con.WM_KEYUP, virtual_key, key_up_lparam)
        if self.current_key:
            self.current_key["key_down"] = False
            self.current_key["presses_remaining"] -= 1
            if self.current_key["is_pickup"] and self.current_key["presses_remaining"] > 0:
                QTimer.singleShot(
                    gap_ms,
                    lambda: self.press_pickup_again(hwnd, virtual_key, generation),
                )
                return
        QTimer.singleShot(gap_ms, lambda: self.continue_auto_key_queue(generation))

    def press_pickup_again(self, hwnd, virtual_key, generation):
        if generation != self.key_send_generation or not self.current_key:
            return
        if not win32gui.IsWindow(hwnd):
            self.continue_auto_key_queue(generation)
            return

        win32api.PostMessage(
            hwnd,
            win32con.WM_KEYDOWN,
            virtual_key,
            self.current_key["key_down_lparam"],
        )
        self.current_key["key_down"] = True
        hold_ms = int(random.uniform(*self.key_hold_range) * 1000)
        gap_ms = int(random.uniform(*self.key_gap_range) * 1000)
        key_up_lparam = self.current_key["key_up_lparam"]
        QTimer.singleShot(
            hold_ms,
            lambda: self.release_auto_key(
                hwnd,
                virtual_key,
                key_up_lparam,
                gap_ms,
                generation,
            ),
        )

    def continue_auto_key_queue(self, generation):
        if generation != self.key_send_generation:
            return
        self.auto_key_sending = False
        self.current_key = None
        self.send_next_auto_key()

    def finish_pickup_lock(self):
        remaining_ms = int((self.pickup_until - time.monotonic()) * 1000)
        if remaining_ms > 0:
            QTimer.singleShot(remaining_ms, self.finish_pickup_lock)
            return
        if self.current_key and self.current_key["is_pickup"] and self.current_key["presses_remaining"] > 0:
            QTimer.singleShot(30, self.finish_pickup_lock)
            return
        self.pickup_until = 0.0
        self.pickup_pending = False
        self.log("拾取技能时长结束，继续发送按键队列。")
        self.send_next_auto_key()

    def send_background_key(self, key):
        key = key.strip()
        if not key:
            return
        if time.monotonic() < self.pickup_until:
            return

        virtual_key = win32api.VkKeyScan(key[0]) & 0xFF
        scan_code = win32api.MapVirtualKey(virtual_key, 0)
        key_down_lparam = (scan_code << 16) | 1
        key_up_lparam = (scan_code << 16) | 0xC0000001

        win32api.PostMessage(self.target_hwnd, win32con.WM_KEYDOWN, virtual_key, key_down_lparam)
        time.sleep(random.uniform(*self.key_hold_range))
        win32api.PostMessage(self.target_hwnd, win32con.WM_KEYUP, virtual_key, key_up_lparam)
        time.sleep(random.uniform(*self.key_gap_range))


if __name__ == "__main__":
    application = QApplication(sys.argv)
    window = TimedKeysGui()
    window.show()
    sys.exit(application.exec())