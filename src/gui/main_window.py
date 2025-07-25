import csv
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTreeView, QTextEdit, QStatusBar, QMenuBar, QToolBar, QDockWidget, QLabel, QFileDialog,
                               QScrollArea, QPushButton, QMessageBox)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QKeySequence, QUndoStack
from PyQt6.QtCore import Qt, QModelIndex
from obspy import read
import numpy as np # Added for np.min and np.max

from core.data_loader import DataLoader, get_p_arrival_time
from core.p_pulse_detector import PPulseDetector
from gui.plot_widgets import WaveformWidget
from gui.commands import PickCommand, AutoPickCommand

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("P波脉冲拾取GUI系统")
        self.setGeometry(100, 100, 1200, 800)
        
        self.loader = None
        self.current_stream = None # 保存当前显示的波形
        self.current_station_id = None # 当前台站ID
        self.current_event_id = None # 当前事件ID
        self.current_picks = {} # 保存当前拾取结果
        self.all_station_picks = {} # { (event, station): picks }
        self.p_pulse_detector = PPulseDetector()
        self.zoom_windows = [] # 管理放大窗口
        self.undo_stack = QUndoStack(self)
        self.setup_ui()

    def setup_ui(self):
        # 创建主窗口的中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # 左侧：文件树
        self.file_tree_dock = QDockWidget("文件浏览器", self)
        self.file_tree_view = QTreeView()
        self.file_tree_model = QStandardItemModel()
        self.file_tree_view.setModel(self.file_tree_model)
        self.file_tree_view.clicked.connect(self.on_tree_item_clicked)
        self.file_tree_dock.setWidget(self.file_tree_view)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.file_tree_dock)

        # 中间：主显示区域和参数面板
        center_layout = QVBoxLayout()
        
        # 主波形显示区域
        self.main_plot_widget = WaveformWidget(main_window=self, parent=self)
        self.main_plot_widget.pick_made.connect(self.handle_manual_pick)
        self.main_plot_widget.zoom_requested.connect(self.create_zoom_window)
        center_layout.addWidget(self.main_plot_widget, stretch=3) # 主窗口比例放大

        # 放大窗口区域 - 使用QScrollArea
        self.zoom_scroll_area = QScrollArea()
        self.zoom_scroll_area.setWidgetResizable(True)
        self.zoom_widget_container = QWidget()
        self.zoom_layout = QHBoxLayout(self.zoom_widget_container)
        self.zoom_scroll_area.setWidget(self.zoom_widget_container)
        center_layout.addWidget(self.zoom_scroll_area, stretch=2)
        
        # 参数显示面板
        self.params_widget = QTextEdit()
        self.params_widget.setReadOnly(True)
        center_layout.addWidget(self.params_widget, stretch=1)

        main_layout.addLayout(center_layout)

        # 创建菜单栏
        self.create_menu_bar()

        # 创建工具栏
        self.create_tool_bar()

        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("准备就绪")
        
        # 添加鼠标操作说明面板
        self.create_mouse_help_panel()

    def create_menu_bar(self):
        menu_bar = self.menuBar()
        # 文件菜单
        file_menu = menu_bar.addMenu("文件")
        open_action = file_menu.addAction("打开目录")
        open_action.triggered.connect(self.open_directory)
        save_action = file_menu.addAction("保存结果 (CSV)")
        save_action.triggered.connect(self.save_results_to_csv)
        save_sac_action = file_menu.addAction("将结果写回SAC文件")
        save_sac_action.triggered.connect(self.save_results_to_sac)
        file_menu.addSeparator()
        file_menu.addAction("退出")
        # 编辑菜单
        edit_menu = menu_bar.addMenu("编辑")
        undo_action = self.undo_stack.createUndoAction(self, "撤销")
        undo_action.setShortcuts(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)
        
        redo_action = self.undo_stack.createRedoAction(self, "重做")
        redo_action.setShortcuts(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)
        
        # 视图菜单
        view_menu = menu_bar.addMenu("视图")
        # 工具菜单
        tools_menu = menu_bar.addMenu("工具")
        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助")

    def create_tool_bar(self):
        tool_bar = self.addToolBar("主工具栏")
        open_action = tool_bar.addAction("打开")
        open_action.triggered.connect(self.open_directory)
        save_action = tool_bar.addAction("保存 (CSV)")
        save_action.triggered.connect(self.save_results_to_csv)
        tool_bar.addSeparator()
        auto_pick_action = tool_bar.addAction("自动拾取")
        auto_pick_action.triggered.connect(self.auto_pick_pulse)
        tool_bar.addAction("手动模式")
        tool_bar.addAction("设置")

    def create_mouse_help_panel(self):
        help_dock = QDockWidget("操作说明", self)
        help_label = QLabel("""
        <b>鼠标操作说明：</b><br>
        <ul>
            <li><b>左键点击</b>：拾取脉冲结束时间</li>
            <li><b>右键点击</b>：拾取P波初动时间</li>
            <li><b>Ctrl+左键</b>：拾取脉冲起始时间</li>
            <li><b>拖拽选择</b>：创建放大窗口</li>
            <li><b>滚轮</b>：缩放时间轴</li>
            <li><b>中键拖拽</b>：平移时间窗口</li>
        </ul>
        """)
        help_label.setWordWrap(True)
        help_dock.setWidget(help_label)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, help_dock)

    def open_directory(self):
        """
        打开一个包含地震数据的根目录
        """
        dir_path = QFileDialog.getExistingDirectory(self, "选择数据根目录", "example_data")
        if dir_path:
            self.status_bar.showMessage(f"正在加载目录: {dir_path}")
            self.loader = DataLoader(dir_path)
            self.loader.scan_files()
            self.populate_file_tree(self.loader.events)
            self.status_bar.showMessage("目录加载完成", 5000)

    def populate_file_tree(self, events_data):
        """
        用扫描到的事件和台站数据填充文件树
        """
        self.file_tree_model.clear()
        self.file_tree_model.setHorizontalHeaderLabels(['事件/台站'])
        root_node = self.file_tree_model.invisibleRootItem()

        for event_id, stations in sorted(events_data.items()):
            event_item = QStandardItem(event_id)
            event_item.setEditable(False)
            root_node.appendRow(event_item)
            for station_id in sorted(stations.keys()):
                station_item = QStandardItem(station_id)
                station_item.setEditable(False)
                # 存储事件和台站ID以便后续检索
                station_item.setData(event_id, Qt.ItemDataRole.UserRole + 1)
                station_item.setData(station_id, Qt.ItemDataRole.UserRole + 2)
                event_item.appendRow(station_item)

    def on_tree_item_clicked(self, index: QModelIndex):
        """
        处理文件树项目点击事件，加载并显示波形
        """
        # 保存上一个台站的拾取结果
        self.update_picks_for_current_station()

        item = self.file_tree_model.itemFromIndex(index)
        if not item or not item.parent(): # 确保点击的是台站项
            self.current_event_id = None
            self.current_station_id = None
            return
            
        self.current_event_id = item.data(Qt.ItemDataRole.UserRole + 1)
        self.current_station_id = item.data(Qt.ItemDataRole.UserRole + 2)
        
        if self.loader and self.current_event_id and self.current_station_id:
            station_key = (self.current_event_id, self.current_station_id)
            self.status_bar.showMessage(f"正在加载 {self.current_event_id}/{self.current_station_id}...")
            self.current_stream = self.loader.load_station_data(self.current_event_id, self.current_station_id)
            # 加载该台站已有的拾取结果
            self.current_picks = self.all_station_picks.get(station_key, {})
            self.undo_stack.clear() # 为新台站清空撤销栈
            self.clear_zoom_windows()
            if self.current_stream:
                self.main_plot_widget.plot_stream(self.current_stream)
                self.display_pick_results(self.current_picks)
                self.main_plot_widget.plot_picks(self.current_picks)
                self.status_bar.showMessage(f"已加载 {self.current_event_id}/{self.current_station_id}", 5000)
            else:
                self.main_plot_widget.clear_plot() # 清除图像
                self.status_bar.showMessage(f"加载失败或无Z分量数据: {self.current_event_id}/{self.current_station_id}", 5000)

    def update_picks_for_current_station(self):
        """如果当前有台站和拾取结果，则保存它们"""
        if self.current_event_id and self.current_station_id and self.current_picks:
            station_key = (self.current_event_id, self.current_station_id)
            self.all_station_picks[station_key] = self.current_picks.copy()

    def auto_pick_pulse(self):
        if not self.current_stream:
            self.status_bar.showMessage("请先在左侧选择一个台站", 5000)
            return

        # 优先使用Z分量进行P波分析
        z_trace = self.current_stream.select(component="Z")
        if not z_trace:
            self.status_bar.showMessage("未找到Z分量数据", 5000)
            return
        
        trace = z_trace[0]
        p_arrival = get_p_arrival_time(trace)
        
        if p_arrival == -12345.0:
            self.status_bar.showMessage("无法从SAC头读取P波到时 (t1/t3)", 5000)
            return
            
        self.status_bar.showMessage("正在自动拾取P波脉冲...")
        results = self.p_pulse_detector.detect_pulse(trace, p_arrival)
        
        if results:
            command = AutoPickCommand(self, results)
            self.undo_stack.push(command)
            self.status_bar.showMessage("自动拾取完成", 5000)
        else:
            self.status_bar.showMessage("自动拾取失败", 5000)
            
    def display_pick_results(self, results):
        """将拾取结果显示在参数面板"""
        
        def format_value(value, format_spec):
            if isinstance(value, (int, float)):
                return format(value, format_spec)
            return "N/A"

        text = (
            f"P波到时 (t_arrival): {format_value(results.get('p_arrival'), '.4f')}\n"
            f"脉冲极性 (polarity): {results.get('polarity', 'N/A')}\n"
            f"脉冲起始 (t_onset): {format_value(results.get('onset_time'), '.4f')}\n"
            f"脉冲结束 (t_end): {format_value(results.get('end_time'), '.4f')}\n"
            f"峰值振幅 (peak_amp): {format_value(results.get('peak_amplitude'), '.4e')}\n"
            f"峰值时间 (t_peak): {format_value(results.get('peak_time'), '.4f')}\n"
            f"脉冲面积 (area): {format_value(results.get('pulse_area'), '.4e')}\n"
        )
        self.params_widget.setText(text)
        
    def handle_manual_pick(self, pick_type: str, time: float):
        """处理手动拾取事件，通过命令模式"""
        command = PickCommand(self, pick_type, time)
        self.undo_stack.push(command)
        self.status_bar.showMessage(f"手动拾取: {pick_type} @ {time:.4f}s", 5000)

    def _apply_pick(self, pick_type, time):
        """实际应用单个拾取结果并更新UI的私有方法"""
        if time is None:
            if pick_type in self.current_picks:
                del self.current_picks[pick_type]
        else:
            self.current_picks[pick_type] = time
        
        self.display_pick_results(self.current_picks)
        self.main_plot_widget.plot_picks(self.current_picks)
        
        # 刷新所有放大窗口
        self._update_zoom_windows_picks()

    def _apply_all_picks(self, picks):
        """实际应用整个拾取字典并更新UI的私有方法"""
        self.current_picks = picks.copy()
        self.display_pick_results(self.current_picks)
        self.main_plot_widget.plot_picks(self.current_picks)
        self._update_zoom_windows_picks()

    def _update_zoom_windows_picks(self):
        """更新所有放大窗口的拾取标记"""
        for zoom_window in self.zoom_windows:
            zoom_widget = zoom_window.findChild(WaveformWidget)
            if zoom_widget:
                zoom_widget.plot_picks(self.current_picks)

    def save_results_to_csv(self):
        """将所有拾取结果保存到CSV文件"""
        self.update_picks_for_current_station() # 确保当前台站的结果也被保存

        if not self.all_station_picks:
            self.status_bar.showMessage("没有可保存的拾取结果", 5000)
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "保存拾取结果", "", "CSV Files (*.csv);;All Files (*)")
        
        if not file_path:
            return
            
        header = ['event_id', 'station_id', 'p_arrival', 'polarity', 'onset_time', 
                  'end_time', 'peak_amplitude', 'peak_time', 'pulse_area']
        
        try:
            with open(file_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
                for (event_id, station_id), picks in sorted(self.all_station_picks.items()):
                    row = {'event_id': event_id, 'station_id': station_id}
                    row.update(picks)
                    writer.writerow(row)
            self.status_bar.showMessage(f"结果已保存到 {file_path}", 5000)
        except IOError as e:
            self.status_bar.showMessage(f"保存失败: {e}", 5000)

    def save_results_to_sac(self):
        """将拾取结果写回到对应的SAC文件头中"""
        self.update_picks_for_current_station()

        if not self.all_station_picks:
            self.status_bar.showMessage("没有可写入的拾取结果", 5000)
            return

        reply = QMessageBox.question(self, '确认操作', 
                                     "此操作将修改原始SAC文件，且无法撤销。\n您确定要继续吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            self.status_bar.showMessage("操作已取消", 3000)
            return

        self.status_bar.showMessage("正在将结果写入SAC文件...")
        
        saved_count = 0
        for (event_id, station_id), picks in self.all_station_picks.items():
            try:
                # 获取该台站所有分量的文件路径
                station_files = self.loader.events[event_id][station_id]
                stream = read(list(station_files.values()))
                
                for trace in stream:
                    # 写入未使用的时间标记和用户自定义变量
                    sac_header = trace.stats.sac
                    sac_header['t4'] = picks.get('p_arrival')
                    sac_header['t5'] = picks.get('onset_time')
                    sac_header['t6'] = picks.get('end_time')
                    sac_header['t7'] = picks.get('peak_time')
                    sac_header['user0'] = picks.get('peak_amplitude')
                    sac_header['user1'] = picks.get('pulse_area')
                    
                    # 写回文件
                    trace.write(trace.stats.network + '.' + trace.stats.station + '.' + trace.stats.channel + '.SAC', format='SAC')
                
                saved_count += 1
            except Exception as e:
                self.status_bar.showMessage(f"写入 {station_id} 失败: {e}", 8000)
                # 继续尝试下一个
                continue
        
        self.status_bar.showMessage(f"成功将 {saved_count} 个台站的结果写入SAC文件", 5000)


    def create_zoom_window(self, start_time_rel, end_time_rel):
        """创建一个新的放大窗口"""
        if not self.current_stream:
            return

        # 创建带关闭按钮的容器
        container = QWidget()
        container_layout = QVBoxLayout()
        container.setLayout(container_layout)
        container.setMinimumWidth(600)  # 设置最小宽度
        
        # 关闭按钮
        close_button = QPushButton("关闭")
        
        # 放大图
        zoom_widget = WaveformWidget(main_window=self, parent=self)
        if self.current_stream:
            zoom_widget.plot_stream(self.current_stream.copy())
            
            # 设置X轴范围
            ref_time = self.current_stream[0].stats.starttime
            start_abs = (ref_time + start_time_rel).matplotlib_date
            end_abs = (ref_time + end_time_rel).matplotlib_date
            
            zoom_widget.axes.set_xlim(start_abs, end_abs)
            
            # 调整图形大小和布局
            zoom_widget.setMinimumHeight(250)
            zoom_widget.figure.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.2)
            
            # 调整Y轴，使波形居中并放大
            data = self.current_stream[0].data
            start_idx = int(start_time_rel * self.current_stream[0].stats.sampling_rate)
            end_idx = int(end_time_rel * self.current_stream[0].stats.sampling_rate)
            
            if start_idx >= 0 and end_idx < len(data) and start_idx < end_idx:
                selected_data = data[start_idx:end_idx]
                if len(selected_data) > 0:
                    min_val = np.min(selected_data)
                    max_val = np.max(selected_data)
                    margin = (max_val - min_val) * 0.1 # 10%边距
                    zoom_widget.axes.set_ylim(min_val - margin, max_val + margin)
            
            # 连接拾取信号
            zoom_widget.pick_made.connect(self.handle_manual_pick)
            
            # 绘制已有拾取标记
            if self.current_picks:
                zoom_widget.plot_picks(self.current_picks)

            zoom_widget.canvas.draw()
        
        container_layout.addWidget(zoom_widget)
        container_layout.addWidget(close_button)
        
        self.zoom_layout.addWidget(container)
        self.zoom_windows.append(container)
        
        # 将关闭按钮与删除函数连接
        close_button.clicked.connect(lambda: self.remove_zoom_window(container))

    def remove_zoom_window(self, window_container):
        """移除一个放大窗口"""
        window_container.deleteLater()
        if window_container in self.zoom_windows:
            self.zoom_windows.remove(window_container)

    def clear_zoom_windows(self):
        """清除所有放大窗口"""
        for window in self.zoom_windows:
            window.deleteLater()
        self.zoom_windows.clear()

if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec())
