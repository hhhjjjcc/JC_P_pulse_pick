from PyQt6.QtGui import QUndoCommand

class PickCommand(QUndoCommand):
    """用于封装手动拾取动作的命令"""
    def __init__(self, main_window, pick_type, new_time, parent=None):
        super().__init__(parent)
        
        self.main_window = main_window
        self.pick_type = pick_type
        self.new_time = new_time
        
        # 为undo操作保存旧值
        self.old_time = self.main_window.current_picks.get(self.pick_type)
        
        if self.old_time is None:
            self.setText(f"添加拾取: {pick_type}")
        else:
            self.setText(f"修改拾取: {pick_type}")

    def redo(self):
        """应用新的拾取时间"""
        self.main_window._apply_pick(self.pick_type, self.new_time)

    def undo(self):
        """恢复到旧的拾取时间"""
        self.main_window._apply_pick(self.pick_type, self.old_time)


class AutoPickCommand(QUndoCommand):
    """用于封装自动拾取动作的命令"""
    def __init__(self, main_window, new_picks, parent=None):
        super().__init__(parent)
        
        self.main_window = main_window
        self.new_picks = new_picks
        
        # 为undo操作保存旧的拾取字典
        self.old_picks = self.main_window.current_picks.copy()
        
        self.setText("自动拾取")

    def redo(self):
        """应用新的自动拾取结果"""
        self.main_window._apply_all_picks(self.new_picks)

    def undo(self):
        """恢复到自动拾取前的状态"""
        self.main_window._apply_all_picks(self.old_picks) 