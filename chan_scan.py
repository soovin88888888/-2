import requests
import time
import datetime
import baostock as bs
import os

# ================= 配置区 =================
# 从 GitHub Secrets 读取密钥，更安全
SCKEY = os.getenv("SERVERCHAN_KEY", "")
# 想要扫描的股票代码列表（baostock格式：sh.600000）
STOCK_LIST = ['sh.600000', 'sz.000001', 'sh.600519', 'sz.300750']
# ==========================================

def is_60min_second_buy(code):
    try:
        bs.login()
        today = datetime.datetime.today().strftime('%Y-%m-%d')
        
        # 1. 获取日线数据（判断是否有大跌背景，模拟一买前提）
        start_date = (datetime.datetime.today() - datetime.timedelta(days=60)).strftime('%Y-%m-%d')
        rs_d = bs.query_history_k_data_plus(code, "date,close,low", start_date=start_date, end_date=today, frequency="d", adjustflag="2")
        daily_data = []
        while (rs_d.error_code == '0') & rs_d.next():
            daily_data.append(rs_d.get_row_data())
            
        if len(daily_data) < 10:
            bs.logout()
            return False, "日线数据不足"
            
        # 2. 获取60分钟数据
        start_60m = (datetime.datetime.today() - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
        rs_60 = bs.query_history_k_data_plus(code, "date,time,close,low,high", start_date=start_60m, end_date=today, frequency="60", adjustflag="2")
        min_data = []
        while (rs_60.error_code == '0') & rs_60.next():
            min_data.append(rs_60.get_row_data())
            
        bs.logout()
        
        if len(min_data) < 8:
            return False, "60min数据不足"
            
        # --- 核心形态判断逻辑 ---
        # 找到60分钟最近的最低点
        lows = [float(row[3]) for row in min_data]
        recent_low_idx = lows.index(min(lows))
        recent_low = lows[recent_low_idx]
        
        # 最低点必须在最近4根K线内（说明刚企稳）
        if recent_low_idx < len(min_data) - 4:
            return False, "仍在探底中"
            
        # 找反弹高点
        if recent_low_idx < 2:
            return False, "反弹结构不完整"
        highs_before_low = [float(row[4]) for row in min_data[:recent_low_idx]]
        rebound_high = max(highs_before_low) if highs_before_low else 0
        
        # 找更早的低点（模拟一买低点）
        if recent_low_idx < 4:
            return False, "结构周期不够"
        earlier_lows = [float(row[3]) for row in min_data[:recent_low_idx-2]]
        first_buy_low = min(earlier_lows) if earlier_lows else 0
        
        # 条件A：回调不破前低（二买核心）
        if recent_low < first_buy_low:
            return False, "跌破前低(二买失败)"
            
        # 条件B：当前价格企稳反弹
        current_close = float(min_data[-1][2])
        low_close = float(min_data[recent_low_idx][2])
        if current_close <= low_close:
            return False, "尚未企稳反弹"
            
        # 条件C：日线前期有大幅下跌（有一买背景）
        daily_closes = [float(row[1]) for row in daily_data]
        if len(daily_closes) > 20:
            drop_pct = (daily_closes[-20] - min(daily_closes[-20:])) / daily_closes[-20]
            if drop_pct < 0.05: # 近20天最大跌幅不足5%
                return False, "无一买背景"

        return True, f"触发二买形态! 当前价:{current_close}"
        
    except Exception as e:
        return False, f"计算出错: {e}"

def main():
    print(f"[{datetime.datetime.now()}] 开始扫描...")
    hit_stocks = []
    
    for stock in STOCK_LIST:
        is_match, msg = is_60min_second_buy(stock)
        print(f"扫描 {stock}: {msg}")
        if is_match:
            hit_stocks.append(f"{stock} - {msg}")
        time.sleep(1)
        
    if hit_stocks and SCKEY:
        title = "🚀 缠论60分钟二买提醒"
        content = "\n\n".join(hit_stocks)
        url = f"https://sctapi.ftqq.com/{SCKEY}.send?text={title}&desp={content}"
        requests.get(url)
        print("✅ 已推送微信提醒！")
    elif not hit_stocks:
        print("今日无符合条件的股票。")

if __name__ == '__main__':
    main()
