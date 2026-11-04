"""养鱼助手。

这是独立于 Windows 版 program.py 的一份实现，依赖与运行环境也完全独立。
核心差异：macOS 没有 PostMessage 这种向后台窗口投递按键的机制，
因此本版本要求游戏处于前台，通过 CGEvent 注入键盘事件。
"""

import logging
import random
import sys
import time

import numpy as np
import pyqtgraph as pg
import sounddevice as sd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if sys.platform != "darwin":
    raise RuntimeError("本程序仅支持 macOS，Windows 请使用项目根目录的 program.py。")

import AppKit
import Quartz

try:
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt,
    )
except ImportError:
    AXIsProcessTrustedWithOptions = None
    kAXTrustedCheckOptionPrompt = None

try:
    import AVFoundation
except ImportError:
    AVFoundation = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# macOS 虚拟键码（US ANSI 布局）。
CHAR_KEY_CODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37,
    "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
    "n": 45, "m": 46, ".": 47, "`": 50,
}

NAMED_KEY_CODES = {
    "return": 36, "enter": 36, "tab": 48, "space": 49, "delete": 51,
    "escape": 53, "esc": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "num0": 82, "num1": 83, "num2": 84, "num3": 85, "num4": 86,
    "num5": 87, "num6": 88, "num7": 89, "num8": 91, "num9": 92,
}

def resolve_key_code(key_text):
    """把用户输入的按键文本解析为 macOS 虚拟键码。"""
    token = key_text.strip().casefold()
    if not token:
        return None
    if token in NAMED_KEY_CODES:
        return NAMED_KEY_CODES[token]
    return CHAR_KEY_CODES.get(token[0])


class WowFishingMacGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("养鱼助手")
        self.resize(1020, 580)
        self.move(self.screen().availableGeometry().center() - self.frameGeometry().center())

        self.target_pid = None
        self.FS = 44100
        self.WAVE_PLOT_POINTS = 1500
        self.audio_buffer = np.zeros(self.WAVE_PLOT_POINTS)
        self.x_axis = np.linspace(-15, 0, self.WAVE_PLOT_POINTS)
        self.current_max_peak = 0.0
        self.audio_stream = None

        self.is_running = False
        self.is_paused = False
        self.is_cooling_down = False
        self.bite_threshold = 0.2
        self.start_time = 0.0
        self.key_hold_range = (0.14, 0.24)
        self.key_gap_range = (0.10, 0.18)

        self.init_ui()
        self.refresh_app_list()
        self.refresh_audio_devices()
        self.request_microphone_access()
        self.restart_audio_stream()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(30)

    def log(self, message):
        full_msg = f"[{time.strftime('%H:%M:%S')}] {message}"
        logging.info(full_msg)
        if hasattr(self, "log_display"):
            self.log_display.append(full_msg)

    # ----------------- 目标应用 -----------------
    def refresh_app_list(self):
        current_target = self.app_combo.currentData()
        self.app_combo.clear()

        found_index = -1
        for application in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            if application.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
                continue
            name = application.localizedName()
            if not name:
                continue
            pid = application.processIdentifier()
            self.app_combo.addItem(f"{name} ({pid})", pid)
            bundle_id = (application.bundleIdentifier() or "").casefold()
            if "魔兽世界" in name or "world of warcraft" in name.casefold() or "worldofwarcraft" in bundle_id:
                found_index = self.app_combo.count() - 1

        if found_index >= 0:
            self.app_combo.setCurrentIndex(found_index)
            self.log(f"已自动锁定: {self.app_combo.currentText()}")
            return

        previous_index = self.app_combo.findData(current_target)
        if previous_index >= 0:
            self.app_combo.setCurrentIndex(previous_index)
        self.log("应用列表已刷新（未检测到魔兽世界）。")

    def find_target_application(self):
        target_pid = self.app_combo.currentData()
        if target_pid is None:
            return None
        for application in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            if application.processIdentifier() == target_pid and not application.isTerminated():
                return application
        return None

    def is_target_frontmost(self):
        application = self.find_target_application()
        if application is None:
            return False
        frontmost = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        return bool(frontmost and frontmost.processIdentifier() == application.processIdentifier())

    def activate_target(self):
        application = self.find_target_application()
        if application is None:
            return False
        return bool(
            application.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        )

    # ----------------- 权限 -----------------
    def has_accessibility_permission(self, prompt=True):
        if AXIsProcessTrustedWithOptions is None:
            return True
        options = {kAXTrustedCheckOptionPrompt: bool(prompt)}
        return bool(AXIsProcessTrustedWithOptions(options))

    def request_microphone_access(self):
        if AVFoundation is None:
            return
        media_type = AVFoundation.AVMediaTypeAudio
        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(media_type)
        if status == AVFoundation.AVAuthorizationStatusAuthorized:
            return
        if status == AVFoundation.AVAuthorizationStatusNotDetermined:
            AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                media_type, lambda granted: None
            )
            self.log("已请求麦克风权限，请在系统弹窗中允许。")
            return
        self.log("麦克风权限被拒绝，请在“系统设置 → 隐私与安全性 → 麦克风”中开启。")

    # ----------------- 按键注入 -----------------
    def post_key(self, key_code, key_down):
        event = Quartz.CGEventCreateKeyboardEvent(None, key_code, key_down)
        if event is None:
            return
        # UI 已移除注入方式选择，统一走 HID 事件层，行为最稳定。
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def send_key(self, key_text):
        """同步发送一次按键（按下 → 保持 → 抬起）。"""
        if not self.ensure_target_ready():
            return

        key_code = resolve_key_code(key_text or "")
        if key_code is None:
            self.log(f"macOS 暂不支持按键: [{key_text}]")
            return

        self.post_key(key_code, True)
        time.sleep(random.uniform(*self.key_hold_range))
        self.post_key(key_code, False)
        time.sleep(random.uniform(*self.key_gap_range))

    # ----------------- 运行状态 -----------------
    def requires_frontmost(self):
        # 固定前台模式：切走游戏时暂停，切回后自动恢复。
        return True

    def ensure_target_ready(self):
        """确认目标可用；不可用时停止，仅仅是失去前台时转为暂停。"""
        if not self.is_running:
            return False

        if self.find_target_application() is None:
            self.stop_fishing("目标应用已退出，自动钓鱼已停止。")
            return False

        if self.requires_frontmost() and not self.is_target_frontmost():
            if not self.is_paused:
                self.is_paused = True
                self.status_label.setText("状态: 已暂停（游戏不在前台）")
                self.log("游戏已离开前台，暂停发送按键；切回游戏后自动恢复。")
            return False

        if self.is_paused:
            self.is_paused = False
            self.status_label.setText("状态: 运行中")
            self.log("游戏已回到前台，恢复自动钓鱼。")
            self.is_cooling_down = False
            self.start_time = time.time()
            QTimer.singleShot(600, self.fishing_loop)
            return False

        return True

    def stop_fishing(self, message):
        self.is_running = False
        self.is_paused = False
        self.is_cooling_down = False
        self.btn_toggle.setText("开启自动钓鱼")
        self.status_label.setText("状态: 已停止")
        self.update_toggle_button_style()
        self.log(message)

    def toggle_fishing(self):
        if self.is_running:
            self.stop_fishing("任务停止。")
            return

        if self.find_target_application() is None:
            self.refresh_app_list()
            if self.find_target_application() is None:
                QMessageBox.warning(self, "错误", "未检测到目标应用，请确认游戏已经启动！")
                return

        if not self.has_accessibility_permission():
            QMessageBox.warning(
                self,
                "需要辅助功能权限",
                "请在“系统设置 → 隐私与安全性 → 辅助功能”中允许本程序控制电脑，然后重新开启。",
            )
            return

        if self.requires_frontmost() and not self.activate_target():
            QMessageBox.warning(self, "错误", "无法将游戏切换到前台。")
            return

        self.is_running = True
        self.is_paused = False
        self.is_cooling_down = False

        self.log(f"任务启动，目标: {self.app_combo.currentText()}")
        if self.requires_frontmost():
            self.log("前台模式：切换到其他应用会暂停，切回游戏自动恢复。")
        else:
            self.log("实验模式：按键直接投递到目标进程，稳定性依游戏而定。")

        self.start_time = time.time() + 5.0
        QTimer.singleShot(5000, self.fishing_loop)
        self.btn_toggle.setText("停止自动钓鱼")
        self.status_label.setText("状态: 运行中")
        self.update_toggle_button_style()

    # ----------------- 音频 -----------------
    def refresh_audio_devices(self):
        self.device_combo.clear()
        for i, device in enumerate(sd.query_devices()):
            if device["max_input_channels"] > 0:
                self.device_combo.addItem(f"[{i}] {device['name']}", i)

    def restart_audio_stream(self):
        if self.audio_stream is not None:
            try:
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None

        dev_idx = self.device_combo.currentData()
        if dev_idx is None:
            self.log("没有可用的音频输入设备。")
            return

        last_error = None
        for samplerate in self.candidate_samplerates(dev_idx):
            try:
                self.audio_stream = sd.InputStream(
                    channels=1,
                    samplerate=samplerate,
                    device=dev_idx,
                    blocksize=1024,
                    callback=self.audio_callback,
                )
                self.audio_stream.start()
                self.FS = int(samplerate)
                self.log(f"音频流已连接（采样率 {self.FS} Hz）。")
                return
            except Exception as error:
                last_error = error
        self.log(f"音频错误: {last_error}")

    def candidate_samplerates(self, dev_idx):
        """优先使用 44100，失败时回退到设备默认采样率（macOS 常见 48000）。"""
        rates = [44100]
        try:
            default_rate = int(sd.query_devices(dev_idx)["default_samplerate"])
            if default_rate not in rates:
                rates.append(default_rate)
        except Exception:
            pass
        for rate in (48000, 22050):
            if rate not in rates:
                rates.append(rate)
        return rates

    def audio_callback(self, indata, frames, time_info, status):
        samples = indata[:, 0]
        self.current_max_peak = float(np.max(np.abs(samples - np.mean(samples))))
        self.audio_buffer = np.roll(self.audio_buffer, -1)
        self.audio_buffer[-1] = self.current_max_peak

    # ----------------- 主循环 -----------------
    def fishing_loop(self):
        if not self.ensure_target_ready():
            return
        self.start_time = time.time()
        self.send_key(self.key_cast.text())
        self.log("抛竿。")

    def update_loop(self):
        self.curve_wave.setData(self.x_axis, self.audio_buffer)
        if not self.ensure_target_ready():
            return

        if self.is_cooling_down:
            return

        if (time.time() - self.start_time) > (22.0 + random.randint(1000, 5000) / 1000.0):
            self.log("超时，重抛。")
            self.fishing_loop()
        elif self.current_max_peak > self.thresh_spin.value():
            self.log(f"咬钩！峰值: {self.current_max_peak:.4f}")
            self.send_key(self.key_interact.text())
            self.is_cooling_down = True
            base_cooldown_ms = random.randint(1000, 6000)
            QTimer.singleShot(base_cooldown_ms, self.finish_cooldown)

    def finish_cooldown(self):
        self.is_cooling_down = False
        self.fishing_loop()

    # ----------------- 界面 -----------------
    def update_threshold_line(self, value):
        self.bite_threshold = value
        self.thresh_line.setPos(value)

    def update_toggle_button_style(self):
        if self.is_running:
            colors = ("#c62828", "#8e0000", "#d32f2f")
        else:
            colors = ("#2e7d32", "#1b5e20", "#388e3c")
        self.btn_toggle.setStyleSheet(
            "QPushButton {"
            f"background-color: {colors[0]};"
            "color: white;"
            f"border: 1px solid {colors[1]};"
            "border-radius: 6px;"
            "padding: 6px 12px;"
            "font-weight: 600;"
            "}"
            f"QPushButton:hover {{ background-color: {colors[2]}; }}"
        )

    def toggle_always_on_top(self, checked):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        if self.isVisible():
            self.show()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        control_layout = QVBoxLayout()
        control_layout.setContentsMargins(6, 6, 6, 6)
        control_layout.setSpacing(6)
        label_width = 96

        self.app_combo = QComboBox()
        btn_refresh = QPushButton("刷新应用列表")
        btn_refresh.clicked.connect(self.refresh_app_list)
        app_row = QHBoxLayout()
        app_label = QLabel("1. 选择游戏应用:")
        app_label.setFixedWidth(label_width)
        app_row.addWidget(app_label)
        app_row.addWidget(self.app_combo)
        app_row.addWidget(btn_refresh)
        control_layout.addLayout(app_row)

        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.restart_audio_stream)
        audio_row = QHBoxLayout()
        audio_label = QLabel("2. 音源输入设备:")
        audio_label.setFixedWidth(label_width)
        audio_row.addWidget(audio_label)
        audio_row.addWidget(self.device_combo)
        control_layout.addLayout(audio_row)

        self.thresh_spin = QDoubleSpinBox()
        self.thresh_spin.setRange(0.001, 1.0)
        self.thresh_spin.setSingleStep(0.01)
        self.thresh_spin.setValue(self.bite_threshold)
        self.thresh_spin.valueChanged.connect(self.update_threshold_line)
        thresh_row = QHBoxLayout()
        thresh_label = QLabel("3. 判定阈值:")
        thresh_label.setFixedWidth(label_width)
        thresh_row.addWidget(thresh_label)
        thresh_row.addWidget(self.thresh_spin)
        thresh_row.addStretch()
        control_layout.addLayout(thresh_row)

        self.key_cast = QLineEdit("1")
        self.key_cast.setMaximumWidth(38)
        self.key_interact = QLineEdit("f")
        self.key_interact.setMaximumWidth(38)

        key_row = QHBoxLayout()
        key_title = QLabel("4. 基础按键:")
        key_title.setFixedWidth(label_width)
        key_row.addWidget(key_title)
        key_row.addWidget(QLabel("抛竿:"))
        key_row.addWidget(self.key_cast)
        key_row.addWidget(QLabel("起竿:"))
        key_row.addWidget(self.key_interact)
        key_row.addStretch()
        control_layout.addLayout(key_row)

        self.btn_toggle = QPushButton("开启自动钓鱼")
        self.btn_toggle.setMinimumSize(156, 40)
        self.update_toggle_button_style()
        self.btn_toggle.clicked.connect(self.toggle_fishing)
        toggle_row = QHBoxLayout()
        toggle_row.addStretch()
        toggle_row.addWidget(self.btn_toggle)
        toggle_row.addStretch()
        control_layout.addLayout(toggle_row)

        self.status_label = QLabel("状态: 已停止")
        self.status_label.setAlignment(Qt.AlignCenter)
        control_layout.addWidget(self.status_label)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        control_layout.addWidget(QLabel("操作日志:"))
        control_layout.addWidget(self.log_display)

        control_widget = QWidget()
        control_widget.setLayout(control_layout)
        control_widget.setFixedWidth(400)
        layout.addWidget(control_widget)

        plot_layout = QVBoxLayout()
        self.plot_wave = pg.PlotWidget(title="实时波形")
        self.plot_wave.setYRange(0, 1.0)
        self.curve_wave = self.plot_wave.plot(self.x_axis, self.audio_buffer, pen="g")
        self.thresh_line = pg.InfiniteLine(
            angle=0, pos=self.bite_threshold, pen=pg.mkPen("r", width=2, style=Qt.DashLine)
        )
        self.plot_wave.addItem(self.thresh_line)
        plot_layout.addWidget(self.plot_wave)
        layout.addLayout(plot_layout, stretch=0)
        layout.setStretch(0, 3)
        layout.setStretch(1, 3)

        self.toggle_always_on_top(True)

    def closeEvent(self, event):
        self.is_running = False
        if self.audio_stream is not None:
            try:
                self.audio_stream.close()
            except Exception:
                pass
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = WowFishingMacGui()
    win.show()
    sys.exit(app.exec())
