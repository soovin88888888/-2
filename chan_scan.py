import requests
import time
import datetime
import baostock as bs
import pandas as pd
import os
from urllib.parse import quote

# ================= 配置区 =================
SCKEY = os.getenv("SERVERCHAN_KEY", "")
# ==========================================

def get_all_stocks():
    """获取全市场股票列表，仅保留300、688开头"""
    print("正在从 BaoStock 获取全市场股票列表...")
    lg = bs.login()
    if lg.error_code != '0':
        print(f"登录失败: {lg.error_msg}")
        return []
    
    rs = bs.query_all_stock(day=datetime.datetime.now().strftime('%Y-%m-%d'))
    data_list = []
    while (rs.error_code == '0') & rs.next():
        data_list.append(rs.get_row_data())
    bs.logout()
    
    if not data_list:
        print("获取股票列表失败")
        return []
        
    df = pd.DataFrame(data_list, columns=rs.fields)
    # 只保留 sz.300 创业板、sh.688 科创板
    mask = df['code'].str.startswith(("sz.300", "sh.688"))
    df = df[mask]
    stock_list = df['code'].tolist()
    print(f"成功获取300/688标的共 {len(stock_list)} 只。")
    return stock_list

def get_stock_data(code, freq, days):
    """获取股票数据（移除重复登录登出）"""
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    
    fields = "date,close,low,high"
    if freq == "60":
        fields += ",time"
        
    rs = bs.query_history_k_data_plus(
        code, fields, start_date=start_date, end_date=end_date, 
        frequency=freq, adjustflag="2"
    )
    
    data_list = []
    while (rs.error_code == '0') & rs.next():
        data_list.append(rs.get_row_data())
    
    if not data_list:
        return None
        
    return pd.DataFrame(data_list, columns=rs.fields)

def is_60min_second_buy(code):
    try:
        daily_df = get_stock_data(code, "d", 60)
        if daily_df is None or len(daily_df) < 20:
            return False, "日线数据不足"
            
        min60_df = get_stock_data(code, "60", 30)
        if min60_df is None or len(min60_df) < 10:
            return False, "60分钟数据不足"
            
        min60_df['close'] = pd.to_numeric(min60_df['close'], errors='coerce')
        min60_df['low'] = pd.to_numeric(min60_df['low'], errors='coerce')
        min60_df['high'] = pd.to_numeric(min60_df['high'], errors='coerce')
        daily_df['close'] = pd.to_numeric(daily_df['close'], errors='coerce')
        
        recent_lows = min60_df['low'].values
        if len(recent_lows) < 5:
            return False, "数据不足"
            
        recent_low = min(recent_lows[-5:])
        recent_low_idx = list(recent_lows[-5:]).index(recent_low)
        
        if recent_low_idx == 4:
            return False, "仍在探底中"
            
        if recent_low_idx > 0:
            rebound_high = min60_df['high'].values[-5:][recent_low_idx-1]
            current_high = min60_df['high'].values[-1]
            if current_high <= rebound_high:
                return False, "反弹力度不足"
                
        daily_closes = daily_df['close'].values[-20:]
        max_drop = (daily_closes[0] - min(daily_closes)) / daily_closes[0]
        if max_drop < 0.08:
            return False, "无一买背景"
            
        current_close = min60_df['close'].values[-1]
        if current_close <= recent_low:
            return False, "尚未企稳"
            
        return True, f"触发二买! 当前价:{current_close:.2f}"
        
    except Exception as e:
        return False, f"计算出错: {str(e)}"

def send_notification(title, content):
    if not SCKEY:
        print("未设置SCKEY，跳过推送")
        return
        
    try:
        encoded_content = quote(content)
        url = f"https://sctapi.ftqq.com/{SCKEY}.send?title={title}&desp={encoded_content}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print("✅ 推送成功")
        else:
            print(f" 推送失败: {response.text}")
    except Exception as e:
        print(f" 推送异常: {e}")

def main():
    # 全局只登录一次
    lg = bs.login()
    if lg.error_code != '0':
        print(f"BaoStock登录失败: {lg.error_msg}")
        return
    
    print(f"[{datetime.datetime.now()}] 开始扫描缠论60分钟二买...")
    hit_stocks = []
    
    stock_list = get_all_stocks()
    if not stock_list:
        print(" 获取股票列表失败")
        bs.logout()
        return
        
    total = len(stock_list)
    for i, stock in enumerate(stock_list):
        print(f" 进度: {i+1}/{total} | 扫描 {stock}...", end='\r')
        
        is_match, msg = is_60min_second_buy(stock)
        if is_match:
            hit_stocks.append(f"{stock} - {msg}")
        time.sleep(0.3)
        
    # 统一登出
    bs.logout()
    
    print("\n" + "="*60)
    print(f"扫描完成! 共扫描 {total} 只股票，命中 {len(hit_stocks)} 只")
    print("="*60)
    
    if hit_stocks:
        title = "缠论60分钟二买提醒"
        content = "\n\n".join(hit_stocks)
        print("\n 命中股票列表:")
        for stock in hit_stocks:
            print(f"  • {stock}")
        send_notification(title, content)
    else:
        print("📭 今日无符合条件的股票")

if __name__ == '__main__':
    main()
