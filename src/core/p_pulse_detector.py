import numpy as np
from scipy.signal import find_peaks
from obspy.core.trace import Trace

class PPulseDetector:
    def __init__(self, threshold_fraction=0.05, search_window=0.5):
        self.threshold_fraction = threshold_fraction
        self.search_window = search_window

    def detect_pulse(self, trace: Trace, p_arrival: float):
        """
        P脉冲自动检测主函数
        :param trace: ObsPy Trace对象，仅包含单个分量（如Z分量）
        :param p_arrival: 从SAC头文件读取的P波到时
        :return: 包含拾取结果的字典
        """
        if not isinstance(trace, Trace) or p_arrival is None:
            return None

        # 1. 数据窗口选择（P波后1秒）
        t0 = trace.stats.starttime + p_arrival
        t1 = t0 + 1.0
        
        win_trace = trace.copy().trim(starttime=t0, endtime=t1)
        
        window_time = win_trace.times(reftime=trace.stats.starttime)
        window_seis = win_trace.data
        
        # 2. 峰值检测
        peaks_info = self.find_peaks_and_polarity(window_seis, window_time)
        if not peaks_info:
            return None
        
        # 3. 脉冲起始点检测 (占位符)
        onset_time = self.detect_onset(window_seis, window_time, peaks_info, p_arrival)
        
        # 4. 脉冲结束点检测（过零点）(占位符)
        end_time = self.detect_zero_crossing(window_seis, window_time, peaks_info)
        
        # 5. 脉冲区域计算 (占位符)
        pulse_area = self.calculate_pulse_area(window_seis, window_time, 
                                             onset_time, end_time)
        
        return {
            'p_arrival': p_arrival,
            'onset_time': onset_time,
            'end_time': end_time,
            'peak_amplitude': peaks_info['main_peak_amp'],
            'peak_time': peaks_info['main_peak_time'],
            'pulse_area': pulse_area,
            'polarity': peaks_info['polarity']
        }
    
    def find_peaks_and_polarity(self, seis, time):
        """检测正负峰值并确定极性"""
        if len(seis) == 0:
            return None

        height_threshold = max(abs(seis)) * 0.1
        pos_peaks, _ = find_peaks(seis, height=height_threshold)
        neg_peaks, _ = find_peaks(-seis, height=height_threshold)
        
        first_pos_peak_time = time[pos_peaks[0]] if len(pos_peaks) > 0 else np.inf
        first_neg_peak_time = time[neg_peaks[0]] if len(neg_peaks) > 0 else np.inf

        if first_pos_peak_time == np.inf and first_neg_peak_time == np.inf:
            return None

        if first_pos_peak_time < first_neg_peak_time:
            polarity = 'positive'
            main_peak_idx = pos_peaks[0]
            main_peak_amp = seis[main_peak_idx]
            main_peak_time = time[main_peak_idx]
        else:
            polarity = 'negative'
            main_peak_idx = neg_peaks[0]
            main_peak_amp = seis[main_peak_idx] # 已经是负值
            main_peak_time = time[main_peak_idx]

        return {
            'main_peak_amp': main_peak_amp,
            'main_peak_time': main_peak_time,
            'main_peak_idx': main_peak_idx,
            'polarity': polarity
        }

    def detect_onset(self, seis, time, peaks_info, p_arrival):
        """
        检测脉冲起始点.
        从主峰向前搜索，找到振幅首次低于主峰振幅特定比例(threshold_fraction)的点。
        """
        main_peak_idx = peaks_info['main_peak_idx']
        main_peak_amp = peaks_info['main_peak_amp']
        onset_threshold = abs(main_peak_amp) * self.threshold_fraction

        # 搜索范围是从P波到时（窗口起点）到主峰
        # np.arange(start, stop, step)
        search_indices = np.arange(main_peak_idx, -1, -1)

        for i in search_indices:
            if abs(seis[i]) < onset_threshold:
                # 我们找到了第一个低于阈值的点，那么起始点就是它之后的一个点
                # 为防止索引越界，如果i是最后一个点，则返回该点的时间
                onset_index = min(i + 1, len(time) - 1)
                return time[onset_index]

        # 如果没有找到低于阈值的点（不太可能，但作为保险），返回P波到时
        return p_arrival

    def detect_zero_crossing(self, seis, time, peaks_info):
        """
        检测脉冲结束点（第一个过零点）.
        从主峰向后搜索，通过线性插值找到第一个过零点。
        """
        peak_idx = peaks_info['main_peak_idx']
        
        # 寻找从主峰开始的第一个符号变化
        for i in range(peak_idx, len(seis) - 1):
            # 如果seis[i]和seis[i+1]异号，说明零点在它们之间
            if np.sign(seis[i]) != np.sign(seis[i+1]):
                # 线性插值计算过零点时间
                y1, y2 = seis[i], seis[i+1]
                t1, t2 = time[i], time[i+1]
                
                # 避免除以零
                if y2 == y1:
                    return t1
                
                t_zero = t1 + (0 - y1) * (t2 - t1) / (y2 - y1)
                return t_zero
            
        # 如果没找到过零点，返回窗口的结束时间
        return time[-1]

    def calculate_pulse_area(self, seis, time, onset_time, end_time):
        """计算脉冲面积 (占位符)"""
        # 简单的实现：使用梯形法则计算面积
        mask = (time >= onset_time) & (time <= end_time)
        if not np.any(mask):
            return 0.0
        pulse_seis = seis[mask]
        pulse_time = time[mask]
        return np.trapz(pulse_seis, pulse_time) 