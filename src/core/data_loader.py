#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from obspy import read
from obspy.core.trace import Trace
from obspy.core.stream import Stream

class DataLoader:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.events = {}

    def scan_files(self):
        """
        Scans the directory and organizes SAC files by event and station.
        """
        for event_dir in os.listdir(self.base_dir):
            event_path = os.path.join(self.base_dir, event_dir)
            if os.path.isdir(event_path):
                self.events[event_dir] = {}
                for sac_file in os.listdir(event_path):
                    if sac_file.upper().endswith("Z.SAC"): # 只查找Z分量
                        parts = sac_file.split('.')
                        station = ".".join(parts[0:2])
                        component = parts[2]
                        if station not in self.events[event_dir]:
                            self.events[event_dir][station] = {}
                        self.events[event_dir][station][component] = os.path.join(event_path, sac_file)

    def load_station_data(self, event_id, station_id) -> Stream:
        """
        Loads Z-component data for a specific event and station.
        """
        if event_id not in self.events or station_id not in self.events[event_id]:
            return None
        
        station_files = self.events[event_id][station_id]
        stream = Stream()
        # 假设Z分量的标识符在文件名中是 'DHZ' 或类似的
        z_component = next((comp for comp in station_files if comp.upper().endswith('Z')), None)

        if z_component and z_component in station_files:
            try:
                trace = read(station_files[z_component])[0]
                stream.append(trace)
            except Exception as e:
                print(f"Error reading {station_files[z_component]}: {e}")
        return stream

def get_p_arrival_time(trace: Trace) -> float:
    """
    Reads the P-wave arrival time from the SAC header.
    Priority: t1 > t3
    """
    if hasattr(trace.stats, 'sac'):
        sac_header = trace.stats.sac
        p_time = -12345.0
        
        if 't1' in sac_header and sac_header['t1'] != -12345:
            p_time = sac_header['t1']
        elif 't3' in sac_header and sac_header['t3'] != -12345:
            p_time = sac_header['t3']
            
        return p_time
    return -12345.0

if __name__ == '__main__':
    # 示例用法
    data_path = '../../example_data' # 调整为你的数据路径
    loader = DataLoader(data_path)
    loader.scan_files()
    
    # 打印扫描到的事件和台站
    for event, stations in loader.events.items():
        print(f"Event: {event}")
        for station, components in stations.items():
            print(f"  Station: {station}, Components: {list(components.keys())}")
            
    # 加载一个台站的数据
    if loader.events:
        first_event = list(loader.events.keys())[0]
        first_station = list(loader.events[first_event].keys())[0]
        
        st = loader.load_station_data(first_event, first_station)
        if st:
            print(f"\nLoaded data for {first_event}/{first_station}:")
            print(st)
            
            # 获取P波到时
            z_trace = st.select(component="Z")[0]
            p_time = get_p_arrival_time(z_trace)
            print(f"P-arrival time from SAC header (t1/t3): {p_time}") 