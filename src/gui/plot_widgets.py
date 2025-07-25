from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
import matplotlib.dates as mdates
import numpy as np
from obspy.core.stream import Stream

class WaveformWidget(QWidget):
    # 信号定义： pick_type (str), time (float, 相对时间)
    pick_made = pyqtSignal(str, float)
    # 信号定义： start_time (float), end_time (float)
    zoom_requested = pyqtSignal(float, float)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.mpl_connect('button_press_event', self.on_mouse_click)
        
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        
        # 创建子图，并调整布局
        self.axes = self.figure.add_subplot(1, 1, 1) # 单个子图
        self.figure.tight_layout(pad=2.0) # 调整布局
        self.pick_markers = [] # 用于存储拾取标记

        # 添加 SpanSelector 用于拖拽放大
        self.span_selector = SpanSelector(
            self.axes,
            self.on_span_select,
            'horizontal',
            useblit=True,
            props=dict(alpha=0.3, facecolor='yellow'),
            interactive=True,
            button=1 # 仅左键
        )

    def plot_stream(self, stream: Stream):
        """
        绘制单分量Z波形数据
        """
        self.clear_plot()
        
        if not stream:
            return
            
        trace = stream.select(component='Z')
        if not trace:
            self.axes.text(0.5, 0.5, 'No Z Component Data', ha='center', va='center')
            self.canvas.draw()
            return
            
        tr = trace[0]
        time_values = [t.matplotlib_date for t in tr.times("utcdatetime")]
        self.axes.plot(time_values, tr.data, color='black', linewidth=0.8)
        self.axes.axhline(0, color='gray', linestyle='--', linewidth=0.6)
        self.axes.set_ylabel('Component Z')
        
        # 自动调整Y轴范围
        data = tr.data
        min_val = np.min(data)
        max_val = np.max(data)
        margin = (max_val - min_val) * 0.1 # 10%的边距
        self.axes.set_ylim(min_val - margin, max_val + margin)
            
        # 格式化x轴为时间
        self.axes.set_xlabel("Time")
        self.axes.xaxis_date()
        self.figure.autofmt_xdate()
        
        self.canvas.draw()
    
    def clear_plot(self):
        """
        清除绘图区域和标记
        """
        for marker in self.pick_markers:
            marker.remove()
        self.pick_markers.clear()

        self.axes.clear()
        self.canvas.draw()

    def plot_picks(self, picks: dict):
        """
        在Z分量图上绘制拾取标记
        """
        # 清除旧标记
        for marker in self.pick_markers:
            marker.remove()
        self.pick_markers.clear()

        if not picks:
            self.canvas.draw()
            return

        z_ax = self.axes
        
        # 转换相对时间到绝对时间
        # 假设stream的第一个trace的starttime是参考
        if self.main_window and self.main_window.current_stream:
            ref_time = self.main_window.current_stream[0].stats.starttime
            
            p_arrival_abs = (ref_time + picks.get('p_arrival', 0)).matplotlib_date
            onset_time_abs = (ref_time + picks.get('onset_time', 0)).matplotlib_date
            end_time_abs = (ref_time + picks.get('end_time', 0)).matplotlib_date

            # 绘制竖线和标记
            if 'p_arrival' in picks:
                m = z_ax.axvline(p_arrival_abs, color='red', linestyle='--', label='P-Arrival')
                self.pick_markers.append(m)
            if 'onset_time' in picks:
                m = z_ax.plot(onset_time_abs, 0, 'go', markersize=8, label='Onset')[0] # 假设在0振幅处标记
                self.pick_markers.append(m)
            if 'end_time' in picks:
                m = z_ax.axvline(end_time_abs, color='green', linestyle='--', label='End')
                self.pick_markers.append(m)

            # 绘制脉冲区域
            if 'onset_time' in picks and 'end_time' in picks:
                ylims = z_ax.get_ylim()
                m = z_ax.fill_betweenx(ylims, onset_time_abs, end_time_abs, color='cyan', alpha=0.3)
                self.pick_markers.append(m)
                z_ax.set_ylim(ylims) # 保持Y轴范围不变

            # 更新图例
            handles, labels = z_ax.get_legend_handles_labels()
            unique_labels = dict(zip(labels, handles))
            z_ax.legend(unique_labels.values(), unique_labels.keys())
            
            self.canvas.draw()

    def on_mouse_click(self, event):
        """处理matplotlib画布上的鼠标点击事件"""
        if event.inaxes != self.axes:
            return

        if not self.main_window or not self.main_window.current_stream:
            return

        # 将点击的x坐标（matplotlib date）转换回相对时间（秒）
        ref_time = self.main_window.current_stream[0].stats.starttime
        clicked_time_abs = mdates.num2date(event.xdata)
        relative_time_sec = clicked_time_abs.replace(tzinfo=None) - ref_time.datetime

        pick_type = None
        # 右键点击
        if event.button == 3:
            pick_type = 'p_arrival'
        # 左键点击
        elif event.button == 1:
            if event.key == 'control':
                pick_type = 'onset_time'
            else:
                pick_type = 'end_time'

        if pick_type:
            self.pick_made.emit(pick_type, relative_time_sec.total_seconds())

    def on_span_select(self, xmin, xmax):
        """当用户拖拽选择一个区域时调用"""
        # 如果选择的范围太小，则不进行任何操作，以避免创建空的缩放窗口。
        if abs(xmax - xmin) < 1e-9:
            return

        if not self.main_window or not self.main_window.current_stream:
            return

        ref_time = self.main_window.current_stream[0].stats.starttime
        
        start_abs = mdates.num2date(xmin)
        end_abs = mdates.num2date(xmax)
        
        start_rel = (start_abs.replace(tzinfo=None) - ref_time.datetime).total_seconds()
        end_rel = (end_abs.replace(tzinfo=None) - ref_time.datetime).total_seconds()
        
        self.zoom_requested.emit(start_rel, end_rel)


if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication
    from obspy import read
    
    app = QApplication(sys.argv)
    
    # 创建一个模拟的父窗口，以便访问 current_stream
    class MockMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.current_stream = None
            layout = QVBoxLayout()
            self.waveform_widget = WaveformWidget(main_window=self, parent=self)
            layout.addWidget(self.waveform_widget)
            self.setLayout(layout)

    main_win = MockMainWindow()

    # 加载示例数据并绘图
    try:
        st = read("../../example_data/20161110030629.440/5B.1107.DH*.SAC")
        main_win.current_stream = st
        main_win.waveform_widget.plot_stream(st)
        
        # 模拟拾取结果
        # 注意：这里的拾取时间是相对于trace开始的相对时间
        ref_time = st[0].stats.starttime
        p_arrival_rel = 10.0 # 假设P波在第10秒
        picks = {
            'p_arrival': p_arrival_rel,
            'onset_time': p_arrival_rel + 0.1,
            'end_time': p_arrival_rel + 0.5,
            'peak_time': p_arrival_rel + 0.2
        }
        main_win.waveform_widget.plot_picks(picks)

    except (FileNotFoundError, IndexError):
        print("请确保示例数据存在于正确的路径下。")
        
    main_win.show()
    sys.exit(app.exec()) 