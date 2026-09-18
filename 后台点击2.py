import win32gui
import win32con
import time
import keyboard
import threading

# 全局变量控制按键状态
pressing = False
target_window = None

def find_window_by_title(title):
    """根据窗口标题查找窗口句柄"""
    def callback(hwnd, hwnds):
        if win32gui.IsWindowVisible(hwnd) and title.lower() in win32gui.GetWindowText(hwnd).lower():
            hwnds.append(hwnd)
        return True
    
    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
    return hwnds[0] if hwnds else None

def press_2_background():
    """在后台窗口连续按数字2键"""
    global pressing, target_window
    
    while pressing:
        if target_window:
            # 发送WM_KEYDOWN消息
            win32gui.SendMessage(target_window, win32con.WM_KEYDOWN, 0x38, 0)
            # 发送WM_KEYUP消息
            win32gui.SendMessage(target_window, win32con.WM_KEYUP, 0x38, 0)
        time.sleep(0.1)  # 按键间隔，可调整

def toggle_pressing():
    """切换按键状态"""
    global pressing, target_window
    
    # 如果没有设置目标窗口，尝试查找
    if not target_window:
        window_title = input("请输入目标窗口标题（部分匹配即可）: ")
        target_window = find_window_by_title(window_title)
        if not target_window:
            print("未找到指定窗口，请确认窗口标题是否正确")
            return
    
    pressing = not pressing
    if pressing:
        print("开始后台连续按2键...")
        # 在新线程中运行按键功能
        thread = threading.Thread(target=press_2_background)
        thread.daemon = True
        thread.start()
    else:
        print("停止按2键")

# 设置热键（例如F6开始/停止）
keyboard.add_hotkey('F6', toggle_pressing)

print("程序已启动，按F6开始/停止后台连续按2键，按ESC退出程序")

# 保持程序运行，直到按下ESC
keyboard.wait('esc')
print("程序已退出")